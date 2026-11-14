"""Versioned, verifiable case reports and exports (ABB-26).

``POST /api/v1/cases/{id}/reports`` reads the case as it is stored *now*, builds a snapshot, renders it as
Markdown and HTML and stores all three as an immutable version (a database trigger rejects later changes).
Each version records its time, the case version it came from, one SHA-256 over every source manifest used,
the hashes of its three representations and the list of relevant changes against the previous version.

Privacy: a report is a shareable document, so it never contains exact coordinates, the generalised cell,
free-text incident notes, e-mail addresses, member names or comment text, whatever the role of the person
who generates or downloads it. Source endpoints lose their query string and only period/variable request
parameters are kept. A final guard removes any stored coordinate value that still appears as text.

Roles: OWNER, EDITOR and REVIEWER generate; every member lists, downloads and verifies.
PDF is not produced (no new dependency, ADR required); the HTML has print styles for "Save as PDF".
"""
from __future__ import annotations

import calendar
from collections import Counter
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import Field as PydanticField
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..db.models import (
    Anomaly, Case, CaseComment, CasePermission, EvidenceClaim, EvidenceConclusion, Field, Hypothesis, Observation,
    Paper, Report, Rotation, SourceManifest, User, utcnow,
)
from ..services import case_report as cr
from ..services.rotations import RotationCompareRequest, RotationComparison, compare_rotations
from .cases import _load, _record, _require_role, _summary
from .deps import CurrentPrincipal, DbSession
from .dto import RequestModel, UserSummary
from .observations import departure_view

router = APIRouter(prefix="/api/v1/cases", tags=["case reports (ABB-26)"])

GENERATOR_ROLES = frozenset({"OWNER", "EDITOR", "REVIEWER"})
REPORT_NOT_FOUND = "Report version not found."
MAX_VERSIONS = 200
DownloadFormat = Literal["markdown", "html", "json"]
_MEDIA = {"markdown": ("text/markdown; charset=utf-8", "md"), "html": ("text/html; charset=utf-8", "html"),
          "json": ("application/json", "json")}


class ReportCreate(RequestModel):
    rotation: RotationCompareRequest | None = PydanticField(
        default=None,
        description="Optional farmer-declared profile. The server runs the deterministic ABB-17 comparison on it "
                    "and embeds the result with the hash of the input; client-computed rotations are never accepted.")


class ReportView(schemas.ContractModel):
    id: UUID
    case_id: UUID
    version: int
    generated_at: datetime
    status: Literal["PRELIMINARY", "REVIEWED"]
    case_version: int | None
    generated_by: UserSummary | None
    formats: list[str]
    checksum_sha256: str | None = PydanticField(description="SHA-256 of the Markdown text")
    html_sha256: str | None
    snapshot_sha256: str | None
    sources_sha256: str | None = PydanticField(description="One hash over every source manifest ID and checksum")
    source_manifest_ids: list[str]
    changes: dict[str, Any] | None
    limitations: list[str]
    downloads: dict[str, str]


class ReportList(schemas.ContractModel):
    items: list[ReportView]


class VerifyResult(schemas.ContractModel):
    version: int
    valid: bool
    checks: dict[str, bool]
    detail: str


# ── snapshot assembly ────────────────────────────────────────────────────────

def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _res(value: Any) -> str | None:
    if isinstance(value, dict):
        text = value.get("description") or value.get("label")
        return str(text) if text else cr.canonical_json(value)
    return str(value) if value else None


def _fields(db: Session, case_id: UUID) -> tuple[list[Field], list[dict[str, Any]]]:
    rows = list(db.scalars(select(Field).where(Field.case_id == case_id).order_by(Field.label, Field.id)))
    out = []
    for n, f in enumerate(rows, start=1):
        shared = f.privacy_tier != "WITHHELD"
        out.append({
            "id": str(f.id), "ref": f"Parcel {n}", "region_label": f.region_label if shared else None,
            "privacy_tier": f.privacy_tier, "area_hectares": f.area_hectares,
            "location_note": "region label only; coordinates and grid cell withheld" if shared else "withheld",
        })
    return rows, out


