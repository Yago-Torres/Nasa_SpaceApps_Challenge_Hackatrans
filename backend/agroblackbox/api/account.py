"""Self-service account data export and deletion (ABB-28).

Data minimisation / retention decision (see ADR-0005): deleting the account does not delete the
``users`` row outright. Several append-only, shared scientific/audit records reference the
acting user with an ``ON DELETE RESTRICT`` foreign key by design -- ``evidence_claims.created_by``,
``evidence_claim_events.actor_id``, ``claim_disagreement_reviews.reviewer_id``,
``uncertainty_answers.answered_by``/``reviewed_by``, ``evidence_conclusions.reviewed_by``,
``evidence_graph_edges.reviewed_by``, ``reviews.reviewer_id`` -- precisely so that a reviewer's
or contributor's identity on a *shared* case's evidence trail is never silently lost (see the
comment on ``EvidenceClaimEvent.actor_id`` in ``db.models``). A hard delete of the user row would
either violate those constraints (if the user ever reviewed or authored anything on a case they
do not own) or require cascading the deletion into other users' cases, which is not this user's
data to erase. Deleting the account instead:

1. permanently erases every case this account **owns** -- fields, permissions, history,
   observations, anomalies, source manifests, hypotheses, claims and their review history,
   disagreement reviews, uncertainty answers and question events, evidence graph conclusions and
   edges, rotations, reviews and reports -- via the same ``ON DELETE CASCADE`` on ``case_id`` that
   backs ``DELETE /api/v1/cases/{id}``;
2. revokes this account's membership (``CasePermission``) on every case owned by someone else;
3. revokes every session;
4. scrubs the identifying profile fields (``email``, ``display_name``) and disables login
   (``password_hash = NULL``), while keeping the row so other users' audit trails stay intact.

This is documented to the user in the response body (``AccountDeletionReceipt``) rather than
claimed as a bare "deleted", consistent with the project's scientific/privacy honesty policy.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select, update

from ..db.models import AuthSession, Case, CasePermission, User, utcnow
from ..security import LOCKOUT_DURATION, MAX_FAILED_LOGINS, verify_password
from .cases import _case_view
from .deps import CurrentPrincipal, DbSession
from .dto import AccountDeleteRequest, AccountDeletionReceipt, AccountExport, SessionSummary, UserOut

router = APIRouter(prefix="/api/v1/account", tags=["account (ABB-28)"])

INVALID_PASSWORD = "Incorrect password."
LOCKED = "Too many failed confirmation attempts. Try again later."


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, display_name=user.display_name, created_at=user.created_at)


@router.get("/export", response_model=AccountExport)
def export_account(principal: CurrentPrincipal, db: DbSession) -> AccountExport:
    """Export the data this account can see about itself: profile, every case it is a member of
    (coordinates already redacted per its role on each case, exactly as ``GET /api/v1/cases``
    would show them) and this account's own session metadata (never a token or its digest)."""
    user = principal.user
    query = (
        select(Case, CasePermission.role)
        .join(CasePermission, CasePermission.case_id == Case.id)
        .where(CasePermission.user_id == user.id)
        .order_by(Case.updated_at.desc(), Case.id)
    )
    cases = [_case_view(db, case, role) for case, role in db.execute(query).all()]
    sessions = db.scalars(
        select(AuthSession).where(AuthSession.user_id == user.id).order_by(AuthSession.created_at)
    ).all()
    session_views = [
        SessionSummary(
            id=session.id, created_at=session.created_at, expires_at=session.expires_at,
            revoked=session.revoked_at is not None, current=session.id == principal.session.id,
        )
        for session in sessions
    ]
    return AccountExport(profile=_user_out(user), cases=cases, sessions=session_views, exported_at=utcnow())


@router.post("/delete", response_model=AccountDeletionReceipt)
def delete_account(body: AccountDeleteRequest, principal: CurrentPrincipal, db: DbSession) -> AccountDeletionReceipt:
    """Irreversible. Requires the current password even though the caller already holds a valid
    session, as a confirmation step before an action that cannot be undone. Wrong passwords use
    the same per-account lockout as ``/auth/login`` (5 failures -> 15 minute 429) so a stolen
    bearer token cannot be used to brute-force the confirmation."""
    user = principal.user
    now = utcnow()
    if user.locked_until is not None and user.locked_until > now:
        retry_after = max(1, int((user.locked_until - now).total_seconds()))
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail=LOCKED,
                             headers={"Retry-After": str(retry_after)})
    if not verify_password(body.password.get_secret_value(), user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.failed_login_count = 0
            user.locked_until = now + LOCKOUT_DURATION
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVALID_PASSWORD)

    cases_deleted = db.scalar(select(func.count()).select_from(Case).where(Case.owner_id == user.id)) or 0
    db.execute(delete(Case).where(Case.owner_id == user.id))
    # Cases this account owned cascade-deleted their CasePermission rows already (ON DELETE
    # CASCADE on case_id); anything left here is membership on someone else's case.
    memberships_revoked = db.scalar(
        select(func.count()).select_from(CasePermission).where(CasePermission.user_id == user.id)
    ) or 0
    db.execute(delete(CasePermission).where(CasePermission.user_id == user.id))

    sessions_revoked = db.scalar(
        select(func.count()).select_from(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
    ) or 0
    db.execute(
        update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )

    user.email = f"deleted-{user.id}@deleted.invalid"
    user.display_name = "Deleted account"
    user.password_hash = None
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()

    return AccountDeletionReceipt(
        cases_deleted=cases_deleted, memberships_revoked=memberships_revoked,
        sessions_revoked=sessions_revoked, deleted_at=now,
    )
