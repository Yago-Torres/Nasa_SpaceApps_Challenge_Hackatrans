"""Request/response models for case observations, the forensic timeline and hypotheses (ABB-10).

Responses extend the shared ABB-02 contracts (``SourceManifest``, ``Observation``,
``Anomaly``, ``Hypothesis``) additively. No model carries a probability, confidence
percentage or causal score.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field as PydanticField, JsonValue, StringConstraints, model_validator

from .. import schemas
from ..services.forensics import TEMPLATE_CODES
from .dto import RequestModel, UserSummary

Text500 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
EvaluationStatus = Literal["OPEN", "COMPATIBLE", "CONTRADICTED", "NOT_EVALUABLE"]
TemplateCode = Literal[TEMPLATE_CODES]  # type: ignore[valid-type]
TimelineKind = Literal["OBSERVED", "FARMER_REPORTED", "HYPOTHESIS", "MISSING_DATA"]
TimelineEventType = Literal[
    "CLIMATE_ANOMALY", "INCIDENT_PERIOD", "CROP_HISTORY", "HYPOTHESIS",
    "DATA_GAP", "NO_OBSERVATIONS", "NO_LOCAL_MEASUREMENTS",
]
Severity = Literal["WITHIN_REFERENCE_SPREAD", "MODERATE_DEPARTURE", "LARGE_DEPARTURE", "NOT_CLASSIFIED"]
Direction = Literal["ABOVE_REFERENCE", "BELOW_REFERENCE", "EQUAL_TO_REFERENCE"]
MAX_EVIDENCE_LINKS = 50


# ── observations ─────────────────────────────────────────────────────────────

class NasaPowerIngestRequest(RequestModel):
    """Coordinates are never sent by the client: the server uses the stored field location."""
    field_id: UUID | None = PydanticField(
        default=None, description="Case field to use; optional when exactly one field has stored coordinates")
    event_year: int | None = PydanticField(
        default=None, ge=1981, description="Defaults to the year of the case incident_start")
    reference_start: int | None = PydanticField(default=None, ge=1981)
    reference_end: int | None = PydanticField(default=None, ge=1981)

    @model_validator(mode="after")
    def _reference_pair(self) -> NasaPowerIngestRequest:
        if (self.reference_start is None) != (self.reference_end is None):
            raise ValueError("reference_start and reference_end must be supplied together")
        return self


class ObservationCoverage(schemas.ContractModel):
    status: Literal["complete", "partial", "missing"]
    reason: str | None = None
    expected_days: int
    valid_days: int
    missing_days: int
    fill_value_days: int
    absent_days: int
    invalid_days: int


class DepartureView(schemas.ContractModel):
    """Descriptive label from the documented rule ``rule_id``; not a probability or a cause."""
    rule_id: str
    severity: Severity
    direction: Direction | None
    departure_in_reference_sd: float | None = PydanticField(
        description="Anomaly divided by the reference sample SD; descriptive only, no significance implied")
    outside_reference_range: bool | None
    reason: str | None


class AnomalyView(schemas.Anomaly):
    reference_status: Literal["complete", "reduced", "insufficient"]
    reference_value: float | None
    reference_standard_deviation: float | None
    reference_minimum: float | None
    reference_maximum: float | None
    reference_years_excluded: list[int]
    departure: DepartureView


class ObservationView(schemas.Observation):
    field_id: UUID | None
    variable_label: str
    source_parameter: str
    aggregation: str
    period_start: date | None
    period_end: date | None
    coverage: ObservationCoverage | None
    anomaly: AnomalyView | None


class SourceManifestView(schemas.SourceManifest):
    """Shared manifest. For REVIEWER/VIEWER the coordinates in ``query_parameters`` are REDACTED."""
    field_id: UUID | None
    field_label: str | None
    revision: int
    ingested_at: datetime
    superseded_at: datetime | None
    superseded_by_id: UUID | None
    content_sha256: str | None = PydanticField(
        description="SHA-256 of the canonical returned values only (no coordinates)")
    event_year: int | None
    reference_start: int | None
    reference_end: int | None
    location_redacted: bool
    created_by: UserSummary | None


class IngestionView(schemas.ContractModel):
    source_kind: Literal["OBSERVED"] = "OBSERVED"
    active: bool = PydanticField(description="False when a newer retrieval superseded this one")
    manifest: SourceManifestView
    method: dict[str, JsonValue]
    quality: dict[str, JsonValue]
    upstream: dict[str, JsonValue]
    observations: list[ObservationView]
    limitations: list[str]


class IngestionResult(IngestionView):
    created: bool = PydanticField(description="False when identical data was already stored (nothing new written)")
    superseded_manifest_id: UUID | None = None


class ObservationList(schemas.ContractModel):
    items: list[IngestionView]


# ── hypotheses ───────────────────────────────────────────────────────────────

class VerificationQuestion(RequestModel):
    question: Text500
    why_it_matters: Text500


def _check_links(supporting: list[UUID] | None, contradicting: list[UUID] | None) -> None:
    for name, ids in (("supporting_evidence_ids", supporting), ("contradicting_evidence_ids", contradicting)):
        if ids is not None and len(set(ids)) != len(ids):
            raise ValueError(f"{name} contains duplicates")
    if supporting and contradicting and set(supporting) & set(contradicting):
        raise ValueError("an evidence item cannot both support and contradict the same hypothesis")


class HypothesisCreate(RequestModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    statement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)]
    supporting_evidence_ids: list[UUID] = PydanticField(default_factory=list, max_length=MAX_EVIDENCE_LINKS)
    contradicting_evidence_ids: list[UUID] = PydanticField(default_factory=list, max_length=MAX_EVIDENCE_LINKS)
    missing_evidence: list[Text500] = PydanticField(default_factory=list, max_length=30)
    limitations: list[Text500] = PydanticField(default_factory=list, max_length=20)
    verification_questions: list[VerificationQuestion] = PydanticField(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _links(self) -> HypothesisCreate:
        _check_links(self.supporting_evidence_ids, self.contradicting_evidence_ids)
        return self


class HypothesisUpdate(RequestModel):
    """Partial update. Changing statement, evidence links or missing evidence resets an evaluation to OPEN."""
    version: int = PydanticField(ge=1, description="Current hypothesis version")
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    statement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)] | None = None
    supporting_evidence_ids: list[UUID] | None = PydanticField(default=None, max_length=MAX_EVIDENCE_LINKS)
    contradicting_evidence_ids: list[UUID] | None = PydanticField(default=None, max_length=MAX_EVIDENCE_LINKS)
    missing_evidence: list[Text500] | None = PydanticField(default=None, max_length=30)
    limitations: list[Text500] | None = PydanticField(default=None, max_length=20)
    verification_questions: list[VerificationQuestion] | None = PydanticField(default=None, max_length=20)

    @model_validator(mode="after")
    def _not_null(self) -> HypothesisUpdate:
        for name in ("statement", "supporting_evidence_ids", "contradicting_evidence_ids", "missing_evidence",
                     "limitations", "verification_questions"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        _check_links(self.supporting_evidence_ids, self.contradicting_evidence_ids)
        return self


class HypothesisStatusChange(RequestModel):
    version: int = PydanticField(ge=1, description="Current hypothesis version")
    status: EvaluationStatus
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)] | None = None

    @model_validator(mode="after")
    def _note_required(self) -> HypothesisStatusChange:
        if self.status != "OPEN" and self.note is None:
            raise ValueError("a note explaining the evaluation is required")
        return self


class HypothesisTemplateRequest(RequestModel):
    codes: list[TemplateCode] | None = PydanticField(  # type: ignore[valid-type]
        default=None, description="Templates to add; all when omitted. Already-added templates are skipped")

    @model_validator(mode="after")
    def _unique(self) -> HypothesisTemplateRequest:
        if self.codes is not None and (not self.codes or len(set(self.codes)) != len(self.codes)):
            raise ValueError("codes must be a non-empty list without duplicates")
        return self


class VerificationQuestionView(schemas.ContractModel):
    question: str
    why_it_matters: str


class EvidenceRef(schemas.ContractModel):
    id: UUID
    evidence_type: Literal["ANOMALY", "OBSERVATION", "EVIDENCE_CLAIM", "LOCAL_ANSWER"]
    kind: str = PydanticField(description="Source classification, e.g. OBSERVED or LITERATURE_METADATA")
    label: str
    start: date | None = None
    end: date | None = None
    active: bool = PydanticField(description="False when the evidence belongs to a superseded retrieval")


class HypothesisView(schemas.Hypothesis):
    title: str | None
    origin: Literal["USER", "TEMPLATE"]
    template_code: str | None
    verification_questions: list[VerificationQuestionView]
    evaluation_note: str | None
    evaluated_by: UserSummary | None
    evaluated_at: datetime | None
    version: int
    created_by: UserSummary | None
    created_at: datetime
    updated_at: datetime
    evidence: list[EvidenceRef]


class HypothesisList(schemas.ContractModel):
    items: list[HypothesisView]
    limitations: list[str]


class HypothesisTemplateView(schemas.ContractModel):
    code: str
    source_kind: Literal["HYPOTHESIS"] = "HYPOTHESIS"
    title: str
    statement: str
    related_variables: list[str]
    missing_evidence: list[str]
    verification_questions: list[VerificationQuestionView]
    limitations: list[str]


class HypothesisTemplateCatalog(schemas.ContractModel):
    items: list[HypothesisTemplateView]
    limitations: list[str]


# ── timeline ─────────────────────────────────────────────────────────────────

class TimelineProvenance(schemas.ContractModel):
    source_kind: str = PydanticField(description="OBSERVED, FARMER_REPORTED, HYPOTHESIS or MISSING_DATA")
    description: str
    case_id: UUID
    case_version: int | None = None
    source_manifest_id: UUID | None = None
    observation_id: UUID | None = None
    anomaly_id: UUID | None = None
    hypothesis_id: UUID | None = None
    field_id: UUID | None = None
    field_label: str | None = None
    provider: str | None = None
    dataset: str | None = None
    dataset_version: str | None = None
    source_uri: str | None = None
    retrieved_at: datetime | None = None
    checksum_sha256: str | None = None
    processing_version: str | None = None
    spatial_resolution: schemas.Resolution | None = None
    temporal_resolution: schemas.Resolution | None = None


class ObservedValue(schemas.ContractModel):
    variable: str
    variable_label: str
    source_parameter: str
    value: float | None
    units: str
    reference_value: float | None
    anomaly: float | None
    reference_start: int
    reference_end: int
    reference_sample_count: int
    reference_standard_deviation: float | None
    reference_minimum: float | None
    reference_maximum: float | None


class DataQuality(schemas.ContractModel):
    status: Literal["complete", "partial", "missing"]
    reference_status: Literal["complete", "reduced", "insufficient"]
    flags: list[str]
    reason: str | None


class HypothesisLinks(schemas.ContractModel):
    status: str
    supporting_event_ids: list[UUID]
    contradicting_event_ids: list[UUID]
    evidence_not_on_timeline: list[UUID] = PydanticField(
        description="Linked evidence without a timeline event (literature, or superseded retrievals)")


class TimelineEvent(schemas.ContractModel):
    id: UUID
    kind: TimelineKind
    event_type: TimelineEventType
    start: date | None
    end: date | None
    title: str
    description: str
    overlaps_incident: bool | None = PydanticField(
        description="Temporal overlap with the reported incident period only; not evidence of a cause")
    observed: ObservedValue | None = None
    departure: DepartureView | None = None
    data_quality: DataQuality | None = None
    hypothesis: HypothesisLinks | None = None
    crops: list[str] = PydanticField(default_factory=list)
    provenance: TimelineProvenance
    limitations: list[str] = PydanticField(min_length=1)


class TimelineLayer(schemas.ContractModel):
    kind: TimelineKind
    description: str
    event_count: int


class Timeline(schemas.ContractModel):
    case_id: UUID
    case_version: int
    generated_at: datetime
    incident_start: date
    incident_end: date | None
    layers: list[TimelineLayer]
    events: list[TimelineEvent]
    severity_rule: dict[str, JsonValue]
    limitations: list[str]