def _sources_and_observations(db: Session, case_id: UUID) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifests = list(db.scalars(select(SourceManifest).where(SourceManifest.case_id == case_id)
                                .order_by(SourceManifest.ingested_at, SourceManifest.revision, SourceManifest.id)))
    sources = [{
        "id": str(m.id), "provider": m.provider, "dataset": m.dataset, "source_uri": cr.safe_source_uri(m.source_uri),
        "query": cr.safe_query(m.query_parameters), "retrieved_at": _iso(m.retrieved_at),
        "checksum_sha256": m.checksum_sha256, "content_sha256": m.content_sha256, "dataset_version": m.dataset_version,
        "processing_version": m.processing_version, "license": m.license, "revision": m.revision,
        "superseded": m.superseded_at is not None, "superseded_by_id": str(m.superseded_by_id) if m.superseded_by_id else None,
        "event_year": m.event_year, "reference_start": m.reference_start, "reference_end": m.reference_end,
        "spatial_resolution": _res(m.spatial_resolution), "temporal_resolution": _res(m.temporal_resolution),
        "limitations": [str(x) for x in (m.limitations or [])],
    } for m in manifests]
    current = {m.id for m in manifests if m.superseded_at is None}
    observations: list[dict[str, Any]] = []
    if current:
        rows = db.execute(select(Observation, Anomaly).outerjoin(Anomaly, Anomaly.observation_id == Observation.id)
                          .where(Observation.case_id == case_id, Observation.source_manifest_id.in_(current))
                          .order_by(Observation.source_manifest_id, Observation.observed_at, Observation.variable)).all()
        for o, a in rows:
            dep = departure_view(o, a) if a is not None else None
            observations.append({
                "id": str(o.id), "source_id": str(o.source_manifest_id), "variable": o.variable,
                "label": o.variable.replace("_", " "), "month": calendar.month_abbr[o.observed_at.month] + f" {o.observed_at.year}",
                "value": o.value, "units": o.units, "anomaly": a.value if a else None,
                "reference_value": a.reference_value if a else None,
                "reference_sample_count": a.reference_sample_count if a else 0,
                "reference_status": a.reference_status if a else "none",
                "departure": f"{dep.severity} {dep.direction or ''}".strip() if dep else None,
                "flags": list(o.quality_flags or []),
            })
    return sources, observations


def _hypotheses(db: Session, case_id: UUID) -> list[dict[str, Any]]:
    return [{
        "id": str(h.id), "title": h.title or h.statement[:80], "statement": h.statement, "status": h.status,
        "origin": h.origin, "supporting_count": len(h.supporting_evidence_ids or []),
        "contradicting_count": len(h.contradicting_evidence_ids or []), "evaluation_note": h.evaluation_note,
        "missing_evidence": [str(x) for x in (h.missing_evidence or [])],
        "limitations": [str(x) for x in (h.limitations or [])], "version": h.version,
    } for h in db.scalars(select(Hypothesis).where(Hypothesis.case_id == case_id)
                          .order_by(Hypothesis.created_at, Hypothesis.id))]


def _claims(db: Session, case_id: UUID) -> list[dict[str, Any]]:
    rows = db.execute(select(EvidenceClaim, Paper).join(Paper, Paper.id == EvidenceClaim.paper_id)
                      .where(EvidenceClaim.case_id == case_id)
                      .order_by(EvidenceClaim.created_at, EvidenceClaim.id)).all()
    return [{
        "id": str(c.id), "claim_text": c.claim_text, "review_status": c.review_status,
        "evidence_class": "LITERATURE_REVIEWED" if c.review_status == "ACCEPTED" else "LITERATURE_METADATA",
        "paper_id": str(p.id), "paper_title": p.title, "paper_year": p.year, "doi": p.doi_id,
        "doi_url": cr.doi_url(p.doi_id), "doi_status": p.doi_status, "openalex_id": p.openalex_id,
        "study_design": c.study_design, "evidence_basis": c.evidence_basis, "version": c.version,
        "limitations": [str(x) for x in (c.limitations or [])],
    } for c, p in rows]


