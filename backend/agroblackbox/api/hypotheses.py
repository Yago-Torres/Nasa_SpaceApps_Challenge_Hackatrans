"""Rival hypotheses for a case (ABB-10).

Rules (docs/science/TIMELINE_HYPOTHESES.md):
- Status is set by people only: OPEN (default), COMPATIBLE, CONTRADICTED or NOT_EVALUABLE.
  No status means "demonstrated cause" and no numeric probability or score exists.
- COMPATIBLE needs at least one supporting evidence link, CONTRADICTED at least one
  contradicting link, NOT_EVALUABLE at least one missing-evidence entry; every status
  change other than OPEN needs a note.
- Evidence links must reference evidence of the same case (observations, anomalies or
  evidence claims); unknown or foreign ids are rejected (422).
- OWNER/EDITOR create, edit and delete; OWNER/EDITOR/REVIEWER change the status; VIEWER reads.
  Changes need the case to be DRAFT/INVESTIGATING and not archived, carry the hypothesis
  ``version`` (409 on conflict) and are appended to ``case_history`` (case version unchanged).
- Editing the statement, evidence links or missing evidence resets an evaluation to OPEN.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Anomaly, EvidenceClaim, Hypothesis, Observation, SourceManifest, User, utcnow
from ..services.forensics import (
    HYPOTHESIS_LIMITATION,
    HYPOTHESIS_TEMPLATES,
    TEMPLATE_LIMITATION,
    template,
)
from ..services.metrics import VARIABLES
from .cases import EDITOR_ROLES, _load, _record, _require_editable, _require_role, _summary
from .deps import CurrentPrincipal, DbSession
from .evidence_dto import (
    EvidenceRef,
    HypothesisCreate,
    HypothesisList,
    HypothesisStatusChange,
    HypothesisTemplateCatalog,
    HypothesisTemplateRequest,
    HypothesisTemplateView,
    HypothesisUpdate,
    HypothesisView,
)

router = APIRouter(prefix="/api/v1/cases", tags=["case hypotheses (ABB-10)"])
catalog_router = APIRouter(prefix="/api/v1", tags=["case hypotheses (ABB-10)"])

EVALUATOR_ROLES = frozenset({"OWNER", "EDITOR", "REVIEWER"})
MAX_HYPOTHESES = 50
HYPOTHESIS_NOT_FOUND = "Hypothesis not found."
CONTENT_FIELDS = ("statement", "supporting_evidence_ids", "contradicting_evidence_ids", "missing_evidence")
EDITABLE_FIELDS = (*CONTENT_FIELDS, "title", "limitations", "verification_questions")
LIST_LIMITATIONS = [
    HYPOTHESIS_LIMITATION,
    "Status values record a human evaluation of the linked evidence: COMPATIBLE means consistent with it, "
    "not proven; CONTRADICTED means at least one linked item argues against it; NOT_EVALUABLE means the "
    "evidence needed is missing.",
    "Rival hypotheses are listed side by side; none is ranked or scored.",
]
LABELS = {spec.key: spec.label for spec in VARIABLES}


# ── evidence resolution ─────────────────────────────────────────────────────

def _month_label(observation: Observation) -> str:
    return f"{LABELS.get(observation.variable, observation.variable)}, {observation.observed_at:%b %Y}"


def resolve_evidence(db: Session, case_id: UUID, ids: Iterable[UUID]) -> dict[UUID, EvidenceRef]:
    """Evidence of this case only. Ids from other cases resolve like nonexistent ids."""
    wanted = set(ids)
    found: dict[UUID, EvidenceRef] = {}
    if not wanted:
        return found
    rows = db.execute(
        select(Anomaly, Observation, SourceManifest.superseded_at)
        .join(Observation, Observation.id == Anomaly.observation_id)
        .join(SourceManifest, SourceManifest.id == Observation.source_manifest_id)
        .where(Anomaly.case_id == case_id, Anomaly.id.in_(wanted))
    ).all()
    for anomaly, observation, superseded_at in rows:
        found[anomaly.id] = EvidenceRef(
            id=anomaly.id, evidence_type="ANOMALY", kind="OBSERVED", label=f"Anomaly: {_month_label(observation)}",
            start=observation.period_start, end=observation.period_end, active=superseded_at is None)
    rows = db.execute(
        select(Observation, SourceManifest.superseded_at)
        .join(SourceManifest, SourceManifest.id == Observation.source_manifest_id)
        .where(Observation.case_id == case_id, Observation.id.in_(wanted - found.keys()))
    ).all()
    for observation, superseded_at in rows:
        found[observation.id] = EvidenceRef(
            id=observation.id, evidence_type="OBSERVATION", kind="OBSERVED",
            label=f"Observation: {_month_label(observation)}", start=observation.period_start,
            end=observation.period_end, active=superseded_at is None)
    for claim in db.scalars(select(EvidenceClaim).where(
            EvidenceClaim.case_id == case_id, EvidenceClaim.id.in_(wanted - found.keys()))):
        reviewed = claim.reviewed_at is not None and claim.review_status not in (None, "PENDING")
        found[claim.id] = EvidenceRef(
            id=claim.id, evidence_type="EVIDENCE_CLAIM",
            kind="LITERATURE_REVIEWED" if reviewed else "LITERATURE_METADATA",
            label=claim.claim_text[:160], active=True)
    return found


def _require_evidence(db: Session, case_id: UUID, ids: list[UUID]) -> None:
    unknown = sorted(str(i) for i in set(ids) - resolve_evidence(db, case_id, ids).keys())
    if unknown:
        raise HTTPException(422,
                            detail="Evidence not found in this case: " + ", ".join(unknown))


def _require_evaluable(hypothesis: Hypothesis, new_status: str) -> None:
    problem = None
    if new_status == "COMPATIBLE" and not hypothesis.supporting_evidence_ids:
        problem = "COMPATIBLE needs at least one supporting evidence link."
    elif new_status == "CONTRADICTED" and not hypothesis.contradicting_evidence_ids:
        problem = "CONTRADICTED needs at least one contradicting evidence link."
    elif new_status == "NOT_EVALUABLE" and not hypothesis.missing_evidence:
        problem = "NOT_EVALUABLE needs at least one missing-evidence entry describing what is lacking."
    if problem:
        raise HTTPException(422, detail=problem)


# ── views ────────────────────────────────────────────────────────────────────

def _limitations(items: Iterable[str]) -> list[str]:
    result = [HYPOTHESIS_LIMITATION]
    result.extend(item for item in items if item != HYPOTHESIS_LIMITATION)
    return result


def _view(hypothesis: Hypothesis, evidence: dict[UUID, EvidenceRef], users: dict[UUID, User]) -> HypothesisView:
    linked = [UUID(i) for i in (*hypothesis.supporting_evidence_ids, *hypothesis.contradicting_evidence_ids)]
    return HypothesisView(
        id=hypothesis.id, case_id=hypothesis.case_id, statement=hypothesis.statement,
        supporting_evidence_ids=hypothesis.supporting_evidence_ids,
        contradicting_evidence_ids=hypothesis.contradicting_evidence_ids,
        missing_evidence=list(hypothesis.missing_evidence or []), limitations=_limitations(hypothesis.limitations),
        status=hypothesis.status, title=hypothesis.title, origin=hypothesis.origin,
        template_code=hypothesis.template_code, verification_questions=list(hypothesis.verification_questions or []),
        evaluation_note=hypothesis.evaluation_note,
        evaluated_by=_summary(users.get(hypothesis.evaluated_by_id)) if hypothesis.evaluated_by_id else None,
        evaluated_at=hypothesis.evaluated_at, version=hypothesis.version,
        created_by=_summary(users.get(hypothesis.created_by_id)) if hypothesis.created_by_id else None,
        created_at=hypothesis.created_at, updated_at=hypothesis.updated_at,
        evidence=[evidence[i] for i in dict.fromkeys(linked) if i in evidence],
    )


def views(db: Session, case_id: UUID, hypotheses: list[Hypothesis]) -> list[HypothesisView]:
    ids = {UUID(i) for h in hypotheses for i in (*h.supporting_evidence_ids, *h.contradicting_evidence_ids)}
    evidence = resolve_evidence(db, case_id, ids)
    user_ids = {u for h in hypotheses for u in (h.created_by_id, h.evaluated_by_id) if u}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    return [_view(h, evidence, users) for h in hypotheses]


def _snapshot(hypothesis: Hypothesis) -> dict[str, Any]:
    return {
        "id": str(hypothesis.id), "title": hypothesis.title, "statement": hypothesis.statement,
        "status": hypothesis.status, "origin": hypothesis.origin, "template_code": hypothesis.template_code,
        "supporting_evidence_ids": list(hypothesis.supporting_evidence_ids),
        "contradicting_evidence_ids": list(hypothesis.contradicting_evidence_ids),
        "missing_evidence": list(hypothesis.missing_evidence or []),
    }


def _hypothesis_or_404(db: Session, case_id: UUID, hypothesis_id: UUID, *, lock: bool = False) -> Hypothesis:
    hypothesis = db.get(Hypothesis, hypothesis_id, with_for_update=lock, populate_existing=lock)
    if hypothesis is None or hypothesis.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=HYPOTHESIS_NOT_FOUND)
    return hypothesis


def _require_hypothesis_version(hypothesis: Hypothesis, version: int) -> None:
    if hypothesis.version != version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"The hypothesis changed since you loaded it (current version {hypothesis.version}). "
                   "Reload and retry.")


def _require_capacity(db: Session, case_id: UUID, adding: int) -> None:
    count = db.scalar(select(func.count()).select_from(Hypothesis).where(Hypothesis.case_id == case_id)) or 0
    if count + adding > MAX_HYPOTHESES:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"A case can hold at most {MAX_HYPOTHESES} hypotheses.")


def _ordered(db: Session, case_id: UUID) -> list[Hypothesis]:
    return list(db.scalars(
        select(Hypothesis).where(Hypothesis.case_id == case_id).order_by(Hypothesis.created_at, Hypothesis.id)
    ).all())


def _template_view(item: dict[str, Any]) -> HypothesisTemplateView:
    return HypothesisTemplateView(
        code=item["code"], title=item["title"], statement=item["statement"],
        related_variables=list(item["related_variables"]), missing_evidence=list(item["missing_evidence"]),
        verification_questions=list(item["verification_questions"]),
        limitations=[HYPOTHESIS_LIMITATION, TEMPLATE_LIMITATION],
    )


# ── routes ───────────────────────────────────────────────────────────────────

@catalog_router.get("/hypothesis-templates", response_model=HypothesisTemplateCatalog)
def hypothesis_templates() -> HypothesisTemplateCatalog:
    """Default rival-hypothesis templates with verification questions. Static; not case evidence."""
    return HypothesisTemplateCatalog(items=[_template_view(t) for t in HYPOTHESIS_TEMPLATES],
                                     limitations=[HYPOTHESIS_LIMITATION, TEMPLATE_LIMITATION])


@router.get("/{case_id}/hypotheses", response_model=HypothesisList)
def list_hypotheses(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> HypothesisList:
    _load(db, case_id, principal.user.id)
    return HypothesisList(items=views(db, case_id, _ordered(db, case_id)), limitations=LIST_LIMITATIONS)


@router.post("/{case_id}/hypotheses", response_model=HypothesisView, status_code=status.HTTP_201_CREATED)
def create_hypothesis(case_id: UUID, body: HypothesisCreate, principal: CurrentPrincipal,
                      db: DbSession) -> HypothesisView:
    """OWNER/EDITOR. New hypotheses are always OPEN."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    _require_capacity(db, case_id, 1)
    _require_evidence(db, case_id, [*body.supporting_evidence_ids, *body.contradicting_evidence_ids])
    now = utcnow()
    hypothesis = Hypothesis(
        case_id=case_id, title=body.title, statement=body.statement, status="OPEN", origin="USER",
        supporting_evidence_ids=[str(i) for i in body.supporting_evidence_ids],
        contradicting_evidence_ids=[str(i) for i in body.contradicting_evidence_ids],
        missing_evidence=list(body.missing_evidence), limitations=_limitations(body.limitations),
        verification_questions=[q.model_dump() for q in body.verification_questions], version=1,
        created_by_id=principal.user.id, created_at=now, updated_at=now,
    )
    db.add(hypothesis)
    db.flush()
    _record(db, case, principal.user, "HYPOTHESIS_CREATED",
            {"hypothesis_id": str(hypothesis.id), "hypothesis": {"before": None, "after": _snapshot(hypothesis)}},
            bump=False)
    db.commit()
    return views(db, case_id, [hypothesis])[0]


