"""ABB-25 collaboration checks that need no database: plain-text cleaning, request validation, the
location rules of shared views, activity classification, 503 behaviour and the OpenAPI surface."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from agroblackbox.api.activity import history_category, history_target
from agroblackbox.api.collaboration_dto import (
    CommentCreate,
    CommentEdit,
    InvitationCreate,
    ShareLinkCreate,
    ShareSections,
    clean_text,
)
from agroblackbox.api.deps import STORAGE_UNAVAILABLE, get_session_factory
from agroblackbox.api.sharing import shared_field
from agroblackbox.app import app

LAT, LON = 41.6543, -0.8765
SECTIONS = {"incident_notes": False, "field_labels": False, "location_detail": "APPROXIMATE", "hypotheses": True,
            "evidence_claims": True, "conclusions": True, "member_names": False, "comments": False}


@pytest.mark.parametrize("raw,expected", [
    ("plain", "plain"),
    ("  padded \n", "padded"),
    ("a\r\nb\rc", "a\nb\nc"),
    ("tab\tkept", "tab\tkept"),
    ("nul\x00bell\x07esc\x1bdel\x7f", "nulbellescdel"),
    ("rtl‮override⁦isolate⁩", "rtloverrideisolate"),
    ("zero​width﻿", "zerowidth"),
    ("family \U0001F468‍\U0001F469", "family \U0001F468‍\U0001F469"),  # ZWJ kept
    ("é", "é"),  # NFC
    ("<script>alert(1)</script>", "<script>alert(1)</script>"),  # markup is text, never removed or escaped
])
def test_clean_text_removes_only_invisible_controls(raw, expected):
    assert clean_text(raw) == expected


def test_comment_create_rules():
    assert CommentCreate(body=" hi ").target_kind == "CASE"
    target = uuid4()
    assert CommentCreate(body="x", target_kind="HYPOTHESIS", target_id=target).target_id == target
    assert CommentCreate(body="x", parent_id=uuid4()).target_kind == "CASE"
    for bad in (
        {"body": ""}, {"body": "\u0000‮  "}, {"body": "x" * 4001},
        {"body": "x", "target_kind": "HYPOTHESIS"},
        {"body": "x", "target_kind": "CASE", "target_id": str(uuid4())},
        {"body": "x", "target_kind": "PAPER", "target_id": str(uuid4())},
        {"body": "x", "parent_id": str(uuid4()), "target_kind": "CASE"},
        {"body": "x", "parent_id": str(uuid4()), "target_id": None},
        {"body": "x", "html": True},
    ):
        with pytest.raises(ValidationError):
            CommentCreate(**bad)
    assert len(CommentCreate(body="x" * 4000 + "\u0000" * 10).body) == 4000
    with pytest.raises(ValidationError):
        CommentEdit(version=0, body="x")


def test_invitation_create_normalises_email_and_bounds_expiry():
    invitation = InvitationCreate(email=" Guest@Example.TEST ", role="REVIEWER", note=" hello\u0000 ")
    assert (invitation.email, invitation.note, invitation.expires_in_days) == ("guest@example.test", "hello", 14)
    for bad in ({"role": "OWNER"}, {"expires_in_days": 31}, {"expires_in_days": 0}, {"note": "x" * 501},
                {"email": "not-an-email"}):
        with pytest.raises(ValidationError):
            InvitationCreate(**{"email": "a@example.test", "role": "VIEWER", **bad})


def test_share_link_needs_explicit_consent_and_every_section():
    assert ShareLinkCreate(consent=True, sections=SECTIONS).expires_in_days == 14
    for bad in (
        {"consent": False, "sections": SECTIONS},
        {"sections": SECTIONS},
        {"consent": True, "sections": {k: v for k, v in SECTIONS.items() if k != "member_names"}},
        {"consent": True, "sections": {**SECTIONS, "location_detail": "EXACT"}},
        {"consent": True, "sections": {**SECTIONS, "coordinates": True}},
        {"consent": True, "sections": SECTIONS, "expires_in_days": 31},
    ):
        with pytest.raises(ValidationError):
            ShareLinkCreate(**bad)


def _field(tier: str, *, lat=LAT, lon=LON, rounding=0.5, consent=False):
    return SimpleNamespace(label="Private parcel name", privacy_tier=tier, latitude=lat, longitude=lon,
                           rounding_deg=rounding, region_label="Synthetic region",
                           precise_location_consent=consent)


@pytest.mark.parametrize("tier,detail,expected", [
    ("APPROXIMATE", "APPROXIMATE", ("APPROXIMATE", 41.75, -0.75, "Synthetic region")),
    ("APPROXIMATE", "REGION", ("REGION_ONLY", None, None, "Synthetic region")),
    ("APPROXIMATE", "NONE", ("NONE", None, None, None)),
    ("EXACT", "APPROXIMATE", ("REGION_ONLY", None, None, "Synthetic region")),
    ("REGION_ONLY", "APPROXIMATE", ("REGION_ONLY", None, None, "Synthetic region")),
    ("WITHHELD", "APPROXIMATE", ("NONE", None, None, None)),
])
def test_shared_field_is_the_more_private_of_choice_and_tier(tier, detail, expected):
    lat = None if tier == "WITHHELD" else LAT
    lon = None if tier == "WITHHELD" else LON
    sections = ShareSections(**{**SECTIONS, "location_detail": detail})
    shown = shared_field(_field(tier, lat=lat, lon=lon, consent=tier == "EXACT"), 2, sections)
    assert (shown.location_precision, shown.latitude, shown.longitude, shown.region_label) == expected
    assert shown.label == "Field 2"
    assert str(LAT) not in shown.model_dump_json() and str(LON) not in shown.model_dump_json()


def test_shared_field_consent_for_members_does_not_extend_to_share_links():
    sections = ShareSections(**SECTIONS)
    shown = shared_field(_field("APPROXIMATE", consent=True), 1, sections)
    assert (shown.latitude, shown.longitude) == (41.75, -0.75)
    labelled = shared_field(_field("APPROXIMATE"), 1, ShareSections(**{**SECTIONS, "field_labels": True}))
    assert labelled.label == "Private parcel name"


@pytest.mark.parametrize("action,category", [
    ("PERMISSION_GRANTED", "PERMISSION"), ("INVITATION_ACCEPTED", "INVITATION"),
    ("SHARE_LINK_REVOKED", "SHARING"), ("CONCLUSION_REVIEWED", "REVIEW"), ("GRAPH_EDGE_REVIEWED", "REVIEW"),
    ("HYPOTHESIS_EVALUATED", "REVIEW"), ("STATUS_CHANGED", "WORKFLOW"), ("HYPOTHESIS_CREATED", "EVIDENCE"),
    ("EVIDENCE_CLAIM_DELETED", "EVIDENCE"), ("FIELD_ADDED", "CASE"), ("CREATED", "CASE"),
])
def test_history_categories(action, category):
    assert history_category(action) == category


def test_history_targets_prefer_specific_ids_and_fall_back_to_the_case():
    case_id, record = uuid4(), str(uuid4())
    assert history_target(case_id, {"edge_id": record, "conclusion_id": "x"}).model_dump() == \
           {"kind": "GRAPH_EDGE", "id": record}
    assert history_target(case_id, {"invitation_id": record, "user_id": "u"}).kind == "INVITATION"
    assert history_target(case_id, {"field": {"before": None, "after": {"id": record}}}).model_dump() == \
           {"kind": "FIELD", "id": record}
    assert history_target(case_id, {"title": {"before": "a", "after": "b"}}).model_dump() == \
           {"kind": "CASE", "id": str(case_id)}


@pytest.mark.asyncio
async def test_collaboration_routes_return_503_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app.dependency_overrides.pop(get_session_factory, None)
    bearer = {"Authorization": "Bearer whatever"}
    case_id = uuid4()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        responses = [
            await client.get(f"/api/v1/shared/{'A' * 43}"),
            await client.get("/api/v1/invitations", headers=bearer),
            await client.get(f"/api/v1/cases/{case_id}/activity", headers=bearer),
            await client.post(f"/api/v1/cases/{case_id}/comments", headers=bearer, json={"body": "x"}),
        ]
    assert [r.status_code for r in responses] == [503] * 4
    assert all(r.json() == {"detail": STORAGE_UNAVAILABLE} for r in responses)


def test_openapi_documents_collaboration_routes():
    schema = app.openapi()
    paths = schema["paths"]
    for path in ("/api/v1/cases/{case_id}/invitations", "/api/v1/cases/{case_id}/invitations/{invitation_id}",
                 "/api/v1/invitations", "/api/v1/invitations/{invitation_id}/accept",
                 "/api/v1/invitations/{invitation_id}/decline", "/api/v1/cases/{case_id}/comments",
                 "/api/v1/cases/{case_id}/comments/{comment_id}",
                 "/api/v1/cases/{case_id}/comments/{comment_id}/revisions", "/api/v1/cases/{case_id}/activity",
                 "/api/v1/cases/{case_id}/share-links", "/api/v1/cases/{case_id}/share-links/{link_id}",
                 "/api/v1/shared/{token}"):
        assert path in paths, path
    assert "security" not in paths["/api/v1/shared/{token}"]["get"]  # public, token in the path
    assert paths["/api/v1/cases/{case_id}/activity"]["get"]["security"] == [{"HTTPBearer": []}]
    shared = schema["components"]["schemas"]["SharedField"]["properties"]
    assert "precise_location_consent" not in shared
    assert "email" not in schema["components"]["schemas"]["ReceivedInvitationView"]["properties"]
