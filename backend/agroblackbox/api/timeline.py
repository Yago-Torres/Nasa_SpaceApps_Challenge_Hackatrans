"""Forensic case timeline (ABB-10): observed, farmer-reported, hypothesis and missing-data layers.

The timeline places evidence side by side. It never links events causally: ``overlaps_incident``
is a calendar overlap, severity is the documented descriptive rule in
``services.forensics.SEVERITY_RULE`` and hypotheses keep their human-set status.
Provenance never includes request coordinates (see ``api.observations`` for redaction).
"""
from __future__ import annotations

from datetime import date
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Anomaly, Case, Field, Hypothesis, Observation, SourceManifest, utcnow
from ..schemas import Resolution
from ..services.forensics import SEVERITY_LIMITATIONS, SEVERITY_RULE, SEVERITY_RULE_ID
from ..services.metrics import VARIABLES
from .cases import _load
from .deps import CurrentPrincipal, DbSession
from .evidence_dto import (
    DataQuality,
    HypothesisLinks,
    ObservedValue,
    Timeline,
    TimelineEvent,
    TimelineLayer,
    TimelineProvenance,
)
from .observations import departure_view, load_ingestions

router = APIRouter(prefix="/api/v1/cases", tags=["case timeline (ABB-10)"])

SPECS = {spec.key: spec for spec in VARIABLES}
LAYER_ORDER = ("OBSERVED", "FARMER_REPORTED", "HYPOTHESIS", "MISSING_DATA")
LAYER_DESCRIPTIONS = {
    "OBSERVED": "Monthly NASA POWER values and their descriptive anomalies (regional grid cell, not the field).",
    "FARMER_REPORTED": "Information reported by the case team; not independently verified.",
    "HYPOTHESIS": "Candidate explanations with their human evaluation; none is a demonstrated cause.",
    "MISSING_DATA": "Periods or measurements without usable evidence.",
}
FARMER_LIMITATION = "Reported by the case team; not independently verified."
SEVERITY_TEXT = {
    "WITHIN_REFERENCE_SPREAD": "within 1 reference standard deviation of the reference mean",
    "MODERATE_DEPARTURE": "between 1 and 2 reference standard deviations from the reference mean",
    "LARGE_DEPARTURE": "2 or more reference standard deviations from the reference mean",
    "NOT_CLASSIFIED": "not classified",
}


def _event_id(case_id: UUID, name: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"urn:agroblackbox:case:{case_id}:timeline:{name}")


def _incident_window(case: Case) -> tuple[date, date]:
    return case.incident_start, case.incident_end or case.incident_start


def _overlaps(start: date | None, end: date | None, window: tuple[date, date]) -> bool | None:
    if start is None or end is None:
        return None
    return start <= window[1] and end >= window[0]


def _signed(value: float | None, units: str) -> str:
    return "n/a" if value is None else f"{value:+.2f} {units}"


def _manifest_provenance(case: Case, manifest: SourceManifest, fields: dict[UUID, Field],
                         observation: Observation, anomaly: Anomaly, kind: str) -> TimelineProvenance:
    field = fields.get(manifest.field_id) if manifest.field_id else None
    return TimelineProvenance(
        source_kind=kind,
        description=("NASA POWER daily point data aggregated to a calendar month by AGRO BLACK BOX; anomaly "
                     "against the stored reference years."),
        case_id=case.id, source_manifest_id=manifest.id, observation_id=observation.id, anomaly_id=anomaly.id,
        field_id=manifest.field_id, field_label=field.label if field else None, provider=manifest.provider,
        dataset=manifest.dataset, dataset_version=manifest.dataset_version, source_uri=manifest.source_uri,
        retrieved_at=manifest.retrieved_at, checksum_sha256=manifest.checksum_sha256,
        processing_version=manifest.processing_version,
        spatial_resolution=Resolution.model_validate(observation.spatial_resolution),
        temporal_resolution=Resolution.model_validate(observation.temporal_resolution),
    )