@router.post("/{case_id}/hypotheses/templates", response_model=HypothesisList, status_code=status.HTTP_201_CREATED,
             responses={200: {"description": "Every requested template was already added", "model": HypothesisList}})
def add_template_hypotheses(case_id: UUID, body: HypothesisTemplateRequest, principal: CurrentPrincipal,
                            db: DbSession, response: Response) -> HypothesisList:
    """OWNER/EDITOR. Adds default rival hypotheses (status OPEN, origin TEMPLATE); skips ones already added.
    Returns the hypotheses created by this call."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    codes = body.codes or [t["code"] for t in HYPOTHESIS_TEMPLATES]
    existing = set(db.scalars(select(Hypothesis.template_code).where(
        Hypothesis.case_id == case_id, Hypothesis.template_code.is_not(None))))
    pending = [code for code in codes if code not in existing]
    if not pending:
        response.status_code = status.HTTP_200_OK
        return HypothesisList(items=[], limitations=LIST_LIMITATIONS)
    _require_capacity(db, case_id, len(pending))
    created: list[Hypothesis] = []
    for code in pending:
        item = template(code)
        now = utcnow()
        hypothesis = Hypothesis(
            case_id=case_id, title=item["title"], statement=item["statement"], status="OPEN", origin="TEMPLATE",
            template_code=code, supporting_evidence_ids=[], contradicting_evidence_ids=[],
            missing_evidence=list(item["missing_evidence"]),
            limitations=[HYPOTHESIS_LIMITATION, TEMPLATE_LIMITATION],
            verification_questions=list(item["verification_questions"]), version=1,
            created_by_id=principal.user.id, created_at=now, updated_at=now,
        )
        db.add(hypothesis)
        created.append(hypothesis)
    db.flush()
    for hypothesis in created:
        _record(db, case, principal.user, "HYPOTHESIS_CREATED",
                {"hypothesis_id": str(hypothesis.id), "hypothesis": {"before": None, "after": _snapshot(hypothesis)}},
                bump=False)
    db.commit()
    return HypothesisList(items=views(db, case_id, created), limitations=LIST_LIMITATIONS)


@router.get("/{case_id}/hypotheses/{hypothesis_id}", response_model=HypothesisView)
def get_hypothesis(case_id: UUID, hypothesis_id: UUID, principal: CurrentPrincipal, db: DbSession) -> HypothesisView:
    _load(db, case_id, principal.user.id)
    return views(db, case_id, [_hypothesis_or_404(db, case_id, hypothesis_id)])[0]


@router.patch("/{case_id}/hypotheses/{hypothesis_id}", response_model=HypothesisView)
def update_hypothesis(case_id: UUID, hypothesis_id: UUID, body: HypothesisUpdate, principal: CurrentPrincipal,
                      db: DbSession) -> HypothesisView:
    """OWNER/EDITOR. Changing statement, evidence links or missing evidence resets an evaluation to OPEN."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    hypothesis = _hypothesis_or_404(db, case_id, hypothesis_id, lock=True)
    _require_hypothesis_version(hypothesis, body.version)
    updates: dict[str, Any] = {}
    for name in EDITABLE_FIELDS:
        if name not in body.model_fields_set:
            continue
        value = getattr(body, name)
        if name in ("supporting_evidence_ids", "contradicting_evidence_ids"):
            value = [str(i) for i in value]
        elif name == "verification_questions":
            value = [q.model_dump() for q in value]
        elif name == "limitations":
            value = _limitations(value)
        elif isinstance(value, list):
            value = list(value)
        updates[name] = value
    supporting = updates.get("supporting_evidence_ids", hypothesis.supporting_evidence_ids)
    contradicting = updates.get("contradicting_evidence_ids", hypothesis.contradicting_evidence_ids)
    if set(supporting) & set(contradicting):
        raise HTTPException(422,
                            detail="An evidence item cannot both support and contradict the same hypothesis.")
    _require_evidence(db, case_id, [UUID(i) for i in (*updates.get("supporting_evidence_ids", []),
                                                      *updates.get("contradicting_evidence_ids", []))])
    changes: dict[str, Any] = {}
    for name, new in updates.items():
        old = getattr(hypothesis, name)
        if old != new:
            changes[name] = {"before": old, "after": new}
            setattr(hypothesis, name, new)
    if not changes:
        return views(db, case_id, [hypothesis])[0]
    note = None
    if hypothesis.status != "OPEN" and any(name in changes for name in CONTENT_FIELDS):
        changes["status"] = {"before": hypothesis.status, "after": "OPEN"}
        hypothesis.status = "OPEN"
        hypothesis.evaluation_note = None
        hypothesis.evaluated_by_id = None
        hypothesis.evaluated_at = None
        note = "Evaluation reset to OPEN because the hypothesis content changed."
    hypothesis.version += 1
    hypothesis.updated_at = utcnow()
    _record(db, case, principal.user, "HYPOTHESIS_UPDATED",
            {"hypothesis_id": str(hypothesis.id), "hypothesis_version": hypothesis.version, **changes},
            bump=False, note=note)
    db.commit()
    return views(db, case_id, [hypothesis])[0]


