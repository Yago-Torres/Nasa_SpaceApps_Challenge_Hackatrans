"""ABB-29 end-to-end main journey against a disposable PostgreSQL database (TEST_DATABASE_URL).

One user story, only through the public HTTP API (no database seeding, no service calls):

    creation -> NASA POWER -> evidence (paper, claim, review) -> hypothesis -> conclusion
             -> 3 rotation alternatives -> external review -> versioned, verifiable report

NASA POWER, OpenAlex and Crossref are replaced by explicit SYNTHETIC fixtures (``e2e_fixtures``,
``test_api_timeline_hypotheses.power_payload``, ``evidence_fakes``); nothing here touches the network. The same
journey against the real services is a manual smoke test: ``test_real_sources_smoke.py``.

The second half pins the failures of that journey that are known and must stay visible: upstream NASA failure,
a month without usable data, permissions, and the private-data guarantees.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

import e2e_fixtures as fx
from agroblackbox.api.deps import get_session_factory
from agroblackbox.app import app
from agroblackbox.db.session import create_database_engine, session_factory
from agroblackbox.evidence_seed import PILOT_SEED
from evidence_fakes import install, pilot_upstream
from test_api_timeline_hypotheses import EXACT_LAT, EXACT_LON, Upstream, ingest, nasa, power_payload  # noqa: F401
from test_evidence_claims import FULL_TEXT_SOURCE, claim_body
from test_rotations import profile as rotation_profile

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = [pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration"),
              pytest.mark.e2e]
V1 = fx.V1
DOI = PILOT_SEED[0]["doi"]


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
    fac = session_factory(api_engine)
    app.dependency_overrides[get_session_factory] = lambda: fac
    yield fac
    app.dependency_overrides.pop(get_session_factory, None)


@pytest.fixture
def scholarly(monkeypatch):
    return install(monkeypatch, pilot_upstream())


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── journey helpers: every call goes through the API a real user's browser uses ─────────────────────────────────

async def sign_up(client, who: tuple[str, str]) -> dict[str, str]:
    email, name = who
    registered = await client.post(f"{V1}/auth/register", json={"email": email, "password": fx.PASSWORD,
                                                                "display_name": name})
    assert registered.status_code == 201, registered.text
    login = await client.post(f"{V1}/auth/login", json={"email": email, "password": fx.PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def create_case(client, owner) -> dict:
    created = await client.post(f"{V1}/cases", json=fx.case_body(EXACT_LAT, EXACT_LON), headers=owner)
    assert created.status_code == 201, created.text
    return created.json()


async def invite_and_accept(client, owner, guest, cid, who, role):
    invitation = await client.post(f"{V1}/cases/{cid}/invitations", headers=owner,
                                   json={"email": who[0], "role": role})
    assert invitation.status_code == 201, invitation.text
    accepted = await client.post(f"{V1}/invitations/{invitation.json()['id']}/accept", headers=guest)
    assert accepted.status_code == 200, accepted.text


def private_strings() -> list[str]:
    return [str(EXACT_LAT), str(EXACT_LON), fx.PRIVATE_NOTE, "Ana Example", fx.OWNER[0], fx.REVIEWER[0],
            fx.VIEWER[0], fx.OWNER[1], fx.REVIEWER[1], f"{fx.SYNTHETIC_LABEL} parcel A"]


def assert_no_private_data(label: str, body: str):
    for secret in private_strings():
        assert secret not in body, f"{label} leaks {secret!r}"


# ── the main journey ────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_main_journey_from_case_creation_to_verifiable_report(client, nasa, scholarly):
    nasa["use"](Upstream(power_payload()))
    owner = await sign_up(client, fx.OWNER)
    reviewer = await sign_up(client, fx.REVIEWER)

    # 1. creation: the wizard payload becomes a private DRAFT case owned by the caller
    case = await create_case(client, owner)
    cid = case["id"]
    assert case["status"] == "DRAFT" and case["my_role"] == "OWNER" and case["visibility"] == "PRIVATE"
    await invite_and_accept(client, owner, reviewer, cid, fx.REVIEWER, "REVIEWER")
    moved = await client.post(f"{V1}/cases/{cid}/status", headers=owner,
                              json={"version": case["version"], "status": "INVESTIGATING"})
    assert moved.status_code == 200 and moved.json()["status"] == "INVESTIGATING"

    # 2. NASA: observations keep provenance; June 2022 is a large precipitation departure
    ingested = await ingest(client, owner, cid)
    assert ingested.status_code == 201, ingested.text
    observations = ingested.json()["observations"]
    june = next(o for o in observations if o["variable"] == "precipitation" and o["observed_at"].startswith("2022-06"))
    assert june["anomaly"]["departure"]["severity"] == "LARGE_DEPARTURE"
    assert june["anomaly"]["departure"]["direction"] == "BELOW_REFERENCE"
    timeline = (await client.get(f"{V1}/cases/{cid}/timeline", headers=owner)).json()
    kinds = {e["kind"] for e in timeline["events"]}
    assert "OBSERVED" in kinds and "FARMER_REPORTED" in kinds

    # 3. evidence: paper verified upstream, claim written by the owner, accepted by the reviewer only
    paper = await client.post(f"{V1}/evidence/papers", headers=owner, json={"doi": DOI})
    assert paper.status_code in (200, 201), paper.text
    claim_resp = await client.post(f"{V1}/cases/{cid}/claims", headers=owner,
                                   json=claim_body(paper.json()["id"], claim_text=fx.CLAIM_TEXT))
    assert claim_resp.status_code == 201, claim_resp.text
    claim = claim_resp.json()
    assert claim["review_status"] == "PENDING"
    own_review = await client.post(f"{V1}/cases/{cid}/claims/{claim['id']}/review", headers=owner, json={
        "version": claim["version"], "decision": "ACCEPTED", "note": "self review", "source_consulted": FULL_TEXT_SOURCE})
    assert own_review.status_code == 403
    reviewed = await client.post(f"{V1}/cases/{cid}/claims/{claim['id']}/review", headers=reviewer, json={
        "version": claim["version"], "decision": "ACCEPTED", "note": f"{fx.SYNTHETIC_LABEL} review note",
        "source_consulted": FULL_TEXT_SOURCE})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review_status"] == "ACCEPTED"

    # 4. hypothesis -> evaluated by the reviewer -> conclusion with a complete evidence trail, reviewed
    hyp = await client.post(f"{V1}/cases/{cid}/hypotheses", headers=owner, json={
        "title": f"{fx.SYNTHETIC_LABEL} water deficit", "statement": "Rain deficit in June may have stressed the crop.",
        "supporting_evidence_ids": [june["anomaly"]["id"], claim["id"]], "missing_evidence": ["Soil moisture records"],
        "limitations": [fx.HYPOTHESIS_LIMITATION]})
    assert hyp.status_code == 201, hyp.text
    hyp = hyp.json()
    evaluated = await client.post(f"{V1}/cases/{cid}/hypotheses/{hyp['id']}/status", headers=reviewer, json={
        "version": hyp["version"], "status": "COMPATIBLE", "note": "June deficit is compatible in time."})
    assert evaluated.status_code == 200, evaluated.text
    graph = f"{V1}/cases/{cid}/evidence-graph"
    conclusion = await client.post(f"{graph}/conclusions", headers=owner, json={
        "title": f"{fx.SYNTHETIC_LABEL} conclusion", "statement": fx.CONCLUSION_TEXT,
        "limitations": ["Regional grid-cell data only."],
        "supporting": [{"node_id": f"anomaly:{june['anomaly']['id']}", "note": "June departure"},
                       {"node_id": f"hypothesis:{hyp['id']}", "note": "Evaluated hypothesis"},
                       {"node_id": "farmer:incident", "note": "Farmer report"}],
        "limited_by": [{"node_id": "missing:no-local-measurements", "note": "No rain gauge records."}],
        "addresses_hypothesis_ids": [hyp["id"]]})
    assert conclusion.status_code == 201, conclusion.text
    conclusion = conclusion.json()
    assert conclusion["trace_complete"] is True and conclusion["review_status"] == "PENDING"
    accepted = await client.post(f"{graph}/conclusions/{conclusion['id']}/review", headers=reviewer, json={
        "version": conclusion["version"], "decision": "ACCEPTED", "note": "Checked the cited evidence trail."})
    assert accepted.status_code == 200, accepted.text
    trace = (await client.get(f"{graph}/trace/{conclusion['node_id']}", headers=reviewer)).json()
    assert trace["complete"] is True and trace["summary"]["reaches_observed_data"] is True
    assert trace["summary"]["reaches_literature"] is True and trace["summary"]["reaches_farmer_report"] is True

    # 5. rotations: current rotation plus the three rule-generated alternatives, descriptive only
    rotations = await client.post(f"{V1}/rotations/compare", json={"profile": rotation_profile()})
    assert rotations.status_code == 200, rotations.text
    strategies = rotations.json()["strategies"]
    assert [s["strategy_kind"] for s in strategies] == ["CURRENT", "MINIMAL_CHANGE", "FAMILY_DIVERSIFICATION", "CALENDAR_COVER"]
    assert all(s["verified_impact"] is None for s in strategies)   # no invented benefit

    # 6. external review: only a REVIEWER may close the review step
    assert (await client.post(f"{V1}/cases/{cid}/status", headers=owner, json={
        "version": (await client.get(f"{V1}/cases/{cid}", headers=owner)).json()["version"],
        "status": "REVIEWED"})).status_code == 403
    current = (await client.get(f"{V1}/cases/{cid}", headers=reviewer)).json()
    reviewed_case = await client.post(f"{V1}/cases/{cid}/status", headers=reviewer, json={
        "version": current["version"], "status": "REVIEWED", "note": f"{fx.SYNTHETIC_LABEL} external review done"})
    assert reviewed_case.status_code == 200 and reviewed_case.json()["status"] == "REVIEWED"

    # 7. report: authentic NASA identifiers, reviewed evidence, the three alternatives, no private data
    created = await client.post(f"{V1}/cases/{cid}/reports", headers=owner, json={"rotation": {"profile": rotation_profile()}})
    assert created.status_code == 201, created.text
    meta = created.json()
    assert meta["version"] == 1 and len(meta["source_manifest_ids"]) == 1
    verify = (await client.get(f"{V1}/cases/{cid}/reports/1/verify", headers=reviewer)).json()
    assert verify["valid"] is True and all(verify["checks"].values())
    markdown = (await client.get(f"{V1}/cases/{cid}/reports/1/download", params={"format": "markdown"},
                                 headers=reviewer))
    assert markdown.status_code == 200 and markdown.headers["x-report-sha256"] == meta["checksum_sha256"]
    md = markdown.text
    assert meta["source_manifest_ids"][0] in md and "POWER Daily API v2.10.3" in md and "LARGE_DEPARTURE" in md
    assert DOI in md and "LITERATURE_REVIEWED" in md and fx.CONCLUSION_TEXT in md
    for kind in ("MINIMAL_CHANGE", "FAMILY_DIVERSIFICATION", "CALENDAR_COVER"):
        assert kind in md
    assert_no_private_data("report markdown", md)
    pdf = await client.get(f"{V1}/cases/{cid}/reports/1/download", params={"format": "pdf"}, headers=reviewer)
    assert pdf.status_code == 200 and pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF") and pdf.headers["x-report-sha256"] == meta["pdf_sha256"]
    assert hashlib.sha256(pdf.content).hexdigest() == meta["pdf_sha256"]
    for fmt in ("html", "json"):
        body = await client.get(f"{V1}/cases/{cid}/reports/1/download", params={"format": fmt}, headers=owner)
        assert body.status_code == 200
        assert_no_private_data(f"report {fmt}", body.text)

    # the audit trail names every step of the journey
    history = (await client.get(f"{V1}/cases/{cid}/history", headers=owner)).json()
    actions = {h["action"] for h in history}
    assert {"CREATED", "STATUS_CHANGED", "REPORT_GENERATED"} <= actions


# ── known failures of the journey: detected and pinned ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [httpx.Response(503, text="upstream down"), httpx.Response(429, text="slow down"),
                                   httpx.Response(200, text="not json")])
async def test_nasa_failure_stops_the_journey_honestly_without_invented_data(client, nasa, scholarly, reply):
    nasa["use"](Upstream(reply))
    owner = await sign_up(client, fx.OWNER)
    case = await create_case(client, owner)
    cid = case["id"]
    failed = await ingest(client, owner, cid)
    assert failed.status_code == 502
    assert str(EXACT_LAT) not in failed.text and "power.larc" not in failed.text   # generic message, no URL/query
    assert (await client.get(f"{V1}/cases/{cid}/observations", headers=owner)).json()["items"] == []
    # the case and its report remain usable and say that no NASA series exists
    report = await client.post(f"{V1}/cases/{cid}/reports", headers=owner, json={})
    assert report.status_code == 201 and report.json()["source_manifest_ids"] == []
    md = (await client.get(f"{V1}/cases/{cid}/reports/1/download", params={"format": "markdown"}, headers=owner)).text
    assert "LARGE_DEPARTURE" not in md and "POWER Daily API" not in md
    assert_no_private_data("report without NASA data", md)


@pytest.mark.asyncio
async def test_month_without_usable_data_is_not_classified_never_given_a_value(client, nasa, scholarly):
    payload = power_payload()
    rain = payload["properties"]["parameter"]["PRECTOTCORR"]
    for key in list(rain):
        if key.startswith("202206"):
            rain[key] = -999.0                        # NASA fill value for the whole of June 2022
    nasa["use"](Upstream(payload))
    owner = await sign_up(client, fx.OWNER)
    cid = (await create_case(client, owner))["id"]
    response = await ingest(client, owner, cid)
    assert response.status_code == 201, response.text
    june = [o for o in response.json()["observations"]
            if o["variable"] == "precipitation" and o["observed_at"].startswith("2022-06")]
    assert june and all(o["value"] is None and o["anomaly"]["value"] is None
                        and o["anomaly"]["departure"]["severity"] == "NOT_CLASSIFIED" for o in june)
    report = await client.post(f"{V1}/cases/{cid}/reports", headers=owner, json={})
    assert report.status_code == 201
    md = (await client.get(f"{V1}/cases/{cid}/reports/1/download", params={"format": "markdown"}, headers=owner)).text
    june_rows = [line for line in md.splitlines() if "Jun 2022" in line and "precipitation" in line]
    assert june_rows and all("NOT_CLASSIFIED" in r and "DEPARTURE" not in r.replace("NOT_CLASSIFIED", "")
                             for r in june_rows)   # no departure is claimed for a month without data


@pytest.mark.asyncio
async def test_permissions_hold_along_the_whole_journey(client, nasa, scholarly):
    nasa["use"](Upstream(power_payload()))
    owner = await sign_up(client, fx.OWNER)
    reviewer = await sign_up(client, fx.REVIEWER)
    viewer = await sign_up(client, fx.VIEWER)
    stranger = await sign_up(client, fx.STRANGER)
    cid = (await create_case(client, owner))["id"]
    await invite_and_accept(client, owner, reviewer, cid, fx.REVIEWER, "REVIEWER")
    await invite_and_accept(client, owner, viewer, cid, fx.VIEWER, "VIEWER")
    assert (await ingest(client, owner, cid)).status_code == 201

    # a viewer reads but changes nothing; a stranger cannot even learn that the case exists
    assert (await ingest(client, viewer, cid)).status_code == 403
    assert (await client.post(f"{V1}/cases/{cid}/reports", headers=viewer, json={})).status_code == 403
    assert (await client.post(f"{V1}/cases/{cid}/hypotheses", headers=viewer,
                              json={"statement": "Synthetic hypothesis"})).status_code == 403
    for path in ("", "/timeline", "/observations", "/claims", "/evidence-graph", "/reports", "/history"):
        assert (await client.get(f"{V1}/cases/{cid}{path}", headers=stranger)).status_code == 404, path
        assert (await client.get(f"{V1}/cases/{cid}{path}")).status_code == 401, path

    # reviewers and viewers get the privacy-reduced location, never the stored coordinates (case notes are
    # shared with members by design; the report is what must never carry them)
    for who in (reviewer, viewer):
        seen = await client.get(f"{V1}/cases/{cid}", headers=who)
        assert seen.status_code == 200
        assert str(EXACT_LAT) not in seen.text and str(EXACT_LON) not in seen.text
    own = (await client.get(f"{V1}/cases/{cid}", headers=owner)).json()["fields"][0]
    assert own["latitude"] is not None


@pytest.mark.asyncio
async def test_an_account_export_and_delete_leave_no_orphan_journey_data(client, nasa, scholarly, factory):
    nasa["use"](Upstream(power_payload()))
    owner = await sign_up(client, fx.OWNER)
    cid = (await create_case(client, owner))["id"]
    assert (await ingest(client, owner, cid)).status_code == 201
    exported = await client.get(f"{V1}/account/export", headers=owner)
    assert exported.status_code == 200 and cid in exported.text
    deleted = await client.post(f"{V1}/account/delete", headers=owner,
                                json={"password": fx.PASSWORD})
    assert deleted.status_code in (200, 202, 204), deleted.text
    with factory() as s:
        for table in ("cases", "observations", "source_manifests"):
            assert s.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one() == 0, table
