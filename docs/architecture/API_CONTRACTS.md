# API contracts — implemented vs target

**Live source of truth for currently implemented endpoints:** FastAPI OpenAPI at `http://localhost:8000/openapi.json` after backend startup. The existing baseline uses `/api/*`, not yet `/api/v1/*`.

## Implemented (as of initial archive)

- `GET /api/health` — API status and version.
- `GET /api/climate?latitude=&longitude=&event_year=&reference_start=&reference_end=` — NASA POWER daily-based monthly anomalies, SHA-256 and caveats. Live upstream request required; errors may return 502. Small reference windows should not be called climatological normals.
- `GET /api/literature?query=` — OpenAlex bibliographic results with per-DOI Crossref verification (ABB-13), not full-text validated claims. Typed `LiteratureSearchResult` (see OpenAPI). Baseline item fields `title, year, doi (https://doi.org/ URL), openalex_id, kind, source, caveat` are kept; additive fields: `source_kind=LITERATURE_METADATA`, `evidence_status=BIBLIOGRAPHIC_MATCH_ONLY`, `doi_id`, `doi_status` (`VERIFIED_CROSSREF | METADATA_MISMATCH | NOT_FOUND_IN_CROSSREF | VERIFICATION_UNAVAILABLE | MALFORMED_DOI | NO_DOI`), `authors`, `venue`, `publication_type`, `licenses` (as reported by source), `landing_page_url`, `is_open_access`, `metadata_discrepancies`, `retrievals` (source, endpoint without credentials, `retrieved_at`, HTTP status) and `processing_version`; top level adds `query`, `retrieved_at`, `total_openalex_matches`, `duplicates_removed`, `limitations`. OpenAlex failure/rate limit returns 502 with a generic message (no URL/credentials); Crossref failure degrades to `VERIFICATION_UNAVAILABLE`. A DOI is never inferred.
- `GET /api/rotations/demo` — three illustrative rotations, not water/yield forecasts.
- `POST /api/report` — Markdown case note from submitted payload; preliminary and not independently validated.

Frontend consumers, screens and the interface fields the UI requests from A and B: `docs/architecture/FRONTEND_INTEGRATION.md`.

## Proposed release 1.0 API (NOT IMPLEMENTED)

Formalize versioned `/api/v1` resources and schema generation through approved contracts:

- `/api/v1/cases` — typed case CRUD and permission tiers.
- `/api/v1/cases/{case_id}/observations` — evidence source manifest, jobs, quality flags.
- `/api/v1/cases/{case_id}/timeline` — observed, local and hypothetical event layers.
- `/api/v1/evidence/search` and `/api/v1/evidence/findings` — DOI discovery and human-verified findings.
- `/api/v1/cases/{case_id}/hypotheses` — supporting, contradictory and missing evidence.
- `/api/v1/cases/{case_id}/rotations/compare` — three+ feasible options with explicit scenarios.
- `/api/v1/cases/{case_id}/reviews` — reviewer comments and decisions with access control.
- `/api/v1/cases/{case_id}/reports` — versioned human-readable case reports.

Do not implement paths/types or migrate existing consumers without a documented feature spec and coordination with affected consumers. Breaking changes require a compatibility plan, contract tests and updated docs.

## Shared response requirements

Use strongly typed fields for `provenance`, `units`, `spatial_resolution`, `temporal_resolution`, `source_kind`, `limitations`, `created_at`, `processing_version` where applicable. Observations are data; hypotheses must never present a numeric causal score without a validated method.
