"""Registered papers and case-scoped evidence claims with human review (ABB-14).

Papers (``/api/v1/evidence/papers``)
- Registration takes only an identifier (DOI or OpenAlex ID). The server fetches the metadata
  from OpenAlex and checks the DOI in Crossref (``services.literature.lookup_paper``); client
  metadata is never accepted. Papers are deduplicated by DOI and OpenAlex ID. A stored paper is
  re-fetched only when its DOI status may still change (mismatch / not found / unavailable) and no
  accepted claim cites it. Any authenticated user may register and read papers: they are public
  bibliographic records, not case data.

Claims (``/api/v1/cases/{case_id}/claims``) follow the case permissions of ADR-0004:
- No case permission → 404. VIEWER/REVIEWER cannot write claims (403). Writes need an editable case.
- OWNER/EDITOR create, edit and delete claims. Any content edit returns the claim to PENDING.
- OWNER/EDITOR/REVIEWER can record review decisions, but never on a claim they created or edited.
- ACCEPTED requires that the reviewer consulted the full text with legitimate access and a licence,
  a resolved paper identity, a study design and the reported outcome. Only ACCEPTED claims are
  ``LITERATURE_REVIEWED``; everything else is ``LITERATURE_METADATA``.
- Every creation, edit and decision is appended to ``evidence_claim_events`` with the actor, time,
  note, source consulted and a snapshot of the paper identity.
"""
from __future__ import annotations

import asyncio
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import schemas
from ..db.models import Case, ClaimDisagreementReview, EvidenceClaim, EvidenceClaimEvent, Paper, User, utcnow
from ..evidence_seed import PILOT_SEED, seed_claim_content
from ..services import literature as lit
from .cases import EDITABLE_STATUSES, EDITOR_ROLES, _load, _record, _require_editable, _require_role, _summary
from .deps import CurrentPrincipal, DbSession
from .evidence_dto import (
    ClaimContent,
    ClaimContextView,
    ClaimCreate,
    ClaimEventView,
    ClaimList,
    ClaimPatch,
    ClaimView,
    PaperRegistration,
    PaperSummary,
    PaperView,
    PilotImportItem,
    PilotImportResult,
    ReportedOutcomeView,
    ReviewDecision,
    SourceConsultedView,
    SourceLocatorView,
    license_key,
)

papers_router = APIRouter(prefix="/api/v1/evidence", tags=["evidence (ABB-14)"])
claims_router = APIRouter(prefix="/api/v1/cases/{case_id}/claims", tags=["evidence (ABB-14)"])

REVIEW_ROLES = frozenset({"OWNER", "EDITOR", "REVIEWER"})
UNRESOLVED_IDENTITY = frozenset({"METADATA_MISMATCH", "VERIFICATION_UNAVAILABLE"})
REFRESHABLE = frozenset({"METADATA_MISMATCH", "NOT_FOUND_IN_CROSSREF", "VERIFICATION_UNAVAILABLE"})
DECISIONS_FROM: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"ACCEPTED", "REJECTED", "CHANGES_REQUESTED"}),
    "ACCEPTED": frozenset({"REJECTED", "CHANGES_REQUESTED"}),  # withdrawal of an acceptance
}
CONTENT_FIELDS = (
    "claim_text", "study_context", "study_design", "context", "reported_outcome", "source_locator",
    "quoted_fragment", "evidence_basis", "access_basis", "content_license", "limitations",
    "intervention", "comparator", "outcome_variable", "effect_direction",  # ABB-15
)
PAPER_LIMITATION = "Bibliographic metadata does not establish a scientific finding"
CLAIM_NOT_FOUND = "Claim not found."
LIST_LIMITATIONS = [
    "Only ACCEPTED claims (source_kind LITERATURE_REVIEWED) were checked by a named member against the full "
    "text of the cited source; every other claim is an unreviewed working note.",
    "Outcomes, units and uncertainty are reproduced as stated in each source; nothing is recomputed or pooled.",
    "A reviewed claim describes the studied population and conditions; it does not establish transferability "
    "to this farm.",
]
PILOT_LIMITATIONS = [
    "Pilot cards are imported as PENDING, METADATA_ONLY claims; their text was not checked against the papers.",
    "Paper metadata is fetched from OpenAlex/Crossref at import time; nothing from the seed file is treated "
    "as verified.",
]

