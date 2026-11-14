"""ABB-05/ABB-06 tests that need no database: hashing, tokens, redaction, 503 behaviour."""
from __future__ import annotations

import hashlib
import math

import httpx
import pytest
from pydantic import ValidationError

from agroblackbox.api.deps import STORAGE_UNAVAILABLE, get_session_factory
from agroblackbox.api.dto import CaseCreate, FieldInput, RegisterRequest
from agroblackbox.app import app
from agroblackbox.db.session import create_database_engine, session_factory
from agroblackbox.privacy import REDACTED, redact_coordinates, snap_to_cell_centre, visible_location
from agroblackbox.security import (
    hash_password,
    new_session_token,
    password_policy_error,
    token_digest,
    verify_password,
)

PASSWORD = "synthetic-correct-horse-42"


def test_password_hash_roundtrip_uses_salted_scrypt():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first.startswith("scrypt$16384$8$1$") and first != second  # per-user random salt
    assert PASSWORD not in first
    assert verify_password(PASSWORD, first) and verify_password(PASSWORD, second)
    assert not verify_password(PASSWORD + "x", first)


@pytest.mark.parametrize("encoded", [None, "", "plain", "bcrypt$1$2$3$4$5", "scrypt$x$8$1$AA==$AA==",
                                     "scrypt$16384$8$1$not-base64!$AA=="])
def test_malformed_or_missing_hash_never_verifies(encoded):
    assert verify_password(PASSWORD, encoded) is False


def test_password_policy_message_never_contains_the_password():
    assert password_policy_error(PASSWORD) is None
    message = password_policy_error("short")
    assert message and "short" not in message
    assert password_policy_error("x" * 257)


def test_session_tokens_are_random_and_only_digests_are_stored():
    tokens = {new_session_token() for _ in range(50)}
    assert len(tokens) == 50 and all(len(t) >= 43 for t in tokens)
    token = next(iter(tokens))
    assert token_digest(token) == hashlib.sha256(token.encode()).hexdigest()


@pytest.mark.parametrize("value,step,limit,expected", [
    (41.6543, 0.5, 90, 41.75), (-0.8765, 0.5, 180, -0.75), (41.6543, 0.1, 90, 41.65),
    (0.3, 0.1, 90, 0.35), (-0.05, 0.1, 90, -0.05), (41.6543, 1.0, 90, 41.5),
    (90.0, 1.0, 90, 89.5), (-90.0, 1.0, 90, -89.5), (180.0, 0.1, 180, 179.95), (-180.0, 0.5, 180, -179.75),
])
def test_snap_to_grid_cell_centre(value, step, limit, expected):
    assert snap_to_cell_centre(value, step, limit) == expected


@pytest.mark.parametrize("value,step", [(41.6543, 0.1), (-0.8765, 0.5), (12.34, 1.0), (-33.3333, 0.1)])
def test_snapping_matches_frontend_round_to_cell_for_interior_values(value, step):
    frontend = round((math.floor(value / step) * step + step / 2) * 1000) / 1000
    assert snap_to_cell_centre(value, step, 180) == pytest.approx(frontend, abs=1e-9)


def test_snapping_rejects_unsupported_steps():
    with pytest.raises(ValueError):
        snap_to_cell_centre(1.0, 0.25, 90)


@pytest.mark.parametrize("role,tier,consent,expected", [
    ("OWNER", "REGION_ONLY", False, (41.6543, -0.8765, "EXACT")),
    ("EDITOR", "APPROXIMATE", False, (41.6543, -0.8765, "EXACT")),
    ("VIEWER", "APPROXIMATE", False, (41.75, -0.75, "APPROXIMATE")),
    ("REVIEWER", "APPROXIMATE", False, (41.75, -0.75, "APPROXIMATE")),
    ("VIEWER", "REGION_ONLY", False, (None, None, "REGION_ONLY")),
    ("REVIEWER", "REGION_ONLY", True, (41.6543, -0.8765, "EXACT")),
    ("VIEWER", "EXACT", True, (41.6543, -0.8765, "EXACT")),
    ("VIEWER", "UNKNOWN_TIER", False, (None, None, "NONE")),
])
def test_visible_location_by_role_tier_and_consent(role, tier, consent, expected):
    location = visible_location(role=role, privacy_tier=tier, latitude=41.6543, longitude=-0.8765,
                                rounding_deg=0.5, precise_location_consent=consent)
    assert (location.latitude, location.longitude, location.precision) == expected