def _observation_events(case: Case, manifests: list[SourceManifest], observations: dict[UUID, list[Observation]],
                        anomalies: dict[UUID, Anomaly], fields: dict[UUID, Field]) -> list[TimelineEvent]:
    window = _incident_window(case)
    events: list[TimelineEvent] = []
    for manifest in manifests:
        for observation in observations.get(manifest.id, []):
            anomaly = anomalies.get(observation.id)
            if anomaly is None:  # pragma: no cover - ingestion always stores one anomaly per observation
                continue
            spec = SPECS.get(observation.variable)
            label = spec.label if spec else observation.variable
            month = f"{observation.observed_at:%B %Y}"
            coverage = observation.coverage or {}
            quality = DataQuality(status=coverage.get("status", "missing"), reference_status=anomaly.reference_status,
                                  flags=list(observation.quality_flags or []),
                                  reason=coverage.get("reason"))
            observed = ObservedValue(
                variable=observation.variable, variable_label=label,
                source_parameter=spec.source_parameter if spec else observation.variable, value=observation.value,
                units=observation.units, reference_value=anomaly.reference_value, anomaly=anomaly.value,
                reference_start=anomaly.reference_start.year, reference_end=anomaly.reference_end.year,
                reference_sample_count=anomaly.reference_sample_count,
                reference_standard_deviation=anomaly.reference_standard_deviation,
                reference_minimum=anomaly.reference_minimum, reference_maximum=anomaly.reference_maximum,
            )
            limitations = [*observation.limitations, *anomaly.limitations]
            if manifest.field_id is None:
                limitations.append("The field these values were retrieved for has been removed from the case.")
            common = dict(
                id=anomaly.id, start=observation.period_start, end=observation.period_end,
                overlaps_incident=_overlaps(observation.period_start, observation.period_end, window),
                observed=observed, data_quality=quality,
            )
            if anomaly.value is not None:
                departure = departure_view(observation, anomaly)
                ref = f"{anomaly.reference_start.year}–{anomaly.reference_end.year}"
                events.append(TimelineEvent(
                    **common, kind="OBSERVED", event_type="CLIMATE_ANOMALY",
                    title=f"{label}, {month}: {observation.value:.2f} {observation.units} "
                          f"(anomaly {_signed(anomaly.value, anomaly.units)} vs {ref} mean)",
                    description=(f"Monthly {label.lower()} was {SEVERITY_TEXT[departure.severity]} "
                                 f"(rule {SEVERITY_RULE_ID}). Descriptive comparison only; it does not establish a "
                                 "cause of crop damage."),
                    departure=departure,
                    provenance=_manifest_provenance(case, manifest, fields, observation, anomaly, "OBSERVED"),
                    limitations=[*limitations, *SEVERITY_LIMITATIONS],
                ))
            else:
                reason = coverage.get("reason") if coverage.get("status") != "complete" else None
                reason = reason or "Reference value unavailable (fewer than 3 complete reference years)."
                events.append(TimelineEvent(
                    **common, kind="MISSING_DATA", event_type="DATA_GAP",
                    title=f"{label}, {month}: no anomaly computed",
                    description=f"{reason} No value is substituted.",
                    provenance=_manifest_provenance(case, manifest, fields, observation, anomaly, "MISSING_DATA"),
                    limitations=limitations,
                ))
    return events


def _farmer_events(case: Case) -> list[TimelineEvent]:
    provenance = TimelineProvenance(source_kind="FARMER_REPORTED", description="Case record entered by the case team.",
                                    case_id=case.id, case_version=case.version)
    events = [TimelineEvent(
        id=_event_id(case.id, "incident"), kind="FARMER_REPORTED", event_type="INCIDENT_PERIOD",
        start=case.incident_start, end=case.incident_end, title="Reported incident period",
        description=case.incident_notes or "No incident notes were recorded.", overlaps_incident=True,
        provenance=provenance,
        limitations=[FARMER_LIMITATION] + ([] if case.incident_end else
                                           ["The incident end date was not reported."]),
    )]
    if case.crop_history:
        crops = list(case.crop_history)
        events.append(TimelineEvent(
            id=_event_id(case.id, "crop-history"), kind="FARMER_REPORTED", event_type="CROP_HISTORY",
            start=None, end=None, title="Reported crop history",
            description="Crops reported for this case: " + ", ".join(crops) + ".", overlaps_incident=None,
            crops=crops, provenance=provenance,
            limitations=[FARMER_LIMITATION, "Crop history is undated in the current case record."],
        ))
    return events


def _coverage_gaps(case: Case, manifests: list[SourceManifest]) -> list[TimelineEvent]:
    start, end = _incident_window(case)
    covered = {m.event_year for m in manifests if m.event_year is not None}
    events: list[TimelineEvent] = []
    provenance = TimelineProvenance(source_kind="MISSING_DATA", description="Derived from the stored case evidence.",
                                    case_id=case.id, case_version=case.version)
    for year in range(start.year, end.year + 1):
        if year in covered:
            continue
        events.append(TimelineEvent(
            id=_event_id(case.id, f"no-observations:{year}"), kind="MISSING_DATA", event_type="NO_OBSERVATIONS",
            start=max(start, date(year, 1, 1)), end=min(end, date(year, 12, 31)),
            title=f"No NASA POWER observations stored for {year}",
            description=("No retrieval covers this part of the reported incident period. An OWNER or EDITOR can "
                         "request one; nothing is estimated in the meantime."),
            overlaps_incident=True, provenance=provenance,
            limitations=["Absence of stored observations is not evidence of normal conditions."],
        ))
    events.append(TimelineEvent(
        id=_event_id(case.id, "no-local-measurements"), kind="MISSING_DATA", event_type="NO_LOCAL_MEASUREMENTS",
        start=case.incident_start, end=case.incident_end,
        title="No field-scale measurements recorded",
        description=("The case holds no rain-gauge, soil-moisture, irrigation or crop-stage records; regional NASA "
                     "values cannot replace them."),
        overlaps_incident=True, provenance=provenance,
        limitations=["The current case model has no structured store for local measurements."],
    ))
    return events


