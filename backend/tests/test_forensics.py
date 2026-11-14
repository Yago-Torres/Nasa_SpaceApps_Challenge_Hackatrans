"""ABB-10 tests that need no database: severity rule, templates, request validation, 503 and OpenAPI."""
from __future__ import annotations

import re
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from agroblackbox.api.deps import STORAGE_UNAVAILABLE, get_session_factory
from agroblackbox.api.forensics_dto import (
    HypothesisCreate,
    HypothesisStatusChange,
    HypothesisTemplateRequest,
    HypothesisUpdate,
    NasaPowerIngestRequest,
    TimelineEvent,
)
from agroblackbox.app import app
from agroblackbox.schemas import Hypothesis
from agroblackbox.services.forensics import (
    HYPOTHESIS_TEMPLATES,
    SEVERITY_RULE,
    classify_departure,
    content_sha256,
    default_reference_window,
    ingestion_key,
)

CAUSAL_WORDS = re.compile(r"\b(caused|proven|proof|confirmed|demonstrated that|probability|likelihood|percent)\b",
                          re.IGNORECASE)


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# ── severity rule ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("anomaly,sd,severity,direction,ratio", [
    (0.0, 10.0, "WITHIN_REFERENCE_SPREAD", "EQUAL_TO_REFERENCE", 0.0),
    (9.99, 10.0, "WITHIN_REFERENCE_SPREAD", "ABOVE_REFERENCE", 1.0),  # 0.999 rounds for display only
    (10.0, 10.0, "MODERATE_DEPARTURE", "ABOVE_REFERENCE", 1.0),
    (-19.99, 10.0, "MODERATE_DEPARTURE", "BELOW_REFERENCE", -2.0),
    (-20.0, 10.0, "LARGE_DEPARTURE", "BELOW_REFERENCE", -2.0),
    (-46.5, 10.82, "LARGE_DEPARTURE", "BELOW_REFERENCE", -4.3),
])
def test_departure_thresholds_are_inclusive_at_one_and_two_sd(anomaly, sd, severity, direction, ratio):
    result = classify_departure(anomaly=anomaly, observed=50 + anomaly, reference_sd=sd, reference_min=40,
                                reference_max=60, reference_sample_count=12)
    assert (result.severity, result.direction) == (severity, direction)
    assert result.departure_in_reference_sd == pytest.approx(ratio, abs=1e-9)
    assert result.reason is None


def test_outside_reference_range_is_reported_separately():
    inside = classify_departure(anomaly=5, observed=55, reference_sd=10, reference_min=40, reference_max=60,
                                reference_sample_count=5)
    below = classify_departure(anomaly=-15, observed=35, reference_sd=10, reference_min=40, reference_max=60,
                               reference_sample_count=5)
    assert inside.outside_reference_range is False and below.outside_reference_range is True


@pytest.mark.parametrize("kwargs,reason", [
    (dict(anomaly=None, observed=None, reference_sd=1.0, reference_sample_count=12), "No anomaly"),
    (dict(anomaly=1.0, observed=None, reference_sd=1.0, reference_sample_count=12), "No anomaly"),
    (dict(anomaly=1.0, observed=2.0, reference_sd=None, reference_sample_count=2), "fewer than 3"),
    (dict(anomaly=1.0, observed=2.0, reference_sd=0.0, reference_sample_count=12), "zero spread"),
    (dict(anomaly=float("nan"), observed=2.0, reference_sd=1.0, reference_sample_count=12), "No anomaly"),
])
def test_unclassifiable_departures_say_why(kwargs, reason):
    result = classify_departure(reference_min=None, reference_max=None, **kwargs)
    assert result.severity == "NOT_CLASSIFIED" and reason in result.reason
    assert result.departure_in_reference_sd is None


def test_severity_rule_is_documented_and_non_causal():
    assert SEVERITY_RULE["thresholds_sd"] == {"moderate": 1.0, "large": 2.0}
    assert "Not a probability" in SEVERITY_RULE["interpretation"]
    assert SEVERITY_RULE["review_status"] == "PENDING_SCIENTIFIC_REVIEW"


# ── identity helpers ─────────────────────────────────────────────────────────

