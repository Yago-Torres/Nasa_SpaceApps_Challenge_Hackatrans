"""ABB-05/ABB-06 API integration tests against a disposable PostgreSQL database.

All people, parcels and coordinates are synthetic. Run with TEST_DATABASE_URL set.
"""
from __future__ import annotations

import hashlib
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
from agroblackbox.db.models import AuthSession, User, utcnow
from agroblackbox.db.session import create_database_engine, session_factory

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


# ── helpers ──────────────────────────────────────────────────────────────────

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
            "incident_end": "2022-08-31", "crop_history": ["wheat", "barley"],
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


# ── migration ────────────────────────────────────────────────────────────────

def test_auth_migration_downgrades_and_upgrades_cleanly(api_engine):
    command.downgrade(alembic_config(), "5dac25ea03d7")
    inspector = inspect(api_engine)
    assert not {"sessions", "case_history"} & set(inspector.get_table_names())
    assert "password_hash" not in {c["name"] for c in inspector.get_columns("users")}
    assert "status" not in {c["name"] for c in inspector.get_columns("cases")}
    command.upgrade(alembic_config(), "head")
    inspector = inspect(api_engine)
    assert {"sessions", "case_history"} <= set(inspector.get_table_names())
    assert "rounding_deg" in {c["name"] for c in inspector.get_columns("fields")}


# ── authentication ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_login_me_logout_and_revoked_token(client, factory):
    created = await client.post(f"{V1}/auth/register", json={
        "email": " Owner@Example.TEST ", "password": PASSWORD, "display_name": "Synthetic owner"})
    assert created.status_code == 201
    assert created.json()["email"] == "owner@example.test"
    assert "password" not in created.text and PASSWORD not in created.text

    login = await client.post(f"{V1}/auth/login", json={"email": "OWNER@example.test", "password": PASSWORD})
    assert login.status_code == 200
    body = login.json()
    token = body["access_token"]
    assert body["token_type"] == "bearer" and body["user"]["display_name"] == "Synthetic owner"
    headers = {"Authorization": f"Bearer {token}"}

    with factory() as session:
        stored = session.scalars(select(AuthSession)).one()
        user = session.scalars(select(User)).one()
        assert stored.token_sha256 == hashlib.sha256(token.encode()).hexdigest()
        assert token not in stored.token_sha256
        assert user.password_hash.startswith("scrypt$") and PASSWORD not in user.password_hash
        assert stored.expires_at - stored.created_at == timedelta(hours=12)

    assert (await client.get(f"{V1}/auth/me", headers=headers)).json()["email"] == "owner@example.test"
    assert (await client.post(f"{V1}/auth/logout", headers=headers)).status_code == 204
    revoked = await client.get(f"{V1}/auth/me", headers=headers)
    assert revoked.status_code == 401 and revoked.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_register_validation_and_duplicates(client):
    short = await client.post(f"{V1}/auth/register",
                              json={"email": "a@example.test", "password": "tiny-secret", "display_name": "A"})
    assert short.status_code == 422 and "tiny-secret" not in short.text
    await account(client, "dup@example.test")
    again = await client.post(f"{V1}/auth/register",
                              json={"email": "DUP@example.test", "password": PASSWORD, "display_name": "B"})
    assert again.status_code == 409
    extra = await client.post(f"{V1}/auth/register", json={
        "email": "x@example.test", "password": PASSWORD, "display_name": "X", "role": "ADMIN"})
    assert extra.status_code == 422