def _hypothesis_events(case: Case, hypotheses: list[Hypothesis], active_anomalies: dict[UUID, Anomaly],
                       observation_to_anomaly: dict[UUID, UUID]) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []

    def to_event_ids(ids: list[str], off_timeline: list[UUID]) -> list[UUID]:
        result: list[UUID] = []
        for raw in ids:
            evidence_id = UUID(raw)
            if evidence_id in active_anomalies:
                result.append(evidence_id)
            elif evidence_id in observation_to_anomaly:
                result.append(observation_to_anomaly[evidence_id])
            else:
                off_timeline.append(evidence_id)
        return list(dict.fromkeys(result))

    for hypothesis in hypotheses:
        off: list[UUID] = []
        links = HypothesisLinks(
            status=hypothesis.status,
            supporting_event_ids=to_event_ids(hypothesis.supporting_evidence_ids, off),
            contradicting_event_ids=to_event_ids(hypothesis.contradicting_evidence_ids, off),
            evidence_not_on_timeline=off,
        )
        events.append(TimelineEvent(
            id=hypothesis.id, kind="HYPOTHESIS", event_type="HYPOTHESIS", start=case.incident_start,
            end=case.incident_end, title=hypothesis.title or hypothesis.statement[:120],
            description=f"{hypothesis.statement} (status: {hypothesis.status}).", overlaps_incident=True,
            hypothesis=links,
            provenance=TimelineProvenance(source_kind="HYPOTHESIS", description=(
                "Template hypothesis added by the case team." if hypothesis.origin == "TEMPLATE" else
                "Hypothesis written by the case team."), case_id=case.id, hypothesis_id=hypothesis.id),
            limitations=list(hypothesis.limitations) or ["A hypothesis is not a demonstrated cause."],
        ))
    return events


def build_timeline(db: Session, case: Case) -> Timeline:
    manifests, observations, anomalies = load_ingestions(db, case.id, include_superseded=False)
    fields = {f.id: f for f in db.scalars(select(Field).where(Field.case_id == case.id))}
    hypotheses = list(db.scalars(select(Hypothesis).where(Hypothesis.case_id == case.id)
                                 .order_by(Hypothesis.created_at, Hypothesis.id)))
    active_anomalies = {a.id: a for a in anomalies.values()}
    observation_to_anomaly = {a.observation_id: a.id for a in anomalies.values()}

    events = [
        *_observation_events(case, manifests, observations, anomalies, fields),
        *_farmer_events(case),
        *_hypothesis_events(case, hypotheses, active_anomalies, observation_to_anomaly),
        *_coverage_gaps(case, manifests),
    ]
    events.sort(key=lambda e: (e.start is None, e.start or date.min, LAYER_ORDER.index(e.kind), e.title, str(e.id)))
    counts = {kind: sum(e.kind == kind for e in events) for kind in LAYER_ORDER}
    limitations = [
        "Layers are shown together for comparison; a temporal overlap between events is not evidence of a cause.",
        "OBSERVED events are regional NASA POWER grid-cell values (about ½° × ⅝°), not field measurements.",
        f"Severity labels follow rule {SEVERITY_RULE_ID}, pending scientific review.",
        *SEVERITY_LIMITATIONS,
        "Only the latest retrieval for each field and period is shown; earlier retrievals remain listed by "
        "GET /observations?include_superseded=true.",
    ]
    if case.incident_end is None:
        limitations.append("The incident end date was not reported; overlaps use the start date only.")
    return Timeline(
        case_id=case.id, case_version=case.version, generated_at=utcnow(), incident_start=case.incident_start,
        incident_end=case.incident_end,
        layers=[TimelineLayer(kind=k, description=LAYER_DESCRIPTIONS[k], event_count=counts[k]) for k in LAYER_ORDER],
        events=events, severity_rule=SEVERITY_RULE, limitations=limitations,
    )


@router.get("/{case_id}/timeline", response_model=Timeline)
def case_timeline(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> Timeline:
    """Every member. Events from all layers, oldest first; undated events last."""
    case, _ = _load(db, case_id, principal.user.id)
    return build_timeline(db, case)
