"""Resilience primitives for slow/fragile external APIs (ABB-27).

Two small modules, no FastAPI routes and no new dependency:

- ``tasks``: a generic in-process task model (identifier, state, timeout, bounded
  retry/backoff, cancellation, in-flight deduplication) used around the NASA POWER
  and OpenAlex/Crossref adapters.
- ``diskcache``: a generic on-disk TTL cache (same pattern ``services.power`` already
  used for NASA POWER, extracted here so ``services.literature`` can reuse it without
  touching the already-tested POWER cache code).

See ``docs/architecture/ADRs/0005-in-process-task-registry-and-caching.md`` for why
this stays in-process (no Redis/worker) for 1.0.
"""
