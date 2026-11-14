"""Owner-consented, revocable, read-only share links (ABB-25).

The OWNER creates a link only with ``consent: true`` and an explicit choice for every section. The raw
token is returned once; only its SHA-256 digest is stored. ``GET /api/v1/shared/{token}`` needs no
account and returns 404 for unknown, revoked or expired tokens (same body).

The shared view is built on each request from the current case, so later edits are visible while the
link is active; revocation and expiry take effect on the next request. It never contains:
exact coordinates (at most the grid-cell centre of an APPROXIMATE field, and only when the owner chose
APPROXIMATE), e-mail addresses, user ids, observations or source manifests (their request parameters
hold the field location), invitation data or deleted comments. Display names appear only if the owner
opted in; otherwise comment authors are "Member 1", "Member 2"… in order of first appearance.

There is no rate limiting in the application (ABB-28); tokens carry 256 bits of randomness and
responses are marked ``no-store``/``noindex``/``no-referrer``.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import (
    Case,
    CaseComment,
    CaseCommentRevision,
    CaseShareLink,
    EvidenceClaim,
    EvidenceConclusion,
    Field,
    Hypothesis,
    Paper,
    User,
    utcnow,
)
from ..privacy import ROUNDING_STEPS, snap_to_cell_centre
from ..security import new_session_token, token_digest
from .cases import OWNER_ONLY, _load, _record, _require_role, _summary
from .collaboration_dto import (
    ShareLinkCreate,
    ShareLinkCreated,
    ShareLinkList,
    ShareLinkView,
    ShareSections,
    SharedCaseSummary,
    SharedCaseView,
    SharedClaim,
    SharedComment,
    SharedConclusion,
    SharedField,
    SharedHypothesis,
    SharedPaper,
)
from .deps import CurrentPrincipal, DbSession

case_router = APIRouter(prefix="/api/v1/cases", tags=["collaboration (ABB-25)"])
public_router = APIRouter(prefix="/api/v1/shared", tags=["collaboration (ABB-25)"])

MAX_ACTIVE_LINKS = 10
SHARE_NOT_FOUND = "Shared case not found."
LINK_NOT_FOUND = "Share link not found."
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
CONSENT_STATEMENT = (
    "The case owner agreed that anyone holding this link can read the selected sections of the case until "
    "the link expires or is revoked. Exact field coordinates, e-mail addresses and account ids are never "
    "included."
)
PUBLIC_HEADERS = {
    "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow",
    "X-Content-Type-Options": "nosniff",
}
SHARED_LIMITATIONS = [
    "Read-only view shared by the case owner; it is not a scientific validation of the case.",
    "Hypotheses are candidate explanations; none is a demonstrated cause.",
    "Locations are withheld or generalised; no exact field coordinates are shared.",
    "Observations and their source records are not included in shared views because their request "
    "parameters contain the field location.",
]


def _status(link: CaseShareLink, now: datetime) -> str:
    if link.revoked_at is not None:
        return "REVOKED"
    return "EXPIRED" if link.expires_at <= now else "ACTIVE"


def _view(link: CaseShareLink, users: dict[UUID, User], now: datetime) -> ShareLinkView:
    return ShareLinkView(
        id=link.id, case_id=link.case_id, label=link.label, sections=ShareSections(**link.sections),
        consent_statement=link.consent_statement, status=_status(link, now),
        created_by=_summary(users.get(link.created_by_id)) if link.created_by_id else None,
        created_at=link.created_at, expires_at=link.expires_at, revoked_at=link.revoked_at,
    )


# ── owner side ───────────────────────────────────────────────────────────────

@case_router.post("/{case_id}/share-links", response_model=ShareLinkCreated, status_code=status.HTTP_201_CREATED)
def create_share_link(case_id: UUID, body: ShareLinkCreate, principal: CurrentPrincipal,
                      db: DbSession) -> ShareLinkCreated:
    """OWNER only, with explicit consent and section choices. The token is shown only in this response."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, OWNER_ONLY)
    now = utcnow()
    active = db.scalar(select(func.count()).select_from(CaseShareLink).where(
        CaseShareLink.case_id == case_id, CaseShareLink.revoked_at.is_(None), CaseShareLink.expires_at > now))
    if (active or 0) >= MAX_ACTIVE_LINKS:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"A case can have at most {MAX_ACTIVE_LINKS} active share links; revoke one first.")
    token = new_session_token()
    sections = body.sections.model_dump(mode="json")
    link = CaseShareLink(
        case_id=case_id, token_sha256=token_digest(token), label=body.label, sections=sections,
        consent_statement=CONSENT_STATEMENT, created_by_id=principal.user.id, created_at=now,
        expires_at=now + timedelta(days=body.expires_in_days),
    )
    db.add(link)
    db.flush()
    _record(db, case, principal.user, "SHARE_LINK_CREATED",
            {"share_link_id": str(link.id), "sections": sections, "expires_at": link.expires_at.isoformat()},
            bump=False)
    db.commit()
    view = _view(link, {principal.user.id: principal.user}, now)
    return ShareLinkCreated(**view.model_dump(), token=token, path=f"/api/v1/shared/{token}")


