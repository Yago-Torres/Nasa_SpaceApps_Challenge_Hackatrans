"""ABB-25 collaboration API against a disposable PostgreSQL database: invitations, comments, activity
feed and consented share links. All people, parcels, coordinates and papers are synthetic.
Run with TEST_DATABASE_URL set.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text, update

from agroblackbox.api.deps import get_session_factory
from agroblackbox.app import app
from agroblackbox.db.models import (
    CaseComment,
    CaseCommentRevision,
    CaseInvitation,
    CaseShareLink,
    EvidenceClaim,
    EvidenceClaimEvent,
    Paper,
)
from agroblackbox.db.session import create_database_engine, session_factory

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration")

PASSWORD = "synthetic-correct-horse-42"
EXACT_LAT, EXACT_LON = 41.6543, -0.8765
V1 = "/api/v1"
T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
SECTIONS = {"incident_notes": False, "field_labels": False, "location_detail": "APPROXIMATE", "hypotheses": True,
            "evidence_claims": True, "conclusions": True, "member_names": False, "comments": True}


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

async def account(client, email: str, name: str) -> dict[str, str]:
    registered = await client.post(f"{V1}/auth/register",
                                   json={"email": email, "password": PASSWORD, "display_name": name})
    assert registered.status_code == 201, registered.text
    login = await client.post(f"{V1}/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def user_id(client, headers) -> str:
    return (await client.get(f"{V1}/auth/me", headers=headers)).json()["id"]


def parcel(**overrides):
    return {"label": "Synthetic parcel A", "privacy_tier": "APPROXIMATE", "latitude": EXACT_LAT,
            "longitude": EXACT_LON, "region_label": "Synthetic region", "rounding_deg": 0.5,
            "limitations": ["Synthetic test parcel; not a real farm"], **overrides}


async def new_case(client, headers, **overrides) -> dict:
    body = {"title": "SYNTHETIC case - not a real incident", "incident_start": "2022-05-01",
            "incident_end": "2022-08-31", "crop_history": ["wheat", "barley"],
            "incident_notes": "Synthetic private note: neighbour Ana Example, phone 000.", "fields": [parcel()],
            **overrides}
    response = await client.post(f"{V1}/cases", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def invite(client, owner, cid, email, role="VIEWER", **extra) -> httpx.Response:
    return await client.post(f"{V1}/cases/{cid}/invitations", headers=owner, json={"email": email, "role": role,
                                                                                   **extra})


async def join(client, owner, guest, cid, email, role) -> None:
    created = await invite(client, owner, cid, email, role)
    assert created.status_code == 201, created.text
    accepted = await client.post(f"{V1}/invitations/{created.json()['id']}/accept", headers=guest)
    assert accepted.status_code == 200, accepted.text


async def comment(client, headers, cid, body="Synthetic comment", **extra) -> httpx.Response:
    return await client.post(f"{V1}/cases/{cid}/comments", headers=headers, json={"body": body, **extra})


def seed_claim(factory, case_id: str, author_id: str, reviewer_id: str) -> dict[str, str]:
    """An ACCEPTED claim with its creation and review events, as the ABB-14 API records them."""
    with factory.begin() as session:
        paper = Paper(title="Synthetic paper on water deficit", year=2020, doi_id=f"10.5555/{uuid4().hex[:8]}",
                      doi_status="VERIFIED_CROSSREF", bibliographic_metadata={}, limitations=["Synthetic paper"])
        session.add(paper)
        session.flush()
        claim = EvidenceClaim(case_id=case_id, paper_id=paper.id, claim_text="Synthetic reviewed claim",
                              study_context="Synthetic context", limitations=["Synthetic claim"],
                              created_by=author_id, study_design="FIELD_EXPERIMENT",
                              reported_outcome={"outcome": "Synthetic outcome"}, review_status="ACCEPTED",
                              reviewed_by=reviewer_id, reviewed_at=T0, evidence_basis="FULL_TEXT",
                              access_basis="AUTHOR_PROVIDED_COPY", content_license="synthetic terms", version=2)
        session.add(claim)
        session.flush()
        snapshot = {"doi": paper.doi_id, "title": paper.title}
        session.add_all([
            EvidenceClaimEvent(claim_id=claim.id, case_id=case_id, claim_version=1, action="CREATED",
                               actor_id=author_id, created_at=T0 - timedelta(hours=1), to_status="PENDING",
                               paper_snapshot=snapshot, changes={}),
            EvidenceClaimEvent(claim_id=claim.id, case_id=case_id, claim_version=2, action="REVIEWED",
                               actor_id=reviewer_id, created_at=T0, from_status="PENDING", to_status="ACCEPTED",
                               note="Synthetic: checked table 2 of the full text.",
                               source_consulted={"evidence_basis": "FULL_TEXT", "locator": "Table 2"},
                               paper_snapshot=snapshot, changes={}),
        ])
        return {"paper": str(paper.id), "claim": str(claim.id), "doi": paper.doi_id}


def assert_no_exact_coordinates(payload: str) -> None:
    assert str(EXACT_LAT) not in payload and str(EXACT_LON) not in payload


# ── migration ────────────────────────────────────────────────────────────────

def test_collaboration_migration_downgrades_and_upgrades(api_engine):
    tables = {"case_invitations", "case_comments", "case_comment_revisions", "case_share_links"}
    command.downgrade(alembic_config(), "f4b81d2c6e93")
    assert not tables & set(inspect(api_engine).get_table_names())
    command.upgrade(alembic_config(), "head")
    assert tables <= set(inspect(api_engine).get_table_names())


# ── acceptance 1: two people collaborate without private information leaking ─

@pytest.mark.asyncio
async def test_invited_member_collaborates_without_private_exposure(client):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    guest = await account(client, "guest@example.test", "Synthetic guest")
    case = await new_case(client, owner)
    cid = case["id"]

    created = await invite(client, owner, cid, "Guest@Example.test", "REVIEWER", note="Please review <b>June</b>.",
                           expires_in_days=7)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["email"], body["role"], body["status"]) == ("guest@example.test", "REVIEWER", "PENDING")
    assert body["note"] == "Please review <b>June</b>."
    expires = datetime.fromisoformat(body["expires_at"]) - datetime.fromisoformat(body["created_at"])
    assert expires == timedelta(days=7)

    # before accepting, the guest has no access to the case
    assert (await client.get(f"{V1}/cases/{cid}", headers=guest)).status_code == 404
    mine = await client.get(f"{V1}/invitations", headers=guest)
    assert mine.status_code == 200
    [received] = mine.json()["items"]
    assert received["case"] == {"id": cid, "title": case["title"]}
    assert received["invited_by"]["display_name"] == "Synthetic owner"
    assert "owner@example.test" not in mine.text and "latitude" not in mine.text
    assert_no_exact_coordinates(mine.text)

    accepted = await client.post(f"{V1}/invitations/{received['id']}/accept", headers=guest)
    assert accepted.status_code == 200
    assert accepted.json() == {"invitation_id": received["id"], "case_id": cid, "status": "ACCEPTED",
                               "role": "REVIEWER"}
    assert (await client.get(f"{V1}/invitations", headers=guest)).json()["items"] == []
    assert (await client.post(f"{V1}/invitations/{received['id']}/accept", headers=guest)).status_code == 404

    seen = await client.get(f"{V1}/cases/{cid}", headers=guest)
    assert seen.status_code == 200 and seen.json()["my_role"] == "REVIEWER"
    assert seen.json()["visibility"] == "SHARED"
    assert_no_exact_coordinates(seen.text)
    members = await client.get(f"{V1}/cases/{cid}/permissions", headers=guest)
    assert all(m["email"] is None for m in members.json())
    for path in ("history", "activity"):
        payload = await client.get(f"{V1}/cases/{cid}/{path}", headers=guest)
        assert payload.status_code == 200
        assert "@example.test" not in payload.text  # invitation audit never carries the e-mail
        assert_no_exact_coordinates(payload.text)
    history = (await client.get(f"{V1}/cases/{cid}/history", headers=owner)).json()
    actions = [h["action"] for h in history]
    assert actions[-2:] == ["INVITATION_CREATED", "INVITATION_ACCEPTED"]
    assert history[-1]["actor"]["display_name"] == "Synthetic guest"
    assert history[-1]["changes"]["role"] == {"before": None, "after": "REVIEWER"}
    assert history[-1]["version"] == 1  # membership changes do not bump the case version
    owner_list = (await client.get(f"{V1}/cases/{cid}/invitations", headers=owner)).json()["items"]
    assert owner_list[0]["status"] == "ACCEPTED" and owner_list[0]["responded_at"]


@pytest.mark.asyncio
async def test_invitations_do_not_reveal_whether_an_account_exists(client):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    await account(client, "known@example.test", "Synthetic known")
    cid = (await new_case(client, owner))["id"]
    known = await invite(client, owner, cid, "known@example.test")
    unknown = await invite(client, owner, cid, "nobody@example.test")
    assert known.status_code == unknown.status_code == 201
    assert set(known.json()) == set(unknown.json())
    strip = ("id", "email", "created_at", "expires_at")
    assert {k: v for k, v in known.json().items() if k not in strip} == \
           {k: v for k, v in unknown.json().items() if k not in strip}
    history = (await client.get(f"{V1}/cases/{cid}/history", headers=owner)).json()
    created = [h for h in history if h["action"] == "INVITATION_CREATED"]
    assert len(created) == 2 and set(created[0]["changes"]) == set(created[1]["changes"])


@pytest.mark.asyncio
async def test_invitation_lifecycle_expiry_revocation_and_conflicts(client, factory):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    editor = await account(client, "editor@example.test", "Synthetic editor")
    guest = await account(client, "guest@example.test", "Synthetic guest")
    other = await account(client, "other@example.test", "Synthetic other")
    stranger = await account(client, "stranger@example.test", "Synthetic stranger")
    cid = (await new_case(client, owner))["id"]
    await join(client, owner, editor, cid, "editor@example.test", "EDITOR")

    # authorization: owner only; non-members cannot even see the case
    assert (await invite(client, editor, cid, "x@example.test")).status_code == 403
    assert (await client.get(f"{V1}/cases/{cid}/invitations", headers=editor)).status_code == 403
    assert (await invite(client, stranger, cid, "x@example.test")).status_code == 404
    assert (await client.post(f"{V1}/cases/{cid}/invitations", json={"email": "x@example.test",
                                                                      "role": "VIEWER"})).status_code == 401

    # validation and conflicts
    assert (await invite(client, owner, cid, "x@example.test", "OWNER")).status_code == 422
    assert (await invite(client, owner, cid, "x@example.test", expires_in_days=31)).status_code == 422
    assert (await invite(client, owner, cid, "x@example.test", expires_in_days=0)).status_code == 422
    assert (await invite(client, owner, cid, "x@example.test", note="‮\u0000 ")).status_code == 422
    assert (await invite(client, owner, cid, "owner@example.test")).status_code == 409
    assert (await invite(client, owner, cid, "editor@example.test")).status_code == 409

    first = (await invite(client, owner, cid, "guest@example.test")).json()
    assert (await invite(client, owner, cid, "guest@example.test")).status_code == 409  # one pending per e-mail
    # someone else cannot answer it, whatever their account
    for headers in (other, stranger, owner):
        assert (await client.post(f"{V1}/invitations/{first['id']}/accept", headers=headers)).status_code == 404
    assert (await client.post(f"{V1}/invitations/{uuid4()}/accept", headers=guest)).status_code == 404

    # expiry: hidden from the invitee, EXPIRED for the owner, not revocable, a new one can be sent
    with factory.begin() as session:
        session.execute(update(CaseInvitation).where(CaseInvitation.id == first["id"])
                        .values(created_at=T0 - timedelta(days=20), expires_at=T0 - timedelta(days=6)))
    assert (await client.get(f"{V1}/invitations", headers=guest)).json()["items"] == []
    assert (await client.post(f"{V1}/invitations/{first['id']}/accept", headers=guest)).status_code == 404
    listed = (await client.get(f"{V1}/cases/{cid}/invitations", headers=owner)).json()["items"]
    assert [i["status"] for i in listed if i["id"] == first["id"]] == ["EXPIRED"]
    assert (await client.delete(f"{V1}/cases/{cid}/invitations/{first['id']}", headers=owner)).status_code == 409

    # revocation is immediate
    second = (await invite(client, owner, cid, "guest@example.test", "EDITOR")).json()
    assert (await client.delete(f"{V1}/cases/{cid}/invitations/{second['id']}", headers=editor)).status_code == 403
    assert (await client.delete(f"{V1}/cases/{cid}/invitations/{second['id']}", headers=owner)).status_code == 204
    assert (await client.post(f"{V1}/invitations/{second['id']}/accept", headers=guest)).status_code == 404
    assert (await client.delete(f"{V1}/cases/{cid}/invitations/{second['id']}", headers=owner)).status_code == 409
    assert (await client.delete(f"{V1}/cases/{cid}/invitations/{uuid4()}", headers=owner)).status_code == 404

    # decline
    third = (await invite(client, owner, cid, "guest@example.test", "VIEWER")).json()
    declined = await client.post(f"{V1}/invitations/{third['id']}/decline", headers=guest)
    assert declined.status_code == 200 and declined.json()["status"] == "DECLINED" and declined.json()["role"] is None
    assert (await client.get(f"{V1}/cases/{cid}", headers=guest)).status_code == 404

    history = (await client.get(f"{V1}/cases/{cid}/history", headers=owner)).json()
    actions = [h["action"] for h in history if h["action"].startswith("INVITATION_")]
    assert actions.count("INVITATION_CREATED") == 4
    assert {"INVITATION_ACCEPTED", "INVITATION_REVOKED", "INVITATION_DECLINED"} <= set(actions)
    statuses = {i["id"]: i["status"] for i in
                (await client.get(f"{V1}/cases/{cid}/invitations", headers=owner)).json()["items"]}
    assert (statuses[first["id"]], statuses[second["id"]], statuses[third["id"]]) == ("EXPIRED", "REVOKED", "DECLINED")

    # the direct grant (ABB-06) keeps working
    direct = await client.post(f"{V1}/cases/{cid}/permissions", headers=owner,
                               json={"email": "other@example.test", "role": "VIEWER"})
    assert direct.status_code == 201


# ── acceptance 2: a guest comments, another member reviews, the owner revokes ─

@pytest.mark.asyncio
async def test_guest_comments_reviewer_evaluates_and_owner_revokes(client):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    viewer = await account(client, "viewer@example.test", "Synthetic viewer")
    reviewer = await account(client, "reviewer@example.test", "Synthetic reviewer")
    cid = (await new_case(client, owner))["id"]
    await join(client, owner, viewer, cid, "viewer@example.test", "VIEWER")
    await join(client, owner, reviewer, cid, "reviewer@example.test", "REVIEWER")
    hypothesis = await client.post(f"{V1}/cases/{cid}/hypotheses", headers=owner, json={
        "title": "Water deficit", "statement": "Synthetic: a dry June may have contributed.",
        "missing_evidence": ["Soil moisture measurements"]})
    assert hypothesis.status_code == 201, hypothesis.text
    hid = hypothesis.json()["id"]

    on_case = await comment(client, viewer, cid, "Synthetic: the yellowing began after the irrigation stop.")
    assert on_case.status_code == 201, on_case.text
    assert on_case.json()["target"] == {"kind": "CASE", "id": None}
    assert on_case.json()["author"]["display_name"] == "Synthetic viewer"
    on_hypothesis = await comment(client, viewer, cid, "Synthetic objection: June rain was normal locally.",
                                  target_kind="HYPOTHESIS", target_id=hid)
    assert on_hypothesis.status_code == 201
    reply = await comment(client, reviewer, cid, "Synthetic: noted, we lack local gauges.",
                          parent_id=on_hypothesis.json()["id"])
    assert reply.status_code == 201
    assert reply.json()["target"] == {"kind": "HYPOTHESIS", "id": hid}

    evaluated = await client.post(f"{V1}/cases/{cid}/hypotheses/{hid}/status", headers=reviewer, json={
        "version": 1, "status": "NOT_EVALUABLE", "note": "Synthetic: no soil moisture data to check."})
    assert evaluated.status_code == 200, evaluated.text
    assert (await client.post(f"{V1}/cases/{cid}/hypotheses/{hid}/status", headers=viewer, json={
        "version": 2, "status": "OPEN"})).status_code == 403

    revoke = await client.delete(f"{V1}/cases/{cid}/permissions/{await user_id(client, viewer)}", headers=owner)
    assert revoke.status_code == 204
    assert (await client.get(f"{V1}/cases/{cid}/comments", headers=viewer)).status_code == 404
    assert (await comment(client, viewer, cid)).status_code == 404
    listed = (await client.get(f"{V1}/cases/{cid}/comments?target_kind=HYPOTHESIS&target_id={hid}",
                               headers=reviewer)).json()
    assert listed["total"] == 2 and listed["items"][0]["author"]["display_name"] == "Synthetic viewer"
    assert listed["items"][0]["reply_count"] == 1

    activity = (await client.get(f"{V1}/cases/{cid}/activity?order=asc&limit=200", headers=owner)).json()
    kinds = [e["kind"] for e in activity["items"]]
    assert kinds.index("COMMENT_POSTED") < kinds.index("HYPOTHESIS_EVALUATED") < kinds.index("PERMISSION_REVOKED")
    review = next(e for e in activity["items"] if e["kind"] == "HYPOTHESIS_EVALUATED")
    assert review["actor"]["display_name"] == "Synthetic reviewer" and review["category"] == "REVIEW"
    assert review["target"] == {"kind": "HYPOTHESIS", "id": hid}
    assert review["evidence"]["missing_evidence"] == ["Soil moisture measurements"]
    assert review["note"] == "Synthetic: no soil moisture data to check."


# ── comments ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_comment_targets_must_belong_to_the_case(client):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    case = await new_case(client, owner)
    other = await new_case(client, owner, title="SYNTHETIC second case")
    cid = case["id"]
    foreign = await client.post(f"{V1}/cases/{other['id']}/hypotheses", headers=owner,
                                json={"title": "Foreign", "statement": "Synthetic foreign hypothesis."})
    assert foreign.status_code == 201
    cases = (
        ({"target_kind": "HYPOTHESIS", "target_id": foreign.json()["id"]}, 422),
        ({"target_kind": "FIELD", "target_id": other["fields"][0]["id"]}, 422),
        ({"target_kind": "CLAIM", "target_id": str(uuid4())}, 422),
        ({"target_kind": "TIMELINE_EVENT", "target_id": str(uuid4())}, 422),
        ({"target_kind": "CASE", "target_id": case["fields"][0]["id"]}, 422),
        ({"target_kind": "FIELD"}, 422),
        ({"target_kind": "PAPER", "target_id": str(uuid4())}, 422),
        ({"target_kind": "FIELD", "target_id": case["fields"][0]["id"]}, 201),
    )
    for extra, expected in cases:
        response = await comment(client, owner, cid, **extra)
        assert response.status_code == expected, (extra, response.text)
    timeline = (await client.get(f"{V1}/cases/{cid}/timeline", headers=owner)).json()
    incident = next(e for e in timeline["events"] if e["kind"] == "FARMER_REPORTED")
    assert (await comment(client, owner, cid, target_kind="TIMELINE_EVENT",
                          target_id=incident["id"])).status_code == 201

    parent = (await comment(client, owner, cid, "Synthetic parent")).json()
    child = await comment(client, owner, cid, "Synthetic child", parent_id=parent["id"])
    assert child.status_code == 201
    assert (await comment(client, owner, cid, parent_id=child.json()["id"])).status_code == 422  # one level
    assert (await comment(client, owner, cid, parent_id=parent["id"], target_kind="CASE")).status_code == 422
    assert (await comment(client, owner, cid, parent_id=str(uuid4()))).status_code == 422
    foreign_parent = (await comment(client, owner, other["id"], "Synthetic other-case comment")).json()
    assert (await comment(client, owner, cid, parent_id=foreign_parent["id"])).status_code == 422
    assert (await client.get(f"{V1}/cases/{cid}/comments/{foreign_parent['id']}",
                             headers=owner)).status_code == 404


@pytest.mark.asyncio
async def test_comment_edit_history_tombstones_and_permissions(client, factory):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    editor = await account(client, "editor@example.test", "Synthetic editor")
    viewer = await account(client, "viewer@example.test", "Synthetic viewer")
    cid = (await new_case(client, owner))["id"]
    await join(client, owner, editor, cid, "editor@example.test", "EDITOR")
    await join(client, owner, viewer, cid, "viewer@example.test", "VIEWER")
    created = (await comment(client, viewer, cid, "First synthetic text")).json()
    url = f"{V1}/cases/{cid}/comments/{created['id']}"
    assert created["can_edit"] and created["can_delete"] and created["version"] == 1

    assert (await client.patch(url, headers=editor, json={"version": 1, "body": "Hijack"})).status_code == 403
    assert (await client.patch(url, headers=owner, json={"version": 1, "body": "Hijack"})).status_code == 403
    edited = await client.patch(url, headers=viewer, json={"version": 1, "body": "Second synthetic text"})
    assert edited.status_code == 200
    assert (edited.json()["body"], edited.json()["version"], edited.json()["revision_count"]) == \
           ("Second synthetic text", 2, 1)
    assert edited.json()["edited_at"]
    assert (await client.patch(url, headers=viewer, json={"version": 1, "body": "Stale"})).status_code == 409
    await client.patch(url, headers=viewer, json={"version": 2, "body": "Third synthetic text"})
    revisions = (await client.get(f"{url}/revisions", headers=editor)).json()
    assert [(r["revision"], r["body"]) for r in revisions] == [(1, "First synthetic text"),
                                                                (2, "Second synthetic text")]
    as_editor = (await client.get(url, headers=editor)).json()
    assert not as_editor["can_edit"] and not as_editor["can_delete"]
    assert (await client.delete(f"{url}?version=3", headers=editor)).status_code == 403
    assert (await client.delete(f"{url}?version=2", headers=owner)).status_code == 409

    deleted = await client.delete(f"{url}?version=3", headers=owner)  # owner moderation
    assert deleted.status_code == 204
    tomb = (await client.get(url, headers=viewer)).json()
    assert tomb["deleted"] and tomb["body"] is None and tomb["revision_count"] == 0
    assert tomb["deleted_by"]["display_name"] == "Synthetic owner" and not tomb["can_edit"]
    assert (await client.get(f"{url}/revisions", headers=viewer)).status_code == 410
    assert (await client.patch(url, headers=viewer, json={"version": 4, "body": "Again"})).status_code == 409
    assert (await client.delete(f"{url}?version=4", headers=viewer)).status_code == 409
    assert (await comment(client, editor, cid, parent_id=created["id"])).status_code == 409
    listed = (await client.get(f"{V1}/cases/{cid}/comments", headers=editor)).json()
    assert listed["total"] == 1 and listed["items"][0]["deleted"]
    assert "Third synthetic text" not in str(listed)
    with factory() as session:  # kept for audit, not served
        row = session.get(CaseComment, created["id"])
        assert row.body == "Third synthetic text" and row.deleted_at is not None
        assert session.scalar(select(func.count()).select_from(CaseCommentRevision)) == 2

    activity = (await client.get(f"{V1}/cases/{cid}/activity?order=asc&limit=200", headers=viewer)).json()
    comment_events = [(e["kind"], e["actor"]["display_name"]) for e in activity["items"] if e["category"] == "COMMENT"]
    assert comment_events == [("COMMENT_POSTED", "Synthetic viewer"), ("COMMENT_EDITED", "Synthetic viewer"),
                              ("COMMENT_EDITED", "Synthetic viewer"), ("COMMENT_DELETED", "Synthetic owner")]
    assert "synthetic text" not in str(activity)  # the feed never repeats comment text


@pytest.mark.asyncio
async def test_comment_text_is_plain_text_returned_verbatim(client):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    cid = (await new_case(client, owner))["id"]
    markup = '<script>alert(1)</script><img src=x onerror="alert(2)"> & {{7*7}} **bold**'
    created = await comment(client, owner, cid, markup)
    assert created.status_code == 201
    assert created.headers["content-type"].startswith("application/json")
    assert created.json()["body"] == markup and created.json()["body_format"] == "text/plain"
    fetched = await client.get(f"{V1}/cases/{cid}/comments/{created.json()['id']}", headers=owner)
    assert fetched.json()["body"] == markup
    cleaned = await comment(client, owner, cid, "  a\u0000b‮ c\r\nd\te‍\U0001F33E  ")
    assert cleaned.json()["body"] == "ab c\nd\te‍\U0001F33E"
    assert (await comment(client, owner, cid, " \u0007‮ ")).status_code == 422
    assert (await comment(client, owner, cid, "x" * 4001)).status_code == 422
    assert (await comment(client, owner, cid, "x" * 4000)).status_code == 201
    assert (await comment(client, owner, cid, "ok", unexpected=True)).status_code == 422
    # archived cases are read-only
    case = (await client.get(f"{V1}/cases/{cid}", headers=owner)).json()
    await client.post(f"{V1}/cases/{cid}/archive", headers=owner, json={"version": case["version"],
                                                                        "archived": True})
    assert (await comment(client, owner, cid)).status_code == 409


# ── acceptance 3: the activity log keeps author, instant and evidence ─────────

@pytest.mark.asyncio
async def test_activity_feed_keeps_author_instant_and_evidence(client, factory):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    reviewer = await account(client, "reviewer@example.test", "Synthetic reviewer")
    viewer = await account(client, "viewer@example.test", "Synthetic viewer")
    stranger = await account(client, "stranger@example.test", "Synthetic stranger")
    cid = (await new_case(client, owner))["id"]
    await join(client, owner, reviewer, cid, "reviewer@example.test", "REVIEWER")
    await join(client, owner, viewer, cid, "viewer@example.test", "VIEWER")
    seeded = seed_claim(factory, cid, await user_id(client, owner), await user_id(client, reviewer))
    hypothesis = (await client.post(f"{V1}/cases/{cid}/hypotheses", headers=owner, json={
        "title": "Water deficit", "statement": "Synthetic: a dry June may have contributed.",
        "supporting_evidence_ids": [seeded["claim"]]})).json()
    evaluated = await client.post(f"{V1}/cases/{cid}/hypotheses/{hypothesis['id']}/status", headers=reviewer,
                                  json={"version": 1, "status": "COMPATIBLE", "note": "Synthetic: the claim fits."})
    assert evaluated.status_code == 200, evaluated.text
    await comment(client, viewer, cid, "Synthetic question", target_kind="CLAIM", target_id=seeded["claim"])
    case = (await client.get(f"{V1}/cases/{cid}", headers=owner)).json()
    added = await client.post(f"{V1}/cases/{cid}/fields", headers=owner, json={
        "version": case["version"], "field": parcel(label="Synthetic parcel B")})
    assert added.status_code == 201

    page = await client.get(f"{V1}/cases/{cid}/activity?limit=200", headers=owner)
    assert page.status_code == 200
    feed = page.json()
    items = feed["items"]
    assert feed["total"] == len(items) and feed["order"] == "desc"
    stamps = [datetime.fromisoformat(e["created_at"]) for e in items]
    assert stamps == sorted(stamps, reverse=True)
    assert all(e["created_at"] for e in items) and all(e["actor"] for e in items)
    by_kind = {e["kind"]: e for e in items}
    for kind in ("CREATED", "INVITATION_CREATED", "INVITATION_ACCEPTED", "HYPOTHESIS_CREATED",
                 "HYPOTHESIS_EVALUATED", "CLAIM_CREATED", "CLAIM_REVIEWED", "COMMENT_POSTED", "FIELD_ADDED"):
        assert kind in by_kind, kind
    claim_review = by_kind["CLAIM_REVIEWED"]
    assert claim_review["source"] == "CLAIM_EVENT" and claim_review["category"] == "REVIEW"
    assert claim_review["actor"]["display_name"] == "Synthetic reviewer"
    assert claim_review["created_at"].startswith("2026-11-14T12:00:00")
    assert claim_review["evidence"]["source_consulted"] == {"evidence_basis": "FULL_TEXT", "locator": "Table 2"}
    assert claim_review["evidence"]["paper"]["doi"] == seeded["doi"]
    assert claim_review["note"] == "Synthetic: checked table 2 of the full text."
    evaluation = by_kind["HYPOTHESIS_EVALUATED"]
    assert evaluation["evidence"]["supporting_evidence_ids"] == [seeded["claim"]]
    assert by_kind["COMMENT_POSTED"]["target"] == {"kind": "CLAIM", "id": seeded["claim"]}
    assert by_kind["INVITATION_ACCEPTED"]["category"] == "INVITATION"
    assert by_kind["FIELD_ADDED"]["target"]["kind"] == "FIELD"
    assert str(EXACT_LAT) in page.text  # the owner sees exact history values

    guest_view = await client.get(f"{V1}/cases/{cid}/activity?limit=200", headers=viewer)
    assert guest_view.status_code == 200 and guest_view.json()["total"] == feed["total"]
    assert_no_exact_coordinates(guest_view.text)
    assert "@example.test" not in guest_view.text

    # pagination is stable and complete in both orders
    pages = []
    for offset in range(0, feed["total"], 3):
        pages += (await client.get(f"{V1}/cases/{cid}/activity?limit=3&offset={offset}",
                                   headers=owner)).json()["items"]
    assert [e["id"] for e in pages] == [e["id"] for e in items]
    ascending = (await client.get(f"{V1}/cases/{cid}/activity?limit=200&order=asc", headers=owner)).json()["items"]
    assert [e["id"] for e in ascending] == [e["id"] for e in reversed(items)]
    assert (await client.get(f"{V1}/cases/{cid}/activity?limit=201", headers=owner)).status_code == 422
    assert (await client.get(f"{V1}/cases/{cid}/activity", headers=stranger)).status_code == 404
    assert (await client.get(f"{V1}/cases/{cid}/activity")).status_code == 401


# ── consented share links ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_share_link_requires_consent_and_exposes_only_a_redacted_view(client, factory):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    editor = await account(client, "editor@example.test", "Synthetic editor")
    viewer = await account(client, "viewer@example.test", "Synthetic viewer")
    case = await new_case(client, owner, fields=[
        parcel(), parcel(label="Synthetic exact parcel", privacy_tier="EXACT", precise_location_consent=True,
                         latitude=EXACT_LAT + 1, longitude=EXACT_LON + 1),
        parcel(label="Synthetic withheld parcel", privacy_tier="WITHHELD", latitude=None, longitude=None)])
    cid = case["id"]
    await join(client, owner, editor, cid, "editor@example.test", "EDITOR")
    await join(client, owner, viewer, cid, "viewer@example.test", "VIEWER")
    await comment(client, viewer, cid, "Synthetic <i>viewer</i> comment")
    await comment(client, editor, cid, "Synthetic editor comment")
    seed_claim(factory, cid, await user_id(client, owner), await user_id(client, editor))
    url = f"{V1}/cases/{cid}/share-links"

    assert (await client.post(url, headers=owner, json={"sections": SECTIONS})).status_code == 422
    assert (await client.post(url, headers=owner, json={"consent": False, "sections": SECTIONS})).status_code == 422
    partial = {k: v for k, v in SECTIONS.items() if k != "comments"}
    assert (await client.post(url, headers=owner, json={"consent": True, "sections": partial})).status_code == 422
    assert (await client.post(url, headers=owner, json={"consent": True, "sections": {
        **SECTIONS, "location_detail": "EXACT"}})).status_code == 422
    assert (await client.post(url, headers=editor, json={"consent": True, "sections": SECTIONS})).status_code == 403
    assert (await client.get(url, headers=viewer)).status_code == 403

    created = await client.post(url, headers=owner, json={"consent": True, "sections": SECTIONS,
                                                           "label": "For the cooperative", "expires_in_days": 3})
    assert created.status_code == 201, created.text
    link = created.json()
    token = link["token"]
    assert len(token) >= 43 and link["path"] == f"/api/v1/shared/{token}" and link["status"] == "ACTIVE"
    with factory() as session:
        stored = session.scalar(select(CaseShareLink))
        assert stored.token_sha256 != token and token not in str(stored.sections)
    listed = await client.get(url, headers=owner)
    assert token not in listed.text and listed.json()["items"][0]["label"] == "For the cooperative"

    public = await client.get(link["path"])  # no account
    assert public.status_code == 200, public.text
    assert public.headers["cache-control"] == "no-store" and public.headers["referrer-policy"] == "no-referrer"
    assert "noindex" in public.headers["x-robots-tag"]
    view = public.json()
    assert_no_exact_coordinates(public.text)
    assert str(EXACT_LAT + 1) not in public.text
    assert "@" not in public.text and cid not in public.text
    for headers in (owner, editor, viewer):
        assert await user_id(client, headers) not in public.text
    assert "Synthetic owner" not in public.text and "Synthetic viewer" not in public.text
    assert view["case"]["incident_notes"] is None and "Ana Example" not in public.text
    fields = {f["label"]: f for f in view["fields"]}
    assert set(fields) == {"Field 1", "Field 2", "Field 3"}
    precisions = sorted(f["location_precision"] for f in view["fields"])
    assert precisions == ["APPROXIMATE", "NONE", "REGION_ONLY"]
    approx = next(f for f in view["fields"] if f["location_precision"] == "APPROXIMATE")
    assert (approx["latitude"], approx["longitude"], approx["rounding_deg"]) == (41.75, -0.75, 0.5)
    exact = next(f for f in view["fields"] if f["location_precision"] == "REGION_ONLY")
    assert exact["latitude"] is None and exact["region_label"] == "Synthetic region"
    assert [c["author"] for c in view["comments"]] == ["Member 1", "Member 2"]
    assert view["comments"][0]["body"] == "Synthetic <i>viewer</i> comment"
    assert view["evidence_claims"][0]["source_kind"] == "LITERATURE_REVIEWED"
    assert view["hypotheses"] == [] and view["conclusions"] == []

    # a narrower link
    narrow = (await client.post(url, headers=owner, json={"consent": True, "sections": {
        **SECTIONS, "location_detail": "NONE", "comments": False, "evidence_claims": False, "member_names": True,
        "field_labels": True, "incident_notes": True}})).json()
    narrow_view = (await client.get(narrow["path"])).json()
    assert narrow_view["comments"] is None and narrow_view["evidence_claims"] is None
    assert {f["location_precision"] for f in narrow_view["fields"]} == {"NONE"}
    assert all(f["region_label"] is None for f in narrow_view["fields"])
    assert "Synthetic parcel A" in {f["label"] for f in narrow_view["fields"]}
    assert narrow_view["case"]["incident_notes"].startswith("Synthetic private note")
    named = (await client.post(url, headers=owner, json={"consent": True, "sections": {
        **SECTIONS, "member_names": True}})).json()
    assert [c["author"] for c in (await client.get(named["path"])).json()["comments"]] == \
           ["Synthetic viewer", "Synthetic editor"]

    # revocation is immediate; expired and unknown tokens look the same
    assert (await client.delete(f"{url}/{link['id']}", headers=editor)).status_code == 403
    assert (await client.delete(f"{url}/{link['id']}", headers=owner)).status_code == 204
    gone = await client.get(link["path"])
    assert gone.status_code == 404 and gone.headers["cache-control"] == "no-store"
    assert (await client.delete(f"{url}/{link['id']}", headers=owner)).status_code == 204  # idempotent
    with factory.begin() as session:
        session.execute(update(CaseShareLink).where(CaseShareLink.id == narrow["id"])
                        .values(created_at=T0 - timedelta(days=10), expires_at=T0 - timedelta(days=1)))
    expired = await client.get(narrow["path"])
    unknown = await client.get(f"{V1}/shared/{'A' * 43}")
    malformed = await client.get(f"{V1}/shared/short")
    assert expired.status_code == unknown.status_code == malformed.status_code == 404
    assert expired.json() == unknown.json() == malformed.json() == {"detail": "Shared case not found."}
    statuses = {i["id"]: i["status"] for i in (await client.get(url, headers=owner)).json()["items"]}
    assert (statuses[link["id"]], statuses[narrow["id"]], statuses[named["id"]]) == ("REVOKED", "EXPIRED", "ACTIVE")
    history = [h["action"] for h in (await client.get(f"{V1}/cases/{cid}/history", headers=owner)).json()]
    assert history.count("SHARE_LINK_CREATED") == 3 and history.count("SHARE_LINK_REVOKED") == 1


# ── authorization matrix and erasure ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_collaboration_authorization_matrix(client):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    members = {}
    for role in ("EDITOR", "REVIEWER", "VIEWER"):
        email = f"{role.lower()}@example.test"
        members[role] = await account(client, email, f"Synthetic {role.lower()}")
    stranger = await account(client, "stranger@example.test", "Synthetic stranger")
    cid = (await new_case(client, owner))["id"]
    for role, headers in members.items():
        await join(client, owner, headers, cid, f"{role.lower()}@example.test", role)
    share_body = {"consent": True, "sections": SECTIONS}

    def calls(n: int):
        return [
            ("POST", f"{V1}/cases/{cid}/invitations", {"email": f"new{n}@example.test", "role": "VIEWER"}),
            ("GET", f"{V1}/cases/{cid}/invitations", None),
            ("POST", f"{V1}/cases/{cid}/share-links", share_body),
            ("GET", f"{V1}/cases/{cid}/share-links", None),
            ("POST", f"{V1}/cases/{cid}/comments", {"body": "Synthetic matrix comment"}),
            ("GET", f"{V1}/cases/{cid}/comments", None),
            ("GET", f"{V1}/cases/{cid}/activity", None),
        ]

    expected = {
        "OWNER": [201, 200, 201, 200, 201, 200, 200],
        "EDITOR": [403, 403, 403, 403, 201, 200, 200],
        "REVIEWER": [403, 403, 403, 403, 201, 200, 200],
        "VIEWER": [403, 403, 403, 403, 201, 200, 200],
        "STRANGER": [404] * 7,
        "ANONYMOUS": [401] * 7,
    }
    identities = {"OWNER": owner, **members, "STRANGER": stranger, "ANONYMOUS": {}}
    for n, (who, headers) in enumerate(identities.items()):
        got = [(await client.request(method, path, json=body, headers=headers)).status_code
               for method, path, body in calls(n)]
        assert got == expected[who], who


@pytest.mark.asyncio
async def test_case_deletion_erases_collaboration_records(client, factory):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    viewer = await account(client, "viewer@example.test", "Synthetic viewer")
    cid = (await new_case(client, owner))["id"]
    await join(client, owner, viewer, cid, "viewer@example.test", "VIEWER")
    await invite(client, owner, cid, "pending@example.test")
    first = (await comment(client, viewer, cid, "Synthetic text")).json()
    await client.patch(f"{V1}/cases/{cid}/comments/{first['id']}", headers=viewer,
                       json={"version": 1, "body": "Synthetic text, edited"})
    link = (await client.post(f"{V1}/cases/{cid}/share-links", headers=owner,
                              json={"consent": True, "sections": SECTIONS})).json()
    version = (await client.get(f"{V1}/cases/{cid}", headers=owner)).json()["version"]
    assert (await client.delete(f"{V1}/cases/{cid}?version={version}", headers=owner)).status_code == 204
    with factory() as session:
        for model in (CaseInvitation, CaseComment, CaseCommentRevision, CaseShareLink):
            assert session.scalar(select(func.count()).select_from(model)) == 0, model
    assert (await client.get(link["path"])).status_code == 404
