"""Request dependencies: database availability and bearer-session authentication."""
from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import AuthSession, User, utcnow
from ..db.session import create_database_engine, session_factory
from ..security import token_digest

STORAGE_UNAVAILABLE = "Persistent storage is not available on this server."


@lru_cache(maxsize=4)
def _factory_for(url: str) -> sessionmaker[Session]:
    return session_factory(create_database_engine(url))


def get_session_factory() -> sessionmaker[Session]:
    """Honest 503 when persistence is not configured; other routes keep working."""
    url = os.getenv("DATABASE_URL", "")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=STORAGE_UNAVAILABLE)
    return _factory_for(url)


def get_db(factory: Annotated[sessionmaker[Session], Depends(get_session_factory)]) -> Iterator[Session]:
    """Handlers commit explicitly; anything uncommitted is rolled back on close."""
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


DbSession = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False, description="Opaque session token from POST /api/v1/auth/login")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


@dataclass(frozen=True)
class Principal:
    user: User
    session: AuthSession


def get_principal(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthorized()
    record = db.scalar(
        select(AuthSession).where(AuthSession.token_sha256 == token_digest(credentials.credentials))
    )
    if record is None or record.revoked_at is not None or record.expires_at <= utcnow():
        raise _unauthorized()
    user = db.get(User, record.user_id)
    if user is None:  # pragma: no cover - sessions cascade on user deletion
        raise _unauthorized()
    return Principal(user=user, session=record)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
