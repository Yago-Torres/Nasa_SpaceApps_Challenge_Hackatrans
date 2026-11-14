"""Account registration, login, logout and identity (ABB-05, ADR-0004)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..db.models import AuthSession, User, utcnow
from ..security import (
    LOCKOUT_DURATION,
    MAX_FAILED_LOGINS,
    SESSION_TTL,
    burn_password_check,
    hash_password,
    new_session_token,
    password_policy_error,
    token_digest,
    verify_password,
)
from .deps import CurrentPrincipal, DbSession
from .dto import LoginRequest, RegisterRequest, SessionOut, UserOut, normalize_email

router = APIRouter(prefix="/api/v1/auth", tags=["auth (ABB-05)"])

INVALID_CREDENTIALS = "Invalid email or password."
LOCKED = "Too many failed sign-in attempts. Try again later."


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, display_name=user.display_name, created_at=user.created_at)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DbSession) -> UserOut:
    """Create an account. Passwords: 12–256 characters, stored only as a salted scrypt hash."""
    password = body.password.get_secret_value()
    if (problem := password_policy_error(password)) is not None:
        raise HTTPException(422, detail=problem)
    if db.scalar(select(User.id).where(User.email == body.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
    user = User(email=body.email, display_name=body.display_name, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An account with this email already exists.") from exc
    return user_out(user)


@router.post("/login", response_model=SessionOut)
def login(body: LoginRequest, db: DbSession) -> SessionOut:
    """Exchange credentials for an opaque bearer token (12 h). 5 consecutive failures lock the
    account for 15 minutes (HTTP 429)."""
    password = body.password.get_secret_value()
    now = utcnow()
    user = db.scalar(select(User).where(User.email == normalize_email(body.email)).with_for_update())
    if user is None or user.password_hash is None:
        burn_password_check(password)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)
    if user.locked_until is not None and user.locked_until > now:
        retry_after = max(1, int((user.locked_until - now).total_seconds()))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, detail=LOCKED, headers={"Retry-After": str(retry_after)}
        )
    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.failed_login_count = 0
            user.locked_until = now + LOCKOUT_DURATION
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)
    user.failed_login_count = 0
    user.locked_until = None
    token = new_session_token()
    session = AuthSession(
        user_id=user.id, token_sha256=token_digest(token), created_at=now, expires_at=now + SESSION_TTL
    )
    db.add(session)
    db.commit()
    return SessionOut(access_token=token, expires_at=session.expires_at, user=user_out(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(principal: CurrentPrincipal, db: DbSession) -> Response:
    """Revoke the presented token immediately."""
    principal.session.revoked_at = utcnow()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(principal: CurrentPrincipal) -> UserOut:
    return user_out(principal.user)
