# E2E journey, API contract checks and real-source smoke test (ABB-29)

Status labels follow `docs/ai/CONTEXT_MAP.md`: only what a runnable check supports is called implemented.

## What exists

| Check | What it proves | Where | Runs in CI |
|---|---|---|---|
| Main journey E2E (API level) | creation → NASA POWER → evidence (paper, claim, independent review) → hypothesis → conclusion with a complete evidence trail → 3 rotation alternatives → REVIEWER closes review → versioned, verifiable report with no private data | `backend/tests/test_e2e_main_journey.py` (`-m e2e`) | yes, own step that fails if the tests are skipped |
| Pinned failures of that journey | NASA 503 / 429 / invalid JSON → 502 with a generic message and no stored data; a month with only NASA fill values is `NOT_CLASSIFIED`, never a number; roles hold from ingestion to report; account delete leaves no case/observation rows | same file | yes |
| OpenAPI vs `frontend/src/api/types.ts` | field existence, nullability, primitive kinds and enum values for every type whose name is also an OpenAPI schema (~130 types); every `/api/...` path the frontend calls exists | `frontend/src/api/contract.test.ts` | yes (`web-build` exports the schema with `scripts/export_openapi.py`) |
| Real-source smoke test | the real NASA POWER, Crossref and OpenAlex still answer in the shape the code needs | `backend/tests/test_real_sources_smoke.py` (`-m real_network`) | **never** (manual) |
| Smoke assertions self-test | the smoke checks accept valid payloads and reject seven broken ones | `backend/tests/test_real_source_checks_offline.py` | yes |

CI also publishes the generated `openapi.json` as the `openapi-contract` artifact (FRONTEND_INTEGRATION A7, first half: the schema is published; switching the frontend to generated types is still open).

## Fixtures: synthetic versus real

- Every fixture of the journey is **SYNTHETIC** and labelled so (`backend/tests/e2e_fixtures.py`: titles, labels, notes, review texts carry the word). NASA POWER is `power_payload()` served through `httpx.MockTransport`; OpenAlex and Crossref are `evidence_fakes`. No test in the default run touches the network.
- Real services are only called by `test_real_sources_smoke.py`, with a public region-level coordinate and a pilot-paper DOI. It sends no private data.
- A synthetic result must never be shown as an observation; the journey asserts the report carries the manifest id and checksum of the (mocked) ingestion and no coordinates, notes, e-mails or parcel names.

## How to run

```bash
# journey (needs PostgreSQL; same variable as the other API tests)
cd backend && TEST_DATABASE_URL=postgresql+psycopg://agro:ci_only@localhost:5432/agroblackbox_test \
  uv run --extra dev pytest -q -m e2e -rs        # or: make e2e
# contract (exports the schema, then runs the Vitest contract test)
make contract
# real services, manual, before a release
make smoke-real        # = RUN_REAL_SOURCES=1 pytest -m real_network -s
```

Without `OPENAPI_JSON` the contract test is skipped, so a plain `npm test` stays offline.

## Contract rules

A frontend type is a *request* when its name ends in Create, Update, Patch, Request, Change, Grant, Input, Edit, Decision, Login or Register; otherwise a *response*.

- Both: a frontend field the backend does not define; a different primitive kind.
- Response: a non-null frontend field the backend may send as null; a backend enum value missing from a frontend union.
- Request: a field optional/nullable in the frontend that the backend requires or rejects; a frontend union value the backend does not accept.
- Not checked: whether a response field the schema marks optional is always present (the OpenAPI document is generated in input mode, so defaulted fields are not `required`), and whether a field is read at the right place.
- `Paper` and `Rotation` in `types.ts` describe the legacy untyped endpoints (`/api/literature`, `/api/rotations/demo`); the OpenAPI schemas of the same name are the v1 contracts, so they are listed in `NOT_COMPARED` with that reason.
- `KNOWN_DRIFT` documents accepted mismatches. The test fails on a new mismatch **and** on a stale entry. Result at ABB-29: no known drift; the checker found none on `main` at `94b0b8c`.
- Negative control: with the schema altered (extra enum value, removed field, newly required field) the test fails with one precise message per change.

## Known gaps (not detected or not covered)

- **No browser E2E.** The journey is API-level; no Playwright/Cypress click-through exists, so RELEASE_1_0 F-10 "real user without manual API calls" stays PARTIAL. A browser suite needs a new dependency and its own decision.
- The journey runs with mocked upstreams; upstream drift is caught only by the manual smoke test.
- The smoke test was **not executed against the real services by the author**: the cloud session that wrote it blocks `power.larc.nasa.gov`, `api.crossref.org` and `api.openalex.org` (CONNECT tunnel 403). Run `make smoke-real` from a networked machine and paste the output below.
- Frontend types for endpoints added later (e.g. evidence graph UI, PR #58) are compared automatically once they share a name with an OpenAPI schema.

## Real-source smoke log (fill in after each manual run)

| Date (UTC) | Who | Result | Notes |
|---|---|---|---|
| 2026-11-14 | cloud agent | **not run** — outbound network blocked, both tests fail with `NASA POWER could not be reached (network error)` and `VERIFICATION_UNAVAILABLE` (clear failure, no false pass) | needs a human run |
