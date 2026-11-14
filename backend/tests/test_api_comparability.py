"""ABB-15 API integration tests against a disposable PostgreSQL database.

People, cases, claims and farms are SYNTHETIC; OpenAlex/Crossref are simulated (``evidence_fakes``).
Run with TEST_DATABASE_URL set.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from agroblackbox.api.deps import get_session_factory
from agroblackbox.app import app
from agroblackbox.db.models import ClaimDisagreementReview, EvidenceClaim
from agroblackbox.db.session import create_database_engine, session_factory
from agroblackbox.evidence_seed import PILOT_SEED
from comparability_fixtures import (
    GLOBAL_META_CONTEXT,
    LIMITED_TRANSFER_EXPECTED,
    MEDITERRANEAN_CLIMATE,
    MEDITERRANEAN_COUNTRY,
    MEDITERRANEAN_PROFILE,
    numeric_score_keys,
)
from evidence_fakes import CC_BY_CROSSREF, install, pilot_upstream

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration")

PASSWORD = "synthetic-correct-horse-42"
V1 = "/api/v1"
DOIS = [entry["doi"] for entry in PILOT_SEED]


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


@pytest.fixture(autouse=True)
def upstream(monkeypatch):
    return install(monkeypatch, pilot_upstream())


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── helpers ──────────────────────────────────────────────────────────────────

async def account(client, email: str) -> dict[str, str]:
    registered = await client.post(f"{V1}/auth/register", json={
        "email": email, "password": PASSWORD, "display_name": "Synthetic " + email.split("@")[0]})
    assert registered.status_code == 201, registered.text
    login = await client.post(f"{V1}/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def new_case(client, headers, **extra) -> str:
    response = await client.post(f"{V1}/cases", headers=headers, json={
        "title": "SYNTHETIC comparability case", "incident_start": "2022-05-01", **extra,
        "fields": [{"label": "Synthetic parcel", "privacy_tier": "REGION_ONLY", "region_label": "Synthetic valley",
                    "limitations": ["Synthetic"]}]})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def share(client, owner, case_id, email, role):
    response = await client.post(f"{V1}/cases/{case_id}/permissions", headers=owner, json={"email": email, "role": role})
    assert response.status_code in (200, 201), response.text


async def paper(client, headers, doi) -> str:
    response = await client.post(f"{V1}/evidence/papers", headers=headers, json={"doi": doi})
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def claim_body(paper_id: str, **overrides) -> dict:
    return {
        "paper_id": paper_id,
        "claim_text": "SYNTHETIC: the legume pre-crop changed main-crop yield.",
        "study_context": "SYNTHETIC study summary.",
        "study_design": "META_ANALYSIS",
        "context": {"crops": ["maize"], "region": "Global"},
        "reported_outcome": {"outcome": "main-crop yield", "comparison": "cereal pre-crop"},
        "source_locator": {"page": "3"},
        "evidence_basis": "FULL_TEXT", "access_basis": "OPEN_ACCESS_LICENSE", "content_license": CC_BY_CROSSREF,
        "limitations": ["Synthetic test claim"],
        "intervention": "Legume pre-crop", "comparator": "Cereal pre-crop", "outcome_variable": "Main-crop yield",
        "effect_direction": "INCREASE",
        **overrides,
    }


async def create_claim(client, headers, case_id, paper_id, **overrides) -> dict:
    response = await client.post(f"{V1}/cases/{case_id}/claims", headers=headers, json=claim_body(paper_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


async def accept(client, headers, case_id, claim) -> dict:
    response = await client.post(f"{V1}/cases/{case_id}/claims/{claim['id']}/review", headers=headers, json={
        "version": claim["version"], "decision": "ACCEPTED", "note": "SYNTHETIC full-text check",
        "source_consulted": {"basis": "FULL_TEXT", "access_basis": "OPEN_ACCESS_LICENSE", "license": CC_BY_CROSSREF,
                             "locator": "Results"}})
    assert response.status_code == 200, response.text
    return response.json()


async def disagreements(client, headers, case_id) -> dict:
    response = await client.get(f"{V1}/cases/{case_id}/claims/disagreements", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def decide(client, headers, case_id, item, decision, note="SYNTHETIC decision note"):
    return await client.post(f"{V1}/cases/{case_id}/claims/disagreements/{item['id']}/review", headers=headers, json={
        "decision": decision, "note": note, "claim_a_version": item["claim_a"]["claim_version"],
        "claim_b_version": item["claim_b"]["claim_version"]})


async def team(client):
    owner = await account(client, "owner@example.test")
    reviewer = await account(client, "reviewer@example.test")
    viewer = await account(client, "viewer@example.test")
    case_id = await new_case(client, owner)
    await share(client, owner, case_id, "reviewer@example.test", "REVIEWER")
    await share(client, owner, case_id, "viewer@example.test", "VIEWER")
    return owner, reviewer, viewer, case_id


async def opposed_pair(client, owner, case_id):
    p1, p2 = await paper(client, owner, DOIS[0]), await paper(client, owner, DOIS[1])
    a = await create_claim(client, owner, case_id, p1)
    b = await create_claim(client, owner, case_id, p2, intervention="  legume PRE-CROP", effect_direction="DECREASE",
                           outcome_variable="main-crop   yield", study_design="FIELD_EXPERIMENT",
                           context={"crops": ["wheat_durum"], "water_regime": "RAINFED",
                                    "geographic_scope": "NATIONAL", "countries": ["es"]})
    return a, b


# ── migration ────────────────────────────────────────────────────────────────

def test_abb15_migration_downgrades_and_upgrades(api_engine):
    command.downgrade(alembic_config(), "e3a9c71f5b20")
    inspector = inspect(api_engine)
    assert "claim_disagreement_reviews" not in inspector.get_table_names()
    assert "effect_direction" not in {c["name"] for c in inspector.get_columns("evidence_claims")}
    command.upgrade(alembic_config(), "head")
    inspector = inspect(api_engine)
    assert "claim_disagreement_reviews" in inspector.get_table_names()
    assert {"intervention", "comparator", "outcome_variable", "effect_direction"} <= {
        c["name"] for c in inspector.get_columns("evidence_claims")}


# ── disagreements ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reviewed_contradiction_is_shown_with_both_references(client, factory):
    owner, reviewer, viewer, case_id = await team(client)
    a, b = await opposed_pair(client, owner, case_id)
    unstated = await create_claim(client, owner, case_id, await paper(client, owner, DOIS[2]),
                                  effect_direction="NOT_STATED")

    listing = await disagreements(client, viewer, case_id)
    assert listing["method_version"].startswith("abb15") and listing["limitations"]
    assert [x["claim_id"] for x in listing["claims_not_compared"]] == [unstated["id"]]
    (item,) = listing["items"]
    assert (item["status"], item["kind"], item["both_claims_reviewed"]) == ("CANDIDATE", "OPPOSITE_DIRECTION", False)
    assert {item["claim_a"]["claim_id"], item["claim_b"]["claim_id"]} == {a["id"], b["id"]}
    assert {item["claim_a"]["paper"]["doi_id"], item["claim_b"]["paper"]["doi_id"]} == {DOIS[0], DOIS[1]}
    assert "not a contradiction" in item["warnings"][0] and item["can_review"] is False  # viewer
    notes = {n["dimension"]: n["status"] for n in item["comparability_notes"]}
    assert notes["COMPARATOR"] == "MATCH" and notes["STUDY_DESIGN"] == "MISMATCH" and notes["CROPS"] == "MISMATCH"
    assert notes["REGION"] == "UNKNOWN"  # claim A only says "Global" in free text, which is never parsed
    assert not numeric_score_keys(listing)

    # unreviewed claims: a contradiction cannot be confirmed, but INCONCLUSIVE can be recorded
    assert (await decide(client, reviewer, case_id, item, "CONFIRMED_CONTRADICTION")).status_code == 409
    inconclusive = await decide(client, reviewer, case_id, item, "INCONCLUSIVE", "SYNTHETIC: subgroups unclear")
    assert inconclusive.status_code == 200, inconclusive.text
    body = inconclusive.json()
    assert body["status"] == "INCONCLUSIVE"
    assert body["current_review"]["reviewer"]["display_name"] == "Synthetic reviewer"
    assert body["current_review"]["note"] == "SYNTHETIC: subgroups unclear"

    # reviewing the claims changes their versions: the earlier decision no longer applies
    by_id = {c["id"]: c for c in (a, b)}
    for claim_id in (item["claim_a"]["claim_id"], item["claim_b"]["claim_id"]):
        await accept(client, reviewer, case_id, by_id[claim_id])
    (item,) = (await disagreements(client, reviewer, case_id))["items"]
    assert item["status"] == "CANDIDATE" and item["both_claims_reviewed"] is True and item["can_review"] is True
    assert [r["applies_to_current_versions"] for r in item["reviews"]] == [False]
    assert any("no longer applies" in w for w in item["warnings"])

    # contributors cannot decide; stale versions are rejected
    assert (await decide(client, owner, case_id, item, "CONFIRMED_CONTRADICTION")).status_code == 403
    stale = {**item, "claim_a": {**item["claim_a"], "claim_version": 1}}
    assert (await decide(client, reviewer, case_id, stale, "CONFIRMED_CONTRADICTION")).status_code == 409

    confirmed = await decide(client, reviewer, case_id, item, "CONFIRMED_CONTRADICTION",
                             "SYNTHETIC: both full texts report opposed yield responses")
    assert confirmed.status_code == 200, confirmed.text
    shown = (await disagreements(client, viewer, case_id))["items"][0]
    assert shown["status"] == "CONFIRMED_CONTRADICTION"
    for side in ("claim_a", "claim_b"):
        assert shown[side]["is_reviewed"] and shown[side]["source_kind"] == "LITERATURE_REVIEWED"
        assert shown[side]["paper"]["doi_id"] in DOIS[:2] and shown[side]["paper"]["title"]
    assert "does not say which study is right" in shown["warnings"][0]
    assert len(shown["reviews"]) == 2 and shown["current_review"]["decision"] == "CONFIRMED_CONTRADICTION"
    with factory() as session:
        rows = session.scalars(select(ClaimDisagreementReview).order_by(ClaimDisagreementReview.reviewed_at)).all()
        assert [r.decision for r in rows] == ["INCONCLUSIVE", "CONFIRMED_CONTRADICTION"]
        assert rows[-1].snapshot["claim_a"]["review_status"] == "ACCEPTED"
        assert {rows[-1].snapshot["claim_a"]["doi_id"], rows[-1].snapshot["claim_b"]["doi_id"]} == set(DOIS[:2])


@pytest.mark.asyncio
async def test_disagreement_permissions_and_candidate_lifecycle(client, factory):
    owner, reviewer, viewer, case_id = await team(client)
    stranger = await account(client, "stranger@example.test")
    a, b = await opposed_pair(client, owner, case_id)
    (item,) = (await disagreements(client, owner, case_id))["items"]
    assert item["can_review"] is False  # the owner wrote both claims

    assert (await client.get(f"{V1}/cases/{case_id}/claims/disagreements", headers=stranger)).status_code == 404
    assert (await decide(client, stranger, case_id, item, "NOT_COMPARABLE")).status_code == 404
    assert (await decide(client, viewer, case_id, item, "NOT_COMPARABLE")).status_code == 403
    unknown = {**item, "id": "00000000-0000-0000-0000-000000000001"}
    assert (await decide(client, reviewer, case_id, unknown, "NOT_COMPARABLE")).status_code == 404
    empty_note = await client.post(f"{V1}/cases/{case_id}/claims/disagreements/{item['id']}/review", headers=reviewer,
                                   json={"decision": "NOT_COMPARABLE", "note": " ", "claim_a_version": 1,
                                         "claim_b_version": 1})
    assert empty_note.status_code == 422

    decided = await decide(client, reviewer, case_id, item, "NOT_COMPARABLE", "SYNTHETIC: different comparators")
    assert decided.status_code == 200 and decided.json()["status"] == "NOT_COMPARABLE"

    # a claim with a disagreement decision is kept for audit
    deleted = await client.delete(f"{V1}/cases/{case_id}/claims/{a['id']}", headers=owner,
                                  params={"version": a["version"]})
    assert deleted.status_code == 409

    # editing the direction removes the candidate (and its id answers 404)
    edited = await client.patch(f"{V1}/cases/{case_id}/claims/{b['id']}", headers=owner,
                                json={"version": b["version"], "effect_direction": "MIXED"})
    assert edited.status_code == 200 and edited.json()["effect_direction"] == "MIXED"
    listing = await disagreements(client, owner, case_id)
    assert listing["items"] == []
    assert {"claim_id": b["id"], "reasons": ["stated direction MIXED is not compared"]} in listing["claims_not_compared"]
    assert (await decide(client, reviewer, case_id, item, "INCONCLUSIVE")).status_code == 404

    # no clear effect vs increase is a different kind of candidate
    await client.patch(f"{V1}/cases/{case_id}/claims/{b['id']}", headers=owner,
                       json={"version": edited.json()["version"], "effect_direction": "NO_CLEAR_EFFECT"})
    (item,) = (await disagreements(client, owner, case_id))["items"]
    assert item["kind"] == "EFFECT_VS_NO_CLEAR_EFFECT"

    # frozen case: decisions need an editable case
    for headers, target in ((owner, "INVESTIGATING"), (reviewer, "REVIEWED")):
        version = (await client.get(f"{V1}/cases/{case_id}", headers=owner)).json()["version"]
        moved = await client.post(f"{V1}/cases/{case_id}/status", headers=headers,
                                  json={"status": target, "version": version})
        assert moved.status_code == 200, moved.text
    frozen = await decide(client, reviewer, case_id, item, "INCONCLUSIVE")
    assert frozen.status_code == 409
    assert len((await disagreements(client, viewer, case_id))["items"]) == 1  # still readable


@pytest.mark.asyncio
async def test_effect_direction_needs_source_text_in_api_and_database(client, factory):
    owner, _, _, case_id = await team(client)
    pid = await paper(client, owner, DOIS[0])
    metadata_only = claim_body(pid, evidence_basis="METADATA_ONLY", access_basis="NONE", content_license=None,
                               reported_outcome={}, source_locator={})
    response = await client.post(f"{V1}/cases/{case_id}/claims", headers=owner, json=metadata_only)
    assert response.status_code == 422 and "metadata alone" in response.text
    claim = await create_claim(client, owner, case_id, pid, evidence_basis="METADATA_ONLY", access_basis="NONE",
                               content_license=None, reported_outcome={}, source_locator={},
                               effect_direction="NOT_STATED")
    with factory() as session:
        row = session.get(EvidenceClaim, claim["id"])
        row.effect_direction = "INCREASE"
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        row = session.get(EvidenceClaim, claim["id"])
        row.evidence_basis, row.access_basis, row.content_license = "FULL_TEXT", "AUTHOR_PROVIDED_COPY", "x"
        row.effect_direction, row.intervention = "INCREASE", None
        with pytest.raises(IntegrityError):
            session.commit()


# ── applicability ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_limited_transfer_example_global_meta_analysis_vs_rainfed_mediterranean(client, factory):
    owner, reviewer, viewer, case_id = await team(client)
    claim = await create_claim(client, owner, case_id, await paper(client, owner, DOIS[0]),
                               context=GLOBAL_META_CONTEXT)
    body = {"farm_profile": {**MEDITERRANEAN_PROFILE, "case_id": case_id},
            "country_code": MEDITERRANEAN_COUNTRY, "koppen_climate": MEDITERRANEAN_CLIMATE}
    with factory() as session:
        before = session.scalar(select(func.count()).select_from(ClaimDisagreementReview))
    response = await client.post(f"{V1}/cases/{case_id}/claims/{claim['id']}/applicability", headers=viewer, json=body)
    assert response.status_code == 200, response.text
    report = response.json()
    assert {d["dimension"]: d["status"] for d in report["dimensions"]} == LIMITED_TRANSFER_EXPECTED
    assert report["transfer_status"] == "DIFFERENCES_FOUND" and report["stored"] is False
    assert report["unknown_dimensions"] == ["SOIL_TEXTURE"]
    assert set(report["differing_dimensions"]) == {"CROPS", "WATER_REGIME", "SOIL_PH", "REGION", "CLIMATE"}
    assert (report["is_reviewed"], report["paper"]["doi_id"]) == (False, DOIS[0])
    assert any("Pooled estimate" in n for n in report["notes"]) and any("not reviewed" in n for n in report["notes"])
    assert all(d["reason"] for d in report["dimensions"])
    assert not numeric_score_keys(report)
    region = next(d for d in report["dimensions"] if d["dimension"] == "REGION")
    assert "Synthetic valley" in region["case_value"] and "not compared" in region["case_value"]
    with factory() as session:  # nothing stored
        assert session.scalar(select(func.count()).select_from(ClaimDisagreementReview)) == before

    reviewed = await client.post(f"{V1}/cases/{case_id}/claims/{claim['id']}/applicability", headers=reviewer,
                                 json=body)
    assert reviewed.status_code == 200


@pytest.mark.asyncio
async def test_applicability_without_data_is_unknown_and_uses_stored_crops(client):
    owner, _, viewer, case_id = await team(client)
    claim = await create_claim(client, owner, case_id, await paper(client, owner, DOIS[0]))
    url = f"{V1}/cases/{case_id}/claims/{claim['id']}/applicability"
    empty = await client.post(url, headers=viewer)
    assert empty.status_code == 200, empty.text
    report = empty.json()
    assert {d["status"] for d in report["dimensions"]} == {"UNKNOWN"}
    assert report["transfer_status"] == "INSUFFICIENT_DATA"
    assert not numeric_score_keys(report)

    other_case = await new_case(client, owner, crop_history=["Maize"])
    other_claim = await create_claim(client, owner, other_case, await paper(client, owner, DOIS[0]))
    stored = (await client.post(f"{V1}/cases/{other_case}/claims/{other_claim['id']}/applicability",
                                headers=owner, json={})).json()
    crops = next(d for d in stored["dimensions"] if d["dimension"] == "CROPS")
    assert (crops["status"], crops["case_value_source"]) == ("MATCH", "case record crop history (FARMER_REPORTED)")

    stranger = await account(client, "stranger@example.test")
    assert (await client.post(url, headers=stranger, json={})).status_code == 404
    assert (await client.post(f"{V1}/cases/{case_id}/claims/{other_claim['id']}/applicability",
                              headers=owner, json={})).status_code == 404
    mismatch = await client.post(url, headers=owner, json={"farm_profile": {"case_id": other_case}})
    assert mismatch.status_code == 422
    for bad in ({"country_code": "Spain"}, {"koppen_climate": "Mediterranean"}, {"score": 0.8}):
        assert (await client.post(url, headers=owner, json=bad)).status_code == 422
    assert (await client.post(url, json={})).status_code == 401