@router.post("/{case_id}/hypotheses/{hypothesis_id}/status", response_model=HypothesisView)
def evaluate_hypothesis(case_id: UUID, hypothesis_id: UUID, body: HypothesisStatusChange,
                        principal: CurrentPrincipal, db: DbSession) -> HypothesisView:
    """OWNER/EDITOR/REVIEWER. Mark a hypothesis COMPATIBLE, CONTRADICTED, NOT_EVALUABLE or back to OPEN.
    None of these states means a demonstrated cause."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EVALUATOR_ROLES)
    _require_editable(case)
    hypothesis = _hypothesis_or_404(db, case_id, hypothesis_id, lock=True)
    _require_hypothesis_version(hypothesis, body.version)
    _require_evaluable(hypothesis, body.status)
    if hypothesis.status == body.status and hypothesis.evaluation_note == body.note:
        return views(db, case_id, [hypothesis])[0]
    changes = {"status": {"before": hypothesis.status, "after": body.status},
               "evaluation_note": {"before": hypothesis.evaluation_note, "after": body.note}}
    hypothesis.status = body.status
    hypothesis.evaluation_note = body.note
    hypothesis.evaluated_by_id = principal.user.id
    hypothesis.evaluated_at = utcnow()
    hypothesis.version += 1
    hypothesis.updated_at = hypothesis.evaluated_at
    _record(db, case, principal.user, "HYPOTHESIS_EVALUATED",
            {"hypothesis_id": str(hypothesis.id), "hypothesis_version": hypothesis.version, **changes},
            bump=False, note=body.note)
    db.commit()
    return views(db, case_id, [hypothesis])[0]


@router.delete("/{case_id}/hypotheses/{hypothesis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hypothesis(
    case_id: UUID, hypothesis_id: UUID, principal: CurrentPrincipal, db: DbSession,
    version: int = Query(ge=1, description="Current hypothesis version"),
) -> Response:
    """OWNER/EDITOR. The deleted content stays in the case history."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    hypothesis = _hypothesis_or_404(db, case_id, hypothesis_id, lock=True)
    _require_hypothesis_version(hypothesis, version)
    _record(db, case, principal.user, "HYPOTHESIS_DELETED",
            {"hypothesis_id": str(hypothesis.id), "hypothesis": {"before": _snapshot(hypothesis), "after": None}},
            bump=False)
    db.delete(hypothesis)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
