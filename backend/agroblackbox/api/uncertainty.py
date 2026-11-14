"""Uncertainty Hunter routes (ABB-19): gaps, local questions and reviewable local answers.

Routes (case permissions of ADR-0004; same auth/503 rules as the other case routes):

- ``GET  /api/v1/cases/{case_id}/uncertainty`` (all members): gap inventory and questions from the
  stored case records (timeline MISSING_DATA markers, hypotheses, evidence claims and applicability).
- ``POST /api/v1/cases/{case_id}/uncertainty`` (all members, nothing stored): the same, plus gaps
  from a supplied farm profile, its ABB-17 checks and ABB-18 ordering, and case-side applicability.
- ``POST …/uncertainty/questions/{question_id}/answers`` (OWNER/EDITOR, editable case): local answer
  (FARMER_REPORTED). A correction supersedes the current answer (send ``replaces_answer_id``).
- ``POST …/uncertainty/answers/{answer_id}/review`` (OWNER/EDITOR/REVIEWER other than the author).
- ``POST …/uncertainty/questions/{question_id}/dismiss`` | ``/reopen`` (OWNER/EDITOR, with a note).
- ``GET  …/uncertainty/answers`` and ``…/uncertainty/questions/{question_id}/history`` (all members).
- ``GET  /api/v1/uncertainty/question-catalogue`` (signed-in users): the static question catalogue.

Answers never overwrite scientific records and nothing is scored (docs/science/UNCERTAINTY_HUNTER.md).
"""
from __future__ import annotations

from collections import Counter
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Case, EvidenceClaim, Field, Hypothesis, UncertaintyAnswer, UncertaintyQuestionEvent, User, utcnow
from ..uncertainty import (
    CATALOGUE,
    LIMITATIONS,
    METHOD_VERSION,
    CaseInput,
    ClaimInput,
    HypothesisInput,
    QuestionResolution,
    QuestionSpec,
    QuestionState,
    TimelineGapInput,
    build_report,
    question_spec,
)
from .cases import EDITOR_ROLES, _load, _require_editable, _require_role, _summary
from .comparability import _facts
from .deps import CurrentPrincipal, DbSession
from .evidence import REVIEW_ROLES, _editable
from .timeline import build_timeline
from .uncertainty_dto import (
    ANSWER_LIMITATIONS,
    AnswerCreate,
    AnswerList,
    AnswerReview,
    AnswerView,
    CatalogueItem,
    QuestionCatalogue,
    QuestionEventView,
    QuestionHistory,
    ReportInputs,
    ReportSummary,
    ResolutionChange,
    UncertaintyReport,
    UncertaintyRequest,
)

router = APIRouter(prefix="/api/v1/cases/{case_id}/uncertainty", tags=["uncertainty hunter (ABB-19)"])
catalog_router = APIRouter(prefix="/api/v1/uncertainty", tags=["uncertainty hunter (ABB-19)"])

QuestionId = Annotated[str, Path(pattern=r"^([A-Z][A-Z_]{2,39}|H-[0-9a-f]{32})$",
                                 description="Catalogue code or H-… id of a question written in a hypothesis")]
CURRENT = ("ANSWERED", "REVIEWED")
QUESTION_NOT_FOUND = "Question not found for this case."
ANSWER_NOT_FOUND = "Answer not found."


# ── loading ──────────────────────────────────────────────────────────────────

def _hypotheses(db: Session, case_id: UUID) -> list[HypothesisInput]:
    rows = db.scalars(select(Hypothesis).where(Hypothesis.case_id == case_id)
                      .order_by(Hypothesis.created_at, Hypothesis.id))
    return [HypothesisInput(
        id=h.id, title=h.title, statement=h.statement, status=h.status, template_code=h.template_code,
        missing_evidence=tuple(h.missing_evidence or ()),
        verification_questions=tuple((q.get("question", ""), q.get("why_it_matters", ""))
                                     for q in (h.verification_questions or []) if q.get("question")),
        evidence_ids=frozenset((*h.supporting_evidence_ids, *h.contradicting_evidence_ids)),
    ) for h in rows]


