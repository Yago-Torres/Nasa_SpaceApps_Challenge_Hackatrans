"""Case invitations accepted by the invitee (ABB-25).

- The OWNER invites an e-mail address with a role (EDITOR, REVIEWER or VIEWER), an optional note and an
  expiry (1–30 days, default 14). The response is the same whether or not an account exists for that
  e-mail, so invitations cannot be used to discover accounts. No e-mail is sent: the invitee sees the
  invitation in ``GET /api/v1/invitations`` after signing in with that address.
- The invitee accepts or declines. Accepting creates the case permission. Anything not addressed to the
  caller's e-mail, already answered, revoked or expired is a 404 for the invitee.
- The owner lists invitations and revokes pending ones. Every change is appended to ``case_history``
  (without the e-mail address, which only the owner sees) and does not bump the case version.
- The direct grant ``POST /cases/{id}/permissions`` keeps working unchanged.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..db.models import Case, CaseInvitation, CasePermission, User, utcnow
from .cases import OWNER_ONLY, _load, _record, _require_role, _summary, _sync_visibility
from .collaboration_dto import (
    InvitationCreate,
    InvitationDecision,
    InvitationList,
    InvitationView,
    InvitedCase,
    ReceivedInvitationList,
    ReceivedInvitationView,
)
from .deps import CurrentPrincipal, DbSession

case_router = APIRouter(prefix="/api/v1/cases", tags=["collaboration (ABB-25)"])
me_router = APIRouter(prefix="/api/v1/invitations", tags=["collaboration (ABB-25)"])

MAX_PENDING_INVITATIONS = 50
INVITATION_NOT_FOUND = "Invitation not found."


def effective_status(invitation: CaseInvitation, now: datetime | None = None) -> str:
    if invitation.status == "PENDING" and invitation.expires_at <= (now or utcnow()):
        return "EXPIRED"
    return invitation.status


def _users(db: Session, ids: set[UUID | None]) -> dict[UUID, User]:
    wanted = {i for i in ids if i is not None}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(wanted)))} if wanted else {}


def _view(invitation: CaseInvitation, users: dict[UUID, User], now: datetime) -> InvitationView:
    return InvitationView(
        id=invitation.id, case_id=invitation.case_id, email=invitation.email, role=invitation.role,
        note=invitation.note, status=effective_status(invitation, now),
        invited_by=_summary(users.get(invitation.created_by_id)) if invitation.created_by_id else None,
        created_at=invitation.created_at, expires_at=invitation.expires_at, responded_at=invitation.responded_at,
        revoked_at=invitation.revoked_at,
    )


def _expire_stale(db: Session, case_id: UUID, email: str | None = None) -> None:
    """Mark lapsed PENDING rows EXPIRED so the one-pending-per-e-mail index frees up."""
    query = update(CaseInvitation).where(
        CaseInvitation.case_id == case_id, CaseInvitation.status == "PENDING", CaseInvitation.expires_at <= utcnow())
    if email is not None:
        query = query.where(CaseInvitation.email == email)
    db.execute(query.values(status="EXPIRED"))


# ── owner side ───────────────────────────────────────────────────────────────

@case_router.post("/{case_id}/invitations", response_model=InvitationView, status_code=status.HTTP_201_CREATED)
def create_invitation(case_id: UUID, body: InvitationCreate, principal: CurrentPrincipal,
                      db: DbSession) -> InvitationView:
    """OWNER only. Same 201 response whether or not the e-mail has an account (no enumeration).
    409 if that person is already a member or already has a pending invitation."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, OWNER_ONLY)
    if body.email == principal.user.email:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="You already own this case.")
    # Only reveals membership, which the owner already sees in the member list.
    member = db.scalar(
        select(CasePermission.id).join(User, User.id == CasePermission.user_id)
        .where(CasePermission.case_id == case_id, User.email == body.email)
    )
    if member is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="That person is already a member; change their role in the member list.")
    _expire_stale(db, case_id, body.email)
    pending = db.scalar(select(func.count()).select_from(CaseInvitation).where(
        CaseInvitation.case_id == case_id, CaseInvitation.status == "PENDING"))
    if db.scalar(select(CaseInvitation.id).where(
            CaseInvitation.case_id == case_id, CaseInvitation.email == body.email,
            CaseInvitation.status == "PENDING")) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="A pending invitation for that e-mail already exists; revoke it first.")
    if (pending or 0) >= MAX_PENDING_INVITATIONS:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"A case can have at most {MAX_PENDING_INVITATIONS} pending invitations.")
    now = utcnow()
    invitation = CaseInvitation(
        case_id=case_id, email=body.email, role=body.role, note=body.note, status="PENDING",
        created_by_id=principal.user.id, created_at=now, expires_at=now + timedelta(days=body.expires_in_days),
    )
    db.add(invitation)
    db.flush()
    _record(db, case, principal.user, "INVITATION_CREATED",
            {"invitation_id": str(invitation.id), "role": {"before": None, "after": body.role},
             "expires_at": invitation.expires_at.isoformat()}, bump=False)
    db.commit()
    return _view(invitation, {principal.user.id: principal.user}, now)


