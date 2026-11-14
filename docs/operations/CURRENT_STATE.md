# Current implementation ledger (reviewed source of truth)

**Snapshot:** 2026-11-14 repository package. Update this ledger in PRs after integration, not from an unverified AI promise. Tests should be run again in each developer environment.

| Capability | Current status | Evidence/path | Next required work |
|---|---|---|---|
| NASA POWER fetch | IMPLEMENTED DEVELOPMENT BASELINE | `backend/agroblackbox/services/power.py` | validate live requests, edge cases, timezone, rates, provenance |
| Climate anomalies | IMPLEMENTED DEVELOPMENT BASELINE | `services/metrics.py`, `backend/tests/test_metrics.py` | scientific baseline validation / source comparability |
| Scientific bibliography search + DOI verification (ABB-13) | IMPLEMENTED & TESTED (metadata only) | `services/literature.py`, `backend/tests/test_literature.py`, PR #35 | team OpenAlex API key, caching/retries (ABB-27), persistence (ABB-03), reviewed claims (ABB-14); non-Crossref DOI agencies not checked |
| Rotation examples | IMPLEMENTED *ILLUSTRATIVE ONLY* | `services/rotations.py` | user inputs, crop constraints, meaningful comparison |
| Case note Markdown export | IMPLEMENTED DEVELOPMENT BASELINE | `services/report.py` | persisted cases, citations, report snapshot and download |
| React app shell, design system, EN/ES (ABB-20) | IMPLEMENTED & TESTED | `frontend/src/app`, `frontend/src/design`, `frontend/src/i18n`, `frontend/src/features`, 17 Vitest tests, PR #36 | persisted cases (ABB-06), map (ABB-21), timeline (ABB-22), graph (ABB-23) |
| Reproducible development toolchain | IMPLEMENTED & TESTED | tracked Python/npm locks, `.github/workflows/ci.yml`, `scripts/check_context.py`, CI run `43593848025` | keep locks and runtime pins synchronized when dependencies change |
| Shared API 1.0 data contracts | IN PROGRESS — LOCALLY VERIFIED | `backend/agroblackbox/schemas.py`, `backend/tests/test_contracts.py`, ADR-0002 | B/C semantic review, generated frontend types and route-by-route adoption remain |
| User accounts / permissions | NOT BUILT | — | auth flow, privacy, role tests |
| Incident wizard + location privacy UI (ABB-21) | IN PROGRESS — UI TESTED, DEV STORAGE ONLY | `frontend/src/cases`, `frontend/src/features/cases`, 12 Vitest tests (privacy redaction, validation, create → list → edit flow) | real `/api/v1/cases` + auth (ABB-05/06), server-side guest redaction, basemap after tile-provider decision |
| PostgreSQL case/artifact persistence (ABB-03) | IMPLEMENTED INTERNAL LAYER — API INTEGRATION PENDING | `backend/agroblackbox/db`, `backend/migrations`, `backend/tests/test_persistence.py`, ADR-0003 | authenticated API adoption (ABB-05/06), production backup/restore operations |
| GPM / HLS | NOT BUILT | — | source adapter(s), QA, geospatial comparability |
| Evidence graph & reviewed claims | NOT BUILT | — | schema, reviewer signoff, graph UI |
| Rotations modeled vs constraints | NOT BUILT | — | scientific / agronomic rules, verified examples |
| Uncertainty Hunter | NOT BUILT | — | missing data/questions and sensitivity |
| Cross-community case review | NOT BUILT | — | permissions, invitations, audit log |
| PostgreSQL / Redis integration | POSTGRESQL IMPLEMENTED; REDIS NOT WIRED | SQLAlchemy/Alembic + PostgreSQL CI; `compose.yaml` also starts unused Redis | Redis job integration, deployment and recovery runbook |

## Verification (update with exact command outputs after each run)