def _timeline_gaps(db: Session, case: Case) -> list[TimelineGapInput]:
    return [TimelineGapInput(id=e.id, event_type=e.event_type, title=e.title, description=e.description,
                             variable=e.observed.variable if e.observed else None,
                             overlaps_incident=e.overlaps_incident)
            for e in build_timeline(db, case).events if e.kind == "MISSING_DATA"]


def _claims(db: Session, case_id: UUID) -> list[ClaimInput]:
    rows = db.scalars(select(EvidenceClaim).where(EvidenceClaim.case_id == case_id)
                      .order_by(EvidenceClaim.created_at, EvidenceClaim.id))
    return [ClaimInput(facts=_facts(c), label=c.claim_text[:160]) for c in rows]


def _case_input(db: Session, case: Case) -> CaseInput:
    labels = tuple(dict.fromkeys(db.scalars(select(Field.region_label).where(Field.case_id == case.id)
                                            .order_by(Field.label, Field.id))))
    return CaseInput(case_id=case.id, incident_start=case.incident_start, incident_end=case.incident_end,
                     crop_history=tuple(case.crop_history or ()), region_labels=labels)


def _events(db: Session, case_id: UUID, question_id: str | None = None) -> list[UncertaintyQuestionEvent]:
    query = select(UncertaintyQuestionEvent).where(UncertaintyQuestionEvent.case_id == case_id)
    if question_id is not None:
        query = query.where(UncertaintyQuestionEvent.question_id == question_id)
    return list(db.scalars(query.order_by(UncertaintyQuestionEvent.created_at, UncertaintyQuestionEvent.id)))


def _current_answers(db: Session, case_id: UUID) -> dict[str, UncertaintyAnswer]:
    rows = db.scalars(select(UncertaintyAnswer).where(UncertaintyAnswer.case_id == case_id,
                                                      UncertaintyAnswer.status.in_(CURRENT)))
    return {a.question_id: a for a in rows}


def _states(db: Session, case_id: UUID) -> dict[str, QuestionState]:
    latest: dict[str, UncertaintyQuestionEvent] = {}
    for event in _events(db, case_id):
        latest[event.question_id] = event
    current = _current_answers(db, case_id)
    return {qid: QuestionState(status=e.to_status, current_answer_id=current[qid].id if qid in current else None,
                               updated_at=e.created_at, note=e.note, snapshot=e.question_snapshot)
            for qid, e in latest.items()}


def _question_status(db: Session, case_id: UUID, question_id: str) -> str:
    events = _events(db, case_id, question_id)
    return events[-1].to_status if events else "OPEN"


def _spec_or_404(db: Session, case_id: UUID, question_id: str) -> QuestionSpec:
    spec = question_spec(question_id, hypotheses=_hypotheses(db, case_id))
    if spec is None:
        events = _events(db, case_id, question_id)
        if events:  # a question written in a hypothesis that has since changed: keep its recorded text
            snap = events[-1].question_snapshot
            spec = QuestionSpec(question_id, snap["kind"], snap["category"], snap["question"], snap["why_it_matters"],
                                snap["measurement"], tuple(snap.get("units") or ()), snap.get("answer_route"),
                                snap.get("origin", "HYPOTHESIS_TEXT"))
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=QUESTION_NOT_FOUND)
    return spec


# ── views ────────────────────────────────────────────────────────────────────

def _users(db: Session, ids: set[UUID | None]) -> dict[UUID, User]:
    ids = {i for i in ids if i}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


def _answer_views(db: Session, case: Case, role: str, me: User, answers: list[UncertaintyAnswer]) -> list[AnswerView]:
    users = _users(db, {u for a in answers for u in (a.answered_by, a.reviewed_by)})
    may_review = role in REVIEW_ROLES and _editable(case)
    return [AnswerView(
        id=a.id, case_id=a.case_id, question_id=a.question_id, question=a.question_snapshot.get("question", ""),
        value_text=a.value_text, value_number=a.value_number, unit=a.unit, observed_from=a.observed_from,
        observed_to=a.observed_to, origin=a.origin, method=a.method, source_reference=a.source_reference, note=a.note,
        status=a.status, is_reviewed=a.status == "REVIEWED", answered_by=_summary(users.get(a.answered_by)),
        answered_at=a.answered_at, reviewed_by=_summary(users.get(a.reviewed_by)) if a.reviewed_by else None,
        reviewed_at=a.reviewed_at, review_note=a.review_note, superseded_by_id=a.superseded_by_id,
        superseded_at=a.superseded_at, version=a.version,
        can_review=may_review and a.answered_by != me.id and a.status in CURRENT,
        limitations=list(ANSWER_LIMITATIONS),
    ) for a in answers]