_HTTP_URL: TypeAdapter[HttpUrl] = TypeAdapter(HttpUrl)


# ── papers ───────────────────────────────────────────────────────────────────

def _url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        _HTTP_URL.validate_python(value)
    except ValidationError:
        return None
    return value


def _clip(value: Any, limit: int) -> str | None:
    return value[:limit] if isinstance(value, str) and value else None


def _apply_record(paper: Paper, record: lit.PaperRecord) -> None:
    paper.title = record.title
    paper.year = record.year
    paper.doi_id = record.doi_id
    paper.doi_status = record.doi_status
    paper.openalex_id = record.openalex_id
    paper.bibliographic_metadata = record.model_dump(
        mode="json", exclude={"title", "year", "doi_id", "doi_status", "openalex_id"}
    )
    paper.limitations = [PAPER_LIMITATION, record.caveat]


def paper_view(paper: Paper) -> PaperView:
    meta = paper.bibliographic_metadata or {}
    year = paper.year if isinstance(paper.year, int) and 1600 <= paper.year <= 2200 else None
    retrievals = [
        schemas.PaperRetrieval(
            source=item["source"], endpoint=item["endpoint"], record_id=_clip(item.get("record_id"), 500),
            retrieved_at=item["retrieved_at"], http_status=item.get("http_status"), outcome=item["outcome"],
        )
        for item in meta.get("retrievals") or [] if _url(item.get("endpoint"))
    ]
    return PaperView(
        id=paper.id, title=paper.title[:1_000], year=year, doi=_url(meta.get("doi")), doi_id=paper.doi_id,
        doi_status=paper.doi_status, openalex_id=_url(paper.openalex_id),
        authors=[
            schemas.PaperAuthor(name=author["name"][:500], orcid=_url(author.get("orcid")))
            for author in meta.get("authors") or [] if author.get("name")
        ],
        venue=_clip(meta.get("venue"), 500), publication_type=_clip(meta.get("publication_type"), 120),
        licenses=[
            schemas.PaperLicense(value=item["value"][:500], reported_by=item["reported_by"],
                                 content_version=_clip(item.get("content_version"), 120))
            for item in meta.get("licenses") or [] if item.get("value")
        ],
        landing_page_url=_url(meta.get("landing_page_url")),
        is_open_access=meta.get("is_open_access") if isinstance(meta.get("is_open_access"), bool) else None,
        metadata_discrepancies=list(meta.get("metadata_discrepancies") or []),
        retrievals=retrievals, processing_version=meta.get("processing_version") or lit.PROCESSING_VERSION,
        limitations=list(paper.limitations or []) or [PAPER_LIMITATION],
        source=meta.get("source") or "OpenAlex metadata", caveat=meta.get("caveat") or "",
    )


def paper_summary(paper: Paper) -> PaperSummary:
    meta = paper.bibliographic_metadata or {}
    return PaperSummary(
        id=paper.id, title=paper.title, year=paper.year, doi=meta.get("doi"), doi_id=paper.doi_id,
        doi_status=paper.doi_status, openalex_id=paper.openalex_id,
        is_open_access=meta.get("is_open_access") if isinstance(meta.get("is_open_access"), bool) else None,
        licenses=[item["value"] for item in meta.get("licenses") or [] if item.get("value")],
        caveat=meta.get("caveat") or "",
    )


def _has_accepted_claims(db: Session, paper: Paper) -> bool:
    return db.scalar(
        select(EvidenceClaim.id).where(EvidenceClaim.paper_id == paper.id, EvidenceClaim.review_status == "ACCEPTED")
        .limit(1)
    ) is not None


def _refreshable(db: Session, paper: Paper) -> bool:
    return paper.doi_status in REFRESHABLE and not _has_accepted_claims(db, paper)


def _find_by_identity(db: Session, record: lit.PaperRecord) -> Paper | None:
    conditions = []
    if record.doi_id:
        conditions.append(Paper.doi_id == record.doi_id)
    if record.openalex_id:
        conditions.append(Paper.openalex_id == record.openalex_id)
    matches = db.scalars(select(Paper).where(or_(*conditions))).all() if conditions else []
    by_doi = [paper for paper in matches if record.doi_id and paper.doi_id == record.doi_id]
    return (by_doi or matches or [None])[0]


