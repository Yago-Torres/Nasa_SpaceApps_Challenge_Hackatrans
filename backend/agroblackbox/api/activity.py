"""Read-only case activity feed (ABB-25): one chronological view over the existing audit records.

Nothing is copied or stored. Sources:

- ``case_history`` (CASE_HISTORY): case edits, workflow, permissions, invitations, share links, hypothesis
  evaluations, conclusion/edge reviews, deletions. ``changes`` is served with coordinates REDACTED for
  REVIEWER/VIEWER, exactly like ``GET /cases/{id}/history``.
- ``evidence_claim_events`` (CLAIM_EVENT): claim creation, edits and review decisions with the source the
  reviewer consulted and the paper identity at that moment.
- ``claim_disagreement_reviews`` (DISAGREEMENT_REVIEW): decisions on candidate contradictions.
- ``case_comments`` / ``case_comment_revisions`` (COMMENT): posted, edited and deleted events; the text
  itself is served by the comments endpoints, not here.

``evidence`` is what the source recorded with the action; it is null when the source recorded nothing
(e.g. history rows written before ABB-25 started recording the evidence of hypothesis evaluations and
conclusion/edge reviews).
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import String, func, literal, select, union_all
from sqlalchemy.orm import Session

from ..db.models import (
    CaseComment,
    CaseCommentRevision,
    CaseHistory,
    ClaimDisagreementReview,
    EvidenceClaimEvent,
    User,
)
from ..privacy import PRECISE_ROLES, redact_coordinates
from .cases import _load, _summary
from .collaboration_dto import ActivityEntry, ActivityPage, ActivityTarget
from .deps import CurrentPrincipal, DbSession

router = APIRouter(prefix="/api/v1/cases", tags=["collaboration (ABB-25)"])

SOURCES = ["CASE_HISTORY", "CLAIM_EVENT", "DISAGREEMENT_REVIEW", "COMMENT"]
_ID_KEYS = (
    ("edge_id", "GRAPH_EDGE"), ("conclusion_id", "CONCLUSION"), ("hypothesis_id", "HYPOTHESIS"),
    ("field_id", "FIELD"), ("claim_id", "CLAIM"), ("invitation_id", "INVITATION"),
    ("share_link_id", "SHARE_LINK"), ("user_id", "USER"),
)
_SNAPSHOT_KEYS = (
    ("edge", "GRAPH_EDGE"), ("conclusion", "CONCLUSION"), ("hypothesis", "HYPOTHESIS"), ("field", "FIELD"),
    ("claim", "CLAIM"),
)


def history_category(action: str) -> str:
    if action.startswith("PERMISSION_"):
        return "PERMISSION"
    if action.startswith("INVITATION_"):
        return "INVITATION"
    if action.startswith("SHARE_LINK_"):
        return "SHARING"
    if action.endswith("_REVIEWED") or action == "HYPOTHESIS_EVALUATED":
        return "REVIEW"
    if action == "STATUS_CHANGED":
        return "WORKFLOW"
    if action.startswith(("HYPOTHESIS_", "CONCLUSION_", "GRAPH_EDGE_", "EVIDENCE_")):
        return "EVIDENCE"
    return "CASE"


def history_target(case_id: UUID, changes: dict[str, Any]) -> ActivityTarget:
    for key, kind in _ID_KEYS:
        if isinstance(changes.get(key), str):
            return ActivityTarget(kind=kind, id=changes[key])
    for key, kind in _SNAPSHOT_KEYS:
        value = changes.get(key)
        if isinstance(value, dict):
            snapshot = value.get("after") or value.get("before")
            if isinstance(snapshot, dict) and snapshot.get("id"):
                return ActivityTarget(kind=kind, id=str(snapshot["id"]))
    return ActivityTarget(kind="CASE", id=str(case_id))


def _union(case_id: UUID):
    def part(tag: str, record_id, at, *conditions):
        return select(literal(tag, String).label("src"), record_id.label("record_id"), at.label("at")).where(*conditions)

    return union_all(
        part("H", CaseHistory.id, CaseHistory.created_at, CaseHistory.case_id == case_id),
        part("C", EvidenceClaimEvent.id, EvidenceClaimEvent.created_at, EvidenceClaimEvent.case_id == case_id),
        part("D", ClaimDisagreementReview.id, ClaimDisagreementReview.reviewed_at,
             ClaimDisagreementReview.case_id == case_id),
        part("P", CaseComment.id, CaseComment.created_at, CaseComment.case_id == case_id),
        part("E", CaseCommentRevision.id, CaseCommentRevision.created_at, CaseCommentRevision.case_id == case_id),
        part("X", CaseComment.id, CaseComment.deleted_at, CaseComment.case_id == case_id,
             CaseComment.deleted_at.is_not(None)),
    ).subquery()


def _load_records(db: Session, keys: list[tuple[str, UUID]]) -> dict[str, dict[UUID, Any]]:
    wanted: dict[str, set[UUID]] = {}
    for tag, record_id in keys:
        wanted.setdefault({"X": "P"}.get(tag, tag), set()).add(record_id)
    models = {"H": CaseHistory, "C": EvidenceClaimEvent, "D": ClaimDisagreementReview, "P": CaseComment,
              "E": CaseCommentRevision}
    loaded = {tag: {row.id: row for row in db.scalars(select(models[tag]).where(models[tag].id.in_(ids)))}
              for tag, ids in wanted.items()}
    revisions = loaded.get("E", {})
    if revisions:  # an edit event needs its comment's target
        missing = {r.comment_id for r in revisions.values()} - set(loaded.get("P", {}))
        if missing:
            loaded.setdefault("P", {}).update(
                {row.id: row for row in db.scalars(select(CaseComment).where(CaseComment.id.in_(missing)))})
    return loaded


def _entry(tag: str, row: Any, case_id: UUID, role: str, users: dict[UUID, User],
           comments: dict[UUID, CaseComment]) -> ActivityEntry:
    def who(user_id: UUID | None):
        return _summary(users.get(user_id)) if user_id else None

    if tag == "H":
        changes = row.changes or {}
        if role not in PRECISE_ROLES:
            changes = redact_coordinates(changes)
        evidence = changes.get("evidence")
        return ActivityEntry(
            id=f"history:{row.id}", source="CASE_HISTORY", kind=row.action, category=history_category(row.action),
            actor=who(row.actor_id), created_at=row.created_at, target=history_target(case_id, changes),
            note=row.note, evidence=evidence if isinstance(evidence, dict) else None,
            changes=changes,
        )
    if tag == "C":
        evidence: dict[str, Any] = {"paper": row.paper_snapshot, "claim_version": row.claim_version}
        if row.source_consulted:
            evidence["source_consulted"] = row.source_consulted
        return ActivityEntry(
            id=f"claim-event:{row.id}", source="CLAIM_EVENT", kind=f"CLAIM_{row.action}",
            category="REVIEW" if row.action == "REVIEWED" else "EVIDENCE", actor=who(row.actor_id),
            created_at=row.created_at, target=ActivityTarget(kind="CLAIM", id=str(row.claim_id)), note=row.note,
            evidence=evidence,
            changes={"review_status": {"before": row.from_status, "after": row.to_status}, **(row.changes or {})},
        )
    if tag == "D":
        return ActivityEntry(
            id=f"disagreement-review:{row.id}", source="DISAGREEMENT_REVIEW", kind="DISAGREEMENT_REVIEWED",
            category="REVIEW", actor=who(row.reviewer_id), created_at=row.reviewed_at,
            target=ActivityTarget(kind="DISAGREEMENT", id=str(row.pair_id)), note=row.note,
            evidence={"claims": [{"id": str(row.claim_a_id), "version": row.claim_a_version},
                                 {"id": str(row.claim_b_id), "version": row.claim_b_version}],
                      "decision": row.decision},
        )
    if tag == "E":
        comment = comments.get(row.comment_id)
        target = ActivityTarget(kind=comment.target_kind, id=str(comment.target_id) if comment.target_id else
                                str(case_id)) if comment else None
        return ActivityEntry(
            id=f"comment:{row.comment_id}:revision:{row.revision}", source="COMMENT", kind="COMMENT_EDITED",
            category="COMMENT", actor=who(row.edited_by_id), created_at=row.created_at, target=target,
            changes={"comment_id": str(row.comment_id), "revision": row.revision},
        )
    target = ActivityTarget(kind=row.target_kind, id=str(row.target_id) if row.target_id else str(case_id))
    if tag == "X":
        return ActivityEntry(
            id=f"comment:{row.id}:deleted", source="COMMENT", kind="COMMENT_DELETED", category="COMMENT",
            actor=who(row.deleted_by_id), created_at=row.deleted_at, target=target,
            changes={"comment_id": str(row.id)},
        )
    return ActivityEntry(
        id=f"comment:{row.id}", source="COMMENT", kind="COMMENT_REPLIED" if row.parent_id else "COMMENT_POSTED",
        category="COMMENT", actor=who(row.author_id), created_at=row.created_at, target=target,
        changes={"comment_id": str(row.id), "parent_id": str(row.parent_id) if row.parent_id else None},
    )


def _actor_ids(tag: str, row: Any) -> set[UUID | None]:
    return {
        "H": lambda: {row.actor_id}, "C": lambda: {row.actor_id}, "D": lambda: {row.reviewer_id},
        "P": lambda: {row.author_id}, "X": lambda: {row.deleted_by_id}, "E": lambda: {row.edited_by_id},
    }[tag]()


@router.get("/{case_id}/activity", response_model=ActivityPage)
def case_activity(
    case_id: UUID, principal: CurrentPrincipal, db: DbSession,
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0, le=100_000),
    order: Literal["asc", "desc"] = Query(default="desc", description="desc = newest first"),
) -> ActivityPage:
    """Every member. Who did what, when, on which record, and with which evidence."""
    _, role = _load(db, case_id, principal.user.id)
    feed = _union(case_id)
    total = db.scalar(select(func.count()).select_from(feed)) or 0
    at = feed.c.at.desc() if order == "desc" else feed.c.at.asc()
    keys = [(tag, record_id) for tag, record_id, _ in db.execute(
        select(feed.c.src, feed.c.record_id, feed.c.at).order_by(at, feed.c.src, feed.c.record_id)
        .limit(limit).offset(offset)).all()]
    records = _load_records(db, keys)
    rows = [(tag, records[{"X": "P"}.get(tag, tag)][record_id]) for tag, record_id in keys]
    actor_ids = set().union(*(_actor_ids(tag, row) for tag, row in rows)) if rows else set()
    wanted = {i for i in actor_ids if i}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(wanted)))} if wanted else {}
    comments = records.get("P", {})
    return ActivityPage(
        items=[_entry(tag, row, case_id, role, users, comments) for tag, row in rows],
        total=total, limit=limit, offset=offset, order=order, sources=SOURCES,
    )