@case_router.get("/{case_id}/invitations", response_model=InvitationList)
def list_invitations(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> InvitationList:
    """OWNER only (the list contains e-mail addresses). Newest first, every status."""
    _, role = _load(db, case_id, principal.user.id)
    _require_role(role, OWNER_ONLY)
    rows = db.scalars(select(CaseInvitation).where(CaseInvitation.case_id == case_id)
                      .order_by(CaseInvitation.created_at.desc(), CaseInvitation.id)).all()
    users = _users(db, {row.created_by_id for row in rows})
    now = utcnow()
    return InvitationList(items=[_view(row, users, now) for row in rows])


@case_router.delete("/{case_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(case_id: UUID, invitation_id: UUID, principal: CurrentPrincipal, db: DbSession) -> Response:
    """OWNER only. Pending invitations only (409 once answered, revoked or expired). Effective at once."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, OWNER_ONLY)
    invitation = db.get(CaseInvitation, invitation_id, with_for_update=True)
    if invitation is None or invitation.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=INVITATION_NOT_FOUND)
    current = effective_status(invitation)
    if current != "PENDING":
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"The invitation is {current}; it cannot be revoked.")
    invitation.status = "REVOKED"
    invitation.revoked_at = utcnow()
    invitation.revoked_by_id = principal.user.id
    _record(db, case, principal.user, "INVITATION_REVOKED",
            {"invitation_id": str(invitation.id), "status": {"before": "PENDING", "after": "REVOKED"}}, bump=False)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── invitee side ─────────────────────────────────────────────────────────────

@me_router.get("", response_model=ReceivedInvitationList)
def my_invitations(principal: CurrentPrincipal, db: DbSession) -> ReceivedInvitationList:
    """Pending, unexpired invitations addressed to the signed-in account's e-mail, newest first."""
    rows = db.execute(
        select(CaseInvitation, Case).join(Case, Case.id == CaseInvitation.case_id)
        .where(CaseInvitation.email == principal.user.email, CaseInvitation.status == "PENDING",
               CaseInvitation.expires_at > utcnow())
        .order_by(CaseInvitation.created_at.desc(), CaseInvitation.id)
    ).all()
    users = _users(db, {invitation.created_by_id for invitation, _ in rows})
    return ReceivedInvitationList(items=[
        ReceivedInvitationView(
            id=invitation.id, case=InvitedCase(id=case.id, title=case.title), role=invitation.role,
            note=invitation.note,
            invited_by=_summary(users.get(invitation.created_by_id)) if invitation.created_by_id else None,
            created_at=invitation.created_at, expires_at=invitation.expires_at,
        )
        for invitation, case in rows
    ])


def _addressed_to_me(db: Session, invitation_id: UUID, user: User) -> tuple[CaseInvitation, Case]:
    invitation = db.get(CaseInvitation, invitation_id)
    if (invitation is None or invitation.email != user.email or effective_status(invitation) != "PENDING"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=INVITATION_NOT_FOUND)
    # Lock order: case first (as every case mutation does), then the invitation.
    case = db.get(Case, invitation.case_id, with_for_update=True, populate_existing=True)
    invitation = db.get(CaseInvitation, invitation_id, with_for_update=True, populate_existing=True)
    if case is None or invitation is None or effective_status(invitation) != "PENDING":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=INVITATION_NOT_FOUND)
    return invitation, case


@me_router.post("/{invitation_id}/accept", response_model=InvitationDecision)
def accept_invitation(invitation_id: UUID, principal: CurrentPrincipal, db: DbSession) -> InvitationDecision:
    user = principal.user
    invitation, case = _addressed_to_me(db, invitation_id, user)
    permission = db.scalar(
        select(CasePermission).where(CasePermission.case_id == case.id, CasePermission.user_id == user.id))
    if permission is not None and permission.role == "OWNER":  # pragma: no cover - owners cannot be invited
        raise HTTPException(status.HTTP_409_CONFLICT, detail="You already own this case.")
    before = permission.role if permission is not None else None
    if permission is None:
        db.add(CasePermission(case_id=case.id, user_id=user.id, role=invitation.role))
    else:
        permission.role = invitation.role
    invitation.status = "ACCEPTED"
    invitation.responded_at = utcnow()
    invitation.responded_by_id = user.id
    db.flush()
    _record(db, case, user, "INVITATION_ACCEPTED",
            {"invitation_id": str(invitation.id), "user_id": str(user.id),
             "role": {"before": before, "after": invitation.role}}, bump=False)
    _sync_visibility(db, case)
    db.commit()
    return InvitationDecision(invitation_id=invitation.id, case_id=case.id, status="ACCEPTED", role=invitation.role)


@me_router.post("/{invitation_id}/decline", response_model=InvitationDecision)
def decline_invitation(invitation_id: UUID, principal: CurrentPrincipal, db: DbSession) -> InvitationDecision:
    user = principal.user
    invitation, case = _addressed_to_me(db, invitation_id, user)
    invitation.status = "DECLINED"
    invitation.responded_at = utcnow()
    invitation.responded_by_id = user.id
    _record(db, case, user, "INVITATION_DECLINED",
            {"invitation_id": str(invitation.id), "status": {"before": "PENDING", "after": "DECLINED"}}, bump=False)
    db.commit()
    return InvitationDecision(invitation_id=invitation.id, case_id=case.id, status="DECLINED", role=None)