def _conclusions(db: Session, case_id: UUID) -> list[dict[str, Any]]:
    return [{
        "id": str(c.id), "title": c.title or c.statement[:80], "statement": c.statement,
        "review_status": c.review_status, "review_note": c.review_note, "version": c.version,
        "limitations": [str(x) for x in (c.limitations or [])],
    } for c in db.scalars(select(EvidenceConclusion).where(EvidenceConclusion.case_id == case_id)
                          .order_by(EvidenceConclusion.created_at, EvidenceConclusion.id))]


def _rotation_section(request: RotationCompareRequest | None) -> dict[str, Any] | None:
    if request is None:
        return None
    result: RotationComparison = compare_rotations(request)
    strategies = []
    for st in result.strategies:
        conflicts = [f"{c.constraint}: {c.status} — {c.detail}" for c in st.constraint_checks
                     if c.status != "SATISFIED"]
        conflicts += [f"Transition {t.from_crop} → {t.to_crop}: {t.status} — {t.message}"
                      for t in st.transitions if t.status in ("INCOMPATIBLE", "TIGHT")]
        conflicts += [f"Review required: {x}" for x in st.conditions_requiring_review]
        strategies.append({
            "id": st.id, "name": st.name, "strategy_kind": st.strategy_kind, "is_current": st.is_current,
            "sequence_origin": st.sequence_origin, "selection_rule": st.selection_rule, "years": st.years,
            "screening_result": st.screening_result, "conflicts": conflicts, "risks": list(st.risks),
            "possible_benefits": list(st.possible_benefits), "limitations": list(st.limitations),
            "evidence_refs": [{"title": e.title, "doi": e.doi} for e in st.evidence_refs],
        })
    return {
        "status": result.status, "horizon_years": result.horizon_years, "rule_set_version": result.rule_set_version,
        "catalog_version": result.catalog_version, "strategies": strategies, "limitations": list(result.limitations),
        "input_sha256": cr.sha256_text(cr.canonical_json(request.model_dump(mode="json"))),
    }


def _recorded_rotations(db: Session, case_id: UUID) -> list[dict[str, Any]]:
    return [{"id": str(r.id), "name": r.name, "source_kind": r.source_kind, "years": r.years,
             "assumptions": list(r.assumptions or []), "limitations": list(r.limitations or [])}
            for r in db.scalars(select(Rotation).where(Rotation.case_id == case_id).order_by(Rotation.name, Rotation.id))]


def _collaboration(db: Session, case_id: UUID, claims: list[EvidenceClaim], conclusions: list[EvidenceConclusion]) -> dict[str, Any]:
    roles = Counter(db.scalars(select(CasePermission.role).where(CasePermission.case_id == case_id)))
    comments = db.scalar(select(func.count()).select_from(CaseComment).where(
        CaseComment.case_id == case_id, CaseComment.deleted_at.is_(None))) or 0
    reviewed = [c for c in claims if c.review_status != "PENDING"]
    return {"members_by_role": dict(roles), "comments": comments, "claims_reviewed": len(reviewed),
            "distinct_claim_reviewers": len({c.reviewed_by for c in reviewed if c.reviewed_by}),
            "conclusions_reviewed": sum(1 for c in conclusions if c.review_status != "PENDING")}