- Static project-context integrity: `uv run --no-project python scripts/check_context.py`.
- Backend: `cd backend && uv lock --check && uv run --locked --extra dev pytest -q` with dependencies.
- Frontend: `cd frontend && npm ci && npm run build` with Node.js 24 in an Internet-enabled Linux/WSL environment.
- Real NASA/OpenAlex network path: **not verified by archive creation**; each team must test and log successful retrieved dataset/source.

ABB-01 verification on 2026-11-14: context policy found 22 required files; `uv lock --check` and strict sync succeeded; backend reported `3 passed`; Node `v24.22.3` with npm `11.19.1` completed `npm ci` and the production build with zero reported vulnerabilities and no unreviewed install scripts. GitHub Actions run `43593848025` passed `api-tests`, `web-build` and `context-policy` for commit `7081f6990684cb3e058e404dae4ca63c7593260e`.

ABB-13 verification on 2026-11-14 (branch `feat/13-openalex-crossref` merged with `main` at `e6c030a`, WSL Ubuntu, uv 0.12.21): `uv lock --check` resolved 25 packages; `uv run --locked --extra dev pytest -q` reported `36 passed` (33 offline literature tests with simulated OpenAlex/Crossref); context policy found 22 required files. Live network path at 12:05 UTC without API key: anonymous OpenAlex search first returned HTTP 503 (search paused under load; service raised 502, no fabricated content); retry returned 6 works, all `VERIFIED_CROSSREF`, including `10.1038/s41467-022-32464-0`; 3 had OpenAlex/Crossref publication-year differences recorded in `metadata_discrepancies`. Results are bibliographic metadata only, not reviewed scientific claims.

ABB-20 local verification on 2026-11-14 (branch `claude/adoring-clarke-41j86y`): `npm run build` passed (tsc + vite); `npm test` → 4 files, 17 tests passed; design-token contrast check passed; `npx impeccable@4.8.0 detect src` reported no findings. With the backend running, `/api/climate?latitude=41.6&longitude=-0.9&event_year=2022&reference_start=2010&reference_end=2021` returned a live NASA POWER record (HTTP 200, payload SHA-256 starting `906dbfc82f6f841c`) rendered in the Investigation screen; `/api/literature` returned 502 because OpenAlex answered 429 Too Many Requests to the shared egress IP (backend supports `OPENALEX_API_KEY`); the UI showed the error state with no substitute data.

ABB-02 local verification on 2026-11-14 after integrating ABB-13 and rebasing over ABB-20: OpenAPI serialized successfully with 28 component schemas; contract JSON/privacy/null validation, ABB-13 `Paper` semantic compatibility and existing API 422 paths passed; the complete backend reported `42 passed`. Context policy found 25 required files; the frontend production build and all 17 Vitest tests passed with Node 24. ABB-13 endpoint tests were migrated from the incompatible blocking `TestClient` path to async `httpx.ASGITransport` without changing their assertions. The shared models are published in OpenAPI locally, but `/api/v1` routes, persistence adoption and generated frontend types are not implemented by ABB-02.

ABB-03 local verification on 2026-11-14 against PostgreSQL 17: the initial Alembic migration upgraded an empty database, downgraded to base and upgraded again; `alembic check` reported no schema drift. The complete backend reported `48 passed`, including persistence across sessions, referential/privacy constraints, observation provenance, optimistic concurrent updates and the explicitly synthetic seed. Context policy found 25 required files; the frontend production build passed and all 29 Vitest tests passed with Node 24. Authenticated persistence routes, Redis jobs and production backup/restore remain separate work.

## Dependency-management note

Python is managed solely by `uv` in `backend/`; the tracked `backend/uv.lock` is mandatory and CI rejects drift with `uv lock --check` plus `uv sync --locked`. The tracked frontend lock is installed with `npm ci`. A fresh strict install may require registry access when caches are empty.

## First integration workstreams

1. **A:** Incident NASA records with source manifest + reliable baselines + quality flags.
2. **B:** Evidence data model, DOI verification and three constraint-aware rotations.
3. **C:** Database-backed case creation, authenticated review and frontend integration contracts.

Do not mark a 1.0 feature complete until the corresponding acceptance criteria in `docs/product/RELEASE_1_0.md` are exercised.
