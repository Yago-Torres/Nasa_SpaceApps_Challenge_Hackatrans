"""ABB-26 case report API against a disposable PostgreSQL database (TEST_DATABASE_URL).

NASA POWER is simulated with httpx.MockTransport (reusing the ABB-10 synthetic series); every person, parcel,
coordinate, note, paper and DOI is SYNTHETIC. The tests check what a downloaded report really contains, that
nothing private leaks into it, that versions are immutable and verifiable, and that a regenerated report
names what changed.
"""
from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError

from agroblackbox.api.deps import get_session_factory
from agroblackbox.app import app
from agroblackbox.db.models import (
    CaseComment, EvidenceClaim, EvidenceConclusion, Hypothesis, Paper, Report, SourceManifest, User,
)
from agroblackbox.db.session import create_database_engine, session_factory
from test_api_timeline_hypotheses import EXACT_LAT, EXACT_LON, PASSWORD, V1, Upstream, ingest, nasa, power_payload  # noqa: F401
from test_rotations import profile as rotation_profile

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration")
T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
NOTE = "Synthetic private note: neighbour Ana Example, phone 000-111."
COMMENT_TEXT = "Synthetic private comment about the neighbour's tractor."


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


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def account(client, email: str, name: str) -> dict[str, str]:
    assert (await client.post(f"{V1}/auth/register", json={"email": email, "password": PASSWORD,
                                                           "display_name": name})).status_code == 201
    login = await client.post(f"{V1}/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def make_case(client, owner) -> dict:
    body = {"title": "SYNTHETIC case - not a real incident", "incident_start": "2022-05-01", "incident_end": "2022-08-31",
            "crop_history": ["wheat", "barley"], "incident_notes": NOTE,
            "fields": [{"label": "Synthetic parcel A", "privacy_tier": "APPROXIMATE", "latitude": EXACT_LAT,
                        "longitude": EXACT_LON, "region_label": "Synthetic region", "rounding_deg": 0.5,
                        "limitations": ["Synthetic test parcel; not a real farm"]}]}
    created = await client.post(f"{V1}/cases", json=body, headers=owner)
    assert created.status_code == 201, created.text
    return created.json()


async def add_member(client, owner, cid, email, role):
    response = await client.post(f"{V1}/cases/{cid}/permissions", json={"email": email, "role": role}, headers=owner)
    assert response.status_code in (200, 201), response.text


def seed_evidence(factory, cid: str, author: str, reviewer: str, *, doi: str = "10.5555/synthetic.0001") -> dict:
    with factory.begin() as s:
        paper = Paper(title="Synthetic paper on water deficit", year=2020, doi_id=doi,
                      doi_status="VERIFIED_CROSSREF", bibliographic_metadata={}, limitations=["Synthetic paper"])
        s.add(paper)
        s.flush()
        accepted = EvidenceClaim(case_id=cid, paper_id=paper.id, claim_text="Synthetic reviewed claim | with pipe",
                                 study_context="ctx", limitations=["Synthetic claim limitation"], created_by=author,
                                 study_design="FIELD_EXPERIMENT", reported_outcome={"outcome": "x"},
                                 review_status="ACCEPTED", reviewed_by=reviewer, reviewed_at=T0,
                                 evidence_basis="FULL_TEXT", access_basis="AUTHOR_PROVIDED_COPY",
                                 content_license="synthetic terms", version=2)
        pending = EvidenceClaim(case_id=cid, paper_id=paper.id, claim_text="Synthetic metadata-only claim",
                                study_context="ctx", limitations=["Synthetic pending limitation"], created_by=author)
        hypothesis = Hypothesis(case_id=cid, title="Synthetic water deficit", statement="Rain deficit in June <b>x</b>.",
                                status="COMPATIBLE", limitations=["Synthetic hypothesis limitation"],
                                supporting_evidence_ids=["a"], contradicting_evidence_ids=[],
                                missing_evidence=["Soil moisture records"], evaluation_note="Compatible in time only.")
        conclusion = EvidenceConclusion(case_id=cid, title="Synthetic conclusion", statement="Water stress is a candidate.",
                                        limitations=["Synthetic conclusion limitation"], review_status="ACCEPTED",
                                        review_note="Checked by a reviewer.", reviewed_by=reviewer, reviewed_at=T0,
                                        contributor_ids=[author])
        s.add_all([accepted, pending, hypothesis, conclusion])
        s.flush()
        s.add(CaseComment(case_id=cid, author_id=author, body=COMMENT_TEXT, target_kind="CASE"))
        return {"accepted": str(accepted.id), "pending": str(pending.id), "hypothesis": str(hypothesis.id),
                "conclusion": str(conclusion.id), "doi": doi}


async def uid(client, headers) -> str:
    return (await client.get(f"{V1}/auth/me", headers=headers)).json()["id"]


async def download(client, headers, cid, version, fmt):
    return await client.get(f"{V1}/cases/{cid}/reports/{version}/download", params={"format": fmt}, headers=headers)


def assert_private(text_: str):
    for secret in (str(EXACT_LAT), str(EXACT_LON), NOTE, "Ana Example", COMMENT_TEXT, "owner@example.test",
                   "reviewer@example.test", "viewer@example.test", "Synthetic owner", "Synthetic reviewer"):
        assert secret not in text_, secret


# ── migration and immutability ───────────────────────────────────────────────

def test_report_migration_and_write_once_trigger(api_engine):
    command.downgrade(alembic_config(), "a7c2e9d4b158")
    assert "content_pdf" not in {c["name"] for c in inspect(api_engine).get_columns("reports")}
    assert "snapshot" not in {c["name"] for c in inspect(api_engine).get_columns("reports")}
    command.upgrade(alembic_config(), "head")
    assert {"snapshot", "content_markdown", "content_html", "sources_sha256"} <= {
        c["name"] for c in inspect(api_engine).get_columns("reports")}


@pytest.mark.asyncio
async def test_stored_version_cannot_be_updated_in_the_database(client, factory):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    case = await make_case(client, owner)
    created = await client.post(f"{V1}/cases/{case['id']}/reports", json={}, headers=owner)
    assert created.status_code == 201, created.text
    with pytest.raises(DBAPIError, match="immutable"):
        with factory.begin() as s:
            s.execute(text("UPDATE reports SET content_markdown = 'tampered' WHERE case_id = :c"), {"c": case["id"]})
    with pytest.raises(DBAPIError, match="immutable"):
        with factory.begin() as s:
            s.execute(text("UPDATE reports SET snapshot = '{}'::jsonb WHERE case_id = :c"), {"c": case["id"]})
    with pytest.raises(DBAPIError, match="immutable"):
        with factory.begin() as s:
            s.execute(text("UPDATE reports SET content_pdf = '\\x00'::bytea WHERE case_id = :c"), {"c": case["id"]})


@pytest.mark.asyncio
async def test_report_stored_before_pdf_existed_answers_404_for_pdf_only(client, factory, api_engine):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    case = await make_case(client, owner)
    cid = case["id"]
    assert (await client.post(f"{V1}/cases/{cid}/reports", json={}, headers=owner)).status_code == 201
    with api_engine.begin() as conn:  # emulate a row stored by the previous migration
        conn.execute(text("ALTER TABLE reports DISABLE TRIGGER trg_reports_immutable"))
        conn.execute(text("UPDATE reports SET content_pdf = NULL, pdf_sha256 = NULL"))
        conn.execute(text("ALTER TABLE reports ENABLE TRIGGER trg_reports_immutable"))
    meta = (await client.get(f"{V1}/cases/{cid}/reports/1", headers=owner)).json()
    assert "pdf" not in meta["formats"] and "pdf" not in meta["downloads"] and meta["pdf_sha256"] is None
    assert (await download(client, owner, cid, 1, "pdf")).status_code == 404
    assert (await download(client, owner, cid, 1, "markdown")).status_code == 200
    verify = (await client.get(f"{V1}/cases/{cid}/reports/1/verify", headers=owner)).json()
    assert verify["valid"] is True and "pdf_sha256" not in verify["checks"]


# ── the complete report, with real NASA, reviewed evidence and collaboration ──

@pytest.mark.asyncio
async def test_complete_report_has_traceable_content_and_no_private_data(client, nasa, factory):
    nasa["use"](Upstream(power_payload()))
    owner = await account(client, "owner@example.test", "Synthetic owner")
    reviewer = await account(client, "reviewer@example.test", "Synthetic reviewer")
    case = await make_case(client, owner)
    cid = case["id"]
    await add_member(client, owner, cid, "reviewer@example.test", "REVIEWER")
    assert (await ingest(client, owner, cid)).status_code == 201
    ids = seed_evidence(factory, cid, await uid(client, owner), await uid(client, reviewer))
    with factory() as s:
        manifest = s.scalar(select(SourceManifest))
        checksum, content_checksum, manifest_id = manifest.checksum_sha256, manifest.content_sha256, str(manifest.id)

    created = await client.post(f"{V1}/cases/{cid}/reports", json={"rotation": {"profile": rotation_profile()}},
                                headers=owner)
    assert created.status_code == 201, created.text
    meta = created.json()
    assert meta["version"] == 1 and meta["status"] == "PRELIMINARY" and meta["changes"]["initial"] is True
    assert meta["source_manifest_ids"] == [manifest_id] and len(meta["sources_sha256"]) == 64
    assert meta["generated_by"]["display_name"] == "Synthetic owner"

    md = (await download(client, owner, cid, 1, "markdown"))
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert md.headers["x-report-sha256"] == meta["checksum_sha256"]
    assert 'filename="cropstory-case-report-v1.md"' in md.headers["content-disposition"]
    md = md.text
    # authentic NASA results and traceable IDs
    assert checksum in md and content_checksum in md and manifest_id in md and "POWER Daily API v2.10.3" in md
    assert "Jun 2022" in md and "-46.5" in md and "LARGE_DEPARTURE" in md
    assert "https://power.larc.nasa.gov" in md and "latitude=" not in md.lower()
    # DOIs, claim IDs, review classes
    assert "10.5555/synthetic.0001" in md and ids["accepted"][:8] in md and ids["pending"][:8] in md
    assert "LITERATURE_REVIEWED" in md and "LITERATURE_METADATA" in md
    assert ids["hypothesis"] in md and ids["conclusion"] in md and "Soil moisture records" in md
    assert "with pipe" in md and "Synthetic reviewed claim / with pipe" in md   # pipes cannot break tables
    assert "&lt;b&gt;" in md and "<b>" not in md                               # markup neutralised
    # three rotation alternatives plus the current one, from the real deterministic engine
    for kind in ("CURRENT", "MINIMAL_CHANGE", "FAMILY_DIVERSIFICATION", "CALENDAR_COVER"):
        assert kind in md
    assert "Input profile hash" in md and "Possible benefits (unverified)" in md
    # collaboration summary without people
    assert "OWNER: 1" in md and "REVIEWER: 1" in md and "Active comments:** 1" in md
    assert "Parcel 1" in md and "Synthetic region" in md and "Synthetic parcel A" not in md
    assert_private(md)

    html_doc = await download(client, owner, cid, 1, "html")
    assert html_doc.headers["content-type"].startswith("text/html")
    assert "sandbox" in html_doc.headers["content-security-policy"]
    page = html_doc.text
    assert 'href="https://doi.org/10.5555/synthetic.0001"' in page and "<script" not in page.lower()
    assert "&lt;b&gt;x&lt;/b&gt;" in page and "<b>x</b>" not in page
    assert_private(page)

    snap = await download(client, owner, cid, 1, "json")
    assert snap.headers["content-type"] == "application/json"
    assert_private(snap.text)
    query = snap.json()["sources"][0]["query"]
    assert query["start"] == "20100101" and query["end"] == "20221231"
    assert not {"latitude", "longitude"} & set(query)

    pdf = await download(client, owner, cid, 1, "pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-") and pdf.content.rstrip().endswith(b"%%EOF")
    assert pdf.headers["x-report-sha256"] == meta["pdf_sha256"] == hashlib.sha256(pdf.content).hexdigest()
    assert 'filename="cropstory-case-report-v1.pdf"' in pdf.headers["content-disposition"]
    assert "pdf" in meta["formats"] and meta["downloads"]["pdf"].endswith("download?format=pdf")
    assert str(EXACT_LAT).encode() not in pdf.content and NOTE.encode() not in pdf.content

    verify = (await client.get(f"{V1}/cases/{cid}/reports/1/verify", headers=owner)).json()
    assert verify["valid"] is True and all(verify["checks"].values()) and verify["checks"]["pdf_sha256"] is True
    history = (await client.get(f"{V1}/cases/{cid}/history", headers=owner)).json()
    generated = [h for h in history if h["action"] == "REPORT_GENERATED"]
    assert len(generated) == 1 and generated[0]["changes"]["report_version"] == 1


@pytest.mark.asyncio
async def test_regenerated_report_names_version_date_and_changes(client, nasa, factory):
    nasa["use"](Upstream(power_payload()))
    owner = await account(client, "owner@example.test", "Synthetic owner")
    reviewer = await account(client, "reviewer@example.test", "Synthetic reviewer")
    case = await make_case(client, owner)
    cid = case["id"]
    await add_member(client, owner, cid, "reviewer@example.test", "REVIEWER")
    ids = seed_evidence(factory, cid, await uid(client, owner), await uid(client, reviewer))
    first = (await client.post(f"{V1}/cases/{cid}/reports", json={}, headers=owner)).json()
    first_md = (await download(client, owner, cid, 1, "markdown")).text

    again = (await client.post(f"{V1}/cases/{cid}/reports", json={}, headers=owner)).json()
    assert again["version"] == 2 and again["changes"]["initial"] is False and again["changes"]["items"] == []
    assert again["generated_at"] > first["generated_at"] and again["checksum_sha256"] != first["checksum_sha256"]

    reviewer_id = await uid(client, reviewer)
    with factory.begin() as s:
        s.add(Hypothesis(case_id=cid, title="Synthetic pest pressure", statement="Pest pressure.", status="OPEN",
                         limitations=["Synthetic"], supporting_evidence_ids=[], contradicting_evidence_ids=[],
                         missing_evidence=[]))
        claim = s.get(EvidenceClaim, ids["pending"])
        claim.review_status, claim.version, claim.reviewed_by, claim.reviewed_at = "REJECTED", 2, reviewer_id, T0
    nasa["use"](Upstream(power_payload(june_rain=0.5)))
    assert (await ingest(client, owner, cid)).status_code == 201

    third = (await client.post(f"{V1}/cases/{cid}/reports", json={}, headers=owner)).json()
    changes = {(i["section"], i["change"]): i["label"] for i in third["changes"]["items"]}
    assert third["version"] == 3 and third["changes"]["previous_version"] == 2
    assert changes[("hypotheses", "ADDED")] == "Synthetic pest pressure"
    assert ("claims", "CHANGED") in changes and ("sources", "ADDED") in changes
    md3 = (await download(client, owner, cid, 3, "markdown")).text
    assert "Compared with version 2" in md3 and "Synthetic pest pressure" in md3 and "CHANGED" in md3
    # earlier versions are untouched, byte for byte, and the list is newest first
    assert (await download(client, owner, cid, 1, "markdown")).text == first_md
    listing = (await client.get(f"{V1}/cases/{cid}/reports", headers=owner)).json()["items"]
    assert [r["version"] for r in listing] == [3, 2, 1]
    for v in (1, 2, 3):
        assert (await client.get(f"{V1}/cases/{cid}/reports/{v}/verify", headers=owner)).json()["valid"] is True


# ── permissions and tamper detection ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_roles_and_tamper_detection(client, factory, api_engine):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    viewer = await account(client, "viewer@example.test", "Synthetic viewer")
    stranger = await account(client, "stranger@example.test", "Synthetic stranger")
    case = await make_case(client, owner)
    cid = case["id"]
    await add_member(client, owner, cid, "viewer@example.test", "VIEWER")
    assert (await client.post(f"{V1}/cases/{cid}/reports", json={}, headers=viewer)).status_code == 403
    assert (await client.post(f"{V1}/cases/{cid}/reports", json={}, headers=stranger)).status_code == 404
    assert (await client.post(f"{V1}/cases/{cid}/reports", json={"surprise": 1}, headers=owner)).status_code == 422
    assert (await client.post(f"{V1}/cases/{cid}/reports", json={}, headers={})).status_code == 401
    assert (await client.post(f"{V1}/cases/{cid}/reports", json={}, headers=owner)).status_code == 201

    # a viewer reads the same private-data-free document; a stranger learns nothing
    seen = await download(client, viewer, cid, 1, "markdown")
    assert seen.status_code == 200 and "Synthetic parcel A" not in seen.text
    assert_private(seen.text)
    for path in ("", "/1", "/1/download", "/1/verify"):
        assert (await client.get(f"{V1}/cases/{cid}/reports{path}", headers=stranger)).status_code == 404
    assert (await client.get(f"{V1}/cases/{cid}/reports/9", headers=owner)).status_code == 404
    assert (await client.get(f"{V1}/cases/{cid}/reports/1/download", params={"format": "docx"}, headers=owner)
            ).status_code == 422

    # bypassing the trigger (superuser) changes the text: verify must say so
    with api_engine.begin() as conn:
        conn.execute(text("ALTER TABLE reports DISABLE TRIGGER trg_reports_immutable"))
        conn.execute(text("UPDATE reports SET content_markdown = content_markdown || 'tampered'"))
        conn.execute(text("ALTER TABLE reports ENABLE TRIGGER trg_reports_immutable"))
    verify = (await client.get(f"{V1}/cases/{cid}/reports/1/verify", headers=owner)).json()
    assert verify["valid"] is False and verify["checks"]["markdown_sha256"] is False
    assert verify["checks"]["snapshot_sha256"] is True and verify["checks"]["pdf_sha256"] is True
    with api_engine.begin() as conn:
        conn.execute(text("ALTER TABLE reports DISABLE TRIGGER trg_reports_immutable"))
        conn.execute(text("UPDATE reports SET content_pdf = '\\x255044462d'::bytea"))
        conn.execute(text("ALTER TABLE reports ENABLE TRIGGER trg_reports_immutable"))
    assert (await client.get(f"{V1}/cases/{cid}/reports/1/verify", headers=owner)).json()["checks"]["pdf_sha256"] is False


@pytest.mark.asyncio
async def test_coordinate_guard_removes_stored_coordinates_found_in_free_text(client, factory):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    case = await make_case(client, owner)
    cid = case["id"]
    with factory.begin() as s:
        s.add(Hypothesis(case_id=cid, title=f"Check near {EXACT_LAT}", statement=f"Observed at {EXACT_LAT}, {EXACT_LON}.",
                         status="OPEN", limitations=["x"], supporting_evidence_ids=[], contradicting_evidence_ids=[],
                         missing_evidence=[]))
    assert (await client.post(f"{V1}/cases/{cid}/reports", json={}, headers=owner)).status_code == 201
    md = (await download(client, owner, cid, 1, "markdown")).text
    assert str(EXACT_LAT) not in md and str(EXACT_LON) not in md and "[location withheld]" in md
    assert "Coordinate strings removed by the final guard: 3" in md
