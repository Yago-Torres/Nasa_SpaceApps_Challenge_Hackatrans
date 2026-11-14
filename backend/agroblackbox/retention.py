"""Data retention: purge of stale authentication sessions (ABB-28).

A session row that is expired or revoked proves nothing: its digest cannot authenticate anymore,
so keeping it indefinitely serves no security purpose beyond a short forensic window. This module
purges rows that passed that window. It is not wired to a scheduler (no job runner is deployed
yet, see ``docs/operations/CURRENT_STATE.md`` Redis row); an operator runs it manually or a future
scheduled job calls ``purge_stale_sessions`` directly. It never touches a session that is still
active, unexpired and unrevoked.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from .db.models import AuthSession, utcnow

# Forensic window: how long an expired/revoked session row is kept before it is purged.
RETENTION_WINDOW = timedelta(days=30)


def purge_stale_sessions(
    db: Session, *, now: datetime | None = None, window: timedelta = RETENTION_WINDOW,
) -> int:
    """Delete session rows that expired, or were revoked, more than ``window`` ago.

    Returns the number of rows deleted. Commits the deletion (callers that already manage a
    transaction may pass a session whose commit is a no-op for them, e.g. one bound to
    ``expire_on_commit=False``)."""
    cutoff = (now or utcnow()) - window
    result = db.execute(
        delete(AuthSession).where(or_(AuthSession.expires_at <= cutoff, AuthSession.revoked_at <= cutoff))
    )
    db.commit()
    return result.rowcount or 0


def _main() -> None:  # pragma: no cover - thin CLI wrapper; exercised manually by operators
    import argparse

    from .db.session import create_database_engine, database_url, session_factory, session_scope

    parser = argparse.ArgumentParser(description="Purge expired/revoked session rows (ABB-28 retention).")
    parser.add_argument(
        "--days", type=int, default=RETENTION_WINDOW.days,
        help="Keep a session row for this many days after it expired or was revoked (default: 30).",
    )
    args = parser.parse_args()
    engine = create_database_engine(database_url())
    with session_scope(session_factory(engine)) as session:
        deleted = purge_stale_sessions(session, window=timedelta(days=args.days))
    print(f"Purged {deleted} stale session row(s).")


if __name__ == "__main__":  # pragma: no cover
    _main()