@pytest.mark.asyncio
async def test_wrong_password_and_unknown_email_are_indistinguishable(client):
    await account(client, "owner@example.test")
    wrong = await client.post(f"{V1}/auth/login", json={"email": "owner@example.test", "password": "wrong-" + PASSWORD})
    unknown = await client.post(f"{V1}/auth/login", json={"email": "nobody@example.test", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password."}


@pytest.mark.asyncio
async def test_brute_force_lockout_blocks_even_the_correct_password(client, factory):
    await account(client, "owner@example.test")
    for _ in range(5):
        failed = await client.post(f"{V1}/auth/login", json={"email": "owner@example.test", "password": "guess-guess-guess"})
        assert failed.status_code == 401
    locked = await client.post(f"{V1}/auth/login", json={"email": "owner@example.test", "password": PASSWORD})
    assert locked.status_code == 429 and 0 < int(locked.headers["retry-after"]) <= 900
    assert "access_token" not in locked.text

    with factory.begin() as session:  # simulate the 15-minute lock expiring
        session.execute(update(User).values(locked_until=utcnow() - timedelta(seconds=1)))
    unlocked = await client.post(f"{V1}/auth/login", json={"email": "owner@example.test", "password": PASSWORD})
    assert unlocked.status_code == 200
    with factory() as session:
        user = session.scalars(select(User)).one()
        assert user.failed_login_count == 0 and user.locked_until is None


@pytest.mark.asyncio
async def test_expired_token_is_rejected(client, factory):
    headers = await account(client, "owner@example.test")
    assert (await client.get(f"{V1}/auth/me", headers=headers)).status_code == 200
    with factory.begin() as session:
        session.execute(update(AuthSession).values(created_at=utcnow() - timedelta(days=2),
                                                   expires_at=utcnow() - timedelta(seconds=1)))
    expired = await client.get(f"{V1}/auth/me", headers=headers)
    assert expired.status_code == 401
    assert (await client.get(f"{V1}/cases", headers=headers)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-real-token"},
                                     {"Authorization": "Basic b3duZXI6cGFzcw=="}, {"Authorization": "Bearer "}])
async def test_missing_or_malformed_credentials_get_401(client, headers):
    for method, path in (("GET", "/cases"), ("POST", "/cases"), ("GET", "/auth/me"), ("POST", "/auth/logout")):
        response = await client.request(method, V1 + path, headers=headers, json=case_body() if method == "POST" else None)
        assert response.status_code == 401, (method, path, response.status_code)


# ── case CRUD, versions and history ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_owner_creates_updates_and_history_keeps_previous_values(client, api_engine):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    case = await new_case(client, owner)
    assert (case["version"], case["status"], case["my_role"], case["visibility"]) == (1, "DRAFT", "OWNER", "PRIVATE")
    field = case["fields"][0]
    assert (field["latitude"], field["longitude"], field["location_precision"]) == (EXACT_LAT, EXACT_LON, "EXACT")

    updated = await client.patch(f"{V1}/cases/{case['id']}", headers=owner, json={
        "version": 1, "title": "SYNTHETIC case - renamed", "incident_notes": None})
    assert updated.status_code == 200
    assert (updated.json()["version"], updated.json()["incident_notes"]) == (2, None)

    history = (await client.get(f"{V1}/cases/{case['id']}/history", headers=owner)).json()
    assert [entry["action"] for entry in history] == ["CREATED", "UPDATED"]
    change = history[1]
    assert change["version"] == 2 and change["actor"]["display_name"] == "Synthetic owner"
    assert change["changes"]["title"] == {"before": "SYNTHETIC case - not a real incident",
                                          "after": "SYNTHETIC case - renamed"}
    assert change["changes"]["incident_notes"]["before"] == "Synthetic farmer report for tests."
    assert history[0]["changes"]["fields"][0]["latitude"] == EXACT_LAT  # owner sees full history

    # Restart: a brand-new engine and session factory still return the persisted case.
    restarted_engine = create_database_engine(TEST_URL)
    restarted = session_factory(restarted_engine)
    app.dependency_overrides[get_session_factory] = lambda: restarted
    try:
        reopened = await client.get(f"{V1}/cases/{case['id']}", headers=owner)
        assert reopened.status_code == 200 and reopened.json()["title"] == "SYNTHETIC case - renamed"
        listed = (await client.get(f"{V1}/cases", headers=owner)).json()["items"]
        assert [item["id"] for item in listed] == [case["id"]]
    finally:
        restarted_engine.dispose()


@pytest.mark.asyncio
async def test_stale_version_is_rejected_with_409(client):
    owner = await account(client, "owner@example.test")
    case = await new_case(client, owner)
    first = await client.patch(f"{V1}/cases/{case['id']}", headers=owner, json={"version": 1, "title": "First"})
    stale = await client.patch(f"{V1}/cases/{case['id']}", headers=owner, json={"version": 1, "title": "Stale"})
    assert first.status_code == 200 and stale.status_code == 409
    assert "current version 2" in stale.json()["detail"]
    assert (await client.get(f"{V1}/cases/{case['id']}", headers=owner)).json()["title"] == "First"


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [
    {"fields": []},
    {"fields": [parcel(latitude=91)]},
    {"fields": [parcel(privacy_tier="WITHHELD")]},
    {"fields": [parcel(privacy_tier="EXACT")]},
    {"fields": [parcel(rounding_deg=0.25)]},
    {"fields": [parcel(longitude=None)]},
    {"incident_end": "2022-01-01"},
    {"incident_start": "not-a-date"},
    {"visibility": "PUBLIC_ROUNDED"},
])
async def test_invalid_case_inputs_are_rejected(client, overrides):
    owner = await account(client, "owner@example.test")
    response = await client.post(f"{V1}/cases", json=case_body(**overrides), headers=owner)
    assert response.status_code == 422
    assert (await client.get(f"{V1}/cases", headers=owner)).json()["items"] == []