def _event_views(db: Session, events: list[UncertaintyQuestionEvent]) -> list[QuestionEventView]:
    users = _users(db, {e.actor_id for e in events})
    return [QuestionEventView(id=e.id, question_id=e.question_id, action=e.action, answer_id=e.answer_id,
                              actor=_summary(users.get(e.actor_id)), created_at=e.created_at,
                              from_status=e.from_status, to_status=e.to_status, note=e.note, changes=e.changes)
            for e in events]


def _report(db: Session, case: Case, body: UncertaintyRequest) -> UncertaintyReport:
    profile = body.farm_profile
    if profile is not None and profile.case_id not in (None, case.id):
        raise HTTPException(422, detail="farm_profile.case_id refers to a different case.")
    report = build_report(
        _case_input(db, case), hypotheses=_hypotheses(db, case.id), timeline_gaps=_timeline_gaps(db, case),
        claims=_claims(db, case.id), profile=profile, country=body.country_code, climate=body.koppen_climate,
        horizon_years=body.horizon_years, states=_states(db, case.id))
    causes = Counter(g.cause for g in report.gaps)
    return UncertaintyReport(
        case_id=case.id, case_version=case.version, generated_at=utcnow(), method_version=METHOD_VERSION,
        inputs=ReportInputs(farm_profile_supplied=report.profile_supplied, country_code=body.country_code,
                            koppen_climate=body.koppen_climate, rotation_status=report.rotation_status),
        summary=ReportSummary(
            gaps=len(report.gaps), gaps_by_cause=dict(sorted(causes.items())), questions=len(report.questions),
            open_questions=sum(q.resolution.status == "OPEN" for q in report.questions),
            gaps_not_answerable_locally=sum(not g.answerable_locally for g in report.gaps)),
        gaps=report.gaps, questions=report.questions, prioritisation=report.prioritisation,
        limitations=report.limitations,
    )


def _event(db: Session, case_id: UUID, question_id: str, *, action: str, actor: User, from_status: str,
           to_status: str, spec: QuestionSpec, answer_id: UUID | None = None, note: str | None = None,
           changes: dict[str, Any] | None = None) -> None:
    db.add(UncertaintyQuestionEvent(
        case_id=case_id, question_id=question_id, action=action, answer_id=answer_id, actor_id=actor.id,
        created_at=utcnow(), from_status=from_status, to_status=to_status, note=note,
        question_snapshot=spec.snapshot(), changes=changes or {}))


# ── routes ───────────────────────────────────────────────────────────────────

@catalog_router.get("/question-catalogue", response_model=QuestionCatalogue)
def question_catalogue(principal: CurrentPrincipal) -> QuestionCatalogue:
    """Static catalogue of local questions and analysis tasks. Questions written in hypotheses are added per case."""
    return QuestionCatalogue(method_version=METHOD_VERSION, limitations=list(LIMITATIONS), items=[
        CatalogueItem(id=s.code, kind=s.kind, category=s.category, question=s.question, why_it_matters=s.why_it_matters,
                      measurement=s.measurement, units=list(s.units), answer_route=s.answer_route) for s in CATALOGUE])