def test_content_checksum_ignores_order_and_contains_no_request_parameters():
    a = {"PRECTOTCORR": {"20220101": 1.0, "20220102": 2.0}, "T2M_MAX": {"20220101": 10.0}, "EXTRA": {"x": 1}}
    b = {"T2M_MAX": {"20220101": 10.0}, "PRECTOTCORR": {"20220102": 2.0, "20220101": 1.0}}
    names = ("PRECTOTCORR", "T2M_MAX")
    assert content_sha256(a, names) == content_sha256(b, names)
    changed = {**b, "T2M_MAX": {"20220101": 10.5}}
    assert content_sha256(changed, names) != content_sha256(b, names)


def test_ingestion_key_depends_on_field_and_period_only():
    base = dict(provider="NASA POWER", field_id=str(uuid4()), event_year=2022, reference_start=2010,
                reference_end=2021)
    assert ingestion_key(**base) == ingestion_key(**base)
    assert ingestion_key(**base) != ingestion_key(**{**base, "reference_start": 2011})


@pytest.mark.parametrize("year,expected", [(2022, (2010, 2021)), (1990, (1981, 1989)), (2026, (2014, 2025))])
def test_default_reference_window_is_the_twelve_preceding_years(year, expected):
    assert default_reference_window(year) == expected


# ── templates ────────────────────────────────────────────────────────────────

def test_templates_are_rival_open_questions_without_causal_claims():
    codes = [t["code"] for t in HYPOTHESIS_TEMPLATES]
    assert len(codes) == len(set(codes)) >= 5
    assert {"WATER_DEFICIT", "HEAT_STRESS", "PEST_DISEASE", "MANAGEMENT", "SOIL_LIMITATION"} <= set(codes)
    for item in HYPOTHESIS_TEMPLATES:
        assert "may have contributed" in item["statement"]
        assert item["verification_questions"] and item["missing_evidence"]
        text = " ".join([item["title"], item["statement"], *item["missing_evidence"],
                         *(q["question"] + q["why_it_matters"] for q in item["verification_questions"])])
        assert not CAUSAL_WORDS.search(text), item["code"]


@pytest.mark.asyncio
async def test_template_catalogue_is_served_without_a_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    async with _client() as client:
        response = await client.get("/api/v1/hypothesis-templates")
    assert response.status_code == 200
    body = response.json()
    assert all(item["source_kind"] == "HYPOTHESIS" for item in body["items"])
    assert "not a diagnosis" in " ".join(body["limitations"])
    keys = {key for item in body["items"] for key in item}
    assert not any(re.search(r"probab|score|confidence|rank", key) for key in keys)


# ── request validation ───────────────────────────────────────────────────────

@pytest.mark.parametrize("payload", [
    {"latitude": 41.6, "longitude": -0.9},
    {"reference_start": 2010},
    {"event_year": 1970},
    {"field_id": "not-a-uuid"},
])
def test_ingest_request_never_accepts_coordinates_and_validates_years(payload):
    with pytest.raises(ValidationError):
        NasaPowerIngestRequest.model_validate(payload)


def test_hypothesis_requests_reject_scores_duplicates_and_conflicting_links():
    evidence = uuid4()
    with pytest.raises(ValidationError):
        HypothesisCreate.model_validate({"statement": "x", "probability": 0.8})
    with pytest.raises(ValidationError):
        HypothesisCreate.model_validate({"statement": "x", "status": "SUPPORTED"})
    with pytest.raises(ValidationError, match="both support and contradict"):
        HypothesisCreate.model_validate({"statement": "x", "supporting_evidence_ids": [str(evidence)],
                                         "contradicting_evidence_ids": [str(evidence)]})
    with pytest.raises(ValidationError, match="duplicates"):
        HypothesisCreate.model_validate({"statement": "x", "supporting_evidence_ids": [str(evidence)] * 2})
    with pytest.raises(ValidationError, match="cannot be null"):
        HypothesisUpdate.model_validate({"version": 1, "statement": None})