@pytest.mark.asyncio
async def test_update_rejects_invalid_dates_and_nulls(client):
    owner = await account(client, "owner@example.test")
    case = await new_case(client, owner)
    bad_dates = await client.patch(f"{V1}/cases/{case['id']}", headers=owner,
                                   json={"version": 1, "incident_start": "2022-09-30"})
    null_title = await client.patch(f"{V1}/cases/{case['id']}", headers=owner, json={"version": 1, "title": None})
    assert bad_dates.status_code == 422 and null_title.status_code == 422


# ── access control and privacy ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_other_user_cannot_list_get_update_or_delete(client):
    owner = await account(client, "owner@example.test")
    stranger = await account(client, "stranger@example.test")
    case = await new_case(client, owner)
    cid = case["id"]
    assert (await client.get(f"{V1}/cases", headers=stranger)).json()["items"] == []
    attempts = [
        await client.get(f"{V1}/cases/{cid}", headers=stranger),
        await client.patch(f"{V1}/cases/{cid}", headers=stranger, json={"version": 1, "title": "Hijack"}),
        await client.delete(f"{V1}/cases/{cid}?version=1", headers=stranger),
        await client.get(f"{V1}/cases/{cid}/history", headers=stranger),
        await client.get(f"{V1}/cases/{cid}/permissions", headers=stranger),
        await client.post(f"{V1}/cases/{cid}/permissions", headers=stranger,
                          json={"email": "stranger@example.test", "role": "EDITOR"}),
        await client.post(f"{V1}/cases/{cid}/fields", headers=stranger, json={"version": 1, "field": parcel()}),
        await client.post(f"{V1}/cases/{cid}/status", headers=stranger, json={"version": 1, "status": "INVESTIGATING"}),
    ]
    assert [r.status_code for r in attempts] == [404] * len(attempts)
    missing = await client.get(f"{V1}/cases/00000000-0000-4000-8000-000000000000", headers=stranger)
    assert attempts[0].json() == missing.json()  # same answer as a nonexistent case
    for response in attempts:
        assert_no_exact_coordinates(response.text)
    assert (await client.get(f"{V1}/cases/{cid}", headers=owner)).json()["title"] == case["title"]


@pytest.mark.asyncio
async def test_viewer_is_read_only_and_never_receives_precise_coordinates(client):
    owner = await account(client, "owner@example.test")
    viewer = await account(client, "viewer@example.test")
    case = await new_case(client, owner)
    cid = case["id"]
    await share(client, owner, cid, "viewer@example.test", "VIEWER")

    seen = await client.get(f"{V1}/cases/{cid}", headers=viewer)
    listed = await client.get(f"{V1}/cases", headers=viewer)
    history = await client.get(f"{V1}/cases/{cid}/history", headers=viewer)
    members = await client.get(f"{V1}/cases/{cid}/permissions", headers=viewer)
    for response in (seen, listed, history, members):
        assert response.status_code == 200
        assert_no_exact_coordinates(response.text)
    field = seen.json()["fields"][0]
    assert (field["latitude"], field["longitude"], field["location_precision"]) == (41.75, -0.75, "APPROXIMATE")
    assert seen.json()["my_role"] == "VIEWER" and seen.json()["visibility"] == "SHARED"
    assert history.json()[0]["changes"]["fields"][0]["latitude"] == "REDACTED"
    assert all(member["email"] is None for member in members.json())

    denied = [
        await client.patch(f"{V1}/cases/{cid}", headers=viewer, json={"version": 1, "title": "Viewer edit"}),
        await client.post(f"{V1}/cases/{cid}/fields", headers=viewer, json={"version": 1, "field": parcel()}),
        await client.patch(f"{V1}/cases/{cid}/fields/{field['id']}", headers=viewer,
                           json={"version": 1, "privacy_tier": "REGION_ONLY"}),
        await client.post(f"{V1}/cases/{cid}/status", headers=viewer, json={"version": 1, "status": "INVESTIGATING"}),
        await client.post(f"{V1}/cases/{cid}/archive", headers=viewer, json={"version": 1, "archived": True}),
        await client.delete(f"{V1}/cases/{cid}?version=1", headers=viewer),
    ]
    assert [r.status_code for r in denied] == [403] * len(denied)
    assert (await client.get(f"{V1}/cases/{cid}", headers=owner)).json()["version"] == 1