@router.get("", response_model=UncertaintyReport)
def uncertainty_report(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> UncertaintyReport:
    """All members. Gaps, questions and what they could change, from the stored case records only."""
    case, _ = _load(db, case_id, principal.user.id)
    return _report(db, case, UncertaintyRequest())


@router.post("", response_model=UncertaintyReport)
def uncertainty_report_with_inputs(case_id: UUID, principal: CurrentPrincipal, db: DbSession,
                                   body: UncertaintyRequest | None = None) -> UncertaintyReport:
    """All members; nothing is stored. Adds gaps from a farm profile (ABB-11 issues, ABB-17 checks and screening,
    ABB-18 ordering) and case-side applicability values (country, Koppen-Geiger class) given in the request."""
    case, _ = _load(db, case_id, principal.user.id)
    return _report(db, case, body or UncertaintyRequest())


@router.get("/answers", response_model=AnswerList)
def list_answers(case_id: UUID, principal: CurrentPrincipal, db: DbSession,
                 question_id: str | None = Query(default=None, max_length=40)) -> AnswerList:
    """All members. Every answer, including superseded and rejected ones, oldest first."""
    case, role = _load(db, case_id, principal.user.id)
    query = select(UncertaintyAnswer).where(UncertaintyAnswer.case_id == case_id)
    if question_id is not None:
        query = query.where(UncertaintyAnswer.question_id == question_id)
    answers = list(db.scalars(query.order_by(UncertaintyAnswer.answered_at, UncertaintyAnswer.id)))
    return AnswerList(items=_answer_views(db, case, role, principal.user, answers), limitations=list(ANSWER_LIMITATIONS))


@router.post("/questions/{question_id}/answers", response_model=AnswerView, status_code=status.HTTP_201_CREATED)
def answer_question(case_id: UUID, question_id: QuestionId, body: AnswerCreate, principal: CurrentPrincipal,
                    db: DbSession) -> AnswerView:
    """OWNER/EDITOR. Records a FARMER_REPORTED answer. To correct the current answer, send its id as
    ``replaces_answer_id``: the old answer is kept as SUPERSEDED. Analysis tasks are answered in their own workflow."""
    me = principal.user
    case, role = _load(db, case_id, me.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    spec = _spec_or_404(db, case_id, question_id)
    if spec.answer_route is not None:
        raise HTTPException(422, detail=f"{question_id} is an analysis task; it is resolved through "
                                        f"{spec.answer_route}, not with a local answer.")
    current_status = _question_status(db, case_id, question_id)
    if current_status == "DISMISSED":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The question is dismissed; reopen it before answering.")
    current = db.scalar(select(UncertaintyAnswer).where(
        UncertaintyAnswer.case_id == case_id, UncertaintyAnswer.question_id == question_id,
        UncertaintyAnswer.status.in_(CURRENT)).with_for_update())
    if (current.id if current else None) != body.replaces_answer_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=(
            f"The current answer is {current.id if current else 'none'}; send it as replaces_answer_id to correct it "
            "(reload and retry)."))
    now = utcnow()
    answer = UncertaintyAnswer(
        case_id=case_id, question_id=question_id, question_snapshot=spec.snapshot(), value_text=body.value_text,
        value_number=body.value_number, unit=body.unit, observed_from=body.observed_from,
        observed_to=body.observed_to, origin=body.origin, method=body.method, source_reference=body.source_reference,
        note=body.note, status="ANSWERED", answered_by=me.id, answered_at=now, version=1)
    if current is not None:
        current.status, current.superseded_at = "SUPERSEDED", now
        current.version += 1
        db.flush()  # free the "one current answer" index slot before inserting
    db.add(answer)
    db.flush()
    if current is not None:
        current.superseded_by_id = answer.id
    _event(db, case_id, question_id, action="ANSWERED", actor=me, from_status=current_status, to_status="ANSWERED",
           spec=spec, answer_id=answer.id, note=body.note,
           changes={"replaces_answer_id": str(current.id) if current else None,
                    "value_text": body.value_text, "value_number": body.value_number, "unit": body.unit,
                    "origin": body.origin})
    db.commit()
    return _answer_views(db, case, role, me, [answer])[0]


@router.post("/answers/{answer_id}/review", response_model=AnswerView)
def review_answer(case_id: UUID, answer_id: UUID, body: AnswerReview, principal: CurrentPrincipal,
                  db: DbSession) -> AnswerView:
    """OWNER/EDITOR/REVIEWER other than the author. REVIEWED: checked against the documentation available;
    REJECTED: not accepted (the question returns to OPEN). A REVIEWED answer can later be REJECTED."""
    me = principal.user
    case, role = _load(db, case_id, me.id, lock=True)
    _require_role(role, REVIEW_ROLES)
    _require_editable(case)
    answer = db.get(UncertaintyAnswer, answer_id, with_for_update=True, populate_existing=True)
    if answer is None or answer.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ANSWER_NOT_FOUND)
    if answer.answered_by == me.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="You recorded this answer; a different case member must review it.")
    if answer.version != body.version:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=(
            f"The answer changed since you loaded it (current version {answer.version}). Reload and retry."))
    allowed = {"ANSWERED": {"REVIEWED", "REJECTED"}, "REVIEWED": {"REJECTED"}}.get(answer.status, set())
    if body.decision not in allowed:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"An answer that is {answer.status} cannot be marked {body.decision}.")
    from_status = _question_status(db, case_id, answer.question_id)
    before = answer.status
    answer.status, answer.reviewed_by, answer.reviewed_at, answer.review_note = body.decision, me.id, utcnow(), body.note
    answer.version += 1
    spec = _spec_or_404(db, case_id, answer.question_id)
    _event(db, case_id, answer.question_id, action=body.decision, actor=me, from_status=from_status,
           to_status="REVIEWED" if body.decision == "REVIEWED" else "OPEN", spec=spec, answer_id=answer.id,
           note=body.note, changes={"answer_status": {"before": before, "after": body.decision}})
    db.commit()
    return _answer_views(db, case, role, me, [answer])[0]


