# Backend-specific agent instructions

Inherit repository `AGENTS.md`. Scientific integrity is the top priority.
- `backend/agroblackbox/app.py` is the currently implemented API entrypoint; `services/` contains baseline integrations.
- Use Pydantic request/response models for **new** endpoints; add tests covering invalid inputs, missing data and upstream failures.
- No unsupported causal attribution, fake probabilities, yield or water savings. Keep evidence provenance explicit.
- Review `docs/architecture/API_CONTRACTS.md` and `docs/science/SCIENTIFIC_POLICY.md` before editing.
- Planned PostgreSQL/Redis modules must not be described as already integrated.
- Significant scientific algorithm changes require explicit assumptions, regression tests, scientific review and a decision record in the Issue or ADR before integration.

- Use `uv sync --extra dev`, `uv run --extra dev pytest -q` and `uv add` for every backend dependency/task. Do not use pip or manually activate Python environments.
