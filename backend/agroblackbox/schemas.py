"""Versioned, provider-neutral data contracts for the AGRO BLACK BOX 1.0 API.

These schemas describe the target shared contract. Existing ``/api/*`` routes remain
compatible until their implementation is migrated through the relevant roadmap Issue.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field as PydanticField,
    HttpUrl,
    JsonValue,
    model_validator,
)
from pydantic.json_schema import models_json_schema


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VersionedContract(ContractModel):
    schema_version: Literal["1.0"] = "1.0"


class SourceKind(str, Enum):
    OBSERVED = "OBSERVED"
    FARMER_REPORTED = "FARMER_REPORTED"
    LITERATURE_METADATA = "LITERATURE_METADATA"
    LITERATURE_REVIEWED = "LITERATURE_REVIEWED"
    HYPOTHESIS = "HYPOTHESIS"
    MODEL_SCENARIO = "MODEL_SCENARIO"
    ILLUSTRATIVE = "ILLUSTRATIVE"


class PrivacyTier(str, Enum):
    EXACT = "EXACT"
    APPROXIMATE = "APPROXIMATE"
    REGION_ONLY = "REGION_ONLY"
    WITHHELD = "WITHHELD"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REJECTED = "REJECTED"


class Resolution(ContractModel):
    value: float | None = PydanticField(default=None, ge=0)
    unit: str = PydanticField(min_length=1, max_length=40)
    description: str = PydanticField(min_length=1, max_length=500)


class SourceManifest(VersionedContract):
    id: UUID
    provider: str = PydanticField(min_length=1, max_length=120)
    dataset: str = PydanticField(min_length=1, max_length=200)
    source_uri: HttpUrl
    query_parameters: dict[str, JsonValue]
    retrieved_at: datetime
    checksum_sha256: str = PydanticField(pattern=r"^[0-9a-f]{64}$")
    dataset_version: str | None = PydanticField(default=None, max_length=120)
    processing_version: str = PydanticField(min_length=1, max_length=120)
    license: str | None = PydanticField(default=None, max_length=200)
    spatial_resolution: Resolution
    temporal_resolution: Resolution
    limitations: list[str] = PydanticField(min_length=1)

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "schema_version": "1.0",
                "id": "11111111-1111-4111-8111-111111111111",
                "provider": "NASA POWER",
                "dataset": "POWER Daily Point Meteorology",
                "source_uri": "https://power.larc.nasa.gov/api/temporal/daily/point",
                "query_parameters": {"community": "AG", "time-standard": "UTC"},
                "retrieved_at": "2026-11-14T12:00:00Z",
                "checksum_sha256": "a" * 64,
                "dataset_version": None,
                "processing_version": "agroblackbox-0.1.0",
                "license": "NASA data policy applies",
                "spatial_resolution": {
                    "value": 0.5,
                    "unit": "degree",
                    "description": "Gridded regional product; not a parcel measurement",
                },
                "temporal_resolution": {
                    "value": 1,
                    "unit": "day",
                    "description": "Daily values in UTC",
                },
                "limitations": ["Spatial support is coarser than an agricultural field"],
            }
        },
    )


class Field(VersionedContract):
    id: UUID
    label: str = PydanticField(min_length=1, max_length=160)
    privacy_tier: PrivacyTier
    latitude: float | None = PydanticField(default=None, ge=-90, le=90)
    longitude: float | None = PydanticField(default=None, ge=-180, le=180)
    region_label: str = PydanticField(min_length=1, max_length=160)
    area_hectares: float | None = PydanticField(default=None, gt=0)
    limitations: list[str] = PydanticField(default_factory=list)

    @model_validator(mode="after")
    def coordinates_are_a_pair(self) -> Field:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        if self.privacy_tier == PrivacyTier.EXACT and self.latitude is None:
            raise ValueError("EXACT fields require coordinates")
        if self.privacy_tier == PrivacyTier.WITHHELD and self.latitude is not None:
            raise ValueError("WITHHELD fields cannot expose coordinates")
        return self


class Case(VersionedContract):
    id: UUID
    title: str = PydanticField(min_length=1, max_length=200)
    incident_start: date
    incident_end: date | None = None
    fields: list[Field] = PydanticField(min_length=1)
    crop_history: list[str] = PydanticField(default_factory=list)
    incident_notes: str | None = PydanticField(default=None, max_length=10_000)
    visibility: Literal["PRIVATE", "SHARED", "PUBLIC_ROUNDED"] = "PRIVATE"
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def dates_are_ordered(self) -> Case:
        if self.incident_end is not None and self.incident_end < self.incident_start:
            raise ValueError("incident_end cannot precede incident_start")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "schema_version": "1.0",
                "id": "22222222-2222-4222-8222-222222222222",
                "title": "Documented drought-stress investigation fixture",
                "incident_start": "2022-05-01",
                "incident_end": "2022-08-31",
                "fields": [
                    {
                        "schema_version": "1.0",
                        "id": "33333333-3333-4333-8333-333333333333",
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
        },
    )


class Observation(VersionedContract):
    id: UUID
    case_id: UUID
    source_manifest_id: UUID
    source_kind: Literal[SourceKind.OBSERVED] = SourceKind.OBSERVED
    variable: str = PydanticField(min_length=1, max_length=120)
    value: float | None
    units: str = PydanticField(min_length=1, max_length=40)
    observed_at: datetime
    spatial_resolution: Resolution
    temporal_resolution: Resolution
    quality_flags: list[str] = PydanticField(default_factory=list)
    limitations: list[str] = PydanticField(min_length=1)


class Anomaly(VersionedContract):
    id: UUID
    observation_id: UUID
    value: float | None
    units: str = PydanticField(min_length=1, max_length=40)
    method: str = PydanticField(min_length=1, max_length=300)
    reference_start: date
    reference_end: date
    reference_sample_count: int = PydanticField(ge=0)
    quality_flags: list[str] = PydanticField(default_factory=list)
    limitations: list[str] = PydanticField(min_length=1)

    @model_validator(mode="after")
    def reference_dates_are_ordered(self) -> Anomaly:
        if self.reference_end < self.reference_start:
            raise ValueError("reference_end cannot precede reference_start")
        return self


# ABB-10 (additive, contract 1.0): COMPATIBLE / CONTRADICTED / NOT_EVALUABLE are the
# evidence-evaluation states used by the case-bound hypothesis API. None of them means a
# demonstrated cause. The original values stay valid for compatibility; the case API never
# sets SUPPORTED, CHALLENGED or REJECTED (see docs/science/TIMELINE_HYPOTHESES.md).
HypothesisStatus = Literal[
    "OPEN", "SUPPORTED", "CHALLENGED", "REJECTED", "COMPATIBLE", "CONTRADICTED", "NOT_EVALUABLE"
]
HYPOTHESIS_STATUSES: tuple[str, ...] = (
    "OPEN", "SUPPORTED", "CHALLENGED", "REJECTED", "COMPATIBLE", "CONTRADICTED", "NOT_EVALUABLE"
)


class Hypothesis(VersionedContract):
    id: UUID
    case_id: UUID
    source_kind: Literal[SourceKind.HYPOTHESIS] = SourceKind.HYPOTHESIS
    statement: str = PydanticField(min_length=1, max_length=2_000)
    supporting_evidence_ids: list[UUID] = PydanticField(default_factory=list)
    contradicting_evidence_ids: list[UUID] = PydanticField(default_factory=list)
    missing_evidence: list[str] = PydanticField(default_factory=list)
    limitations: list[str] = PydanticField(min_length=1)
    status: HypothesisStatus = "OPEN"


class PaperAuthor(ContractModel):
    name: str = PydanticField(min_length=1, max_length=500)
    orcid: HttpUrl | None = None


class PaperLicense(ContractModel):
    value: str = PydanticField(min_length=1, max_length=500)
    reported_by: Literal["OpenAlex", "Crossref"]
    content_version: str | None = PydanticField(default=None, max_length=120)


class PaperRetrieval(ContractModel):
    source: Literal["OpenAlex", "Crossref"]
    endpoint: HttpUrl
    record_id: str | None = PydanticField(default=None, max_length=500)
    retrieved_at: datetime
    http_status: int | None = PydanticField(default=None, ge=100, le=599)
    outcome: str = PydanticField(min_length=1, max_length=120)


class Paper(VersionedContract):
    id: UUID
    source_kind: Literal[SourceKind.LITERATURE_METADATA] = SourceKind.LITERATURE_METADATA
    evidence_status: Literal["BIBLIOGRAPHIC_MATCH_ONLY"] = "BIBLIOGRAPHIC_MATCH_ONLY"
    title: str = PydanticField(min_length=1, max_length=1_000)
    year: int | None = PydanticField(default=None, ge=1600, le=2200)
    doi: HttpUrl | None = None
    doi_id: str | None = PydanticField(default=None, max_length=300)
    doi_status: Literal[
        "VERIFIED_CROSSREF",
        "METADATA_MISMATCH",
        "NOT_FOUND_IN_CROSSREF",
        "VERIFICATION_UNAVAILABLE",
        "MALFORMED_DOI",
        "NO_DOI",
    ]
    openalex_id: HttpUrl | None = None
    authors: list[PaperAuthor] = PydanticField(default_factory=list)
    venue: str | None = PydanticField(default=None, max_length=500)
    publication_type: str | None = PydanticField(default=None, max_length=120)
    licenses: list[PaperLicense] = PydanticField(default_factory=list)
    landing_page_url: HttpUrl | None = None
    is_open_access: bool | None = None
    metadata_discrepancies: list[str] = PydanticField(default_factory=list)
    retrievals: list[PaperRetrieval] = PydanticField(min_length=1)
    processing_version: str = PydanticField(min_length=1, max_length=120)
    source_manifest_id: UUID | None = None
    limitations: list[str] = PydanticField(
        default_factory=lambda: ["Bibliographic metadata does not establish a scientific finding"]
    )


class EvidenceClaim(VersionedContract):
    id: UUID
    paper_id: UUID
    source_kind: SourceKind
    claim_text: str = PydanticField(min_length=1, max_length=5_000)
    study_context: str = PydanticField(min_length=1, max_length=5_000)
    review_status: ReviewStatus = ReviewStatus.PENDING
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    limitations: list[str] = PydanticField(min_length=1)

    @model_validator(mode="after")
    def reviewed_claims_have_a_reviewer(self) -> EvidenceClaim:
        if self.source_kind not in {
            SourceKind.LITERATURE_METADATA,
            SourceKind.LITERATURE_REVIEWED,
        }:
            raise ValueError("evidence claims must be literature metadata or reviewed literature")
        if self.source_kind == SourceKind.LITERATURE_REVIEWED:
            if self.reviewed_by is None or self.reviewed_at is None:
                raise ValueError("reviewed literature requires reviewer identity and timestamp")
            if self.review_status == ReviewStatus.PENDING:
                raise ValueError("reviewed literature cannot have PENDING review status")
        return self


class Rotation(VersionedContract):
    id: UUID
    case_id: UUID
    source_kind: Literal[SourceKind.MODEL_SCENARIO, SourceKind.ILLUSTRATIVE]
    name: str = PydanticField(min_length=1, max_length=200)
    years: list[list[str]] = PydanticField(min_length=1)
    is_current: bool = False
    assumptions: list[str] = PydanticField(min_length=1)
    constraints: list[str] = PydanticField(default_factory=list)
    verified_impact: None = None
    limitations: list[str] = PydanticField(min_length=1)


class Review(VersionedContract):
    id: UUID
    case_id: UUID
    reviewer_id: UUID
    status: ReviewStatus
    comment: str = PydanticField(min_length=1, max_length=10_000)
    created_at: datetime
    target_kind: Literal["CASE", "HYPOTHESIS", "EVIDENCE_CLAIM", "ROTATION", "REPORT"]
    target_id: UUID


class Report(VersionedContract):
    id: UUID
    case_id: UUID
    version: int = PydanticField(ge=1)
    generated_at: datetime
    status: Literal["PRELIMINARY", "REVIEWED"] = "PRELIMINARY"
    format: Literal["MARKDOWN", "PDF", "JSON"]
    content_uri: HttpUrl | None = None
    checksum_sha256: str | None = PydanticField(default=None, pattern=r"^[0-9a-f]{64}$")
    source_manifest_ids: list[UUID] = PydanticField(default_factory=list)
    limitations: list[str] = PydanticField(min_length=1)


class ApiError(VersionedContract):
    code: str = PydanticField(min_length=1, max_length=80)
    message: str = PydanticField(min_length=1, max_length=1_000)
    details: list[dict[str, JsonValue]] = PydanticField(default_factory=list)


CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    Resolution,
    SourceManifest,
    Field,
    Case,
    Observation,
    Anomaly,
    Hypothesis,
    Paper,
    EvidenceClaim,
    Rotation,
    Review,
    Report,
    ApiError,
)


def contract_openapi_schemas() -> dict[str, Any]:
    """Return shared schemas using FastAPI's component reference namespace."""
    _, schema = models_json_schema(
        [(model, "validation") for model in CONTRACT_MODELS],
        title="AGRO BLACK BOX 1.0 shared contracts",
        ref_template="#/components/schemas/{model}",
    )
    return schema.get("$defs", {})