@pytest.mark.asyncio
async def test_privacy_tiers_and_revocable_precise_consent(client):
    owner = await account(client, "owner@example.test")
    reviewer = await account(client, "reviewer@example.test")
    case = await new_case(client, owner, fields=[
        parcel(label="A approximate consented", precise_location_consent=True),
        parcel(label="B region only", privacy_tier="REGION_ONLY", rounding_deg=None),
        parcel(label="C withheld", privacy_tier="WITHHELD", latitude=None, longitude=None, rounding_deg=None),
    ])
    cid = case["id"]
    await share(client, owner, cid, "reviewer@example.test", "REVIEWER")
    fields = {f["label"][0]: f for f in (await client.get(f"{V1}/cases/{cid}", headers=reviewer)).json()["fields"]}
    assert (fields["A"]["latitude"], fields["A"]["location_precision"]) == (EXACT_LAT, "EXACT")
    assert (fields["B"]["latitude"], fields["B"]["longitude"], fields["B"]["location_precision"]) == (None, None, "REGION_ONLY")
    assert fields["B"]["region_label"] == "Synthetic region"
    assert (fields["C"]["latitude"], fields["C"]["location_precision"]) == (None, "NONE")

    revoked = await client.patch(f"{V1}/cases/{cid}/fields/{fields['A']['id']}", headers=owner,
                                 json={"version": 1, "precise_location_consent": False})
    assert revoked.status_code == 200 and revoked.json()["version"] == 2
    after = await client.get(f"{V1}/cases/{cid}", headers=reviewer)
    assert_no_exact_coordinates(after.text)
    a = next(f for f in after.json()["fields"] if f["label"].startswith("A"))
    assert (a["latitude"], a["longitude"], a["location_precision"]) == (41.75, -0.75, "APPROXIMATE")
    history = (await client.get(f"{V1}/cases/{cid}/history", headers=reviewer)).json()
    assert history[-1]["changes"]["precise_location_consent"] == {"before": True, "after": False}
    assert_no_exact_coordinates(str(history))

    exact_without_consent = await client.patch(f"{V1}/cases/{cid}/fields/{fields['A']['id']}", headers=owner,
                                               json={"version": 2, "privacy_tier": "EXACT"})
    assert exact_without_consent.status_code == 422


@pytest.mark.asyncio
async def test_editor_sees_exact_location_and_edits_but_cannot_manage_access(client):
    owner = await account(client, "owner@example.test")
    editor = await account(client, "editor@example.test")
    await account(client, "third@example.test")
    case = await new_case(client, owner)
    cid = case["id"]
    await share(client, owner, cid, "editor@example.test", "EDITOR")
    seen = (await client.get(f"{V1}/cases/{cid}", headers=editor)).json()
    assert seen["fields"][0]["latitude"] == EXACT_LAT and seen["my_role"] == "EDITOR"
    edit = await client.patch(f"{V1}/cases/{cid}", headers=editor, json={"version": 1, "crop_history": ["maize"]})
    assert edit.status_code == 200 and edit.json()["crop_history"] == ["maize"]
    grant = await client.post(f"{V1}/cases/{cid}/permissions", headers=editor,
                              json={"email": "third@example.test", "role": "VIEWER"})
    delete = await client.delete(f"{V1}/cases/{cid}?version=2", headers=editor)
    assert grant.status_code == 403 and delete.status_code == 403