def resolve_paper(db: Session, *, doi: str | None = None, openalex_id: str | None = None) -> tuple[Paper, bool]:
    """Return ``(paper, created)``. Upstream metadata only; raises HTTPException on failure."""
    if doi is not None:
        key = lit.normalize_doi(doi)
        if key is None:
            raise HTTPException(422, detail="Not a valid DOI.")
        existing = db.scalar(select(Paper).where(Paper.doi_id == key))
    else:
        key = lit.normalize_openalex_id(openalex_id)
        if key is None:
            raise HTTPException(422, detail="Not a valid OpenAlex work ID.")
        existing = db.scalar(select(Paper).where(Paper.openalex_id == key))
    if existing is not None and not _refreshable(db, existing):
        return existing, False
    db.rollback()  # do not hold a database transaction open while upstream sources are consulted
    try:
        record = asyncio.run(lit.lookup_paper(doi=key if doi is not None else None,
                                              openalex_id=key if doi is None else None))
    except lit.PaperNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=exc.public_message) from exc
    except lit.LiteratureSourceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=exc.public_message) from exc
    paper = _find_by_identity(db, record)
    if paper is not None and not _refreshable(db, paper):
        return paper, False
    created = paper is None
    if paper is None:
        paper = Paper()
        db.add(paper)
    _apply_record(paper, record)
    try:
        db.commit()
    except IntegrityError as exc:  # concurrent registration of the same work
        db.rollback()
        paper = _find_by_identity(db, record)
        if paper is None:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                detail="This work conflicts with another registered paper record.") from exc
        return paper, False
    return paper, created


@papers_router.post("/papers", response_model=PaperView, status_code=status.HTTP_201_CREATED)
def register_paper(body: PaperRegistration, principal: CurrentPrincipal, db: DbSession, response: Response) -> PaperView:
    """Register a work by DOI or OpenAlex ID. Metadata is fetched from OpenAlex and the DOI checked in
    Crossref; 201 when stored, 200 when it was already registered. 404 if no source knows it, 502 if
    the sources are unavailable (nothing is stored). The result is LITERATURE_METADATA only."""
    paper, created = resolve_paper(db, doi=body.doi, openalex_id=body.openalex_id)
    if not created:
        response.status_code = status.HTTP_200_OK
    return paper_view(paper)


@papers_router.get("/papers/{paper_id}", response_model=PaperView)
def get_paper(paper_id: UUID, principal: CurrentPrincipal, db: DbSession) -> PaperView:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Paper not found.")
    return paper_view(paper)


# ── claim helpers ────────────────────────────────────────────────────────────

def _claim_or_404(db: Session, case_id: UUID, claim_id: UUID, *, lock: bool = False) -> EvidenceClaim:
    claim = db.get(EvidenceClaim, claim_id, with_for_update=lock, populate_existing=lock)
    if claim is None or claim.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=CLAIM_NOT_FOUND)
    return claim


def _require_claim_version(claim: EvidenceClaim, version: int) -> None:
    if claim.version != version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"The claim changed since you loaded it (current version {claim.version}). Reload and retry.",
        )


def _editable(case: Case) -> bool:
    return case.archived_at is None and case.status in EDITABLE_STATUSES


def _paper_or_404(db: Session, paper_id: UUID) -> Paper:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail="Paper not found. Register it first with POST /api/v1/evidence/papers.")
    return paper


def _check_license_matches_paper(access_basis: str, license_value: str | None, paper: Paper) -> None:
    """OPEN_ACCESS_LICENSE must name a licence that OpenAlex/Crossref actually recorded for the paper."""
    if access_basis != "OPEN_ACCESS_LICENSE":
        return
    recorded = [item["value"] for item in (paper.bibliographic_metadata or {}).get("licenses") or []
                if item.get("value")]
    if not recorded:
        raise HTTPException(422, detail="OPEN_ACCESS_LICENSE needs a licence recorded for this paper by "
                                        "OpenAlex or Crossref; none is recorded. Choose another access basis "
                                        "and state its terms.")
    if license_value is None or license_key(license_value) not in {license_key(value) for value in recorded}:
        raise HTTPException(422, detail="The licence must be one recorded for this paper: " + ", ".join(recorded))


