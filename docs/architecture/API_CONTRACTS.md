# API contracts — implemented vs target

**Live source of truth for currently implemented endpoints:** FastAPI OpenAPI at `http://localhost:8000/openapi.json` after backend startup. The existing baseline uses `/api/*`, not yet `/api/v1/*`.

## Implemented (as of initial archive)

- `GET /api/health` — API status and version.
- `GET /api/climate?latitude=&longitude=&event_year=&reference_start=&reference_end=` — NASA POWER daily-based monthly anomalies, SHA-256 and caveats. Live upstream request required; errors may return 502. Small reference windows should not be called climatological normals.
- `GET /api/literature?query=` — OpenAlex bibliographic results with per-DOI Crossref verification (ABB-13), not full-text validated claims. Typed `LiteratureSearchResult` (see OpenAPI). Baseline item fields `title, year, doi (https://doi.org/ URL), openalex_id, kind, source, caveat` are kept; additive fields: `source_kind=LITERATURE_METADATA`, `evidence_status=BIBLIOGRAPHIC_MATCH_ONLY`, `doi_id`, `doi_status` (`VERIFIED_CROSSREF | METADATA_MISMATCH | NOT_FOUND_IN_CROSSREF | VERIFICATION_UNAVAILABLE | MALFORMED_DOI | NO_DOI`), `authors`, `venue`, `publication_type`, `licenses` (as reported by source), `landing_page_url`, `is_open_access`, `metadata_discrepancies`, `retrievals` (source, endpoint without credentials, `retrieved_at`, HTTP status) and `processing_version`; top level adds `query`, `retrieved_at`, `total_openalex_matches`, `duplicates_removed`, `limitations`. OpenAlex failure/rate limit returns 502 with a generic message (no URL/credentials); Crossref failure degrades to `VERIFICATION_UNAVAILABLE`. A DOI is never inferred.
- `GET /api/rotations/demo` — three illustrative rotations, not water/yield forecasts.
- `POST /api/report` — Markdown case note from submitted payload; preliminary and not independently validated.

Frontend consumers, screens and the interface fields the UI requests from A and B: `docs/architecture/FRONTEND_INTEGRATION.md`.

## Shared 1.0 schemas (IMPLEMENTED CONTRACT; ROUTE INTEGRATION PENDING)

ABB-02 publishes the following Pydantic models in OpenAPI `components.schemas`: `Case`, `Field`, `SourceManifest`, `Observation`, `Anomaly`, `Hypothesis`, `Paper`, `EvidenceClaim`, `Rotation`, `Review`, `Report` and `ApiError`. The OpenAPI info object carries `x-agro-contract-version: 1.0`.

- Unknown fields are rejected by the shared models.
- Nullable values are explicit; a missing observation is `null` with quality flags and limitations.
- `SourceManifest` retains provider, dataset, query parameters, retrieval time, checksum, processing version, license, resolution and limitations.
- Exact/withheld coordinate rules are validated by `Field`.
- Literature metadata cannot silently become a reviewed finding.
- The shared `Paper` preserves ABB-13 bibliographic semantics (`year`, DOI status, structured authors, licences and retrieval provenance); persistence may later attach a `SourceManifest` without discarding those fields.
- Hypotheses never include an unsupported causal score.
- Rotation impact remains null until a separately validated model supplies it.

The current React baseline still declares local `Climate`, `Paper` and `Rotation` types matching the existing `/api/*` responses. C should replace those types with a generated client only when the corresponding routes adopt the shared models.

See `docs/architecture/ADRs/0002-versioned-shared-contracts.md`.

## PostgreSQL persistence (IMPLEMENTED INTERNAL LAYER; API ROUTES PENDING)

ABB-03 persists the shared domains in PostgreSQL through SQLAlchemy models and Alembic migrations. The internal `CaseRepository` creates private cases with an owner permission and uses an explicit version for concurrent updates. This does not expose new routes or bypass the future authentication/authorization work. See ADR-0003.

## Proposed release 1.0 routes (NOT IMPLEMENTED)

Formalize versioned `/api/v1` resources through their owning roadmap Issues:

- `/api/v1/cases` — typed case CRUD and permission tiers.
- `/api/v1/cases/{case_id}/observations` — evidence source manifest, jobs, quality flags.
- `/api/v1/cases/{case_id}/timeline` — observed, local and hypothetical event layers.
- `/api/v1/evidence/search` and `/api/v1/evidence/findings` — DOI discovery and human-verified findings.
- `/api/v1/cases/{case_id}/hypotheses` — supporting, contradictory and missing evidence.
- `/api/v1/cases/{case_id}/rotations/compare` — three+ feasible options with explicit scenarios.
- `/api/v1/cases/{case_id}/reviews` — reviewer comments and decisions with access control.
- `/api/v1/cases/{case_id}/reports` — versioned human-readable case reports.

Do not migrate existing consumers without coordination with affected domains. Breaking changes require a compatibility plan, contract tests, updated docs and a new contract version when compatibility cannot be preserved.

## Shared response requirements

Use strongly typed fields for `provenance`, `units`, `spatial_resolution`, `temporal_resolution`, `source_kind`, `limitations`, `created_at`, `processing_version` where applicable. Observations are data; hypotheses must never present a numeric causal score without a validated method.
