# ADR-0003 — PostgreSQL persistence boundary

- Status: accepted for ABB-03 implementation
- Date: 2026-11-14
- Related Issue: ABB-03 / #3

## Decision

Use SQLAlchemy 2.x with psycopg 3 and Alembic migrations. PostgreSQL is the only supported persistent database; tests use a disposable PostgreSQL database rather than SQLite so JSONB, constraints, transactions and foreign keys are exercised as deployed.

The database layer lives under `agroblackbox/db`. ORM entities store cases, fields, permissions and scientific artifacts, while repositories own transactional access and optimistic case-version updates. API routes remain separate until their owning Issues add authentication and authorization.

Exact coordinates require explicit consent and cannot be stored for a `WITHHELD` field. Scientific artifacts retain source classification, resolution, quality flags and limitations. Test records are conspicuously synthetic; no seed is presented as NASA data.

## Consequences

- `DATABASE_URL` is required when persistence is used; credentials are supplied by the environment and never logged.
- Initial migrations upgrade an empty database and fully downgrade. CI runs the PostgreSQL integration suite.
- Schema evolution requires a new Alembic revision. Authentication, public CRUD routes and backup operations remain separate roadmap work.