def _resolution(case_id: UUID, question_id: str, body: ResolutionChange, principal, db: Session, *,
                action: str, from_required: str, to_status: str) -> QuestionHistory:
    me = principal.user
    case, role = _load(db, case_id, me.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    spec = _spec_or_404(db, case_id, question_id)
    current = _question_status(db, case_id, question_id)
    if current != from_required:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"The question is {current}; only a {from_required} question can be "
                                   f"{action.lower()}.")
    _event(db, case_id, question_id, action=action, actor=me, from_status=current, to_status=to_status, spec=spec,
           note=body.note)
    db.commit()
    return _history(db, case, role, me, question_id)


@router.post("/questions/{question_id}/dismiss", response_model=QuestionHistory)
def dismiss_question(case_id: UUID, question_id: QuestionId, body: ResolutionChange, principal: CurrentPrincipal,
                     db: DbSession) -> QuestionHistory:
    """OWNER/EDITOR. Marks an OPEN question DISMISSED with a note (e.g. not applicable, cannot be obtained).
    The underlying gap stays listed."""
    return _resolution(case_id, question_id, body, principal, db, action="DISMISSED", from_required="OPEN",
                       to_status="DISMISSED")


@router.post("/questions/{question_id}/reopen", response_model=QuestionHistory)
def reopen_question(case_id: UUID, question_id: QuestionId, body: ResolutionChange, principal: CurrentPrincipal,
                    db: DbSession) -> QuestionHistory:
    """OWNER/EDITOR. Returns a DISMISSED question to OPEN with a note."""
    return _resolution(case_id, question_id, body, principal, db, action="REOPENED", from_required="DISMISSED",
                       to_status="OPEN")


def _history(db: Session, case: Case, role: str, me: User, question_id: str) -> QuestionHistory:
    events = _events(db, case.id, question_id)
    answers = list(db.scalars(select(UncertaintyAnswer).where(
        UncertaintyAnswer.case_id == case.id, UncertaintyAnswer.question_id == question_id)
        .order_by(UncertaintyAnswer.answered_at, UncertaintyAnswer.id)))
    current = next((a for a in answers if a.status in CURRENT), None)
    last = events[-1] if events else None
    spec = question_spec(question_id, hypotheses=_hypotheses(db, case.id))
    if spec is None and last is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=QUESTION_NOT_FOUND)
    text = spec.question if spec else last.question_snapshot.get("question")
    return QuestionHistory(
        case_id=case.id, question_id=question_id, question=text,
        resolution=QuestionResolution(status=last.to_status if last else "OPEN",
                                      current_answer_id=current.id if current else None,
                                      updated_at=last.created_at if last else None, note=last.note if last else None),
        events=_event_views(db, events), answers=_answer_views(db, case, role, me, answers))


@router.get("/questions/{question_id}/history", response_model=QuestionHistory)
def question_history(case_id: UUID, question_id: QuestionId, principal: CurrentPrincipal,
                     db: DbSession) -> QuestionHistory:
    """All members. Every event (answered, reviewed, rejected, dismissed, reopened) and every answer, oldest first."""
    case, role = _load(db, case_id, principal.user.id)
    return _history(db, case, role, principal.user, question_id)
