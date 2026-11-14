"""ABB-14 API integration tests against a disposable PostgreSQL database.

People, cases and claim texts are SYNTHETIC. OpenAlex/Crossref are simulated (``evidence_fakes``);
no test touches the network. Run with TEST_DATABASE_URL set.
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
from agroblackbox.db.models import EvidenceClaim, EvidenceClaimEvent, Paper, utcnow
from agroblackbox.db.session import create_database_engine, session_factory
from agroblackbox.evidence_seed import PILOT_SEED
from evidence_fakes import CC_BY_CROSSREF, FakeScholarly, crossref_reply, install, oa_work, pilot_upstream

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration")

PASSWORD = "synthetic-correct-horse-42"
V1 = "/api/v1"
DOI = PILOT_SEED[0]["doi"]
TITLE = PILOT_SEED[0]["title"]


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


@pytest.fixture
def upstream(monkeypatch):
    return install(monkeypatch, pilot_upstream())


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── helpers ──────────────────────────────────────────────────────────────────

async def account(client, email: str, name: str | None = None) -> dict[str, str]:
    registered = await client.post(f"{V1}/auth/register", json={
        "email": email, "password": PASSWORD, "display_name": name or email.split("@")[0]})
    assert registered.status_code == 201, registered.text
    login = await client.post(f"{V1}/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def me(client, headers) -> str:
    return (await client.get(f"{V1}/auth/me", headers=headers)).json()["id"]


async def new_case(client, headers) -> str:
    response = await client.post(f"{V1}/cases", headers=headers, json={
        "title": "SYNTHETIC evidence case", "incident_start": "2022-05-01",
        "fields": [{"label": "Synthetic parcel", "privacy_tier": "REGION_ONLY", "region_label": "Synthetic region",
                    "limitations": ["Synthetic"]}]})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def share(client, owner, case_id, email, role):
    response = await client.post(f"{V1}/cases/{case_id}/permissions", headers=owner, json={"email": email, "role": role})
    assert response.status_code in (200, 201), response.text


async def register(client, headers, **body) -> dict:
    response = await client.post(f"{V1}/evidence/papers", headers=headers, json=body or {"doi": DOI})
    assert response.status_code in (200, 201), response.text
    return response.json()


def claim_body(paper_id: str, **overrides) -> dict:
    return {
        "paper_id": paper_id,
        "claim_text": "SYNTHETIC: legume pre-crops were associated with higher main-crop yield in pooled trials.",
        "study_context": "Synthetic summary of a global meta-analysis of field experiments.",
        "study_design": "META_ANALYSIS",
        "context": {"crops": ["maize", "wheat"], "region": "Global", "management": "legume pre-crop"},
        "reported_outcome": {"outcome": "main-crop yield", "comparison": "non-legume pre-crop",
                             "effect_as_stated": "SYNTHETIC +20%", "units_as_stated": "% relative change",
                             "uncertainty_as_stated": "SYNTHETIC 95% CI 17-23%"},
        "source_locator": {"page": "3", "section": "Results"},
        "quoted_fragment": "SYNTHETIC short quotation for tests",
        "evidence_basis": "FULL_TEXT", "access_basis": "OPEN_ACCESS_LICENSE",
        "content_license": CC_BY_CROSSREF + "/",
        "limitations": ["Pooled estimate; not a forecast for an individual farm"],
        **overrides,
    }


async def create_claim(client, headers, case_id, paper_id, **overrides) -> dict:
    response = await client.post(f"{V1}/cases/{case_id}/claims", headers=headers, json=claim_body(paper_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


FULL_TEXT_SOURCE = {"basis": "FULL_TEXT", "access_basis": "OPEN_ACCESS_LICENSE", "license": CC_BY_CROSSREF,
                    "locator": "Results p.3, Fig. 2", "consulted_url": "https://doi.org/" + DOI}


async def review(client, headers, case_id, claim, decision="ACCEPTED", source=None, note="SYNTHETIC review note"):
    return await client.post(f"{V1}/cases/{case_id}/claims/{claim['id']}/review", headers=headers, json={
        "version": claim["version"], "decision": decision, "note": note,
        "source_consulted": source or FULL_TEXT_SOURCE})


async def team(client):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    reviewer = await account(client, "reviewer@example.test", "Synthetic reviewer")
    case_id = await new_case(client, owner)
    await share(client, owner, case_id, "reviewer@example.test", "REVIEWER")
    return owner, reviewer, case_id


# ── migration ────────────────────────────────────────────────────────────────

def test_claims_migration_downgrades_and_upgrades_cleanly(api_engine):
    command.downgrade(alembic_config(), "b7e2d4a91c03")
    inspector = inspect(api_engine)
    assert "evidence_claim_events" not in inspector.get_table_names()
    assert "created_by" not in {c["name"] for c in inspector.get_columns("evidence_claims")}
    command.upgrade(alembic_config(), "head")
    inspector = inspect(api_engine)
    assert "evidence_claim_events" in inspector.get_table_names()
    assert {"created_by", "version", "evidence_basis", "access_basis", "origin"} <= {
        c["name"] for c in inspector.get_columns("evidence_claims")}


# ── papers ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_paper_fetches_upstream_and_deduplicates(client, upstream, factory):
    owner = await account(client, "owner@example.test")
    created = await client.post(f"{V1}/evidence/papers", headers=owner, json={"doi": "https://doi.org/" + DOI.upper()})
    assert created.status_code == 201
    paper = created.json()
    assert (paper["doi_id"], paper["doi_status"]) == (DOI, "VERIFIED_CROSSREF")
    assert (paper["source_kind"], paper["evidence_status"]) == ("LITERATURE_METADATA", "BIBLIOGRAPHIC_MATCH_ONLY")
    assert paper["title"] == TITLE and paper["doi"] == "https://doi.org/" + DOI
    assert [r["source"] for r in paper["retrievals"]] == ["OpenAlex", "Crossref"]
    assert {lic["reported_by"] for lic in paper["licenses"]} == {"OpenAlex", "Crossref"}
    assert "scientific finding" in paper["limitations"][0]
    calls = len(upstream.requests)

    again = await client.post(f"{V1}/evidence/papers", headers=owner, json={"doi": "doi:" + DOI})
    by_openalex = await client.post(f"{V1}/evidence/papers", headers=owner, json={"openalex_id": "W901"})
    fetched = await client.get(f"{V1}/evidence/papers/{paper['id']}", headers=owner)
    assert (again.status_code, by_openalex.status_code, fetched.status_code) == (200, 200, 200)
    assert again.json()["id"] == by_openalex.json()["id"] == fetched.json()["id"] == paper["id"]
    assert len(upstream.requests) == calls  # verified papers are not fetched again
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Paper)) == 1


@pytest.mark.asyncio
async def test_registration_rejects_client_metadata_and_bad_identifiers(client, upstream):
    owner = await account(client, "owner@example.test")
    attempts = [
        {"doi": DOI, "title": "Client supplied title", "doi_status": "VERIFIED_CROSSREF"},
        {"doi": DOI, "openalex_id": "W901"},
        {},
        {"doi": "not-a-doi"},
        {"openalex_id": "https://evil.example/W1"},
    ]
    for body in attempts:
        response = await client.post(f"{V1}/evidence/papers", headers=owner, json=body)
        assert response.status_code == 422, body
    assert upstream.requests == []
    assert (await client.post(f"{V1}/evidence/papers", json={"doi": DOI})).status_code == 401
    assert (await client.get(f"{V1}/evidence/papers/00000000-0000-4000-8000-000000000000",
                             headers=owner)).status_code == 404


@pytest.mark.asyncio
async def test_unknown_or_unreachable_works_store_nothing(client, monkeypatch, factory):
    owner = await account(client, "owner@example.test")
    install(monkeypatch, FakeScholarly())
    missing = await client.post(f"{V1}/evidence/papers", headers=owner, json={"doi": "10.9999/synthetic-missing"})
    install(monkeypatch, FakeScholarly(openalex=httpx.Response(429), crossref={DOI: httpx.Response(503)}))
    outage = await client.post(f"{V1}/evidence/papers", headers=owner, json={"doi": DOI})
    assert (missing.status_code, outage.status_code) == (404, 502)
    assert "api.openalex.org" not in outage.text and "nothing was stored" in outage.json()["detail"]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Paper)) == 0


@pytest.mark.asyncio
async def test_unverified_paper_is_reverified_on_next_registration(client, monkeypatch):
    owner = await account(client, "owner@example.test")
    install(monkeypatch, pilot_upstream(**{DOI: httpx.Response(503)}))
    first = await client.post(f"{V1}/evidence/papers", headers=owner, json={"doi": DOI})
    assert first.status_code == 201 and first.json()["doi_status"] == "VERIFICATION_UNAVAILABLE"
    install(monkeypatch, pilot_upstream())
    second = await client.post(f"{V1}/evidence/papers", headers=owner, json={"doi": DOI})
    assert second.status_code == 200 and second.json()["id"] == first.json()["id"]
    assert second.json()["doi_status"] == "VERIFIED_CROSSREF"


# ── claim lifecycle and review ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_claim_review_lifecycle_keeps_reviewer_source_and_history(client, upstream, factory):
    owner, reviewer, case_id = await team(client)
    reviewer_id = await me(client, reviewer)
    paper = await register(client, owner)
    claim = await create_claim(client, owner, case_id, paper["id"])
    assert (claim["review_status"], claim["source_kind"], claim["is_reviewed"]) == ("PENDING", "LITERATURE_METADATA", False)
    assert claim["reviewed_by"] is None and claim["reviewed_at"] is None
    assert claim["can_edit"] and not claim["can_review"]  # the author cannot review
    assert any(w.startswith("Not reviewed") for w in claim["warnings"])

    as_reviewer = (await client.get(f"{V1}/cases/{case_id}/claims/{claim['id']}", headers=reviewer)).json()
    assert as_reviewer["can_review"] and not as_reviewer["can_edit"]

    abstract_only = await review(client, reviewer, case_id, claim,
                                 source={"basis": "ABSTRACT", "access_basis": "PUBLIC_ABSTRACT"})
    assert abstract_only.status_code == 422
    accepted = await review(client, reviewer, case_id, claim)
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert (body["review_status"], body["source_kind"], body["is_reviewed"]) == ("ACCEPTED", "LITERATURE_REVIEWED", True)
    assert body["reviewed_by"] == reviewer_id and body["reviewed_at"] is not None
    assert body["reviewer"]["display_name"] == "Synthetic reviewer" and body["version"] == 2
    assert body["warnings"][0].startswith("Reviewed:")

    listed = (await client.get(f"{V1}/cases/{case_id}/claims", headers=owner)).json()
    assert (listed["reviewed_count"], listed["unreviewed_count"]) == (1, 0)
    assert (await client.get(f"{V1}/cases/{case_id}/claims?review_status=PENDING", headers=owner)).json()["items"] == []

    # Editing an accepted claim withdraws the review but keeps it in the history.
    edited = await client.patch(f"{V1}/cases/{case_id}/claims/{claim['id']}", headers=owner,
                                json={"version": 2, "claim_text": "SYNTHETIC revised claim"})
    assert edited.status_code == 200
    assert (edited.json()["review_status"], edited.json()["source_kind"], edited.json()["reviewed_by"]) == (
        "PENDING", "LITERATURE_METADATA", None)
    history = (await client.get(f"{V1}/cases/{case_id}/claims/{claim['id']}/history", headers=reviewer)).json()
    assert [(e["action"], e["from_status"], e["to_status"]) for e in history] == [
        ("CREATED", None, "PENDING"), ("REVIEWED", "PENDING", "ACCEPTED"), ("UPDATED", "ACCEPTED", "PENDING")]
    decision = history[1]
    assert decision["actor"] == {"id": reviewer_id, "display_name": "Synthetic reviewer"}
    assert decision["note"] == "SYNTHETIC review note" and decision["created_at"]
    assert decision["source_consulted"]["basis"] == "FULL_TEXT"
    assert decision["source_consulted"]["license"] == CC_BY_CROSSREF
    assert decision["source_consulted"]["locator"] == "Results p.3, Fig. 2"
    assert decision["paper_snapshot"]["doi_id"] == DOI and decision["paper_snapshot"]["doi_status"] == "VERIFIED_CROSSREF"
    assert decision["paper_snapshot"]["metadata_retrieved_at"]
    assert history[2]["changes"]["claim_text"]["after"] == "SYNTHETIC revised claim"
    assert "ACCEPTED review no longer applies" in history[2]["note"]
    with factory() as session:
        events = session.scalars(select(EvidenceClaimEvent).where(EvidenceClaimEvent.action == "REVIEWED")).all()
        assert len(events) == 1 and str(events[0].actor_id) == reviewer_id


@pytest.mark.asyncio
async def test_self_review_is_forbidden_for_authors_and_editors(client, upstream, factory):
    owner, reviewer, case_id = await team(client)
    editor = await account(client, "editor@example.test")
    await share(client, owner, case_id, "editor@example.test", "EDITOR")
    paper = await register(client, owner)
    claim = await create_claim(client, owner, case_id, paper["id"])
    assert (await review(client, owner, case_id, claim)).status_code == 403
    edited = await client.patch(f"{V1}/cases/{case_id}/claims/{claim['id']}", headers=editor,
                                json={"version": 1, "study_context": "SYNTHETIC edited context"})
    claim = edited.json()
    denied = await review(client, editor, case_id, claim)
    assert denied.status_code == 403 and "different member" in denied.json()["detail"]
    assert (await review(client, owner, case_id, claim)).status_code == 403
    assert (await review(client, reviewer, case_id, claim)).status_code == 200

    # The database also refuses a claim reviewed by its own author.
    with factory() as session:
        row = session.get(EvidenceClaim, claim["id"])
        row.reviewed_by = row.created_by
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.asyncio
async def test_permissions_on_claims(client, upstream):
    owner, reviewer, case_id = await team(client)
    viewer = await account(client, "viewer@example.test")
    stranger = await account(client, "stranger@example.test")
    await share(client, owner, case_id, "viewer@example.test", "VIEWER")
    paper = await register(client, owner)
    claim = await create_claim(client, owner, case_id, paper["id"])
    base, cid = f"{V1}/cases/{case_id}/claims", claim["id"]
    upstream_calls = len(upstream.requests)

    async def attempts(headers):
        return [
            await client.post(base, headers=headers, json=claim_body(paper["id"])),
            await client.patch(f"{base}/{cid}", headers=headers, json={"version": 1, "claim_text": "Hijack"}),
            await client.delete(f"{base}/{cid}?version=1", headers=headers),
            await client.post(f"{base}/pilot-import", headers=headers),
        ]

    stranger_reads = [await client.get(base, headers=stranger), await client.get(f"{base}/{cid}", headers=stranger),
                      await client.get(f"{base}/{cid}/history", headers=stranger),
                      await review(client, stranger, case_id, claim)]
    assert [r.status_code for r in stranger_reads + await attempts(stranger)] == [404] * 8
    assert [r.status_code for r in await attempts(viewer)] == [403] * 4
    assert [r.status_code for r in await attempts(reviewer)] == [403] * 4
    assert (await review(client, viewer, case_id, claim)).status_code == 403
    for headers in (viewer, reviewer):
        assert (await client.get(base, headers=headers)).status_code == 200
        assert (await client.get(f"{base}/{cid}/history", headers=headers)).status_code == 200
    other_case = await new_case(client, owner)
    assert (await client.get(f"{V1}/cases/{other_case}/claims/{cid}", headers=owner)).status_code == 404
    assert len(upstream.requests) == upstream_calls  # pilot-import never reached upstream for non-editors
    unchanged = (await client.get(f"{base}/{cid}", headers=owner)).json()
    assert unchanged["version"] == 1 and unchanged["review_status"] == "PENDING"


@pytest.mark.asyncio
async def test_acceptance_requires_full_record_and_resolved_identity(client, monkeypatch):
    owner, reviewer, case_id = await team(client)
    install(monkeypatch, pilot_upstream(**{DOI: crossref_reply(DOI, "Nitrogen leaching in maize")}))
    mismatch_paper = await register(client, owner)
    assert mismatch_paper["doi_status"] == "METADATA_MISMATCH"
    install(monkeypatch, pilot_upstream())
    good_paper = await register(client, owner, doi=PILOT_SEED[1]["doi"])

    unknown_design = await create_claim(client, owner, case_id, good_paper["id"], study_design="UNKNOWN")
    no_outcome = await create_claim(client, owner, case_id, good_paper["id"], reported_outcome={})
    unresolved = await create_claim(client, owner, case_id, mismatch_paper["id"],
                                    access_basis="AUTHOR_PROVIDED_COPY", content_license="Author copy, publisher terms")
    openalex_licence = {**FULL_TEXT_SOURCE, "license": "cc-by"}  # the only licence recorded on a mismatch
    for claim, reason, source in ((unknown_design, "study design", None), (no_outcome, "reported outcome", None),
                                  (unresolved, "identity is unresolved", openalex_licence)):
        response = await review(client, reviewer, case_id, claim, source=source)
        assert response.status_code == 409 and reason in response.json()["detail"], response.text
    # Rejecting needs no full text, but still records what was consulted.
    rejected = await review(client, reviewer, case_id, unresolved, "REJECTED",
                            {"basis": "ABSTRACT", "access_basis": "PUBLIC_ABSTRACT"})
    assert rejected.status_code == 200 and rejected.json()["source_kind"] == "LITERATURE_METADATA"
    assert any("Rejected" in w for w in rejected.json()["warnings"])
    assert (await review(client, reviewer, case_id, rejected.json())).status_code == 409  # REJECTED -> ACCEPTED

    wrong_license = await client.post(f"{V1}/cases/{case_id}/claims", headers=owner,
                                      json=claim_body(good_paper["id"], content_license="cc-by-nc-nd"))
    assert wrong_license.status_code == 422 and "licence must be one recorded" in wrong_license.json()["detail"]
    review_wrong_license = await review(client, reviewer, case_id, no_outcome, "CHANGES_REQUESTED",
                                        {**FULL_TEXT_SOURCE, "license": "proprietary"})
    assert review_wrong_license.status_code == 422


@pytest.mark.asyncio
async def test_unreviewed_claim_kinds_never_present_as_reviewed(client, upstream):
    owner, reviewer, case_id = await team(client)
    paper = await register(client, owner)
    metadata_only = await create_claim(client, owner, case_id, paper["id"], evidence_basis="METADATA_ONLY",
                                       access_basis="NONE", content_license=None, quoted_fragment=None,
                                       reported_outcome={"outcome": "yield"})
    abstract = await create_claim(client, owner, case_id, paper["id"], evidence_basis="ABSTRACT",
                                  access_basis="PUBLIC_ABSTRACT", content_license=None)
    assert any(w.startswith("Metadata only") for w in metadata_only["warnings"])
    assert any("not a verified study or trial result" in w for w in abstract["warnings"])
    for claim in (metadata_only, abstract):
        assert (claim["source_kind"], claim["is_reviewed"], claim["review_status"]) == (
            "LITERATURE_METADATA", False, "PENDING")
    smuggled = [
        claim_body(paper["id"], review_status="ACCEPTED"),
        claim_body(paper["id"], source_kind="LITERATURE_REVIEWED"),
        claim_body(paper["id"], evidence_basis="METADATA_ONLY", access_basis="NONE", content_license=None,
                   quoted_fragment=None),  # effect sizes "from metadata"
        claim_body(paper["id"], access_basis="NONE"),
        claim_body(paper["id"], source_locator={}),  # unattributed quote
        claim_body("00000000-0000-4000-8000-000000000000"),
    ]
    statuses = [(await client.post(f"{V1}/cases/{case_id}/claims", headers=owner, json=body)).status_code
                for body in smuggled]
    assert statuses == [422, 422, 422, 422, 422, 404]
    # A changes-requested claim is still unreviewed; an accepted one can be withdrawn.
    changes = await review(client, reviewer, case_id, abstract, "CHANGES_REQUESTED",
                           {"basis": "ABSTRACT", "access_basis": "PUBLIC_ABSTRACT"})
    assert changes.json()["source_kind"] == "LITERATURE_METADATA" and changes.json()["reviewed_at"]
    full = await create_claim(client, owner, case_id, paper["id"])
    accepted = (await review(client, reviewer, case_id, full)).json()
    withdrawn = await review(client, reviewer, case_id, accepted, "REJECTED", note="SYNTHETIC: retraction found")
    assert withdrawn.status_code == 200 and withdrawn.json()["is_reviewed"] is False


@pytest.mark.asyncio
async def test_versions_deletion_and_frozen_cases(client, upstream):
    owner, reviewer, case_id = await team(client)
    paper = await register(client, owner)
    draft = await create_claim(client, owner, case_id, paper["id"])
    reviewed = await create_claim(client, owner, case_id, paper["id"])
    stale = await client.patch(f"{V1}/cases/{case_id}/claims/{draft['id']}", headers=owner,
                               json={"version": 9, "claim_text": "Stale"})
    assert stale.status_code == 409
    null_text = await client.patch(f"{V1}/cases/{case_id}/claims/{draft['id']}", headers=owner,
                                   json={"version": 1, "claim_text": None})
    assert null_text.status_code == 422
    noop = await client.patch(f"{V1}/cases/{case_id}/claims/{draft['id']}", headers=owner,
                              json={"version": 1, "claim_text": draft["claim_text"]})
    assert noop.status_code == 200 and noop.json()["version"] == 1

    rejected = (await review(client, reviewer, case_id, reviewed, "REJECTED")).json()
    kept = await client.delete(f"{V1}/cases/{case_id}/claims/{rejected['id']}?version={rejected['version']}",
                               headers=owner)
    assert kept.status_code == 409
    assert (await client.delete(f"{V1}/cases/{case_id}/claims/{draft['id']}?version=1", headers=owner)).status_code == 204
    assert (await client.get(f"{V1}/cases/{case_id}/claims/{draft['id']}", headers=owner)).status_code == 404
    case_history = (await client.get(f"{V1}/cases/{case_id}/history", headers=owner)).json()
    assert case_history[-1]["action"] == "EVIDENCE_CLAIM_DELETED"
    assert case_history[-1]["changes"]["claim"]["before"]["id"] == draft["id"]

    archived = await client.post(f"{V1}/cases/{case_id}/archive", headers=owner, json={"version": 1, "archived": True})
    assert archived.status_code == 200
    frozen = [
        await client.post(f"{V1}/cases/{case_id}/claims", headers=owner, json=claim_body(paper["id"])),
        await review(client, reviewer, case_id, rejected, "CHANGES_REQUESTED"),
    ]
    assert [r.status_code for r in frozen] == [409, 409]
    assert all("archived" in r.json()["detail"] for r in frozen)
    listed = (await client.get(f"{V1}/cases/{case_id}/claims", headers=reviewer)).json()["items"]
    assert all(not item["can_edit"] and not item["can_review"] for item in listed)


@pytest.mark.asyncio
async def test_database_requires_reviewer_and_timestamp_for_decisions(client, upstream, factory):
    owner, _, case_id = await team(client)
    paper = await register(client, owner)
    claim = await create_claim(client, owner, case_id, paper["id"])
    for changes in ({"review_status": "ACCEPTED"},
                    {"review_status": "ACCEPTED", "reviewed_at": utcnow()},
                    {"review_status": "PENDING", "reviewed_at": utcnow()},
                    {"evidence_basis": "FULL_TEXT", "content_license": None}):
        with factory() as session:
            row = session.get(EvidenceClaim, claim["id"])
            for name, value in changes.items():
                setattr(row, name, value)
            with pytest.raises(IntegrityError):
                session.commit()


# ── pilot cards ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pilot_import_creates_pending_unreviewed_cards_once(client, upstream, factory):
    owner, reviewer, case_id = await team(client)
    first = await client.post(f"{V1}/cases/{case_id}/claims/pilot-import", headers=owner)
    assert first.status_code == 200, first.text
    body = first.json()
    assert [c["origin_ref"] for c in body["created"]] == ["E-001", "E-002", "E-003"]
    assert body["skipped"] == [] and body["failed"] == []
    for card in body["created"]:
        assert (card["review_status"], card["source_kind"], card["is_reviewed"]) == ("PENDING", "LITERATURE_METADATA", False)
        assert (card["evidence_basis"], card["origin"]) == ("METADATA_ONLY", "PILOT_SEED_UNVERIFIED")
        assert card["reviewed_by"] is None and card["quoted_fragment"] is None
        assert card["reported_outcome"]["effect_as_stated"] is None
        assert any("unverified pilot seed" in w for w in card["warnings"])
        assert card["paper"]["doi_status"] == "VERIFIED_CROSSREF" and not card["can_review"]
    again = (await client.post(f"{V1}/cases/{case_id}/claims/pilot-import", headers=owner)).json()
    assert again["created"] == [] and [s["seed_id"] for s in again["skipped"]] == ["E-001", "E-002", "E-003"]
    as_reviewer = (await client.get(f"{V1}/cases/{case_id}/claims", headers=reviewer)).json()
    assert as_reviewer["reviewed_count"] == 0 and all(item["can_review"] for item in as_reviewer["items"])
    # A metadata-only pilot card cannot be accepted until someone records design/outcome from the paper.
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Paper)) == 3
        assert session.scalar(select(func.count()).select_from(EvidenceClaim)
                              .where(EvidenceClaim.review_status != "PENDING")) == 0


@pytest.mark.asyncio
async def test_pilot_import_reports_mismatches_and_outages_per_card(client, monkeypatch):
    owner, _, case_id = await team(client)
    second, third = PILOT_SEED[1]["doi"], PILOT_SEED[2]["doi"]
    fake = pilot_upstream(**{third: httpx.Response(503)})
    fake.by_doi[third] = None  # OpenAlex does not know it and Crossref is down -> unavailable
    fake.by_doi[second] = oa_work("W902", "Synthetic unrelated title", second)
    fake.crossref[second] = crossref_reply(second, "Synthetic unrelated title")
    install(monkeypatch, fake)
    result = (await client.post(f"{V1}/cases/{case_id}/claims/pilot-import", headers=owner)).json()
    assert [c["origin_ref"] for c in result["created"]] == ["E-001"]
    failed = {item["seed_id"]: item["reason"] for item in result["failed"]}
    assert set(failed) == {"E-002", "E-003"}
    assert "does not match the seed title" in failed["E-002"] and "nothing was stored" in failed["E-003"]