def test_withheld_or_missing_coordinates_are_never_visible():
    location = visible_location(role="OWNER", privacy_tier="WITHHELD", latitude=None, longitude=None,
                                rounding_deg=None, precise_location_consent=False)
    assert (location.latitude, location.longitude, location.precision) == (None, None, "NONE")


def test_history_redaction_reaches_nested_coordinates():
    changes = {"fields": [{"latitude": 41.6, "longitude": -0.8, "label": "x"}],
               "latitude": {"before": 41.6, "after": 41.7}, "title": {"before": "a", "after": "b"}}
    redacted = redact_coordinates(changes)
    assert redacted["fields"][0] == {"latitude": REDACTED, "longitude": REDACTED, "label": "x"}
    assert redacted["latitude"] == REDACTED and redacted["title"] == {"before": "a", "after": "b"}
    assert "41.6" not in str(redacted)


def field(**overrides):
    return {"label": "Synthetic parcel", "privacy_tier": "APPROXIMATE", "latitude": 41.6543,
            "longitude": -0.8765, "region_label": "Synthetic region", **overrides}


@pytest.mark.parametrize("overrides", [
    {"latitude": 91}, {"longitude": -181}, {"latitude": None},
    {"privacy_tier": "WITHHELD"},
    {"privacy_tier": "EXACT"},
    {"rounding_deg": 0.3},
    {"unexpected": True},
    {"latitude": float("inf")},
])
def test_field_input_rejects_invalid_locations(overrides):
    with pytest.raises(ValidationError):
        FieldInput(**field(**overrides))


def test_field_input_defaults_approximate_rounding_and_accepts_consented_exact():
    assert FieldInput(**field()).rounding_deg == 0.1
    assert FieldInput(**field(privacy_tier="EXACT", precise_location_consent=True)).latitude == 41.6543
    assert FieldInput(**field(privacy_tier="WITHHELD", latitude=None, longitude=None)).latitude is None


@pytest.mark.parametrize("overrides", [
    {"fields": []}, {"incident_end": "2022-04-01"}, {"incident_start": "1800-01-01"},
    {"incident_start": "2999-01-01"}, {"title": "   "},
])
def test_case_create_rejects_invalid_cases(overrides):
    body = {"title": "Synthetic", "incident_start": "2022-05-01", "fields": [field()], **overrides}
    with pytest.raises(ValidationError):
        CaseCreate(**body)


def test_register_request_normalizes_email_and_hides_password_in_repr():
    request = RegisterRequest(email="  Someone@Example.TEST ", password=PASSWORD, display_name="Synthetic")
    assert request.email == "someone@example.test"
    assert PASSWORD not in repr(request)
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password=PASSWORD, display_name="Synthetic")


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_persistent_routes_return_503_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app.dependency_overrides.pop(get_session_factory, None)
    async with _client() as client:
        responses = [
            await client.post("/api/v1/auth/register",
                              json={"email": "a@example.test", "password": PASSWORD, "display_name": "A"}),
            await client.post("/api/v1/auth/login", json={"email": "a@example.test", "password": PASSWORD}),
            await client.get("/api/v1/cases", headers={"Authorization": "Bearer whatever"}),
            await client.get("/api/v1/auth/me"),
        ]
        health = await client.get("/api/health")
    assert [r.status_code for r in responses] == [503, 503, 503, 503]
    assert all(r.json() == {"detail": STORAGE_UNAVAILABLE} for r in responses)
    assert health.status_code == 200


@pytest.mark.asyncio
async def test_unreachable_database_returns_generic_503():
    url = "postgresql+psycopg://synthetic:secret-value@127.0.0.1:1/unreachable?connect_timeout=2"
    factory = session_factory(create_database_engine(url))
    app.dependency_overrides[get_session_factory] = lambda: factory
    try:
        async with _client() as client:
            response = await client.post("/api/v1/auth/login",
                                         json={"email": "a@example.test", "password": PASSWORD})
    finally:
        app.dependency_overrides.pop(get_session_factory, None)
    assert response.status_code == 503
    assert response.json() == {"detail": STORAGE_UNAVAILABLE}
    assert "secret-value" not in response.text and "127.0.0.1" not in response.text


def test_openapi_documents_auth_and_case_routes():
    schema = app.openapi()
    for path in ("/api/v1/auth/login", "/api/v1/cases", "/api/v1/cases/{case_id}/permissions"):
        assert path in schema["paths"]
    components = schema["components"]["schemas"]
    assert {"CaseView", "CaseFieldView", "SessionOut", "HistoryEntry"} <= set(components)
    assert "location_precision" in components["CaseFieldView"]["properties"]
    assert schema["paths"]["/api/v1/cases"]["get"]["security"] == [{"HTTPBearer": []}]
