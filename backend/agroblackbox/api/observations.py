"""Case-bound NASA POWER ingestion and observation listing (ABB-10).

- The server reads the field's stored coordinates; clients never send them. They are kept in
  the manifest ``query_parameters`` for reproducibility and are shown to OWNER/EDITOR only.
  REVIEWER/VIEWER receive ``"REDACTED"`` in their place and no upstream free-text messages.
- Nothing is persisted when NASA POWER fails or answers unusable data (HTTP 502).
- Re-ingestion is versioned: one active manifest per (field, event year, reference window).
  Identical returned values with the same processing version are not stored twice
  (200, ``created=false``); changed values create a new revision that supersedes the old one.
- Ingestions are recorded in ``case_history`` without bumping the case version (evidence is
  added alongside the case content, like permission changes in ADR-0004).
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import climate
from ..db.models import Anomaly, Field, Observation, SourceManifest, User, utcnow
from ..privacy import PRECISE_ROLES, redact_coordinates
from ..schemas import Resolution
from ..services import power
from ..services.forensics import (
    SEVERITY_RULE_ID,
    classify_departure,
    content_sha256,
    default_reference_window,
    ingestion_key,
)
from ..services.metrics import METHOD_ID, MIN_REFERENCE_YEARS, VARIABLES, analyze_power, reference_label
from .cases import EDITOR_ROLES, _json, _load, _record, _require_editable, _require_role, _summary
from .deps import CurrentPrincipal, DbSession
from .evidence_dto import (
    AnomalyView,
    DepartureView,
    IngestionResult,
    IngestionView,
    NasaPowerIngestRequest,
    ObservationCoverage,
    ObservationList,
    ObservationView,
    SourceManifestView,
)

router = APIRouter(prefix="/api/v1/cases", tags=["case observations (ABB-10)"])

SPEC_BY_KEY = {spec.key: spec for spec in VARIABLES}
COVERAGE_KEYS = ("status", "reason", "expected_days", "valid_days", "missing_days", "fill_value_days",
                 "absent_days", "invalid_days")
MONTHLY_RESOLUTION = Resolution(
    value=1, unit="month",
    description=("Calendar-month aggregate of NASA POWER daily values on UTC days (precipitation: sum; maximum "
                 "temperature: mean); computed only for months with complete daily coverage."))
ANOMALY_METHOD = f"{METHOD_ID}: event-year monthly value minus the mean of the complete reference months"
LOCATION_LIMITATION = ("Observation values identify the NASA POWER grid cell (about ½° × ⅝°) containing the field; "
                       "collaborators can infer that cell, but not the stored point.")


@dataclass(frozen=True)
class IngestionPlan:
    case_id: UUID
    field_id: UUID
    latitude: float
    longitude: float
    event_year: int
    reference_start: int
    reference_end: int


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(422, detail=message)


def _select_field(db: Session, case_id: UUID, field_id: UUID | None) -> Field:
    if field_id is not None:
        field = db.get(Field, field_id)
        if field is None or field.case_id != case_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Field not found.")
        if field.latitude is None or field.longitude is None:
            raise _unprocessable("This field has no stored coordinates; NASA POWER needs a point location.")
        return field
    located = db.scalars(
        select(Field).where(Field.case_id == case_id, Field.latitude.is_not(None)).order_by(Field.label, Field.id)
    ).all()
    if not located:
        raise _unprocessable("No field of this case has stored coordinates; NASA POWER needs a point location.")
    if len(located) > 1:
        raise _unprocessable("This case has several located fields; send field_id.")
    return located[0]


def _plan(db: Session, case_id: UUID, user_id: UUID, body: NasaPowerIngestRequest) -> IngestionPlan:
    case, role = _load(db, case_id, user_id)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    current_year = date.today().year
    event_year = body.event_year or case.incident_start.year
    if event_year > current_year:
        raise _unprocessable("event_year cannot be in the future.")
    if body.reference_start is None:
        reference_start, reference_end = default_reference_window(event_year)
    else:
        reference_start, reference_end = body.reference_start, body.reference_end  # type: ignore[assignment]
    if reference_end < reference_start or reference_start <= event_year <= reference_end:
        raise _unprocessable("Reference years must be ordered and exclude the event year.")
    if reference_end - reference_start + 1 < MIN_REFERENCE_YEARS:
        raise _unprocessable(f"At least {MIN_REFERENCE_YEARS} reference years are required.")
    if reference_end > current_year:
        raise _unprocessable("Reference years cannot be in the future.")
    field = _select_field(db, case_id, body.field_id)
    plan = IngestionPlan(case.id, field.id, field.latitude, field.longitude, event_year,  # type: ignore[arg-type]
                         reference_start, reference_end)
    db.rollback()  # release the connection while NASA POWER is queried
    return plan


def _observation_limitations(spec_key: str) -> list[str]:
    items = ["Regional ½° × ⅝° NASA POWER grid-cell value, not a field, station or rain-gauge measurement."]
    if spec_key == "precipitation":
        items.append("PRECTOTCORR is a bias-corrected reanalysis precipitation estimate (MERRA-2).")
    items.append("Monthly value from UTC days; null when any day of the month is missing, a fill value or "
                 "implausible.")
    return items


def _anomaly_limitations(n_reference_years: int) -> list[str]:
    return [
        reference_label(n_reference_years),
        "Descriptive difference from the reference mean without significance testing.",
        "An anomaly does not establish a cause of crop damage.",
    ]


def _details(record: power.PowerRecord, analysis: dict[str, Any]) -> dict[str, Any]:
    header = record.header
    return {
        "method": {**analysis["method"], "processing_version": power.PROCESSING_VERSION},
        "quality": analysis["quality"],
        "upstream": {
            "title": header.title, "api_name": header.api_name, "api_version": header.api_version,
            "sources": list(header.sources), "fill_value": header.fill_value, "time_standard": header.time_standard,
            "start": header.start, "end": header.end, "messages": list(record.messages),
            "served_from_cache": record.served_from_cache, "upstream_attempts": record.upstream_attempts,
        },
        "variables": [
            {"key": spec.key, "source_parameter": spec.source_parameter, "monthly_aggregation": spec.aggregation_text,
             "monthly_units": spec.monthly_units,
             "source_units": record.variables[spec.source_parameter].units,
             "units_reported_by_source": record.variables[spec.source_parameter].units_reported_by_source}
            for spec in VARIABLES
        ],
    }


def _persist(db: Session, plan: IngestionPlan, user: User, record: power.PowerRecord,
             analysis: dict[str, Any]) -> tuple[SourceManifest, bool, UUID | None]:
    case, role = _load(db, plan.case_id, user.id, lock=True)
    _require_role(role, EDITOR_ROLES)  # permissions may have changed during the retrieval
    _require_editable(case)
    field = db.get(Field, plan.field_id)
    if field is None or field.case_id != case.id or (field.latitude, field.longitude) != (plan.latitude,
                                                                                            plan.longitude):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="The field changed while NASA POWER was queried; nothing was stored. Retry.")
    key = ingestion_key(provider=power.PROVIDER, field_id=str(field.id), event_year=plan.event_year,
                        reference_start=plan.reference_start, reference_end=plan.reference_end)
    content = content_sha256(record.parameter, power.PARAMETERS)
    active = db.scalar(select(SourceManifest).where(
        SourceManifest.case_id == case.id, SourceManifest.ingestion_key == key, SourceManifest.superseded_at.is_(None)
    ).order_by(SourceManifest.revision.desc()).limit(1))
    if active is not None and active.content_sha256 == content \
            and active.processing_version == power.PROCESSING_VERSION:
        db.rollback()
        return active, False, None

    previous_revision = db.scalar(select(func.max(SourceManifest.revision)).where(
        SourceManifest.case_id == case.id, SourceManifest.ingestion_key == key)) or 0
    method = {**analysis["method"], "processing_version": power.PROCESSING_VERSION}
    header = record.header
    manifest = SourceManifest(
        id=uuid4(), case_id=case.id, provider=power.PROVIDER, dataset=power.DATASET, source_uri=power.BASE,
        query_parameters=dict(record.request_params), retrieved_at=record.retrieved_at,
        checksum_sha256=record.sha256,
        dataset_version=" ".join(p for p in (header.api_name, header.api_version) if p) or None,
        processing_version=power.PROCESSING_VERSION, license=None,
        spatial_resolution=climate.SPATIAL_RESOLUTION.model_dump(),
        temporal_resolution=climate.TEMPORAL_RESOLUTION.model_dump(),
        limitations=[*climate._limitations(record, method), LOCATION_LIMITATION],
        field_id=field.id, created_by_id=user.id, ingested_at=utcnow(), ingestion_key=key, content_sha256=content,
        revision=previous_revision + 1, event_year=plan.event_year, reference_start=plan.reference_start,
        reference_end=plan.reference_end, details=_details(record, analysis),
    )
    db.add(manifest)
    db.flush()
    superseded_id = None
    if active is not None:
        active.superseded_at = utcnow()
        active.superseded_by_id = manifest.id
        superseded_id = active.id

    n_reference = plan.reference_end - plan.reference_start + 1
    pairs: list[tuple[Observation, dict[str, Any], Any, dict[str, Any]]] = []
    for row in analysis["monthly"]:
        month = row["month"]
        last_day = calendar.monthrange(plan.event_year, month)[1]
        for spec in VARIABLES:
            quality = row["quality"][spec.key]
            observation = Observation(
                id=uuid4(), case_id=case.id, source_manifest_id=manifest.id, source_kind="OBSERVED",
                variable=spec.key, value=row[spec.observed_field], units=spec.monthly_units,
                observed_at=datetime(plan.event_year, month, 1, tzinfo=UTC),
                spatial_resolution=climate.SPATIAL_RESOLUTION.model_dump(),
                temporal_resolution=MONTHLY_RESOLUTION.model_dump(), quality_flags=list(quality["flags"]),
                limitations=_observation_limitations(spec.key), period_start=date(plan.event_year, month, 1),
                period_end=date(plan.event_year, month, last_day),
                coverage={name: quality[name] for name in COVERAGE_KEYS},
            )
            pairs.append((observation, row, spec, quality))
    db.add_all([pair[0] for pair in pairs])
    db.flush()
    db.add_all([
        Anomaly(
            case_id=case.id, observation_id=observation.id, value=row[spec.anomaly_field], units=spec.monthly_units,
            method=ANOMALY_METHOD, reference_start=date(plan.reference_start, 1, 1),
            reference_end=date(plan.reference_end, 12, 31),
            reference_sample_count=quality["reference"]["sample_count"],
            reference_status=quality["reference"]["status"], reference_value=row[spec.reference_field],
            reference_standard_deviation=quality["reference"]["standard_deviation"],
            reference_minimum=quality["reference"]["minimum"], reference_maximum=quality["reference"]["maximum"],
            reference_years_excluded=list(quality["reference"]["years_excluded"]),
            quality_flags=list(quality["flags"]), limitations=_anomaly_limitations(n_reference),
        )
        for observation, row, spec, quality in pairs
    ])
    _record(db, case, user, "OBSERVATIONS_INGESTED", {
        "source_manifest_id": str(manifest.id), "field_id": str(field.id), "provider": power.PROVIDER,
        "event_year": plan.event_year, "reference_start": plan.reference_start,
        "reference_end": plan.reference_end, "revision": manifest.revision,
        "superseded_manifest_id": str(superseded_id) if superseded_id else None,
        "observation_count": len(pairs), "content_sha256": content, "checksum_sha256": record.sha256,
        "retrieved_at": _json(record.retrieved_at),
    }, bump=False)
    db.commit()
    return manifest, True, superseded_id


# ── views ────────────────────────────────────────────────────────────────────

def departure_view(observation: Observation, anomaly: Anomaly) -> DepartureView:
    result = classify_departure(
        anomaly=anomaly.value, observed=observation.value, reference_sd=anomaly.reference_standard_deviation,
        reference_min=anomaly.reference_minimum, reference_max=anomaly.reference_maximum,
        reference_sample_count=anomaly.reference_sample_count,
    )
    return DepartureView(rule_id=SEVERITY_RULE_ID, severity=result.severity, direction=result.direction,
                         departure_in_reference_sd=result.departure_in_reference_sd,
                         outside_reference_range=result.outside_reference_range, reason=result.reason)


def _anomaly_view(observation: Observation, anomaly: Anomaly) -> AnomalyView:
    return AnomalyView(
        id=anomaly.id, observation_id=observation.id, value=anomaly.value, units=anomaly.units,
        method=anomaly.method, reference_start=anomaly.reference_start, reference_end=anomaly.reference_end,
        reference_sample_count=anomaly.reference_sample_count, quality_flags=list(anomaly.quality_flags or []),
        limitations=list(anomaly.limitations), reference_status=anomaly.reference_status,
        reference_value=anomaly.reference_value, reference_standard_deviation=anomaly.reference_standard_deviation,
        reference_minimum=anomaly.reference_minimum, reference_maximum=anomaly.reference_maximum,
        reference_years_excluded=list(anomaly.reference_years_excluded or []),
        departure=departure_view(observation, anomaly),
    )


def observation_view(observation: Observation, anomaly: Anomaly | None, field_id: UUID | None) -> ObservationView:
    spec = SPEC_BY_KEY.get(observation.variable)
    return ObservationView(
        id=observation.id, case_id=observation.case_id, source_manifest_id=observation.source_manifest_id,
        variable=observation.variable, value=observation.value, units=observation.units,
        observed_at=observation.observed_at, spatial_resolution=observation.spatial_resolution,
        temporal_resolution=observation.temporal_resolution, quality_flags=list(observation.quality_flags or []),
        limitations=list(observation.limitations), field_id=field_id,
        variable_label=spec.label if spec else observation.variable,
        source_parameter=spec.source_parameter if spec else observation.variable,
        aggregation=spec.aggregation_text if spec else "not documented",
        period_start=observation.period_start, period_end=observation.period_end,
        coverage=ObservationCoverage(**observation.coverage) if observation.coverage else None,
        anomaly=_anomaly_view(observation, anomaly) if anomaly is not None else None,
    )


def _guest_details(details: dict[str, Any]) -> dict[str, Any]:
    """Upstream free text could echo the requested point; guests get the count only."""
    upstream = dict(details.get("upstream") or {})
    messages = upstream.pop("messages", []) or []
    upstream["messages_withheld"] = len(messages)
    return {**details, "upstream": upstream}


def ingestion_view(manifest: SourceManifest, observations: list[Observation], anomalies: dict[UUID, Anomaly],
                   role: str, fields: dict[UUID, Field], users: dict[UUID, User]) -> IngestionView:
    precise = role in PRECISE_ROLES
    query = dict(manifest.query_parameters or {})
    redacted = not precise and any(key in query for key in ("latitude", "longitude"))
    details = dict(manifest.details or {}) if precise else _guest_details(dict(manifest.details or {}))
    field = fields.get(manifest.field_id) if manifest.field_id else None
    limitations = list(manifest.limitations)
    if manifest.field_id is None:
        limitations.append("The field these values were retrieved for has been removed from the case.")
    manifest_view = SourceManifestView(
        id=manifest.id, provider=manifest.provider, dataset=manifest.dataset, source_uri=manifest.source_uri,
        query_parameters=query if precise else redact_coordinates(query), retrieved_at=manifest.retrieved_at,
        checksum_sha256=manifest.checksum_sha256, dataset_version=manifest.dataset_version,
        processing_version=manifest.processing_version, license=manifest.license,
        spatial_resolution=manifest.spatial_resolution, temporal_resolution=manifest.temporal_resolution,
        limitations=limitations, field_id=manifest.field_id, field_label=field.label if field else None,
        revision=manifest.revision, ingested_at=manifest.ingested_at, superseded_at=manifest.superseded_at,
        superseded_by_id=manifest.superseded_by_id, content_sha256=manifest.content_sha256,
        event_year=manifest.event_year, reference_start=manifest.reference_start,
        reference_end=manifest.reference_end, location_redacted=redacted,
        created_by=_summary(users.get(manifest.created_by_id)) if manifest.created_by_id else None,
    )
    ordered = sorted(observations, key=lambda o: (o.observed_at, o.variable))
    return IngestionView(
        active=manifest.superseded_at is None, manifest=manifest_view, method=details.get("method") or {},
        quality=details.get("quality") or {}, upstream=details.get("upstream") or {},
        observations=[observation_view(o, anomalies.get(o.id), manifest.field_id) for o in ordered],
        limitations=limitations,
    )


def load_ingestions(db: Session, case_id: UUID, *, include_superseded: bool,
                    manifest_id: UUID | None = None) -> tuple[
        list[SourceManifest], dict[UUID, list[Observation]], dict[UUID, Anomaly]]:
    query = select(SourceManifest).where(SourceManifest.case_id == case_id)
    if manifest_id is not None:
        query = query.where(SourceManifest.id == manifest_id)
    elif not include_superseded:
        query = query.where(SourceManifest.superseded_at.is_(None))
    manifests = list(db.scalars(query.order_by(SourceManifest.ingested_at.desc(), SourceManifest.id)).all())
    ids = [m.id for m in manifests]
    observations: dict[UUID, list[Observation]] = defaultdict(list)
    anomalies: dict[UUID, Anomaly] = {}
    if ids:
        for observation in db.scalars(select(Observation).where(
                Observation.case_id == case_id, Observation.source_manifest_id.in_(ids))):
            observations[observation.source_manifest_id].append(observation)
        for anomaly in db.scalars(select(Anomaly).join(Observation, Observation.id == Anomaly.observation_id).where(
                Anomaly.case_id == case_id, Observation.source_manifest_id.in_(ids))):
            anomalies[anomaly.observation_id] = anomaly
    return manifests, observations, anomalies


def _context(db: Session, case_id: UUID, manifests: list[SourceManifest]) -> tuple[dict[UUID, Field], dict[UUID, User]]:
    fields = {f.id: f for f in db.scalars(select(Field).where(Field.case_id == case_id))}
    user_ids = {m.created_by_id for m in manifests if m.created_by_id}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    return fields, users


def _single_view(db: Session, manifest: SourceManifest, role: str) -> IngestionView:
    _, observations, anomalies = load_ingestions(db, manifest.case_id, include_superseded=True,
                                                 manifest_id=manifest.id)
    fields, users = _context(db, manifest.case_id, [manifest])
    return ingestion_view(manifest, observations.get(manifest.id, []), anomalies, role, fields, users)


# ── routes ───────────────────────────────────────────────────────────────────

@router.post(
    "/{case_id}/observations/nasa-power", response_model=IngestionResult, status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Identical data already stored; nothing new written", "model": IngestionResult},
               502: {"description": "NASA POWER failed or returned unusable data; nothing stored"}},
)
async def ingest_nasa_power(case_id: UUID, body: NasaPowerIngestRequest, principal: CurrentPrincipal,
                            db: DbSession, response: Response) -> IngestionResult:
    """OWNER/EDITOR. Retrieve NASA POWER daily data for a case field's stored location and store the
    monthly observations and anomalies with their source manifest. The client never sends coordinates."""
    plan = await run_in_threadpool(_plan, db, case_id, principal.user.id, body)
    try:
        record = await power.fetch_power(plan.latitude, plan.longitude, plan.event_year, plan.reference_start,
                                         plan.reference_end)
    except power.PowerSourceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=exc.public_message) from exc
    try:
        analysis = analyze_power(record.parameter, plan.event_year, plan.reference_start, plan.reference_end,
                                 fill_value=record.fill_value)
    except ValueError as exc:  # messages come from metrics.py and contain no upstream data
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"NASA POWER data unusable: {exc}.") from exc
    manifest, created, superseded_id = await run_in_threadpool(_persist, db, plan, principal.user, record, analysis)
    if not created:
        response.status_code = status.HTTP_200_OK
    view = await run_in_threadpool(_single_view, db, manifest, "OWNER")  # caller is OWNER/EDITOR
    return IngestionResult(**view.model_dump(), created=created, superseded_manifest_id=superseded_id)


@router.get("/{case_id}/observations", response_model=ObservationList)
def list_observations(
    case_id: UUID, principal: CurrentPrincipal, db: DbSession,
    include_superseded: bool = Query(default=False, description="Also list retrievals replaced by newer ones"),
) -> ObservationList:
    """Every member. Coordinates in the manifest are REDACTED for REVIEWER/VIEWER."""
    _, role = _load(db, case_id, principal.user.id)
    manifests, observations, anomalies = load_ingestions(db, case_id, include_superseded=include_superseded)
    fields, users = _context(db, case_id, manifests)
    return ObservationList(items=[
        ingestion_view(m, observations.get(m.id, []), anomalies, role, fields, users) for m in manifests
    ])