def _contributors(db: Session, claims: list[EvidenceClaim]) -> dict[UUID, set[UUID]]:
    result: dict[UUID, set[UUID]] = {claim.id: {claim.created_by} - {None} for claim in claims}
    if claims:
        rows = db.execute(
            select(EvidenceClaimEvent.claim_id, EvidenceClaimEvent.actor_id).where(
                EvidenceClaimEvent.claim_id.in_([claim.id for claim in claims]),
                EvidenceClaimEvent.action.in_(("CREATED", "UPDATED")),
            )
        ).all()
        for claim_id, actor_id in rows:
            result[claim_id].add(actor_id)
    return result


def _paper_snapshot(paper: Paper) -> dict[str, Any]:
    meta = paper.bibliographic_metadata or {}
    retrieved = [item.get("retrieved_at") for item in meta.get("retrievals") or [] if item.get("retrieved_at")]
    return {
        "paper_id": str(paper.id), "title": paper.title, "year": paper.year, "doi_id": paper.doi_id,
        "doi_status": paper.doi_status, "openalex_id": paper.openalex_id,
        "metadata_retrieved_at": max(retrieved) if retrieved else None,
    }


def _event(
    db: Session, claim: EvidenceClaim, actor: User, action: str, paper: Paper, *, from_status: str | None,
    note: str | None = None, source_consulted: dict[str, Any] | None = None, changes: dict[str, Any] | None = None,
) -> None:
    db.add(EvidenceClaimEvent(
        claim_id=claim.id, case_id=claim.case_id, claim_version=claim.version, action=action, actor_id=actor.id,
        created_at=utcnow(), from_status=from_status, to_status=claim.review_status, note=note,
        source_consulted=source_consulted, paper_snapshot=_paper_snapshot(paper), changes=changes or {},
    ))


def _warnings(claim: EvidenceClaim, paper: Paper) -> list[str]:
    warnings: list[str] = []
    if claim.review_status == "ACCEPTED":
        warnings.append("Reviewed: a named member checked this claim against the full text of the cited source. "
                        "This does not establish that the result transfers to this case.")
    else:
        warnings.append("Not reviewed: a working note linked to bibliographic metadata, not a reviewed finding.")
        if claim.review_status == "REJECTED":
            warnings.append("Rejected by a reviewer; do not use as evidence.")
        elif claim.review_status == "CHANGES_REQUESTED":
            warnings.append("A reviewer requested changes; not usable as reviewed evidence.")
        if claim.evidence_basis == "METADATA_ONLY":
            warnings.append("Metadata only: written from bibliographic metadata; no part of the paper was read.")
        elif claim.evidence_basis == "ABSTRACT":
            warnings.append("Derived from the abstract only; it is not a verified study or trial result.")
        if claim.origin == "PILOT_SEED_UNVERIFIED":
            warnings.append("Imported from the unverified pilot seed; the text has not been checked against the paper.")
    if paper.doi_status != "VERIFIED_CROSSREF":
        warnings.append(f"Paper DOI status {paper.doi_status}: {(paper.bibliographic_metadata or {}).get('caveat', '')}"
                        .strip())
    return warnings


def _views(db: Session, case: Case, role: str, me: User, claims: list[EvidenceClaim]) -> list[ClaimView]:
    papers = {paper.id: paper for paper in db.scalars(
        select(Paper).where(Paper.id.in_({claim.paper_id for claim in claims}))
    )} if claims else {}
    user_ids = {uid for claim in claims for uid in (claim.created_by, claim.reviewed_by) if uid}
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    contributors = _contributors(db, claims)
    editable = _editable(case)
    views = []
    for claim in claims:
        paper = papers[claim.paper_id]
        accepted = claim.review_status == "ACCEPTED"
        views.append(ClaimView(
            id=claim.id, paper_id=claim.paper_id, case_id=claim.case_id,
            source_kind=schemas.SourceKind.LITERATURE_REVIEWED if accepted else schemas.SourceKind.LITERATURE_METADATA,
            is_reviewed=accepted, claim_text=claim.claim_text, study_context=claim.study_context,
            review_status=claim.review_status, reviewed_by=claim.reviewed_by, reviewed_at=claim.reviewed_at,
            reviewer=_summary(users.get(claim.reviewed_by)) if claim.reviewed_by else None,
            created_by=_summary(users.get(claim.created_by)) if claim.created_by else None,
            created_at=claim.created_at, updated_at=claim.updated_at, version=claim.version,
            limitations=list(claim.limitations), paper=paper_summary(paper), study_design=claim.study_design,
            context=ClaimContextView(**(claim.context or {})),
            reported_outcome=ReportedOutcomeView(**(claim.reported_outcome or {})),
            source_locator=SourceLocatorView(**(claim.source_locator or {})),
            quoted_fragment=claim.quoted_fragment, evidence_basis=claim.evidence_basis,
            access_basis=claim.access_basis, content_license=claim.content_license, origin=claim.origin,
            origin_ref=claim.origin_ref, intervention=claim.intervention, comparator=claim.comparator,
            outcome_variable=claim.outcome_variable, effect_direction=claim.effect_direction,
            warnings=_warnings(claim, paper),
            can_edit=role in EDITOR_ROLES and editable,
            can_review=(role in REVIEW_ROLES and editable and me.id not in contributors[claim.id]
                        and claim.review_status in DECISIONS_FROM),
        ))
    return views


