# AGENTS.md — AGRO BLACK BOX (cross-model rules)

## Mission and source of truth

Deliver the **complete AGRO BLACK BOX 1.0 product** specified in `docs/product/RELEASE_1_0.md`. This is the target, not a claim of implementation. Verify current code and `docs/operations/CURRENT_STATE.md`. The canonical product context is this repository, its approved Issues, and reviewed PRs/ADRs — never a model's conversation memory.

## Before touching code

1. Read `docs/ai/CONTEXT_MAP.md`, relevant product/science/architecture docs and applicable nested `AGENTS.md`.
2. Inspect the relevant source, tests, and existing API contract.
3. Link the task to a human-approved Issue (`team-approved` with approval comments), or a documented authorized bug fix.
4. Identify affected domains, dependencies, tests, API changes and required reviewers.
5. Distinguish implemented functionality from approved-but-not-built and proposed scope.

## Coding and scientific rules

- **Python 3.12 + uv only** for backend dependency management/execution. Work inside `backend/` with `uv sync --extra dev`, `uv run ...`, `uv add ...`, and `uv lock`. `uv` manages the Python environment; **do not manually create or activate it** and do not use pip/Poetry.
- Frontend: TypeScript/React/Vite with Node.js 24 + npm. PostgreSQL is the 1.0 persistence target.
- Backend owns scientific computations and API response models. Frontend must never invent scientific results or silently substitute sample data for unavailable live NASA observations.
- Every scientific observation, source, hypothesis or modeled result must retain provenance, units, space/time resolution, limitations and uncertainty as appropriate.
- Input validation, secure defaults, failure states and deterministic tests required. Protect private farm coordinates and user data.
- New dependencies, endpoints, schema changes, external services and major architecture changes must be covered by approved Issue / ADR as applicable.
- Prefer small PRs and no direct pushes to protected `main`.

## Commands (run from repo root unless otherwise stated)

```bash
cd backend && uv sync --extra dev
cd backend && uv run --extra dev pytest -q
uv run --no-project python scripts/check_context.py
cd frontend && npm run build
```

To run the backend: `cd backend && uv run uvicorn agroblackbox.app:app --reload --port 8000`.

## Omarchy, WSL and system access

The README contains the **Omarchy agent setup and operation guide**. Never run privileged commands (`sudo`, `pacman`, `yay`, global `mise` changes, Docker privilege changes) or authenticate external accounts without explicit human permission. WSL users work under the Linux filesystem, not `/mnt/c`.

## Completion checklist

- Run actual tests/build or describe exact blockers.
- Update `docs/operations/CURRENT_STATE.md` only after evidence-backed integration, `docs/architecture/API_CONTRACTS.md`/ADRs if relevant, and `docs/CHANGELOG.md` for user-visible changes.
- Create PR linked to approved Issue with exact verification outputs, data/science/security impacts and handoff for another model.
- Human review and required CI checks before claiming completion.

Details: `docs/governance/FEATURE_POLICY.md`, `docs/governance/TEAM_WORKFLOW.md`, `docs/science/SCIENTIFIC_POLICY.md`.
