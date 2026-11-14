"""Candidate disagreements between claims and study applicability notes (ABB-15).

Routes (case permissions of ADR-0004, same auth/503 rules as ABB-14):

- ``GET  /api/v1/cases/{case_id}/claims/disagreements`` (all members): candidate disagreements
  computed from the structured comparability fields of the case's claims, each with both paper
  references, recorded differences and the human decisions taken so far.
- ``POST /api/v1/cases/{case_id}/claims/disagreements/{id}/review`` (OWNER/EDITOR/REVIEWER who did
  not write either claim; editable case): CONFIRMED_CONTRADICTION | NOT_COMPARABLE | INCONCLUSIVE
  with a note. Confirming needs both claims ACCEPTED. Appended to ``claim_disagreement_reviews``.
- ``POST /api/v1/cases/{case_id}/claims/{claim_id}/applicability`` (all members; nothing stored):
  per-dimension transferability notes between the claim's study context and the case.

The router must be included before ``evidence.claims_router`` so that ``/claims/disagreements``
is not captured by ``/claims/{claim_id}``.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..comparability import (
    APPLICABILITY_LIMITATIONS,
    DESIGN_NOTES,
    DISAGREEMENT_LIMITATIONS,
    METHOD_VERSION,
    NOT_ASSESSED_NOTE,
    Candidate,
    ClaimFacts,
    StudyContext,
    applicability_notes,
    case_conditions,
    comparability_notes,
    find_candidates,
    not_compared_reasons,
    transfer_status,
)
from ..db.models import Case, ClaimDisagreementReview, EvidenceClaim, Field, Paper, User, utcnow
from ..farm_profile import assess_profile
from .cases import _load, _require_editable, _require_role, _summary
from .comparability_dto import (
    ApplicabilityReport,
    ApplicabilityRequest,
    ClaimNotCompared,
    DisagreementClaimRef,
    DisagreementList,
    DisagreementReviewRequest,
    DisagreementReviewView,
    DisagreementView,
)
from .deps import CurrentPrincipal, DbSession
from .evidence import REVIEW_ROLES, _claim_or_404, _contributors, _editable, _paper_or_404, paper_summary

router = APIRouter(prefix="/api/v1/cases/{case_id}/claims", tags=["evidence comparability (ABB-15)"])

DISAGREEMENT_NOT_FOUND = ("Disagreement not found. It is no longer a candidate if a claim was edited, rejected or "
                          "deleted.")
CANDIDATE_WARNING = ("Candidate only: same intervention and outcome variable with a different stated direction, as "
                     "entered by people. It is not a contradiction unless a reviewer confirms it.")
UNREVIEWED_WARNING = ("At least one claim is not reviewed (ACCEPTED); this compares working notes, and a "
                      "contradiction cannot be confirmed yet.")
CONFIRMED_WARNING = ("Confirmed by a reviewer: the two reviewed claims disagree as recorded. This does not say "
                     "which study is right; differences in conditions may explain it.")
STALE_WARNING = ("A previous decision ({decision}) was recorded for earlier versions of these claims and no longer "
                 "applies.")
SAME_PAPER_WARNING = "Both claims cite the same paper (e.g. different subgroups or outcomes)."


def _facts(claim: EvidenceClaim) -> ClaimFacts:
    return ClaimFacts(
        id=claim.id, intervention=claim.intervention, comparator=claim.comparator,
        outcome_variable=claim.outcome_variable, effect_direction=claim.effect_direction,
        review_status=claim.review_status, study_design=claim.study_design,
        context=StudyContext.from_json(claim.context),
    )


def _ref(claim: EvidenceClaim, paper: Paper) -> DisagreementClaimRef:
    accepted = claim.review_status == "ACCEPTED"
    return DisagreementClaimRef(
        claim_id=claim.id, claim_version=claim.version, claim_text=claim.claim_text,
        intervention=claim.intervention, comparator=claim.comparator, outcome_variable=claim.outcome_variable,
        effect_direction=claim.effect_direction, study_design=claim.study_design,
        review_status=claim.review_status, is_reviewed=accepted,
        source_kind=schemas.SourceKind.LITERATURE_REVIEWED if accepted else schemas.SourceKind.LITERATURE_METADATA,
        paper=paper_summary(paper),
    )


def _case_claims(db: Session, case_id: UUID) -> list[EvidenceClaim]:
    return list(db.scalars(select(EvidenceClaim).where(EvidenceClaim.case_id == case_id)
                           .order_by(EvidenceClaim.created_at, EvidenceClaim.id)))


def _views(db: Session, case: Case, role: str, me: User, claims: list[EvidenceClaim],
           candidates: list[Candidate]) -> list[DisagreementView]:
    if not candidates:
        return []
    by_id = {claim.id: claim for claim in claims}
    involved = [by_id[i] for i in dict.fromkeys(x for c in candidates for x in (c.claim_a.id, c.claim_b.id))]
    papers = {p.id: p for p in db.scalars(select(Paper).where(Paper.id.in_({c.paper_id for c in involved})))}
    rows = db.scalars(select(ClaimDisagreementReview).where(
        ClaimDisagreementReview.case_id == case.id,
        ClaimDisagreementReview.pair_id.in_([c.id for c in candidates]),
    ).order_by(ClaimDisagreementReview.reviewed_at, ClaimDisagreementReview.id)).all()
    reviewers = {u.id: u for u in db.scalars(select(User).where(User.id.in_({r.reviewer_id for r in rows})))} \
        if rows else {}
    contributors = _contributors(db, involved)
    may_review = role in REVIEW_ROLES and _editable(case)
    views = []
    for cand in candidates:
        a, b = by_id[cand.claim_a.id], by_id[cand.claim_b.id]
        history = [
            DisagreementReviewView(
                id=r.id, decision=r.decision, note=r.note, reviewer=_summary(reviewers.get(r.reviewer_id)),
                reviewed_at=r.reviewed_at, claim_a_version=r.claim_a_version, claim_b_version=r.claim_b_version,
                applies_to_current_versions=(r.claim_a_version, r.claim_b_version) == (a.version, b.version),
            )
            for r in rows if r.pair_id == cand.id
        ]
        latest = history[-1] if history else None
        current = latest if latest is not None and latest.applies_to_current_versions else None
        both_reviewed = a.review_status == b.review_status == "ACCEPTED"
        warnings = [CONFIRMED_WARNING if current and current.decision == "CONFIRMED_CONTRADICTION"
                    else CANDIDATE_WARNING]
        if not both_reviewed:
            warnings.append(UNREVIEWED_WARNING)
        if latest is not None and current is None:
            warnings.append(STALE_WARNING.format(decision=latest.decision))
        if a.paper_id == b.paper_id:
            warnings.append(SAME_PAPER_WARNING)
        views.append(DisagreementView(
            id=cand.id, case_id=case.id, kind=cand.kind, status=current.decision if current else "CANDIDATE",
            matched_on={"intervention": a.intervention, "outcome_variable": a.outcome_variable},
            claim_a=_ref(a, papers[a.paper_id]), claim_b=_ref(b, papers[b.paper_id]),
            both_claims_reviewed=both_reviewed, comparability_notes=comparability_notes(cand.claim_a, cand.claim_b),
            current_review=current, reviews=history, warnings=warnings,
            can_review=may_review and me.id not in contributors[a.id] | contributors[b.id],
        ))
    return views


@router.get("/disagreements", response_model=DisagreementList)
def list_disagreements(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> DisagreementList:
    """All members. Candidates and decided disagreements, with both references and recorded differences."""
    case, role = _load(db, case_id, principal.user.id)
    claims = _case_claims(db, case_id)
    facts = [_facts(claim) for claim in claims]
    not_compared = [ClaimNotCompared(claim_id=f.id, reasons=reasons) for f in facts
                    if (reasons := not_compared_reasons(f))]
    return DisagreementList(
        case_id=case_id, items=_views(db, case, role, principal.user, claims, find_candidates(facts)),
        claims_not_compared=not_compared, method_version=METHOD_VERSION, limitations=list(DISAGREEMENT_LIMITATIONS),
    )


def _snapshot(cand: Candidate, a: EvidenceClaim, b: EvidenceClaim, papers: dict[UUID, Paper]) -> dict[str, Any]:
    def side(claim: EvidenceClaim) -> dict[str, Any]:
        paper = papers[claim.paper_id]
        return {"claim_id": str(claim.id), "version": claim.version, "review_status": claim.review_status,
                "intervention": claim.intervention, "comparator": claim.comparator,
                "outcome_variable": claim.outcome_variable, "effect_direction": claim.effect_direction,
                "study_design": claim.study_design, "paper_id": str(paper.id), "doi_id": paper.doi_id,
                "title": paper.title}
    return {"kind": cand.kind, "method_version": METHOD_VERSION, "claim_a": side(a), "claim_b": side(b)}


@router.post("/disagreements/{disagreement_id}/review", response_model=DisagreementView)
def review_disagreement(case_id: UUID, disagreement_id: UUID, body: DisagreementReviewRequest,
                        principal: CurrentPrincipal, db: DbSession) -> DisagreementView:
    """OWNER/EDITOR/REVIEWER who neither created nor edited either claim. Records CONFIRMED_CONTRADICTION
    (both claims ACCEPTED), NOT_COMPARABLE or INCONCLUSIVE with a note. Send the claim versions compared."""
    me = principal.user
    case, role = _load(db, case_id, me.id)
    _require_role(role, REVIEW_ROLES)
    _require_editable(case)
    cand = next((c for c in find_candidates([_facts(x) for x in _case_claims(db, case_id)])
                 if c.id == disagreement_id), None)
    if cand is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=DISAGREEMENT_NOT_FOUND)
    a = _claim_or_404(db, case_id, cand.claim_a.id, lock=True)
    b = _claim_or_404(db, case_id, cand.claim_b.id, lock=True)
    locked = find_candidates([_facts(a), _facts(b)])
    if not locked:  # changed between the scan and the lock
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=DISAGREEMENT_NOT_FOUND)
    contributors = _contributors(db, [a, b])
    if me.id in contributors[a.id] | contributors[b.id]:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="You created or edited one of these claims; a different member must decide.")
    if (a.version, b.version) != (body.claim_a_version, body.claim_b_version):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=(
            f"The claims changed since you compared them (current versions {a.version} and {b.version}). "
            "Reload and retry."))
    if body.decision == "CONFIRMED_CONTRADICTION" and not a.review_status == b.review_status == "ACCEPTED":
        raise HTTPException(status.HTTP_409_CONFLICT, detail=(
            "Cannot confirm a contradiction: both claims must be reviewed (ACCEPTED) first. Record INCONCLUSIVE "
            "or NOT_COMPARABLE, or review the claims."))
    papers = {pid: _paper_or_404(db, pid) for pid in {a.paper_id, b.paper_id}}
    db.add(ClaimDisagreementReview(
        case_id=case_id, pair_id=locked[0].id, claim_a_id=a.id, claim_b_id=b.id, claim_a_version=a.version,
        claim_b_version=b.version, decision=body.decision, note=body.note, reviewer_id=me.id, reviewed_at=utcnow(),
        snapshot=_snapshot(locked[0], a, b, papers),
    ))
    db.commit()
    return _views(db, case, role, me, [a, b], locked)[0]


@router.post("/{claim_id}/applicability", response_model=ApplicabilityReport)
def claim_applicability(case_id: UUID, claim_id: UUID, principal: CurrentPrincipal, db: DbSession,
                        body: ApplicabilityRequest | None = None) -> ApplicabilityReport:
    """All members; nothing is stored. Compares the claim's structured study conditions with the case
    (farm profile, country, Koppen-Geiger class, stored crop history) per dimension: MATCH / PARTIAL /
    MISMATCH / UNKNOWN with a reason. Missing data on either side is UNKNOWN; no score is computed."""
    case, _ = _load(db, case_id, principal.user.id)
    claim = _claim_or_404(db, case_id, claim_id)
    body = body or ApplicabilityRequest()
    profile = body.farm_profile
    if profile is not None and profile.case_id not in (None, case_id):
        raise HTTPException(422, detail="farm_profile.case_id refers to a different case.")
    labels = list(dict.fromkeys(db.scalars(select(Field.region_label).where(Field.case_id == case_id)
                                           .order_by(Field.label, Field.id))))
    conditions = case_conditions(profile, case_crops=list(case.crop_history or []), country=body.country_code,
                                 climate=body.koppen_climate, region_labels=labels)
    dimensions = applicability_notes(StudyContext.from_json(claim.context), conditions)
    notes = []
    if claim.study_design in DESIGN_NOTES:
        notes.append(DESIGN_NOTES[claim.study_design])
    accepted = claim.review_status == "ACCEPTED"
    if not accepted:
        notes.append("This claim is not reviewed: its recorded study conditions have not been checked against the "
                     "paper by a second person.")
    if profile is not None and any(i.severity == "ERROR" for i in assess_profile(profile).issues):
        notes.append("The farm profile has consistency errors (see POST /api/v1/farm-profiles/assess); its values "
                     "were compared as given.")
    notes.append(NOT_ASSESSED_NOTE)
    return ApplicabilityReport(
        case_id=case_id, claim_id=claim.id, claim_version=claim.version, claim_review_status=claim.review_status,
        is_reviewed=accepted, study_design=claim.study_design, paper=paper_summary(_paper_or_404(db, claim.paper_id)),
        dimensions=dimensions, transfer_status=transfer_status(dimensions),
        differing_dimensions=[d.dimension for d in dimensions if d.status in ("MISMATCH", "PARTIAL")],
        unknown_dimensions=[d.dimension for d in dimensions if d.status == "UNKNOWN"],
        notes=notes, method_version=METHOD_VERSION, limitations=list(APPLICABILITY_LIMITATIONS),
    )