def _content_of(claim: EvidenceClaim) -> dict[str, Any]:
    return {name: getattr(claim, name) for name in CONTENT_FIELDS}


def _validated(data: dict[str, Any]) -> ClaimContent:
    try:
        return ClaimContent.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(422, detail="; ".join(error["msg"] for error in exc.errors())) from exc


def _new_claim(case_id: UUID, paper_id: UUID, content: ClaimContent, author: User, **extra: Any) -> EvidenceClaim:
    now = utcnow()
    return EvidenceClaim(
        case_id=case_id, paper_id=paper_id, created_by=author.id, created_at=now, updated_at=now, version=1,
        review_status="PENDING", **content.model_dump(mode="json"), **extra,
    )


# ── claim routes ─────────────────────────────────────────────────────────────

@claims_router.get("", response_model=ClaimList)
def list_claims(
    case_id: UUID, principal: CurrentPrincipal, db: DbSession,
    review_status: Literal["PENDING", "ACCEPTED", "CHANGES_REQUESTED", "REJECTED"] | None = Query(default=None),
) -> ClaimList:
    """All members. Reviewed (ACCEPTED, LITERATURE_REVIEWED) and unreviewed claims are flagged per item."""
    case, role = _load(db, case_id, principal.user.id)
    query = select(EvidenceClaim).where(EvidenceClaim.case_id == case_id)
    if review_status is not None:
        query = query.where(EvidenceClaim.review_status == review_status)
    claims = list(db.scalars(query.order_by(EvidenceClaim.created_at, EvidenceClaim.id)))
    items = _views(db, case, role, principal.user, claims)
    reviewed = sum(item.is_reviewed for item in items)
    return ClaimList(items=items, reviewed_count=reviewed, unreviewed_count=len(items) - reviewed,
                     limitations=list(LIST_LIMITATIONS))


@claims_router.post("", response_model=ClaimView, status_code=status.HTTP_201_CREATED)
def create_claim(case_id: UUID, body: ClaimCreate, principal: CurrentPrincipal, db: DbSession) -> ClaimView:
    """OWNER/EDITOR. Starts PENDING (LITERATURE_METADATA) whatever the client sends."""
    case, role = _load(db, case_id, principal.user.id)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    paper = _paper_or_404(db, body.paper_id)
    content = ClaimContent.model_validate(body.model_dump(exclude={"paper_id"}))
    _check_license_matches_paper(content.access_basis, content.content_license, paper)
    claim = _new_claim(case_id, paper.id, content, principal.user)
    db.add(claim)
    db.flush()
    _event(db, claim, principal.user, "CREATED", paper, from_status=None)
    db.commit()
    return _views(db, case, role, principal.user, [claim])[0]


