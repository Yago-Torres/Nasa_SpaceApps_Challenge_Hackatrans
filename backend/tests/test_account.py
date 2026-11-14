"""ABB-28 API integration tests against a disposable PostgreSQL database: self-service account
data export/deletion, the lockout on the deletion confirmation, and that deleting an account
never corrupts another member's case or its append-only evidence trail (the RESTRICT foreign
keys documented in ``agroblackbox.api.account``).

All people, parcels and coordinates are synthetic. Run with TEST_DATABASE_URL set.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text, update

from agroblackbox.api.deps import get_session_factory
from agroblackbox.app import app
from agroblackbox.db.models import AuthSession, CasePermission, EvidenceClaim, Paper, User, utcnow
from agroblackbox.db.session import create_database_engine, session_factory
from agroblackbox.retention import purge_stale_sessions

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration")

PASSWORD = "synthetic-correct-horse-42"
EXACT_LAT, EXACT_LON = 41.6543, -0.8765
V1 = "/api/v1"


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


async def account(client, email: str, name: str = "Synthetic user") -> dict[str, str]:
    registered = await client.post(f"{V1}/auth/register",
                                   json={"email": email, "password": PASSWORD, "display_name": name})
    assert registered.status_code == 201, registered.text
    login = await client.post(f"{V1}/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def parcel(**overrides):
    return {"label": "Synthetic parcel A", "privacy_tier": "APPROXIMATE", "latitude": EXACT_LAT,
            "longitude": EXACT_LON, "region_label": "Synthetic region", "rounding_deg": 0.5,
            "limitations": ["Synthetic test parcel; not a real farm"], **overrides}


def case_body(**overrides):
    return {"title": "SYNTHETIC case - not a real incident", "incident_start": "2022-05-01",
            "incident_end": "2022-08-31", "crop_history": ["wheat"],
            "incident_notes": "Synthetic farmer report for tests.", "fields": [parcel()], **overrides}


async def new_case(client, headers, **overrides) -> dict:
    response = await client.post(f"{V1}/cases", json=case_body(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def share(client, owner, case_id, email, role):
    response = await client.post(f"{V1}/cases/{case_id}/permissions", json={"email": email, "role": role},
                                 headers=owner)
    assert response.status_code in (200, 201), response.text
    return response


def assert_no_exact_coordinates(payload_text: str):
    assert str(EXACT_LAT) not in payload_text and str(EXACT_LON) not in payload_text


# ── export ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_requires_auth(client):
    assert (await client.get(f"{V1}/account/export")).status_code == 401


@pytest.mark.asyncio
async def test_export_contains_profile_cases_and_sessions_but_no_secret(client, factory):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    case = await new_case(client, owner)

    response = await client.get(f"{V1}/account/export", headers=owner)
    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["email"] == "owner@example.test"
    assert "password" not in response.text and "password_hash" not in response.text
    assert [c["id"] for c in body["cases"]] == [case["id"]]
    assert body["cases"][0]["my_role"] == "OWNER"
    assert len(body["sessions"]) == 1 and body["sessions"][0]["current"] is True
    assert body["sessions"][0]["revoked"] is False
    # Never the raw bearer token nor its SHA-256 digest.
    token = owner["Authorization"].split(" ", 1)[1]
    assert token not in response.text
    with factory() as session:
        digest = session.scalars(select(AuthSession.token_sha256)).one()
    assert digest not in response.text


@pytest.mark.asyncio
async def test_export_redacts_coordinates_for_a_reviewer_and_excludes_other_members_private_cases(client, factory):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    reviewer = await account(client, "reviewer@example.test", "Synthetic reviewer")
    case = await new_case(client, owner)
    await share(client, owner, case["id"], "reviewer@example.test", "REVIEWER")
    # Owner's own second, unshared case must never appear in the reviewer's export.
    await new_case(client, owner, title="SYNTHETIC unshared owner case")

    response = await client.get(f"{V1}/account/export", headers=reviewer)
    assert response.status_code == 200
    body = response.json()
    assert len(body["cases"]) == 1 and body["cases"][0]["id"] == case["id"]
    assert body["cases"][0]["my_role"] == "REVIEWER"
    assert_no_exact_coordinates(response.text)


# ── deletion: confirmation and lockout ──────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_requires_auth(client):
    assert (await client.post(f"{V1}/account/delete", json={"password": PASSWORD})).status_code == 401


@pytest.mark.asyncio
async def test_delete_rejects_wrong_password_without_deleting_anything(client, factory):
    owner = await account(client, "owner@example.test")
    case = await new_case(client, owner)

    wrong = await client.post(f"{V1}/account/delete", json={"password": "wrong-" + PASSWORD}, headers=owner)
    assert wrong.status_code == 401 and PASSWORD not in wrong.text

    still_there = await client.get(f"{V1}/cases/{case['id']}", headers=owner)
    assert still_there.status_code == 200


@pytest.mark.asyncio
async def test_delete_confirmation_locks_out_after_five_failures(client, factory):
    owner = await account(client, "owner@example.test")
    for _ in range(5):
        failed = await client.post(f"{V1}/account/delete", json={"password": "guess-guess-guess"}, headers=owner)
        assert failed.status_code == 401
    locked = await client.post(f"{V1}/account/delete", json={"password": PASSWORD}, headers=owner)
    assert locked.status_code == 429 and 0 < int(locked.headers["retry-after"]) <= 900

    with factory.begin() as session:  # simulate the 15-minute lock expiring, like the login test
        session.execute(update(User).values(locked_until=utcnow() - timedelta(seconds=1)))
    unlocked = await client.post(f"{V1}/account/delete", json={"password": PASSWORD}, headers=owner)
    assert unlocked.status_code == 200


# ── deletion: effect ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_erases_owned_cases_revokes_sessions_and_disables_login(client, factory):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    editor = await account(client, "editor@example.test", "Synthetic editor")
    owned = await new_case(client, owner)
    await share(client, owner, owned["id"], "editor@example.test", "EDITOR")

    result = await client.post(f"{V1}/account/delete", json={"password": PASSWORD}, headers=owner)
    assert result.status_code == 200, result.text
    receipt = result.json()
    assert receipt["cases_deleted"] == 1
    assert receipt["sessions_revoked"] == 1
    assert receipt["anonymized"] is True

    # The bearer token used for this very request is revoked immediately afterwards.
    assert (await client.get(f"{V1}/auth/me", headers=owner)).status_code == 401
    # The case is gone for every member, including the editor who was never deleted.
    assert (await client.get(f"{V1}/cases/{owned['id']}", headers=editor)).status_code == 404

    # Login is disabled; re-registering the same e-mail works again (the old row was anonymised,
    # not merely marked -- the unique index on email was freed).
    relogin = await client.post(f"{V1}/auth/login", json={"email": "owner@example.test", "password": PASSWORD})
    assert relogin.status_code == 401
    reregister = await client.post(f"{V1}/auth/register",
                                   json={"email": "owner@example.test", "password": PASSWORD, "display_name": "New"})
    assert reregister.status_code == 201

    with factory() as session:
        rows = session.scalars(select(User)).all()
        deleted_rows = [u for u in rows if u.display_name == "Deleted account"]
        assert len(deleted_rows) == 1
        assert deleted_rows[0].password_hash is None
        assert deleted_rows[0].email.endswith("@deleted.invalid")


@pytest.mark.asyncio
async def test_delete_only_revokes_membership_on_cases_owned_by_others(client, factory):
    owner = await account(client, "owner@example.test")
    viewer = await account(client, "viewer@example.test", "Synthetic viewer")
    other_owned = await new_case(client, owner)
    await share(client, owner, other_owned["id"], "viewer@example.test", "VIEWER")

    result = await client.post(f"{V1}/account/delete", json={"password": PASSWORD}, headers=viewer)
    assert result.status_code == 200, result.text
    receipt = result.json()
    assert receipt["cases_deleted"] == 0
    assert receipt["memberships_revoked"] == 1

    # The owner's case is untouched; the viewer no longer appears in its member list.
    still_there = await client.get(f"{V1}/cases/{other_owned['id']}", headers=owner)
    assert still_there.status_code == 200
    members = await client.get(f"{V1}/cases/{other_owned['id']}/permissions", headers=owner)
    assert {m["role"] for m in members.json()} == {"OWNER"}


@pytest.mark.asyncio
async def test_delete_never_breaks_a_restrict_foreign_key_from_a_shared_case_review_trail(client, factory):
    """A reviewer who authored an evidence claim on someone else's case is referenced by
    ``evidence_claims.created_by`` with ``ON DELETE RESTRICT`` (see db.models and ADR-0005). A
    hard delete of the user row would raise an IntegrityError there; the anonymising delete must
    not touch that row at all and must still succeed."""
    owner = await account(client, "owner@example.test")
    reviewer = await account(client, "reviewer@example.test")
    case = await new_case(client, owner)
    await share(client, owner, case["id"], "reviewer@example.test", "REVIEWER")

    with factory.begin() as session:
        reviewer_user = session.scalars(select(User).where(User.email == "reviewer@example.test")).one()
        paper = Paper(title="Synthetic paper", doi_status="NO_DOI", bibliographic_metadata={}, limitations=[])
        session.add(paper)
        session.flush()
        claim = EvidenceClaim(
            case_id=case["id"], paper_id=paper.id, claim_text="Synthetic claim text.",
            study_context="Synthetic study context.", limitations=[], created_by=reviewer_user.id,
        )
        session.add(claim)
        session.flush()
        claim_id, reviewer_id = claim.id, reviewer_user.id

    result = await client.post(f"{V1}/account/delete", json={"password": PASSWORD}, headers=reviewer)
    assert result.status_code == 200, result.text

    with factory() as session:
        still_there = session.get(EvidenceClaim, claim_id)
        assert still_there is not None and still_there.created_by == reviewer_id
        anonymised_reviewer = session.get(User, reviewer_id)
        assert anonymised_reviewer is not None and anonymised_reviewer.password_hash is None

    # The case itself, owned by someone else, is completely unaffected.
    assert (await client.get(f"{V1}/cases/{case['id']}", headers=owner)).status_code == 200


def test_openapi_documents_account_routes():
    schema = app.openapi()
    for path in (f"{V1}/account/export", f"{V1}/account/delete"):
        assert path in schema["paths"]
    assert "AccountDeletionReceipt" in schema["components"]["schemas"]


# ── retention: session purge ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_purge_stale_sessions_only_removes_sessions_past_the_window(client, factory):
    owner = await account(client, "owner@example.test")
    assert (await client.get(f"{V1}/auth/me", headers=owner)).status_code == 200

    now = utcnow()
    with factory.begin() as session:
        rows = session.scalars(select(AuthSession)).all()
        assert len(rows) == 1
        # Simulate an old, already-expired session alongside the fresh one.
        stale = AuthSession(user_id=rows[0].user_id, token_sha256="0" * 64,
                            created_at=now - timedelta(days=40), expires_at=now - timedelta(days=39))
        session.add(stale)

    with factory() as session:
        deleted = purge_stale_sessions(session, now=now, window=timedelta(days=30))
        remaining = session.scalars(select(AuthSession)).all()
    assert deleted == 1
    assert len(remaining) == 1 and remaining[0].token_sha256 != "0" * 64
