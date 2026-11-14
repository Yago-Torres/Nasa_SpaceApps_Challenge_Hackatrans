"""Plain-text comments on a case and its records (ABB-25).

- Every member may comment, including VIEWER (the Issue: "un invitado puede comentar"). Commenting does
  not change the case content or its version and is allowed in every workflow status, but not on an
  archived (read-only) case.
- Targets: the case itself or a record of the same case (field, observation, anomaly, hypothesis,
  evidence claim, conclusion, evidence-graph edge or timeline event). A target from another case or a
  nonexistent one is rejected with 422; a comment keeps its target id if that record is deleted later.
- Replies are one level deep and inherit the parent's target.
- Only the author edits (current ``version`` required); the replaced text is kept as a revision.
- The author or the case OWNER (moderation) deletes. Deletion is a tombstone: the API stops serving the
  text and its revisions, the rows stay for audit until the case is deleted.
- Bodies are plain text, returned exactly as stored, never interpreted; clients render them as text.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import (
    Anomaly,
    Case,
    CaseComment,
    CaseCommentRevision,
    EvidenceClaim,
    EvidenceConclusion,
    EvidenceGraphEdge,
    Field,
    Hypothesis,
    Observation,
    User,
    utcnow,
)
from .cases import OWNER_ONLY, _load, _summary
from .collaboration_dto import (
    CommentCreate,
    CommentEdit,
    CommentList,
    CommentRevisionView,
    CommentTarget,
    CommentTargetKind,
    CommentView,
)
from .deps import CurrentPrincipal, DbSession

router = APIRouter(prefix="/api/v1/cases", tags=["collaboration (ABB-25)"])

MAX_COMMENTS_PER_CASE = 5000
COMMENT_NOT_FOUND = "Comment not found."
TARGET_MODELS: dict[str, Any] = {
    "FIELD": Field, "OBSERVATION": Observation, "ANOMALY": Anomaly, "HYPOTHESIS": Hypothesis,
    "CLAIM": EvidenceClaim, "CONCLUSION": EvidenceConclusion, "GRAPH_EDGE": EvidenceGraphEdge,
}


def _require_open(case: Case) -> None:
    if case.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The case is archived; unarchive it before commenting.")


def require_target(db: Session, case: Case, kind: str, target_id: UUID | None) -> None:
    """422 unless the target is the case itself or an existing record of this case."""
    if kind == "CASE":
        return
    found = False
    if kind == "TIMELINE_EVENT":
        from .timeline import build_timeline  # local import: the timeline pulls in the ingestion modules

        found = any(event.id == target_id for event in build_timeline(db, case).events)
    else:
        model = TARGET_MODELS[kind]
        found = db.scalar(select(model.id).where(model.id == target_id, model.case_id == case.id)) is not None
    if not found:
        raise HTTPException(422, detail=f"Comment target {kind} {target_id} was not found in this case.")


def _comment_or_404(db: Session, case_id: UUID, comment_id: UUID, *, lock: bool = False) -> CaseComment:
    comment = db.get(CaseComment, comment_id, with_for_update=lock, populate_existing=lock)
    if comment is None or comment.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=COMMENT_NOT_FOUND)
    return comment


def _views(db: Session, comments: list[CaseComment], role: str, me: User) -> list[CommentView]:
    if not comments:
        return []
    ids = [c.id for c in comments]
    revisions = dict(db.execute(
        select(CaseCommentRevision.comment_id, func.count()).where(CaseCommentRevision.comment_id.in_(ids))
        .group_by(CaseCommentRevision.comment_id)).all())
    replies = dict(db.execute(
        select(CaseComment.parent_id, func.count()).where(CaseComment.parent_id.in_(ids))
        .group_by(CaseComment.parent_id)).all())
    wanted = {c.author_id for c in comments} | {c.deleted_by_id for c in comments}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({i for i in wanted if i})))}
    views = []
    for c in comments:
        deleted = c.deleted_at is not None
        mine = c.author_id is not None and c.author_id == me.id
        views.append(CommentView(
            id=c.id, case_id=c.case_id, target=CommentTarget(kind=c.target_kind, id=c.target_id),
            parent_id=c.parent_id, author=_summary(users.get(c.author_id)) if c.author_id else None,
            body=None if deleted else c.body, created_at=c.created_at, edited_at=c.edited_at, version=c.version,
            revision_count=0 if deleted else revisions.get(c.id, 0), reply_count=replies.get(c.id, 0),
            deleted=deleted, deleted_at=c.deleted_at,
            deleted_by=_summary(users.get(c.deleted_by_id)) if c.deleted_by_id else None,
            can_edit=not deleted and mine, can_delete=not deleted and (mine or role in OWNER_ONLY),
        ))
    return views


@router.get("/{case_id}/comments", response_model=CommentList)
def list_comments(
    case_id: UUID, principal: CurrentPrincipal, db: DbSession,
    target_kind: CommentTargetKind | None = Query(default=None, description="Only comments on this kind of target"),
    target_id: UUID | None = Query(default=None, description="Only comments on this record (needs target_kind)"),
    limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0, le=100_000),
) -> CommentList:
    """Every member. Oldest first; replies carry ``parent_id`` (the client groups them). Deleted
    comments stay as tombstones (``deleted: true``, ``body: null``) so threads keep their shape."""
    _, role = _load(db, case_id, principal.user.id)
    if target_id is not None and target_kind is None:
        raise HTTPException(422, detail="target_id needs target_kind.")
    query = select(CaseComment).where(CaseComment.case_id == case_id)
    if target_kind is not None:
        query = query.where(CaseComment.target_kind == target_kind)
    if target_id is not None:
        query = query.where(CaseComment.target_id == target_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(CaseComment.created_at, CaseComment.id).limit(limit).offset(offset)).all()
    return CommentList(items=_views(db, list(rows), role, principal.user), total=total, limit=limit, offset=offset)


@router.post("/{case_id}/comments", response_model=CommentView, status_code=status.HTTP_201_CREATED)
def create_comment(case_id: UUID, body: CommentCreate, principal: CurrentPrincipal, db: DbSession) -> CommentView:
    """Every member, VIEWER included. 422 for a target outside this case; 409 on an archived case."""
    case, role = _load(db, case_id, principal.user.id)
    _require_open(case)
    if db.scalar(select(func.count()).select_from(CaseComment).where(CaseComment.case_id == case_id)) \
            >= MAX_COMMENTS_PER_CASE:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"A case can hold at most {MAX_COMMENTS_PER_CASE} comments.")
    target_kind, target_id = body.target_kind, body.target_id
    if body.parent_id is not None:
        parent = db.get(CaseComment, body.parent_id)
        if parent is None or parent.case_id != case_id:
            raise HTTPException(422, detail="The comment you reply to was not found in this case.")
        if parent.parent_id is not None:
            raise HTTPException(422, detail="Replies are one level deep; reply to the top-level comment.")
        if parent.deleted_at is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="The comment you reply to was deleted.")
        target_kind, target_id = parent.target_kind, parent.target_id
    else:
        require_target(db, case, target_kind, target_id)
    comment = CaseComment(
        case_id=case_id, author_id=principal.user.id, target_kind=target_kind, target_id=target_id,
        parent_id=body.parent_id, body=body.body, version=1, created_at=utcnow(),
    )
    db.add(comment)
    db.commit()
    return _views(db, [comment], role, principal.user)[0]


@router.get("/{case_id}/comments/{comment_id}", response_model=CommentView)
def get_comment(case_id: UUID, comment_id: UUID, principal: CurrentPrincipal, db: DbSession) -> CommentView:
    _, role = _load(db, case_id, principal.user.id)
    return _views(db, [_comment_or_404(db, case_id, comment_id)], role, principal.user)[0]


@router.patch("/{case_id}/comments/{comment_id}", response_model=CommentView)
def edit_comment(case_id: UUID, comment_id: UUID, body: CommentEdit, principal: CurrentPrincipal,
                 db: DbSession) -> CommentView:
    """Author only (403 otherwise). The previous text is kept in the edit history."""
    case, role = _load(db, case_id, principal.user.id)
    _require_open(case)
    comment = _comment_or_404(db, case_id, comment_id, lock=True)
    if comment.author_id != principal.user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the author can edit a comment.")
    if comment.deleted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The comment was deleted.")
    if comment.version != body.version:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"The comment changed since you loaded it (current version {comment.version}).")
    if comment.body != body.body:
        now: datetime = utcnow()
        revision = (db.scalar(select(func.max(CaseCommentRevision.revision))
                              .where(CaseCommentRevision.comment_id == comment.id)) or 0) + 1
        db.add(CaseCommentRevision(comment_id=comment.id, case_id=case_id, revision=revision, body=comment.body,
                                   edited_by_id=principal.user.id, created_at=now))
        comment.body = body.body
        comment.version += 1
        comment.edited_at = now
        db.commit()
    return _views(db, [comment], role, principal.user)[0]


@router.delete("/{case_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    case_id: UUID, comment_id: UUID, principal: CurrentPrincipal, db: DbSession,
    version: int = Query(ge=1, description="Current comment version"),
) -> Response:
    """Author or OWNER. Leaves a tombstone; the text is no longer served."""
    case, role = _load(db, case_id, principal.user.id)
    _require_open(case)
    comment = _comment_or_404(db, case_id, comment_id, lock=True)
    if comment.author_id != principal.user.id and role not in OWNER_ONLY:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Only the author or the case owner can delete a comment.")
    if comment.deleted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The comment was already deleted.")
    if comment.version != version:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"The comment changed since you loaded it (current version {comment.version}).")
    comment.deleted_at = utcnow()
    comment.deleted_by_id = principal.user.id
    comment.version += 1
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{case_id}/comments/{comment_id}/revisions", response_model=list[CommentRevisionView])
def comment_revisions(case_id: UUID, comment_id: UUID, principal: CurrentPrincipal,
                      db: DbSession) -> list[CommentRevisionView]:
    """Every member. Earlier texts, oldest first. 410 once the comment is deleted."""
    _load(db, case_id, principal.user.id)
    comment = _comment_or_404(db, case_id, comment_id)
    if comment.deleted_at is not None:
        raise HTTPException(status.HTTP_410_GONE, detail="The comment was deleted; its text is kept for audit only.")
    rows = db.scalars(select(CaseCommentRevision).where(CaseCommentRevision.comment_id == comment.id)
                      .order_by(CaseCommentRevision.revision)).all()
    editors = {r.edited_by_id for r in rows if r.edited_by_id}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(editors)))}
    return [
        CommentRevisionView(revision=r.revision, body=r.body, replaced_at=r.created_at,
                            edited_by=_summary(users.get(r.edited_by_id)) if r.edited_by_id else None)
        for r in rows
    ]
