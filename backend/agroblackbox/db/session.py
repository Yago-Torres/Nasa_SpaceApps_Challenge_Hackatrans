from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is required for persistent storage")
    if not value.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("ABB-03 persistence requires PostgreSQL")
    return value


def create_database_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    return create_engine(url or database_url(), echo=echo, pool_pre_ping=True)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