@case_router.get("/{case_id}/share-links", response_model=ShareLinkList)
def list_share_links(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> ShareLinkList:
    """OWNER only. Tokens are never shown again."""
    _, role = _load(db, case_id, principal.user.id)
    _require_role(role, OWNER_ONLY)
    rows = db.scalars(select(CaseShareLink).where(CaseShareLink.case_id == case_id)
                      .order_by(CaseShareLink.created_at.desc(), CaseShareLink.id)).all()
    ids = {r.created_by_id for r in rows if r.created_by_id}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    now = utcnow()
    return ShareLinkList(items=[_view(row, users, now) for row in rows])


@case_router.delete("/{case_id}/share-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share_link(case_id: UUID, link_id: UUID, principal: CurrentPrincipal, db: DbSession) -> Response:
    """OWNER only. Immediate: the next public request returns 404. Revoking twice is a no-op."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, OWNER_ONLY)
    link = db.get(CaseShareLink, link_id, with_for_update=True)
    if link is None or link.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=LINK_NOT_FOUND)
    if link.revoked_at is None:
        link.revoked_at = utcnow()
        link.revoked_by_id = principal.user.id
        _record(db, case, principal.user, "SHARE_LINK_REVOKED",
                {"share_link_id": str(link.id), "revoked_at": link.revoked_at.isoformat()}, bump=False)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── public view ──────────────────────────────────────────────────────────────

def shared_field(field: Field, index: int, sections: ShareSections) -> SharedField:
    """The more private of the owner's choice and the field's own tier; never the stored point."""
    label = field.label if sections.field_labels else f"Field {index}"
    detail = sections.location_detail
    if detail == "NONE" or field.privacy_tier == "WITHHELD":
        return SharedField(label=label, region_label=None, location_precision="NONE", latitude=None,
                           longitude=None, rounding_deg=None)
    if (detail == "APPROXIMATE" and field.privacy_tier == "APPROXIMATE" and field.latitude is not None
            and field.longitude is not None and field.rounding_deg in ROUNDING_STEPS):
        return SharedField(
            label=label, region_label=field.region_label, location_precision="APPROXIMATE",
            latitude=snap_to_cell_centre(field.latitude, field.rounding_deg, 90.0),
            longitude=snap_to_cell_centre(field.longitude, field.rounding_deg, 180.0),
            rounding_deg=field.rounding_deg,
        )
    return SharedField(label=label, region_label=field.region_label, location_precision="REGION_ONLY",
                       latitude=None, longitude=None, rounding_deg=None)


def _shared_comments(db: Session, case_id: UUID, sections: ShareSections) -> list[SharedComment]:
    rows = db.scalars(select(CaseComment).where(CaseComment.case_id == case_id, CaseComment.deleted_at.is_(None))
                      .order_by(CaseComment.created_at, CaseComment.id)).all()
    edited = set(db.scalars(select(CaseCommentRevision.comment_id).where(CaseCommentRevision.case_id == case_id)))
    names: dict[UUID | None, str] = {}
    if sections.member_names:
        ids = {r.author_id for r in rows if r.author_id}
        names.update({u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {})
    refs = {row.id: f"C{n}" for n, row in enumerate(rows, start=1)}
    result = []
    for row in rows:
        if row.author_id is None:
            author = "Former member"
        elif sections.member_names:
            author = names.get(row.author_id, "Former member")
        else:
            author = names.setdefault(row.author_id, f"Member {len(names) + 1}")
        result.append(SharedComment(
            ref=refs[row.id], reply_to=refs.get(row.parent_id) if row.parent_id else None, author=author,
            target_kind=row.target_kind, body=row.body, created_at=row.created_at, edited=row.id in edited,
        ))
    return result


def build_shared_view(db: Session, case: Case, link: CaseShareLink) -> SharedCaseView:
    sections = ShareSections(**link.sections)
    fields = db.scalars(select(Field).where(Field.case_id == case.id).order_by(Field.label, Field.id)).all()
    hypotheses = claims = conclusions = comments = None
    if sections.hypotheses:
        hypotheses = [
            SharedHypothesis(
                title=h.title, statement=h.statement, status=h.status, evaluation_note=h.evaluation_note,
                supporting_evidence_count=len(h.supporting_evidence_ids or []),
                contradicting_evidence_count=len(h.contradicting_evidence_ids or []),
                missing_evidence=list(h.missing_evidence or []), limitations=list(h.limitations or []),
            )
            for h in db.scalars(select(Hypothesis).where(Hypothesis.case_id == case.id)
                                .order_by(Hypothesis.created_at, Hypothesis.id))
        ]
    if sections.evidence_claims:
        claims = [
            SharedClaim(
                claim_text=c.claim_text, review_status=c.review_status,
                source_kind="LITERATURE_REVIEWED" if c.review_status == "ACCEPTED" else "LITERATURE_METADATA",
                study_design=c.study_design, paper=SharedPaper(title=p.title, year=p.year, doi=p.doi_id),
                limitations=list(c.limitations or []),
            )
            for c, p in db.execute(select(EvidenceClaim, Paper).join(Paper, Paper.id == EvidenceClaim.paper_id)
                                   .where(EvidenceClaim.case_id == case.id)
                                   .order_by(EvidenceClaim.created_at, EvidenceClaim.id)).all()
        ]
    if sections.conclusions:
        conclusions = [
            SharedConclusion(title=c.title, statement=c.statement, review_status=c.review_status,
                             limitations=list(c.limitations or []))
            for c in db.scalars(select(EvidenceConclusion).where(EvidenceConclusion.case_id == case.id)
                                .order_by(EvidenceConclusion.created_at, EvidenceConclusion.id))
        ]
    if sections.comments:
        comments = _shared_comments(db, case.id, sections)
    return SharedCaseView(
        generated_at=utcnow(), link_expires_at=link.expires_at, sections=sections,
        case=SharedCaseSummary(
            title=case.title, status=case.status, incident_start=case.incident_start, incident_end=case.incident_end,
            crop_history=list(case.crop_history or []),
            incident_notes=case.incident_notes if sections.incident_notes else None, case_version=case.version,
            updated_at=case.updated_at,
        ),
        fields=[shared_field(f, n, sections) for n, f in enumerate(fields, start=1)],
        hypotheses=hypotheses, evidence_claims=claims, conclusions=conclusions, comments=comments,
        limitations=SHARED_LIMITATIONS,
    )


@public_router.get("/{token}", response_model=SharedCaseView)
def shared_case(token: str, db: DbSession, response: Response) -> SharedCaseView:
    """No account needed. 404 (same body) for unknown, revoked or expired links."""
    not_found = HTTPException(status.HTTP_404_NOT_FOUND, detail=SHARE_NOT_FOUND, headers=PUBLIC_HEADERS)
    if not _TOKEN.match(token):
        raise not_found
    link = db.scalar(select(CaseShareLink).where(CaseShareLink.token_sha256 == token_digest(token)))
    if link is None or _status(link, utcnow()) != "ACTIVE":
        raise not_found
    case = db.get(Case, link.case_id)
    if case is None:  # pragma: no cover - links cascade with the case
        raise not_found
    response.headers.update(PUBLIC_HEADERS)
    return build_shared_view(db, case, link)