@pytest.mark.asyncio
async def test_reviewer_workflow_and_reviewer_cannot_change_permissions_or_content(client):
    owner = await account(client, "owner@example.test")
    reviewer = await account(client, "reviewer@example.test")
    viewer = await account(client, "viewer@example.test")
    case = await new_case(client, owner)
    cid = case["id"]
    await share(client, owner, cid, "reviewer@example.test", "REVIEWER")
    await share(client, owner, cid, "viewer@example.test", "VIEWER")
    members = (await client.get(f"{V1}/cases/{cid}/permissions", headers=owner)).json()
    viewer_id = next(m["user_id"] for m in members if m["role"] == "VIEWER")

    reviewer_denied = [
        await client.post(f"{V1}/cases/{cid}/permissions", headers=reviewer,
                          json={"email": "viewer@example.test", "role": "EDITOR"}),
        await client.delete(f"{V1}/cases/{cid}/permissions/{viewer_id}", headers=reviewer),
        await client.patch(f"{V1}/cases/{cid}", headers=reviewer, json={"version": 1, "title": "Reviewer edit"}),
        await client.post(f"{V1}/cases/{cid}/fields", headers=reviewer, json={"version": 1, "field": parcel()}),
        await client.post(f"{V1}/cases/{cid}/status", headers=reviewer, json={"version": 1, "status": "INVESTIGATING"}),
    ]
    assert [r.status_code for r in reviewer_denied] == [403] * len(reviewer_denied)

    async def move(headers, version, target, note=None):
        return await client.post(f"{V1}/cases/{cid}/status", headers=headers,
                                 json={"version": version, "status": target, "note": note})

    assert (await move(owner, 1, "PUBLISHED")).status_code == 409  # DRAFT -> PUBLISHED not allowed
    assert (await move(owner, 1, "INVESTIGATING")).json()["status"] == "INVESTIGATING"
    assert (await move(owner, 2, "REVIEWED")).status_code == 403  # owner cannot self-review
    assert (await move(viewer, 2, "REVIEWED")).status_code == 403
    reviewed = await move(reviewer, 2, "REVIEWED", "Synthetic review note")
    assert reviewed.status_code == 200 and reviewed.json()["version"] == 3
    locked = await client.patch(f"{V1}/cases/{cid}", headers=owner, json={"version": 3, "title": "Late edit"})
    assert locked.status_code == 409
    assert (await move(reviewer, 3, "PUBLISHED")).status_code == 403
    assert (await move(owner, 3, "PUBLISHED")).json()["status"] == "PUBLISHED"
    assert (await move(owner, 4, "INVESTIGATING")).json()["status"] == "INVESTIGATING"

    history = (await client.get(f"{V1}/cases/{cid}/history", headers=owner)).json()
    statuses = [(h["changes"]["status"]["before"], h["changes"]["status"]["after"])
                for h in history if h["action"] == "STATUS_CHANGED"]
    assert statuses == [("DRAFT", "INVESTIGATING"), ("INVESTIGATING", "REVIEWED"),
                        ("REVIEWED", "PUBLISHED"), ("PUBLISHED", "INVESTIGATING")]
    review = next(h for h in history if h["action"] == "STATUS_CHANGED" and h["changes"]["status"]["after"] == "REVIEWED")
    assert review["note"] == "Synthetic review note" and review["actor"]["display_name"] == "Synthetic user"
    assert [h["action"] for h in history].count("PERMISSION_GRANTED") == 2


@pytest.mark.asyncio
async def test_revoking_access_takes_effect_immediately(client):
    owner = await account(client, "owner@example.test")
    viewer = await account(client, "viewer@example.test")
    case = await new_case(client, owner)
    cid = case["id"]
    granted = await share(client, owner, cid, "viewer@example.test", "VIEWER")
    assert granted.status_code == 201
    changed = await share(client, owner, cid, "viewer@example.test", "REVIEWER")
    assert changed.status_code == 200 and changed.json()["role"] == "REVIEWER"
    assert (await client.get(f"{V1}/cases/{cid}", headers=viewer)).status_code == 200

    revoke = await client.delete(f"{V1}/cases/{cid}/permissions/{granted.json()['user_id']}", headers=owner)
    assert revoke.status_code == 204
    assert (await client.get(f"{V1}/cases/{cid}", headers=viewer)).status_code == 404
    assert (await client.get(f"{V1}/cases", headers=viewer)).json()["items"] == []
    assert (await client.get(f"{V1}/cases/{cid}", headers=owner)).json()["visibility"] == "PRIVATE"
    history = (await client.get(f"{V1}/cases/{cid}/history", headers=owner)).json()
    assert [h["action"] for h in history][-3:] == ["PERMISSION_GRANTED", "PERMISSION_CHANGED", "PERMISSION_REVOKED"]