def build_snapshot(db: Session, case: Case, rotation: RotationCompareRequest | None) -> dict[str, Any]:
    """Everything a report says, as plain JSON-safe data (no version/time/changes yet)."""
    field_rows, fields = _fields(db, case.id)
    sources, observations = _sources_and_observations(db, case.id)
    claim_rows = list(db.scalars(select(EvidenceClaim).where(EvidenceClaim.case_id == case.id)))
    conclusion_rows = list(db.scalars(select(EvidenceConclusion).where(EvidenceConclusion.case_id == case.id)))
    snapshot: dict[str, Any] = {
        "schema": cr.SCHEMA,
        "case": {"id": str(case.id), "title": case.title, "status": case.status, "case_version": case.version,
                 "incident_start": case.incident_start.isoformat(), "incident_end": _iso(case.incident_end),
                 "crop_history": [str(x) for x in (case.crop_history or [])]},
        "fields": fields, "sources": sources, "observations": observations,
        "hypotheses": _hypotheses(db, case.id), "claims": _claims(db, case.id),
        "conclusions": _conclusions(db, case.id), "rotations": _rotation_section(rotation),
        "recorded_rotations": _recorded_rotations(db, case.id),
        "collaboration": _collaboration(db, case.id, claim_rows, conclusion_rows),
        "source_hash": cr.sources_hash(sources),
        "limitations": list(cr.REPORT_LIMITATIONS),
        "privacy": {"coordinates_included": False, "incident_notes_included": False, "guard_removed": 0},
    }
    forbidden = [x for f in field_rows for x in (f.latitude, f.longitude)]
    scrubbed, hits = cr.scrub_coordinates(snapshot, forbidden)
    scrubbed["privacy"]["guard_removed"] = hits
    return scrubbed


# ── persistence ──────────────────────────────────────────────────────────────

def _view(report: Report, users: dict[UUID, User]) -> ReportView:
    base = f"/api/v1/cases/{report.case_id}/reports/{report.version}"
    return ReportView(
        id=report.id, case_id=report.case_id, version=report.version, generated_at=report.generated_at,
        status=report.status, case_version=report.case_version,
        generated_by=_summary(users.get(report.generated_by_id)) if report.generated_by_id else None,
        formats=["markdown", "html", "json"], checksum_sha256=report.checksum_sha256, html_sha256=report.html_sha256,
        snapshot_sha256=report.snapshot_sha256, sources_sha256=report.sources_sha256,
        source_manifest_ids=list(report.source_manifest_ids or []), changes=report.changes,
        limitations=list(report.limitations), downloads={f: f"{base}/download?format={f}" for f in _MEDIA},
    )


def _users(db: Session, reports: list[Report]) -> dict[UUID, User]:
    ids = {r.generated_by_id for r in reports if r.generated_by_id}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


def _get(db: Session, case_id: UUID, version: int) -> Report:
    report = db.scalar(select(Report).where(Report.case_id == case_id, Report.version == version))
    if report is None or report.snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=REPORT_NOT_FOUND)
    return report


