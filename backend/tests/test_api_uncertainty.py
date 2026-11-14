"""ABB-19 Uncertainty Hunter API integration tests against a disposable PostgreSQL database.

People, cases, hypotheses and farm profiles are SYNTHETIC. Run with TEST_DATABASE_URL set.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from agroblackbox.api.deps import get_session_factory
from agroblackbox.app import app
from agroblackbox.db.models import Case, UncertaintyAnswer, UncertaintyQuestionEvent, User
from agroblackbox.db.session import create_database_engine, session_factory
from agroblackbox.uncertainty import dynamic_question_id
from comparability_fixtures import numeric_score_keys
from test_rotations import profile as rotation_profile

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration")

PASSWORD = "synthetic-correct-horse-42"
V1 = "/api/v1"
PARENT_REVISION = "f4b81d2c6e93"  # ABB-16 evidence graph


def alembic_config() -> Config:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_URL or "")
    return config


@pytest.fixture(scope="module")
def api_engine():
    engine = create_database_engine(TEST_URL)
    command.downgrade(alembic_config(), "base")
    command.upgrade(alembic_config(), "head")
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def factory(api_engine):
    tables = [t for t in inspect(api_engine).get_table_names() if t != "alembic_version"]
    with api_engine.begin() as connection:
        connection.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE"))
    factory = session_factory(api_engine)
    app.dependency_overrides[get_session_factory] = lambda: factory
    yield factory
    app.dependency_overrides.pop(get_session_factory, None)


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def account(client, email: str) -> dict[str, str]:
    registered = await client.post(f"{V1}/auth/register", json={
        "email": email, "password": PASSWORD, "display_name": "Synthetic " + email.split("@")[0]})
    assert registered.status_code == 201, registered.text
    login = await client.post(f"{V1}/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def team(client):
    owner = await account(client, "owner@example.test")
    editor = await account(client, "editor@example.test")
    reviewer = await account(client, "reviewer@example.test")
    viewer = await account(client, "viewer@example.test")
    stranger = await account(client, "stranger@example.test")
    response = await client.post(f"{V1}/cases", headers=owner, json={
        "title": "SYNTHETIC uncertainty case", "incident_start": "2022-05-01", "incident_end": "2022-08-31",
        "crop_history": ["wheat", "barley"], "incident_notes": "SYNTHETIC yellowing in June.",
        "fields": [{"label": "Synthetic parcel", "privacy_tier": "REGION_ONLY", "region_label": "Synthetic valley",
                    "limitations": ["Synthetic"]}]})
    assert response.status_code == 201, response.text
    case_id = response.json()["id"]
    for email, role in (("editor@example.test", "EDITOR"), ("reviewer@example.test", "REVIEWER"),
                        ("viewer@example.test", "VIEWER")):
        granted = await client.post(f"{V1}/cases/{case_id}/permissions", headers=owner,
                                    json={"email": email, "role": role})
        assert granted.status_code == 201, granted.text
    return case_id, owner, editor, reviewer, viewer, stranger


def url(case_id: str, suffix: str = "") -> str:
    return f"{V1}/cases/{case_id}/uncertainty{suffix}"


async def answer(client, headers, case_id, question_id, **body):
    payload = {"origin": "FARMER_REPORTED", "value_text": "SYNTHETIC answer", **body}
    return await client.post(url(case_id, f"/questions/{question_id}/answers"), headers=headers, json=payload)


def counts(factory) -> tuple[int, int]:
    with factory() as s:
        return (s.scalar(select(func.count()).select_from(UncertaintyAnswer)),
                s.scalar(select(func.count()).select_from(UncertaintyQuestionEvent)))


def test_abb19_migration_downgrades_and_upgrades(api_engine):
    command.downgrade(alembic_config(), PARENT_REVISION)
    names = inspect(api_engine).get_table_names()
    assert "uncertainty_answers" not in names and "uncertainty_question_events" not in names
    command.upgrade(alembic_config(), "head")
    names = inspect(api_engine).get_table_names()
    assert {"uncertainty_answers", "uncertainty_question_events"} <= set(names)


@pytest.mark.asyncio
async def test_report_permissions_and_stateless_profile_inputs(client, factory):
    case_id, owner, editor, reviewer, viewer, stranger = await team(client)
    assert (await client.get(url(case_id))).status_code == 401
    assert (await client.get(url(case_id), headers=stranger)).status_code == 404
    assert (await client.post(url(case_id), headers=stranger, json={})).status_code == 404
    added = await client.post(f"{V1}/cases/{case_id}/hypotheses/templates", headers=owner,
                              json={"codes": ["WATER_DEFICIT", "HEAT_STRESS"]})
    assert added.status_code == 201, added.text

    response = await client.get(url(case_id), headers=viewer)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["stored"] is False and report["inputs"]["farm_profile_supplied"] is False
    keys = {g["key"] for g in report["gaps"]}
    assert "timeline:no-local-measurements" in keys
    assert any(k.startswith("timeline:no-observations:") for k in keys)
    questions = {q["id"]: q for q in report["questions"]}
    stage = questions["CROP_STAGE_AT_EVENT"]
    assert stage["position"] == 1 and stage["open_hypotheses_linked"] == 2
    assert report["prioritisation"]["status"] == "ORDERED_BY_LINK_COUNTS"
    assert questions["NASA_POWER_RETRIEVAL"]["answerable_here"] is False
    for q in report["questions"]:
        assert q["why_it_matters"] and q["measurement"] and "would_change" in q
    assert not numeric_score_keys(report)

    before = counts(factory)
    with_profile = await client.post(url(case_id), headers=reviewer, json={
        "farm_profile": rotation_profile(), "country_code": "es", "koppen_climate": "Csa"})
    assert with_profile.status_code == 200, with_profile.text
    body = with_profile.json()
    assert body["inputs"]["farm_profile_supplied"] is True and body["inputs"]["country_code"] == "ES"
    assert body["inputs"]["rotation_status"] in {"COMPARED", "FEWER_ALTERNATIVES"}
    assert "profile:SOIL_MISSING:soil" in {g["key"] for g in body["gaps"]}
    assert body["summary"]["gaps_not_answerable_locally"] >= 2
    assert counts(factory) == before  # nothing stored
    other = await client.post(url(case_id), headers=owner,
                              json={"farm_profile": {**rotation_profile(), "case_id": str(uuid4())}})
    assert other.status_code == 422
    assert (await client.post(url(case_id), headers=owner, json={"score": 1})).status_code == 422


@pytest.mark.asyncio
async def test_answer_review_correction_and_history(client, factory):
    case_id, owner, editor, reviewer, viewer, stranger = await team(client)
    soil = {"origin": "LOCAL_MEASUREMENT", "value_number": 8.2, "unit": "pH", "method": "SYNTHETIC 1:2.5 water",
            "observed_from": "2022-03-01", "source_reference": "SYNTHETIC lab report 17"}
    assert (await answer(client, stranger, case_id, "SOIL_ANALYSIS", **soil)).status_code == 404
    assert (await answer(client, viewer, case_id, "SOIL_ANALYSIS", **soil)).status_code == 403
    assert (await answer(client, reviewer, case_id, "SOIL_ANALYSIS", **soil)).status_code == 403
    assert (await answer(client, owner, case_id, "NOT_A_QUESTION", **soil)).status_code == 404
    assert (await answer(client, owner, case_id, "not-valid!", **soil)).status_code == 422
    assert (await answer(client, owner, case_id, "CLAIM_REVIEW")).status_code == 422  # analysis task
    assert (await answer(client, owner, case_id, "SOIL_ANALYSIS", value_text=None, value_number=8.2)).status_code == 422

    created = await answer(client, editor, case_id, "SOIL_ANALYSIS", **soil)
    assert created.status_code == 201, created.text
    first = created.json()
    assert (first["status"], first["kind"], first["source_kind"]) == ("ANSWERED", "FARMER_REPORTED", "FARMER_REPORTED")
    assert first["question"].startswith("Is there a soil analysis")
    assert first["can_review"] is False  # the author cannot review

    review_url = url(case_id, f"/answers/{first['id']}/review")
    decision = {"version": first["version"], "decision": "REVIEWED", "note": "SYNTHETIC: lab report seen."}
    assert (await client.post(review_url, headers=editor, json=decision)).status_code == 403  # self-review
    assert (await client.post(review_url, headers=viewer, json=decision)).status_code == 403
    assert (await client.post(review_url, headers=stranger, json=decision)).status_code == 404
    assert (await client.post(review_url, headers=reviewer, json={**decision, "version": 9})).status_code == 409
    reviewed = await client.post(review_url, headers=reviewer, json=decision)
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "REVIEWED" and reviewed.json()["is_reviewed"] is True

    report = (await client.get(url(case_id), headers=owner)).json()
    soil_q = next(q for q in report["questions"] if q["id"] == "SOIL_ANALYSIS")
    assert soil_q["resolution"]["status"] == "REVIEWED" and soil_q["position"] is None
    assert soil_q["resolution"]["current_answer_id"] == first["id"]

    stale = await answer(client, owner, case_id, "SOIL_ANALYSIS", **soil)
    assert stale.status_code == 409  # a current answer exists: must be replaced explicitly
    corrected = await answer(client, owner, case_id, "SOIL_ANALYSIS", **{**soil, "value_number": 8.0},
                             replaces_answer_id=first["id"])
    assert corrected.status_code == 201, corrected.text
    second = corrected.json()

    listed = (await client.get(url(case_id, "/answers"), headers=viewer, params={"question_id": "SOIL_ANALYSIS"})).json()
    statuses = {a["id"]: a for a in listed["items"]}
    assert statuses[first["id"]]["status"] == "SUPERSEDED"
    assert statuses[first["id"]]["superseded_by_id"] == second["id"]
    assert statuses[first["id"]]["value_number"] == 8.2  # never overwritten
    assert statuses[second["id"]]["status"] == "ANSWERED"

    rejected = await client.post(url(case_id, f"/answers/{second['id']}/review"), headers=editor, json={
        "version": second["version"], "decision": "REJECTED", "note": "SYNTHETIC: no lab report attached."})
    assert rejected.status_code == 200, rejected.text
    history = (await client.get(url(case_id, "/questions/SOIL_ANALYSIS/history"), headers=viewer)).json()
    assert [e["action"] for e in history["events"]] == ["ANSWERED", "REVIEWED", "ANSWERED", "REJECTED"]
    assert [e["to_status"] for e in history["events"]] == ["ANSWERED", "REVIEWED", "ANSWERED", "OPEN"]
    assert history["resolution"]["status"] == "OPEN" and history["resolution"]["current_answer_id"] is None
    assert len(history["answers"]) == 2 and all(e["actor"] for e in history["events"])
    assert (await client.get(url(case_id, "/questions/NOT_A_QUESTION/history"), headers=viewer)).status_code == 404


@pytest.mark.asyncio
async def test_dismiss_reopen_and_editability(client, factory):
    case_id, owner, editor, reviewer, viewer, stranger = await team(client)
    note = {"note": "SYNTHETIC: no gauge on this farm."}
    dismiss = url(case_id, "/questions/LOCAL_RAIN_OR_SOIL_MOISTURE/dismiss")
    reopen = url(case_id, "/questions/LOCAL_RAIN_OR_SOIL_MOISTURE/reopen")
    assert (await client.post(dismiss, headers=reviewer, json=note)).status_code == 403
    assert (await client.post(dismiss, headers=owner, json={})).status_code == 422
    assert (await client.post(reopen, headers=owner, json=note)).status_code == 409  # not dismissed
    done = await client.post(dismiss, headers=owner, json=note)
    assert done.status_code == 200 and done.json()["resolution"]["status"] == "DISMISSED"
    assert (await client.post(dismiss, headers=owner, json=note)).status_code == 409
    assert (await answer(client, owner, case_id, "LOCAL_RAIN_OR_SOIL_MOISTURE")).status_code == 409
    report = (await client.get(url(case_id), headers=owner)).json()
    rain = next(q for q in report["questions"] if q["id"] == "LOCAL_RAIN_OR_SOIL_MOISTURE")
    assert rain["resolution"] == {**rain["resolution"], "status": "DISMISSED", "note": note["note"]}
    assert "timeline:no-local-measurements" in {g["key"] for g in report["gaps"]}  # the gap stays listed
    assert (await client.post(reopen, headers=editor, json={"note": "SYNTHETIC: neighbour has a gauge."})).json()[
        "resolution"]["status"] == "OPEN"

    case = (await client.get(f"{V1}/cases/{case_id}", headers=owner)).json()
    archived = await client.post(f"{V1}/cases/{case_id}/archive", headers=owner,
                                 json={"version": case["version"], "archived": True})
    assert archived.status_code == 200
    assert (await answer(client, owner, case_id, "IRRIGATION_RECORDS")).status_code == 409
    assert (await client.post(dismiss, headers=owner, json=note)).status_code == 409
    assert (await client.get(url(case_id), headers=viewer)).status_code == 200  # still readable


@pytest.mark.asyncio
async def test_hypothesis_written_question_and_answer_as_evidence(client, factory):
    case_id, owner, editor, reviewer, viewer, stranger = await team(client)
    created = await client.post(f"{V1}/cases/{case_id}/hypotheses", headers=owner, json={
        "title": "SYNTHETIC frost", "statement": "A late frost may have contributed to the damage.",
        "missing_evidence": ["Night temperature at canopy height"]})
    assert created.status_code == 201, created.text
    qid = dynamic_question_id("missing", "Night temperature at canopy height")
    report = (await client.get(url(case_id), headers=owner)).json()
    assert qid in {q["id"] for q in report["questions"]}
    reply = await answer(client, owner, case_id, qid, value_number=-2.5, unit="°C", value_text=None,
                         observed_from="2022-04-20", observed_to="2022-04-20")
    assert reply.status_code == 201, reply.text
    answer_id = reply.json()["id"]

    linked = await client.post(f"{V1}/cases/{case_id}/hypotheses", headers=owner, json={
        "statement": "SYNTHETIC: frost is compatible with the local record.", "supporting_evidence_ids": [answer_id]})
    assert linked.status_code == 201, linked.text
    [evidence] = linked.json()["evidence"]
    assert (evidence["evidence_type"], evidence["kind"], evidence["active"]) == ("LOCAL_ANSWER", "FARMER_REPORTED", True)

    other_case, *_ = await team_again(client, owner)
    foreign = await client.post(f"{V1}/cases/{other_case}/hypotheses", headers=owner, json={
        "statement": "SYNTHETIC foreign link.", "supporting_evidence_ids": [answer_id]})
    assert foreign.status_code == 422


async def team_again(client, owner):
    response = await client.post(f"{V1}/cases", headers=owner, json={
        "title": "SYNTHETIC second case", "incident_start": "2022-05-01",
        "fields": [{"label": "Synthetic parcel", "privacy_tier": "REGION_ONLY", "region_label": "Synthetic",
                    "limitations": ["Synthetic"]}]})
    assert response.status_code == 201, response.text
    return (response.json()["id"],)


@pytest.mark.asyncio
async def test_database_rejects_self_review_and_two_current_answers(client, factory):
    case_id, owner, *_ = await team(client)
    created = await answer(client, owner, case_id, "MANAGEMENT_LOG")
    assert created.status_code == 201
    with factory() as s:
        row = s.get(UncertaintyAnswer, created.json()["id"])
        row.status, row.reviewed_by, row.review_note = "REVIEWED", row.answered_by, "self"
        row.reviewed_at = row.answered_at
        with pytest.raises(IntegrityError):
            s.commit()
    with factory() as s:
        original = s.get(UncertaintyAnswer, created.json()["id"])
        s.add(UncertaintyAnswer(case_id=original.case_id, question_id="MANAGEMENT_LOG",
                                question_snapshot={}, value_text="duplicate", origin="FARMER_REPORTED",
                                status="ANSWERED", answered_by=original.answered_by,
                                answered_at=original.answered_at))
        with pytest.raises(IntegrityError):
            s.commit()
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(Case)) == 1
        assert s.scalar(select(func.count()).select_from(User)) == 5