@pytest.mark.asyncio
async def test_permission_edge_cases(client):
    owner = await account(client, "owner@example.test")
    case = await new_case(client, owner)
    cid = case["id"]
    unknown = await client.post(f"{V1}/cases/{cid}/permissions", headers=owner,
                                json={"email": "ghost@example.test", "role": "VIEWER"})
    self_grant = await client.post(f"{V1}/cases/{cid}/permissions", headers=owner,
                                   json={"email": "owner@example.test", "role": "VIEWER"})
    owner_role = await client.post(f"{V1}/cases/{cid}/permissions", headers=owner,
                                   json={"email": "owner@example.test", "role": "OWNER"})
    owner_id = (await client.get(f"{V1}/auth/me", headers=owner)).json()["id"]
    revoke_owner = await client.delete(f"{V1}/cases/{cid}/permissions/{owner_id}", headers=owner)
    assert (unknown.status_code, self_grant.status_code, owner_role.status_code, revoke_owner.status_code) == (404, 409, 422, 409)


# ── fields, archive and delete ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_field_management_keeps_at_least_one_field(client):
    owner = await account(client, "owner@example.test")
    case = await new_case(client, owner)
    cid, first_id = case["id"], case["fields"][0]["id"]
    added = await client.post(f"{V1}/cases/{cid}/fields", headers=owner, json={
        "version": 1, "field": parcel(label="Synthetic parcel B", privacy_tier="REGION_ONLY", rounding_deg=None)})
    assert added.status_code == 201 and len(added.json()["fields"]) == 2 and added.json()["version"] == 2
    second_id = next(f["id"] for f in added.json()["fields"] if f["id"] != first_id)
    patched = await client.patch(f"{V1}/cases/{cid}/fields/{second_id}", headers=owner,
                                 json={"version": 2, "area_hectares": 3.5, "privacy_tier": "APPROXIMATE"})
    assert patched.status_code == 200
    second = next(f for f in patched.json()["fields"] if f["id"] == second_id)
    assert (second["area_hectares"], second["rounding_deg"]) == (3.5, 0.1)
    removed = await client.delete(f"{V1}/cases/{cid}/fields/{first_id}?version=3", headers=owner)
    assert removed.status_code == 200 and [f["id"] for f in removed.json()["fields"]] == [second_id]
    last = await client.delete(f"{V1}/cases/{cid}/fields/{second_id}?version=4", headers=owner)
    assert last.status_code == 409
    other_case = await new_case(client, owner)
    foreign = await client.patch(f"{V1}/cases/{other_case['id']}/fields/{second_id}", headers=owner,
                                 json={"version": 1, "label": "Wrong case"})
    assert foreign.status_code == 404
    actions = [h["action"] for h in (await client.get(f"{V1}/cases/{cid}/history", headers=owner)).json()]
    assert actions == ["CREATED", "FIELD_ADDED", "FIELD_UPDATED", "FIELD_REMOVED"]


@pytest.mark.asyncio
async def test_archive_hides_and_freezes_then_owner_deletes(client):
    owner = await account(client, "owner@example.test")
    case = await new_case(client, owner)
    cid = case["id"]
    archived = await client.post(f"{V1}/cases/{cid}/archive", headers=owner, json={"version": 1, "archived": True})
    assert archived.status_code == 200 and archived.json()["archived_at"] is not None
    assert (await client.get(f"{V1}/cases", headers=owner)).json()["items"] == []
    assert len((await client.get(f"{V1}/cases?include_archived=true", headers=owner)).json()["items"]) == 1
    frozen = await client.patch(f"{V1}/cases/{cid}", headers=owner, json={"version": 2, "title": "Edit archived"})
    assert frozen.status_code == 409
    restored = await client.post(f"{V1}/cases/{cid}/archive", headers=owner, json={"version": 2, "archived": False})
    assert restored.json()["archived_at"] is None and restored.json()["version"] == 3
    assert (await client.delete(f"{V1}/cases/{cid}?version=1", headers=owner)).status_code == 409
    assert (await client.delete(f"{V1}/cases/{cid}?version=3", headers=owner)).status_code == 204
    assert (await client.get(f"{V1}/cases/{cid}", headers=owner)).status_code == 404