@router.post("/{case_id}/reports", response_model=ReportView, status_code=status.HTTP_201_CREATED)
def create_report(case_id: UUID, body: ReportCreate, principal: CurrentPrincipal, db: DbSession) -> ReportView:
    """Store a new immutable report version built from the case as it is now."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, GENERATOR_ROLES)
    previous = db.scalar(select(Report).where(Report.case_id == case_id, Report.snapshot.is_not(None))
                         .order_by(Report.version.desc()).limit(1))
    version = (db.scalar(select(func.max(Report.version)).where(Report.case_id == case_id)) or 0) + 1
    if version > MAX_VERSIONS:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"A case can hold at most {MAX_VERSIONS} report versions.")
    now = utcnow()
    snapshot = build_snapshot(db, case, body.rotation)
    snapshot["report"] = {"version": version, "generated_at": now.isoformat(), "status": "PRELIMINARY",
                          "previous_version": previous.version if previous else None}
    snapshot["fingerprints"] = cr.make_fingerprints(snapshot)
    snapshot["changes"] = cr.diff_versions(previous.snapshot if previous else None, snapshot)
    blocks = cr.build_blocks(snapshot)
    markdown = cr.render_markdown(blocks)
    html_doc = cr.render_html(blocks, f"CropStory case report v{version}")
    report = Report(
        case_id=case_id, version=version, generated_at=now, status="PRELIMINARY", format="MARKDOWN",
        content_uri=None, checksum_sha256=cr.sha256_text(markdown),
        source_manifest_ids=[s["id"] for s in snapshot["sources"]], limitations=snapshot["limitations"],
        snapshot=snapshot, snapshot_sha256=cr.sha256_text(cr.canonical_json(snapshot)), content_markdown=markdown,
        content_html=html_doc, html_sha256=cr.sha256_text(html_doc), sources_sha256=snapshot["source_hash"],
        case_version=case.version, changes=snapshot["changes"], generated_by_id=principal.user.id,
    )
    db.add(report)
    db.flush()
    _record(db, case, principal.user, "REPORT_GENERATED",
            {"report_id": str(report.id), "report_version": version, "checksum_sha256": report.checksum_sha256,
             "sources_sha256": report.sources_sha256, "changed_items": len(snapshot["changes"]["items"])}, bump=False)
    db.commit()
    return _view(report, {principal.user.id: principal.user})


@router.get("/{case_id}/reports", response_model=ReportList)
def list_reports(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> ReportList:
    _load(db, case_id, principal.user.id)
    rows = list(db.scalars(select(Report).where(Report.case_id == case_id, Report.snapshot.is_not(None))
                           .order_by(Report.version.desc())))
    users = _users(db, rows)
    return ReportList(items=[_view(r, users) for r in rows])


@router.get("/{case_id}/reports/{version}", response_model=ReportView)
def get_report(case_id: UUID, version: int, principal: CurrentPrincipal, db: DbSession) -> ReportView:
    _load(db, case_id, principal.user.id)
    report = _get(db, case_id, version)
    return _view(report, _users(db, [report]))


@router.get("/{case_id}/reports/{version}/download")
def download_report(case_id: UUID, version: int, principal: CurrentPrincipal, db: DbSession,
                    format: DownloadFormat = Query("markdown")) -> Response:
    """The stored representation, byte for byte. The exact checksum is in ``X-Report-SHA256``."""
    _load(db, case_id, principal.user.id)
    report = _get(db, case_id, version)
    media, ext = _MEDIA[format]
    if format == "markdown":
        content, digest = report.content_markdown, report.checksum_sha256
    elif format == "html":
        content, digest = report.content_html, report.html_sha256
    else:
        content, digest = cr.canonical_json(report.snapshot), report.snapshot_sha256
    headers = {
        "Content-Disposition": f'attachment; filename="cropstory-case-report-v{version}.{ext}"',
        "X-Report-SHA256": digest or "", "X-Report-Version": str(version), "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    }
    return Response(content=content or "", media_type=media, headers=headers)


@router.get("/{case_id}/reports/{version}/verify", response_model=VerifyResult)
def verify_report(case_id: UUID, version: int, principal: CurrentPrincipal, db: DbSession) -> VerifyResult:
    """Recompute the hashes of the stored content and re-render the document from the stored snapshot."""
    _load(db, case_id, principal.user.id)
    report = _get(db, case_id, version)
    blocks = cr.build_blocks(report.snapshot)
    checks = {
        "markdown_sha256": cr.sha256_text(report.content_markdown or "") == report.checksum_sha256,
        "html_sha256": cr.sha256_text(report.content_html or "") == report.html_sha256,
        "snapshot_sha256": cr.sha256_text(cr.canonical_json(report.snapshot)) == report.snapshot_sha256,
        "sources_sha256": cr.sources_hash(report.snapshot["sources"]) == report.sources_sha256,
        "markdown_matches_snapshot": cr.render_markdown(blocks) == report.content_markdown,
        "source_ids_match": [s["id"] for s in report.snapshot["sources"]] == list(report.source_manifest_ids or []),
    }
    ok = all(checks.values())
    return VerifyResult(version=version, valid=ok, checks=checks,
                        detail="Stored content matches its recorded hashes." if ok else
                        "Stored content does not match its recorded hashes; do not rely on this version.")
