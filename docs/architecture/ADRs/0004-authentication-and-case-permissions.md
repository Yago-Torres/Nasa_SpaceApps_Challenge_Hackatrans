# ADR-0004 — Authentication, case permissions and server-side location privacy

- Status: accepted for ABB-05/ABB-06 (2026-11-14). Accepted by the coordinating agent acting for A, B and C on the user's instruction while the other members were offline; security limitations listed below remain open for ABB-28 and a human security review.
- Date: 2026-11-14
- Related GitHub Issues: ABB-05 / #5 (accounts, permissions), ABB-06 / #6 (cases and parcels); context ABB-21 / #21, ABB-28 / #28
- Reviewers / coordination notes: C implements; A reviews API contracts and migration; B reviews that workflow states do not overstate scientific review. The frontend HTTP adapter (`frontend/src/cases/repository.ts`) is separate work.

## Context

ABB-03 added PostgreSQL tables for users, cases, permissions and fields but no routes. Release 1.0 (F-01, F-02) needs sign-in, private-by-default cases, invitation by role, revocable consent for precise locations, versioned editing with an audit trail, and a review workflow. The frontend wizard (ABB-21) stores cases only in the browser and explicitly relies on the server to keep exact coordinates away from guests.

## Options considered

1. **External identity provider (OAuth/OIDC).** Rejected for now: needs an external service decision, secrets and team accounts; not available for local/CI tests.
2. **JWT access tokens.** Rejected: revocation before expiry needs a server-side deny list anyway, and a stolen signing key compromises every account.
3. **Opaque server-side sessions with standard-library password hashing.** Selected: no new dependency, immediate revocation, simple deterministic tests against PostgreSQL.
4. **Password hashing with argon2/bcrypt packages.** Deferred: a new dependency would need its own approval; `hashlib.scrypt` is a memory-hard KDF available in the standard library.

## Decision

### Accounts and sessions

- Passwords: 12–256 characters (length policy only, no composition rules). Stored as `scrypt$N$r$p$salt$hash` with `N=2^14, r=8, p=1`, 64-byte output and a 16-byte random salt per hash (≈16 MiB per hash). Parameters are encoded in each hash so they can be raised later. Verification uses `hmac.compare_digest`. Unknown e-mails are verified against a dummy hash to equalise timing. The password policy error is a fixed message; validation errors never echo the password.
- Login returns an opaque token from `secrets.token_urlsafe(32)` used as `Authorization: Bearer <token>`. Only its SHA-256 hex digest is stored in `sessions` with `created_at`, `expires_at` (12 h, no sliding renewal) and `revoked_at`. Logout revokes the presented token at once.
- Brute force: per-account lockout. Five consecutive failed passwords lock the account for 15 minutes; during the lock even the correct password returns HTTP 429 with `Retry-After`. A successful login resets the counter. There is no IP rate limiting yet (ABB-28).
- Wrong password and unknown e-mail return the same 401 body. Registration with an existing e-mail returns 409 (accepted enumeration trade-off; documented below).
- Nothing logs passwords, tokens or coordinates. Database driver errors map to a generic 503 so connection strings never reach clients.

### Persistence boundary

- `DATABASE_URL` absent or not PostgreSQL → `/api/v1/auth/*` and `/api/v1/cases*` return `503 {"detail": "Persistent storage is not available on this server."}`. Other routes and the test suite without a database keep working.
- Alembic revision `b7e2d4a91c03` (down-revision `5dac25ea03d7`) adds `users.password_hash`, `users.failed_login_count`, `users.locked_until`, table `sessions`, `cases.status`, `cases.archived_at`, `fields.rounding_deg` (backfilled to 0.1 for existing `APPROXIMATE` fields) and table `case_history`. It upgrades and fully downgrades.

### Roles and access

