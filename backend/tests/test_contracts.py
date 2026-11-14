import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from agroblackbox.app import app
from agroblackbox.schemas import Case, Field, Observation, Paper, PrivacyTier, Resolution
from agroblackbox.services.literature import PaperRecord


FIELD_ID = UUID("33333333-3333-4333-8333-333333333333")
CASE_ID = UUID("22222222-2222-4222-8222-222222222222")


def case_payload():
    return {
        "schema_version": "1.0",
        "id": str(CASE_ID),
        "title": "Documented drought-stress investigation fixture",
        "incident_start": "2022-05-01",
        "incident_end": "2022-08-31",
        "fields": [
            {
                "schema_version": "1.0",
                "id": str(FIELD_ID),
                "label": "Sanitized fixture field",
                "privacy_tier": "REGION_ONLY",
                "latitude": None,
                "longitude": None,
                "region_label": "Ebro Valley fixture",
                "area_hectares": None,
                "limitations": ["Synthetic location label; not a real farm record"],
            }
        ],
        "crop_history": ["winter wheat", "barley"],
        "incident_notes": "Illustrative fixture, not an observed loss claim.",
        "visibility": "PRIVATE",
        "created_at": "2026-11-14T12:00:00Z",
        "updated_at": "2026-11-14T12:00:00Z",
    }


def test_openapi_contains_all_v1_contract_components_and_fixture_examples():
    schema = app.openapi()
    expected = {
        "Case",
        "Field",
        "SourceManifest",
        "Observation",
        "Anomaly",
        "Hypothesis",
        "Paper",
        "EvidenceClaim",
        "Rotation",
        "Review",
        "Report",
        "ApiError",
    }
    assert schema["info"]["x-agro-contract-version"] == "1.0"
    assert expected <= schema["components"]["schemas"].keys()
    assert schema["components"]["schemas"]["Case"]["example"]["visibility"] == "PRIVATE"
    assert "fixture" in schema["components"]["schemas"]["Case"]["example"]["title"].lower()


def test_case_contract_validates_json_and_forbids_unknown_fields():
    case = Case.model_validate_json(json.dumps(case_payload()))
    assert case.id == CASE_ID
    assert case.fields[0].privacy_tier == PrivacyTier.REGION_ONLY

    invalid = case_payload() | {"causal_diagnosis": "unsupported"}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Case.model_validate(invalid)


def test_private_coordinate_rules_are_enforced():
    with pytest.raises(ValidationError, match="WITHHELD fields cannot expose coordinates"):
        Field(
            id=FIELD_ID,
            label="Private field",
            privacy_tier="WITHHELD",
            latitude=41.6,
            longitude=-0.9,
            region_label="Private region",
        )


def test_missing_observation_value_is_explicitly_nullable_with_units_and_limitations():
    resolution = Resolution(value=1, unit="day", description="Daily UTC value")
    observation = Observation(
        id="44444444-4444-4444-8444-444444444444",
        case_id=CASE_ID,
        source_manifest_id="11111111-1111-4111-8111-111111111111",
        variable="PRECTOTCORR",
        value=None,
        units="mm/day",
        observed_at=datetime(2022, 5, 1, tzinfo=UTC),
        spatial_resolution=Resolution(
            value=0.5,
            unit="degree",
            description="Regional grid, not a parcel reading",
        ),
        temporal_resolution=resolution,
        quality_flags=["MISSING_UPSTREAM_VALUE"],
        limitations=["No field-scale precipitation measurement"],
    )
    assert observation.value is None
    assert observation.source_kind.value == "OBSERVED"


def test_shared_paper_contract_accepts_abb13_bibliographic_semantics():
    route_record = PaperRecord(
        title="Clearly marked bibliographic fixture",
        year=2022,
        doi="https://doi.org/10.1234/example",
        openalex_id="https://openalex.org/W123",
        caveat="Bibliographic fixture only; findings have not been reviewed.",
        doi_id="10.1234/example",
        doi_status="VERIFIED_CROSSREF",
        authors=[{"name": "A. Researcher", "orcid": None}],
        retrievals=[{
            "source": "OpenAlex",
            "endpoint": "https://api.openalex.org/works",
            "record_id": "https://openalex.org/W123",
            "retrieved_at": "2026-11-14T12:00:00Z",
            "http_status": 200,
            "outcome": "success",
        }],
    )
    paper = Paper(
        id="55555555-5555-4555-8555-555555555555",
        **route_record.model_dump(include={
            "title", "year", "doi", "doi_id", "doi_status", "openalex_id", "authors",
            "venue", "publication_type", "licenses", "landing_page_url", "is_open_access",
            "metadata_discrepancies", "retrievals", "processing_version", "source_kind",
            "evidence_status",
        }),
    )
    assert paper.evidence_status == "BIBLIOGRAPHIC_MATCH_ONLY"
    assert paper.authors[0].name == "A. Researcher"
    assert "scientific finding" in paper.limitations[0]


@pytest.mark.asyncio
async def test_existing_api_invalid_input_still_returns_422():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/report", json={})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "location_label"
