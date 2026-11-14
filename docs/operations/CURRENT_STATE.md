# Current implementation ledger (reviewed source of truth)

**Snapshot:** 2026-11-14 repository package. Update this ledger in PRs after integration, not from an unverified AI promise. Tests should be run again in each developer environment.

| Capability | Current status | Evidence/path | Next required work |
|---|---|---|---|
| NASA POWER fetch | IMPLEMENTED DEVELOPMENT BASELINE | `backend/agroblackbox/services/power.py` | validate live requests, edge cases, timezone, rates, provenance |
| Climate anomalies | IMPLEMENTED DEVELOPMENT BASELINE | `services/metrics.py`, `backend/tests/test_metrics.py` | scientific baseline validation / source comparability |
| Scientific bibliography search | IMPLEMENTED DEVELOPMENT BASELINE | `services/literature.py` | DOI verification, review workflow, Crossref, evidence record |
| Rotation examples | IMPLEMENTED *ILLUSTRATIVE ONLY* | `services/rotations.py` | user inputs, crop constraints, meaningful comparison |
| Case note Markdown export | IMPLEMENTED DEVELOPMENT BASELINE | `services/report.py` | persisted cases, citations, report snapshot and download |
| React app baseline | IMPLEMENTED DEVELOPMENT BASELINE | `frontend/src/main.tsx` | full case/graph/map/collaboration UX, accessibility, tests |
| Reproducible development toolchain | IN PROGRESS — LOCALLY VERIFIED | tracked Python/npm locks, `.github/workflows/ci.yml`, `scripts/check_context.py` | run changed revision in remote CI after the team publishes it |
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

ABB-01 local verification on 2026-11-14: context policy found 22 required files; `uv lock --check` and strict sync succeeded; backend reported `3 passed`; Node `v24.22.3` with npm `11.19.1` completed `npm ci` and the production build with zero reported vulnerabilities and no unreviewed install scripts. Remote CI has not run against these uncommitted changes.

## Dependency-management note

Python is managed solely by `uv` in `backend/`; the tracked `backend/uv.lock` is mandatory and CI rejects drift with `uv lock --check` plus `uv sync --locked`. The tracked frontend lock is installed with `npm ci`. A fresh strict install may require registry access when caches are empty.

## First integration workstreams

1. **A:** Incident NASA records with source manifest + reliable baselines + quality flags.
2. **B:** Evidence data model, DOI verification and three constraint-aware rotations.
3. **C:** Database-backed case creation, authenticated review and frontend integration contracts.

Do not mark a 1.0 feature complete until the corresponding acceptance criteria in `docs/product/RELEASE_1_0.md` are exercised.