| Action | OWNER | EDITOR | REVIEWER | VIEWER | No permission |
|---|---|---|---|---|---|
| List / read case, fields, history, member list | yes | yes | yes | yes | 404 (not in list) |
| Exact coordinates | yes | yes | only with consent or tier EXACT | only with consent or tier EXACT | — |
| Edit case attributes and fields (DRAFT/INVESTIGATING only) | yes | yes | 403 | 403 | 404 |
| DRAFT ↔ INVESTIGATING | yes | yes | 403 | 403 | 404 |
| INVESTIGATING → REVIEWED | 403 | 403 | yes | 403 | 404 |
| REVIEWED → INVESTIGATING | yes | yes | yes | 403 | 404 |
| REVIEWED → PUBLISHED, PUBLISHED → INVESTIGATING | yes | 403 | 403 | 403 | 404 |
| Grant / change / revoke roles, archive, delete | yes | 403 | 403 | 403 | 404 |
| Member e-mail addresses | yes | hidden | hidden | hidden | — |

- A user without a permission row always receives the same 404 as for a nonexistent case. Unauthenticated requests receive 401 with `WWW-Authenticate: Bearer`.
- Cases are private by default. Access is granted by the owner to an existing account by e-mail with role EDITOR, REVIEWER or VIEWER. There is one owner; the owner role cannot be granted or revoked. Permissions are read from the database on every request, so revocation is effective on the member's next request. `visibility` is maintained automatically (`PRIVATE` with only the owner, `SHARED` otherwise); `PUBLIC_ROUNDED` and any public read path are not implemented.
- Owners cannot mark their own case REVIEWED: review requires a separate REVIEWER account. `PUBLISHED` means the team considers the case final; it does not make the case public and does not relax location redaction. Neither status is a scientific validation of hypotheses.

### Location privacy (server-side)

- Owners and editors receive stored coordinates. Reviewers and viewers receive, per field: the stored point if the owner gave `precise_location_consent` (or the tier is `EXACT`, which the database only allows with consent); for `APPROXIMATE` the centre of the containing grid cell of `rounding_deg` ∈ {0.1, 0.5, 1.0} degrees (Decimal arithmetic, clamped inside ±90/±180; same formula as the frontend `roundToCell`); for `REGION_ONLY` only `region_label`; for `WITHHELD` nothing (coordinates cannot be stored). Each field view carries `location_precision` (`EXACT | APPROXIMATE | REGION_ONLY | NONE`).
- Consent is revocable by `PATCH .../fields/{id}` with `precise_location_consent: false`. A field with tier `EXACT` must change tier first (422 otherwise).
- History entries keep previous coordinate values for owners/editors; for reviewers/viewers every `latitude`/`longitude` value inside history is replaced with `"REDACTED"`.

### Versioning and audit

- Every content change (case attributes, fields, workflow status, archive) requires the `version` the client read; a mismatch returns 409 without changes. The case row is locked (`SELECT … FOR UPDATE`) while the version is checked. Successful changes increment `version` and append a `case_history` row with actor, timestamp, resulting version and `{"before", "after"}` values. Permission changes are also recorded (without bumping the version, so sharing does not conflict with concurrent editors).
- Deleting a case (owner, current version required) permanently erases the case, fields, permissions and history; this is the privacy-erasure path pending the retention policy of ABB-28. Archiving is reversible, hides the case from the default list and makes it read-only.

## Tradeoffs and consequences

- No external identity provider, e-mail verification, password reset, MFA or invitation acceptance flow; access is granted directly to an existing account. These remain open for ABB-28 / later Issues.
- Registration (409) and lockout (429) reveal that an account exists; owners granting access learn whether an e-mail is registered. Accepted for the pilot; revisit with e-mail-based invitations.
- Lockout per account allows an attacker to lock a victim out for 15 minutes; there is no IP-based throttling because Redis is not wired.
- Bearer tokens in browser storage are exposed to XSS; the frontend must keep them in memory or session storage and must not log them. HTTPS is mandatory in deployment.
- Expired and revoked session rows are not purged automatically yet.
- Error bodies keep FastAPI's `{"detail": ...}` shape because the frontend client already displays `detail`; adopting the shared `ApiError` model is a separate contract change.

## Rollout / rollback

Deploy with `alembic upgrade head`. Existing users (e.g. the synthetic seed) have no password and cannot log in until a password is set by a future flow. Rollback: `alembic downgrade 5dac25ea03d7` drops sessions, history, workflow status and credentials (data loss for those columns), and the routes must be removed from `app.py` (`include_api_v1`).