@claims_router.post("/pilot-import", response_model=PilotImportResult)
def import_pilot_claims(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> PilotImportResult:
    """OWNER/EDITOR, on explicit request only. Imports the three unverified pilot cards of
    ``docs/science/evidence_seed_UNVERIFIED.json`` as PENDING, METADATA_ONLY claims. Each DOI is
    registered from OpenAlex/Crossref; a card whose registered title does not match is not imported.
    Idempotent per case. The importer counts as a contributor and cannot review these claims."""
    case, role = _load(db, case_id, principal.user.id)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    me = principal.user
    done = set(db.scalars(select(EvidenceClaim.origin_ref).where(
        EvidenceClaim.case_id == case_id, EvidenceClaim.origin == "PILOT_SEED_UNVERIFIED")))
    created: list[EvidenceClaim] = []
    skipped: list[PilotImportItem] = []
    failed: list[PilotImportItem] = []
    for entry in PILOT_SEED:
        item = {"seed_id": entry["id"], "doi": entry["doi"]}
        if entry["id"] in done:
            skipped.append(PilotImportItem(**item, reason="Already imported in this case."))
            continue
        try:
            paper, _ = resolve_paper(db, doi=entry["doi"])
        except HTTPException as exc:
            db.rollback()
            failed.append(PilotImportItem(**item, reason=str(exc.detail)))
            continue
        if not lit.titles_match(entry["title"], paper.title):
            failed.append(PilotImportItem(**item, reason="The registered title does not match the seed title; "
                                                         "not imported. A person must check which work is meant."))
            continue
        claim = _new_claim(case_id, paper.id, _validated(seed_claim_content(entry)), me,
                           origin="PILOT_SEED_UNVERIFIED", origin_ref=entry["id"])
        db.add(claim)
        db.flush()
        _event(db, claim, me, "CREATED", paper, from_status=None,
               note=f"Imported from unverified pilot seed {entry['id']}; not reviewed.")
        db.commit()
        created.append(claim)
    case, role = _load(db, case_id, me.id)
    return PilotImportResult(created=_views(db, case, role, me, created), skipped=skipped, failed=failed,
                             limitations=list(PILOT_LIMITATIONS))


@claims_router.get("/{claim_id}", response_model=ClaimView)
def get_claim(case_id: UUID, claim_id: UUID, principal: CurrentPrincipal, db: DbSession) -> ClaimView:
    case, role = _load(db, case_id, principal.user.id)
    return _views(db, case, role, principal.user, [_claim_or_404(db, case_id, claim_id)])[0]


@claims_router.patch("/{claim_id}", response_model=ClaimView)
def update_claim(case_id: UUID, claim_id: UUID, body: ClaimPatch, principal: CurrentPrincipal,
                 db: DbSession) -> ClaimView:
    """OWNER/EDITOR; send the claim ``version``. Any change returns the claim to PENDING (a previous
    acceptance no longer applies) and the editor becomes a contributor who cannot review it."""
    case, role = _load(db, case_id, principal.user.id)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    claim = _claim_or_404(db, case_id, claim_id, lock=True)
    _require_claim_version(claim, body.version)
    before = _validated(_content_of(claim)).model_dump(mode="json")
    content = _validated({**before, **body.model_dump(mode="json", include=body.model_fields_set - {"version"})})
    paper = _paper_or_404(db, claim.paper_id)
    _check_license_matches_paper(content.access_basis, content.content_license, paper)
    after = content.model_dump(mode="json")
    changes = {name: {"before": before[name], "after": after[name]} for name in CONTENT_FIELDS
               if before[name] != after[name]}
    if changes:
        previous = claim.review_status
        for name in changes:
            setattr(claim, name, after[name])
        claim.version += 1
        claim.updated_at = utcnow()
        claim.review_status, claim.reviewed_by, claim.reviewed_at = "PENDING", None, None
        _event(db, claim, principal.user, "UPDATED", paper, from_status=previous, changes=changes,
               note=None if previous == "PENDING" else f"Content changed; {previous} review no longer applies.")
        db.commit()
    return _views(db, case, role, principal.user, [claim])[0]


@claims_router.delete("/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_claim(
    case_id: UUID, claim_id: UUID, principal: CurrentPrincipal, db: DbSession,
    version: int = Query(ge=1, description="Current claim version"),
) -> Response:
    """OWNER/EDITOR. Only claims that never received a review decision; reviewed claims are kept for
    audit (edit or reject them instead). The deletion is recorded in the case history."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    claim = _claim_or_404(db, case_id, claim_id, lock=True)
    _require_claim_version(claim, version)
    reviewed = db.scalar(select(EvidenceClaimEvent.id).where(
        EvidenceClaimEvent.claim_id == claim.id, EvidenceClaimEvent.action == "REVIEWED").limit(1))
    if reviewed is None:  # ABB-15: decisions on disagreements also keep the claim for audit
        reviewed = db.scalar(select(ClaimDisagreementReview.id).where(or_(
            ClaimDisagreementReview.claim_a_id == claim.id, ClaimDisagreementReview.claim_b_id == claim.id)).limit(1))
    if reviewed is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="This claim has review decisions and is kept for audit; edit or reject it instead.")
    snapshot = {"id": str(claim.id), "paper_id": str(claim.paper_id), "claim_text": claim.claim_text,
                "review_status": claim.review_status, "version": claim.version}
    _record(db, case, principal.user, "EVIDENCE_CLAIM_DELETED", {"claim": {"before": snapshot, "after": None}},
            bump=False)
    db.delete(claim)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@claims_router.post("/{claim_id}/review", response_model=ClaimView)
def review_claim(case_id: UUID, claim_id: UUID, body: ReviewDecision, principal: CurrentPrincipal,
                 db: DbSession) -> ClaimView:
    """OWNER/EDITOR/REVIEWER who neither created nor edited the claim. Records the decision, note and
    the source consulted. ACCEPTED (→ LITERATURE_REVIEWED) needs a full-text check with legitimate
    access, a resolved paper identity, a study design and the reported outcome."""
    case, role = _load(db, case_id, principal.user.id)
    _require_role(role, REVIEW_ROLES)
    _require_editable(case)
    claim = _claim_or_404(db, case_id, claim_id, lock=True)
    _require_claim_version(claim, body.version)
    if principal.user.id in _contributors(db, [claim])[claim.id]:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="You created or edited this claim; a different member must review it.")
    if body.decision not in DECISIONS_FROM.get(claim.review_status, frozenset()):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"A {claim.review_status} claim cannot receive a {body.decision} decision.")
    paper = _paper_or_404(db, claim.paper_id)
    _check_license_matches_paper(body.source_consulted.access_basis, body.source_consulted.license, paper)
    if body.decision == "ACCEPTED":
        problems = []
        if paper.doi_status in UNRESOLVED_IDENTITY:
            problems.append(f"the paper identity is unresolved (DOI status {paper.doi_status}); re-register the "
                            "paper to retry verification")
        if claim.study_design == "UNKNOWN":
            problems.append("the study design is UNKNOWN")
        if not (claim.reported_outcome or {}).get("outcome"):
            problems.append("the reported outcome (as stated in the source) is missing")
        if problems:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Cannot accept: " + "; ".join(problems) + ".")
    previous = claim.review_status
    claim.review_status = body.decision
    claim.reviewed_by = principal.user.id
    claim.reviewed_at = utcnow()
    claim.version += 1
    claim.updated_at = claim.reviewed_at
    _event(db, claim, principal.user, "REVIEWED", paper, from_status=previous, note=body.note,
           source_consulted=body.source_consulted.model_dump(mode="json"))
    db.commit()
    return _views(db, case, role, principal.user, [claim])[0]


@claims_router.get("/{claim_id}/history", response_model=list[ClaimEventView])
def claim_history(case_id: UUID, claim_id: UUID, principal: CurrentPrincipal, db: DbSession) -> list[ClaimEventView]:
    """All members. Oldest first: who created, edited and reviewed the claim, and which source was consulted."""
    _load(db, case_id, principal.user.id)
    claim = _claim_or_404(db, case_id, claim_id)
    events = db.scalars(select(EvidenceClaimEvent).where(EvidenceClaimEvent.claim_id == claim.id)
                        .order_by(EvidenceClaimEvent.created_at, EvidenceClaimEvent.id)).all()
    actors = {user.id: user for user in db.scalars(select(User).where(User.id.in_({e.actor_id for e in events})))}
    return [
        ClaimEventView(
            id=event.id, claim_id=event.claim_id, claim_version=event.claim_version, action=event.action,
            actor=_summary(actors.get(event.actor_id)), created_at=event.created_at,
            from_status=event.from_status, to_status=event.to_status, note=event.note,
            source_consulted=SourceConsultedView(**event.source_consulted) if event.source_consulted else None,
            paper_snapshot=event.paper_snapshot, changes=event.changes or {},
        )
        for event in events
    ]