@pytest.mark.parametrize("payload,ok", [
    ({"version": 1, "status": "COMPATIBLE", "note": "Linked June anomaly is consistent."}, True),
    ({"version": 1, "status": "OPEN"}, True),
    ({"version": 1, "status": "COMPATIBLE"}, False),          # note required
    ({"version": 1, "status": "SUPPORTED", "note": "x"}, False),  # not settable by the case API
    ({"version": 1, "status": "PROVEN", "note": "x"}, False),
    ({"version": 1, "status": "NOT_EVALUABLE", "note": "x", "score": 3}, False),
])
def test_status_change_values(payload, ok):
    if ok:
        assert HypothesisStatusChange.model_validate(payload).status == payload["status"]
    else:
        with pytest.raises(ValidationError):
            HypothesisStatusChange.model_validate(payload)


def test_template_request_rejects_unknown_or_duplicate_codes():
    assert HypothesisTemplateRequest.model_validate({"codes": ["HEAT_STRESS"]}).codes == ["HEAT_STRESS"]
    for codes in (["UNKNOWN"], ["HEAT_STRESS", "HEAT_STRESS"], []):
        with pytest.raises(ValidationError):
            HypothesisTemplateRequest.model_validate({"codes": codes})


def test_shared_hypothesis_contract_change_is_additive():
    base = {"id": str(uuid4()), "case_id": str(uuid4()), "statement": "x", "limitations": ["Candidate only"]}
    for value in ("OPEN", "SUPPORTED", "CHALLENGED", "REJECTED", "COMPATIBLE", "CONTRADICTED", "NOT_EVALUABLE"):
        assert Hypothesis.model_validate({**base, "status": value}).status == value
    with pytest.raises(ValidationError):
        Hypothesis.model_validate({**base, "status": "PROVEN"})
    with pytest.raises(ValidationError):
        Hypothesis.model_validate({**base, "causal_probability": 0.7})


def test_timeline_events_require_limitations():
    with pytest.raises(ValidationError):
        TimelineEvent.model_validate({
            "id": str(uuid4()), "kind": "OBSERVED", "event_type": "CLIMATE_ANOMALY", "start": None, "end": None,
            "title": "t", "description": "d", "overlaps_incident": None,
            "provenance": {"source_kind": "OBSERVED", "description": "d", "case_id": str(uuid4())},
            "limitations": [],
        })


# ── storage boundary and OpenAPI ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_case_evidence_routes_return_503_without_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app.dependency_overrides.pop(get_session_factory, None)
    case_id = uuid4()
    headers = {"Authorization": "Bearer whatever"}
    async with _client() as client:
        responses = [
            await client.post(f"/api/v1/cases/{case_id}/observations/nasa-power", json={}, headers=headers),
            await client.get(f"/api/v1/cases/{case_id}/observations", headers=headers),
            await client.get(f"/api/v1/cases/{case_id}/timeline", headers=headers),
            await client.get(f"/api/v1/cases/{case_id}/hypotheses", headers=headers),
            await client.post(f"/api/v1/cases/{case_id}/hypotheses", json={"statement": "x"}, headers=headers),
        ]
    assert [r.status_code for r in responses] == [503] * 5
    assert all(r.json() == {"detail": STORAGE_UNAVAILABLE} for r in responses)


def test_openapi_documents_timeline_hypothesis_and_observation_routes():
    schema = app.openapi()
    for path in ("/api/v1/cases/{case_id}/observations/nasa-power", "/api/v1/cases/{case_id}/observations",
                 "/api/v1/cases/{case_id}/timeline", "/api/v1/cases/{case_id}/hypotheses",
                 "/api/v1/cases/{case_id}/hypotheses/{hypothesis_id}/status", "/api/v1/hypothesis-templates"):
        assert path in schema["paths"]
    components = schema["components"]["schemas"]
    assert {"Timeline", "TimelineEvent", "HypothesisView", "IngestionResult", "ObservationList"} <= set(components)
    ingest = components["NasaPowerIngestRequest"]["properties"]
    assert "latitude" not in ingest and "longitude" not in ingest
    assert set(components["TimelineEvent"]["properties"]["kind"]["enum"]) == {
        "OBSERVED", "FARMER_REPORTED", "HYPOTHESIS", "MISSING_DATA"}
    names = [*components["HypothesisView"]["properties"], *components["TimelineEvent"]["properties"],
             *components["DepartureView"]["properties"]]
    assert not [n for n in names if re.search(r"probab|score|confidence|likelihood|cause", n)]
