# Current implementation ledger (reviewed source of truth)

**Snapshot:** 2026-11-14 repository package. Update this ledger in PRs after integration, not from an unverified AI promise. Tests should be run again in each developer environment.

| Capability | Current status | Evidence/path | Next required work |
|---|---|---|---|
| NASA POWER fetch | IMPLEMENTED DEVELOPMENT BASELINE | `backend/agroblackbox/services/power.py` | validate live requests, edge cases, timezone, rates, provenance |
| Climate anomalies | IMPLEMENTED DEVELOPMENT BASELINE | `services/metrics.py`, `backend/tests/test_metrics.py` | scientific baseline validation / source comparability |
| Scientific bibliography search + DOI verification (ABB-13) | IMPLEMENTED & TESTED (metadata only) | `services/literature.py`, `backend/tests/test_literature.py`, PR #35 | team OpenAlex API key, caching/retries (ABB-27), persistence (ABB-03), reviewed claims (ABB-14); non-Crossref DOI agencies not checked |
| Rotation examples | IMPLEMENTED *ILLUSTRATIVE ONLY* | `services/rotations.py` | user inputs, crop constraints, meaningful comparison |
| Case note Markdown export | IMPLEMENTED DEVELOPMENT BASELINE | `services/report.py` | persisted cases, citations, report snapshot and download |
| React app shell, design system, EN/ES (ABB-20) | IN PROGRESS — LOCALLY VERIFIED; CI ON PR | `frontend/src/app`, `frontend/src/design`, `frontend/src/i18n`, `frontend/src/features`, 17 Vitest tests | persisted cases (ABB-06), map (ABB-21), timeline (ABB-22), graph (ABB-23) |
| Reproducible development toolchain | IMPLEMENTED & TESTED | tracked Python/npm locks, `.github/workflows/ci.yml`, `scripts/check_context.py`, CI run `43593848025` | keep locks and runtime pins synchronized when dependencies change |
| User accounts / permissions | NOT BUILT | — | auth flow, privacy, role tests |
| Persistent case storage | NOT BUILT | — | SQL models, migrations, repository layer |
| GPM / HLS | NOT BUILT | — | source adapter(s), QA, geospatial comparability |
| Evidence graph & reviewed claims | NOT BUILT | — | schema, reviewer signoff, graph UI |
| Rotations modeled vs constraints | NOT BUILT | — | scientific / agronomic rules, verified examples |
| Uncertainty Hunter | NOT BUILT | — | missing data/questions and sensitivity |
| Cross-community case review | NOT BUILT | — | permissions, invitations, audit log |
| PostgreSQL / Redis integration | NOT BUILT | `compose.yaml` only starts infra | migrations, integration tests, operations |

## Verification (update with exact command outputs after each run)

- Static project-context integrity: `uv run --no-project python scripts/check_context.py`.
- Backend: `cd backend && uv lock --check && uv run --locked --extra dev pytest -q` with dependencies.
- Frontend: `cd frontend && npm ci && npm run build` with Node.js 24 in an Internet-enabled Linux/WSL environment.
- Real NASA/OpenAlex network path: **not verified by archive creation**; each team must test and log successful retrieved dataset/source.

ABB-01 verification on 2026-11-14: context policy found 22 required files; `uv lock --check` and strict sync succeeded; backend reported `3 passed`; Node `v24.22.3` with npm `11.19.1` completed `npm ci` and the production build with zero reported vulnerabilities and no unreviewed install scripts. GitHub Actions run `43593848025` passed `api-tests`, `web-build` and `context-policy` for commit `7081f6990684cb3e058e404dae4ca63c7593260e`.

ABB-13 verification on 2026-11-14 (branch `feat/13-openalex-crossref` merged with `main` at `e6c030a`, WSL Ubuntu, uv 0.12.21): `uv lock --check` resolved 25 packages; `uv run --locked --extra dev pytest -q` reported `36 passed` (33 offline literature tests with simulated OpenAlex/Crossref); context policy found 22 required files. Live network path at 12:05 UTC without API key: anonymous OpenAlex search first returned HTTP 503 (search paused under load; service raised 502, no fabricated content); retry returned 6 works, all `VERIFIED_CROSSREF`, including `10.1038/s41467-022-32464-0`; 3 had OpenAlex/Crossref publication-year differences recorded in `metadata_discrepancies`. Results are bibliographic metadata only, not reviewed scientific claims.

ABB-20 local verification on 2026-11-14 (branch `claude/adoring-clarke-41j86y`): `npm run build` passed (tsc + vite); `npm test` → 4 files, 17 tests passed; design-token contrast check passed; `npx impeccable@4.8.0 detect src` reported no findings. With the backend running, `/api/climate?latitude=41.6&longitude=-0.9&event_year=2022&reference_start=2010&reference_end=2021` returned a live NASA POWER record (HTTP 200, payload SHA-256 starting `906dbfc82f6f841c`) rendered in the Investigation screen; `/api/literature` returned 502 because OpenAlex answered 429 Too Many Requests to the shared egress IP (backend supports `OPENALEX_API_KEY`); the UI showed the error state with no substitute data.

## Dependency-management note

Python is managed solely by `uv` in `backend/`; the tracked `backend/uv.lock` is mandatory and CI rejects drift with `uv lock --check` plus `uv sync --locked`. The tracked frontend lock is installed with `npm ci`. A fresh strict install may require registry access when caches are empty.

## First integration workstreams

1. **A:** Incident NASA records with source manifest + reliable baselines + quality flags.
2. **B:** Evidence data model, DOI verification and three constraint-aware rotations.
3. **C:** Database-backed case creation, authenticated review and frontend integration contracts.

Do not mark a 1.0 feature complete until the corresponding acceptance criteria in `docs/product/RELEASE_1_0.md` are exercised.
