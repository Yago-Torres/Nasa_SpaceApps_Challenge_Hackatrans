# API contracts — implemented vs target

**Live source of truth for currently implemented endpoints:** FastAPI OpenAPI at `http://localhost:8000/openapi.json` after backend startup. The existing baseline uses `/api/*`, not yet `/api/v1/*`.

## Implemented (as of initial archive)

- `GET /api/health` — API status and version.
- `GET /api/climate?latitude=&longitude=&event_year=&reference_start=&reference_end=` (ABB-07/08) — typed `ClimateResponse` (see OpenAPI). Baseline keys `kind, dataset, source_url, data_sha256, request_params, event_year, reference_start, reference_end, monthly[], disclaimer` are kept. Additive: `source_kind=OBSERVED`, `retrieved_at` (UTC, original retrieval time when cached), `spatial_resolution`/`temporal_resolution` (`Resolution`), `provenance` (`SourceManifest` 1.0), `upstream` (POWER header: API version, sources, fill value, time standard, messages), `cache` (`served_from_cache`, `cache_age_seconds`, `ttl_seconds`, `upstream_attempts`), `variables[]`, `method` (formula, reference label, `reference_is_climatological_normal=false`, completeness rule), `quality` (status, counts, warnings), `limitations[]`, and `monthly[].quality.{precipitation,max_temperature}` (status complete/partial/missing, reason, day counts, flags, reference coverage with sample count/excluded years/SD/min/max). Partial months and fill values give `null`, never values. Upstream failure, timeout, rate limit or invalid payload returns 502 with a generic message (no URL/query); invalid inputs return 422 without calling POWER. Small reference windows are not climatological normals. See `docs/science/CLIMATE_ANOMALIES.md`.
- `GET /api/literature?query=` — OpenAlex bibliographic results with per-DOI Crossref verification (ABB-13), not full-text validated claims. Typed `LiteratureSearchResult` (see OpenAPI). Baseline item fields `title, year, doi (https://doi.org/ URL), openalex_id, kind, source, caveat` are kept; additive fields: `source_kind=LITERATURE_METADATA`, `evidence_status=BIBLIOGRAPHIC_MATCH_ONLY`, `doi_id`, `doi_status` (`VERIFIED_CROSSREF | METADATA_MISMATCH | NOT_FOUND_IN_CROSSREF | VERIFICATION_UNAVAILABLE | MALFORMED_DOI | NO_DOI`), `authors`, `venue`, `publication_type`, `licenses` (as reported by source), `landing_page_url`, `is_open_access`, `metadata_discrepancies`, `retrievals` (source, endpoint without credentials, `retrieved_at`, HTTP status) and `processing_version`; top level adds `query`, `retrieved_at`, `total_openalex_matches`, `duplicates_removed`, `limitations`. OpenAlex failure/rate limit returns 502 with a generic message (no URL/credentials); Crossref failure degrades to `VERIFICATION_UNAVAILABLE`. A DOI is never inferred.
- `GET /api/rotations/demo` — three illustrative rotations, not water/yield forecasts.
- `GET /api/v1/crop-catalog` (ABB-11) — `CropCatalog`: crop identity entries (code, EN/ES names, scientific name, family, group, derived `is_legume`), all `review_status=PENDING`, `agronomic_parameters=null`.
- `POST /api/v1/farm-profiles/assess` (ABB-11) — body `FarmProfile` (soil observations with `origin` `LOCAL_MEASUREMENT | FARMER_ESTIMATE | REGIONAL_ESTIMATE | UNKNOWN`, crop history, farmer `local_calendar`, constraints, ordinal priorities); returns `FarmProfileAssessment` (`source_kind=FARMER_REPORTED`, per-section `PROVIDED | PARTIAL | MISSING`, `issues[]` with `severity` `ERROR | WARNING | MISSING_DATA`, `code`, `path`, `message`, `consequence`, and `rotation_input_status`). Stateless: nothing is stored. Structural errors return 422; agronomic inconsistencies return 200 with `ERROR` issues. See `docs/science/FARM_PROFILE.md`.
- `POST /api/v1/rotations/compare` (ABB-17) — body `RotationCompareRequest` {`profile`: `FarmProfile`, optional `horizon_years` 2–10}. Returns `RotationComparison` (`source_kind=MODEL_SCENARIO`, `status` `COMPARED | FEWER_ALTERNATIVES | INSUFFICIENT_INPUT | BLOCKED_BY_PROFILE_ERRORS`, `explanation[]`, `strategies[]` with the current rotation first, `candidate_screening[]` with exclusion/not-evaluable reasons, `incompatible_transitions[]`, `profile_issues`, `rule_set_version`, `catalog_version`, `limitations`). Each `RotationStrategy` has `strategy_kind` `CURRENT | MINIMAL_CHANGE | FAMILY_DIVERSIFICATION | CALENDAR_COVER`, `cycle`, `years`, `transitions[]` (`COMPATIBLE | TIGHT | INCOMPATIBLE | NOT_EVALUABLE` with fallow-gap months), `constraint_checks[]` (`SATISFIED | VIOLATED | REVIEW_REQUIRED | NOT_EVALUABLE`), a descriptive `comparison`, `priorities_addressed[]`, `possible_benefits[]`, `risks[]`, `assumptions[]`, `conditions_requiring_review[]`, `limitations[]`, `evidence_refs[]` (unreviewed literature metadata) and `verified_impact: null`. Stateless; 422 for unknown fields or out-of-range values; no yield, water, income or score fields. See `docs/science/ROTATIONS.md`.
- `POST /api/v1/rotations/scenarios` (ABB-18) — body `ScenarioAnalysisRequest` {`profile`, optional `horizon_years` 2–10, optional `priorities_override` (ordinal ranks), optional `water_override` {`water_regime`, `irrigation_allowance`}, `climate_scenarios[]` (≤6, unique `id`): `HISTORICAL_EPISODE` {`episode` = `source_kind`(OBSERVED)/`dataset`/`data_sha256`/`retrieved_at`/`event_year`/`reference_start`/`reference_end`/`spatial_resolution`/`monthly` copied from `/api/climate` (no coordinates or request parameters accepted), `flag_rules[]` {`condition` DRIER|WETTER|HOTTER|COOLER, `threshold` > 0, `unit` mm|°C}} or `HYPOTHETICAL` {`flags[]` {`condition`, `months[]`}}}. Returns `ScenarioAnalysis` (`status` ANALYSED|NOT_ANALYSED, `source_kind=MODEL_SCENARIO`, `input_sha256`, `applied_inputs`, `scenarios[]` with `scenario_label` HISTORICAL_EPISODE_OBSERVED | HYPOTHETICAL_SCENARIO and `is_forecast: false`, the unchanged ABB-17 `comparison`, `exposure[]` per strategy × scenario (`basis=CALENDAR_OVERLAP_NOT_IMPACT`, EVALUATED|PARTIAL|NOT_EVALUABLE), `ordering` (LEXICOGRAPHIC_BY_FARMER_RANK, `is_recommendation: false`, criteria, criteria_not_used, steps, positions with ties, adjacent_decisions), `trade_offs[]`, `separation[]`, `explanation`, `limitations`, `verified_impact: null`). 422 for duplicate ranks/criteria, rainfed with allowance > 0, unit mismatch, contradictory months, unknown fields.
- `POST /api/v1/rotations/sensitivity` (ABB-18) — body `SensitivityRequest` {`base`: `ScenarioAnalysisRequest`, `change`: `PRIORITY_SWAP` {criterion_a, criterion_b} | `PRIORITIES` | `WATER` | `CLIMATE_SCENARIOS`}. Returns `SensitivityAnalysis` (`status` COMPARED|NOT_COMPARABLE, request/base/variant SHA-256, `change_summary`, `priority_changes`, `criteria_changes`, `screening_changes`, `strategy_changes`, `position_changes`, `pair_changes` with the deciding criterion before/after, `exposure_changes`, `explanation`, `base_ordering`, `variant_ordering`, `verified_impact: null`). Stateless and deterministic; no yield, saving, probability, weight or score fields. See `docs/science/SCENARIOS_SENSITIVITY.md`.
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

## Accounts and cases (IMPLEMENTED — ABB-05/ABB-06, ADR-0004)

Require `DATABASE_URL` (PostgreSQL, migrated to `b7e2d4a91c03`); otherwise 503 `Persistent storage is not available on this server.` Authentication: `Authorization: Bearer <token>` from `POST /api/v1/auth/login`; opaque token, 12 h, revocable with `POST /api/v1/auth/logout`. Errors use `{detail}`: 401 unauthenticated, 404 no access or nonexistent (same body), 403 role not allowed, 409 stale `version` / invalid transition / case not editable, 422 validation, 429 account locked (`Retry-After`).

- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`.
- `POST|GET /api/v1/cases`, `GET|PATCH|DELETE /api/v1/cases/{case_id}`, `POST /api/v1/cases/{case_id}/status`, `POST /api/v1/cases/{case_id}/archive`, `GET /api/v1/cases/{case_id}/history`, `POST /api/v1/cases/{case_id}/fields`, `PATCH|DELETE /api/v1/cases/{case_id}/fields/{field_id}`, `GET|POST /api/v1/cases/{case_id}/permissions`, `DELETE /api/v1/cases/{case_id}/permissions/{user_id}`.
- Responses `CaseView` / `CaseFieldView` extend the shared `Case` / `Field` additively (`version`, `status` DRAFT|INVESTIGATING|REVIEWED|PUBLISHED, `archived_at`, `owner`, `my_role`; `location_precision`, `rounding_deg`, `precise_location_consent`). Coordinates are redacted server-side for REVIEWER/VIEWER: APPROXIMATE → grid-cell centre of `rounding_deg`; REGION_ONLY/WITHHELD → null; exact only with owner consent. Every content change requires the current `version` and appends author, time and before/after values to the history. `PUBLISHED` does not make a case public; `PUBLIC_ROUNDED` is not served.

## Papers and evidence claims (IMPLEMENTED — ABB-14)

Same auth, 503 and error rules as the cases API. See `docs/science/EVIDENCE_CLAIMS.md`.

- `POST /api/v1/evidence/papers` `{doi | openalex_id}` → `PaperView` (shared `Paper` + `source`, `caveat`); 201 created / 200 existing; 404 unknown work, 502 sources unavailable (nothing stored); metadata is always fetched upstream, never taken from the client. `GET /api/v1/evidence/papers/{paper_id}`.
- `GET|POST /api/v1/cases/{case_id}/claims`, `GET|PATCH|DELETE /api/v1/cases/{case_id}/claims/{claim_id}`, `POST …/{claim_id}/review`, `GET …/{claim_id}/history`, `POST /api/v1/cases/{case_id}/claims/pilot-import`.
- `ClaimView` extends the shared `EvidenceClaim` additively (`case_id`, `version`, `is_reviewed`, `reviewer`, `created_by`, `created_at`, `updated_at`, paper summary, `study_design`, `context`, `reported_outcome` as text, `source_locator`, `quoted_fragment`, `evidence_basis`, `access_basis`, `content_license`, `origin`, `origin_ref`, `warnings`, `can_edit`, `can_review`). `source_kind` is `LITERATURE_REVIEWED` only for ACCEPTED claims; `reviewed_by`/`reviewed_at` are the latest decision. Any content edit resets to PENDING. Decisions require a note and `source_consulted`; ACCEPTED requires a FULL_TEXT check with legitimate access and licence, resolved DOI identity, study design and outcome; contributors cannot review their own claims (403).

## Case observations, timeline and hypotheses (IMPLEMENTED — ABB-10)

Same authentication and 401/403/404/409/422/503 rules as the cases API; requires migration `e3a9c71f5b20` (chained after `e3c91f5a7d24`). See `docs/science/TIMELINE_HYPOTHESES.md`.

- `POST /api/v1/cases/{case_id}/observations/nasa-power` (OWNER/EDITOR), body `{field_id?, event_year?, reference_start?, reference_end?}`; coordinates are never accepted from the client (the field's stored location is used server-side). Returns `IngestionResult`: 201 new data, 200 `created=false` when identical, 502 on upstream failure with nothing stored.
- `GET /api/v1/cases/{case_id}/observations?include_superseded=` → `{items: IngestionView[]}` (`SourceManifestView`, `ObservationView` with `AnomalyView` and `departure`). For REVIEWER/VIEWER, `query_parameters` latitude/longitude are `"REDACTED"` and upstream messages are withheld.
- `GET /api/v1/cases/{case_id}/timeline` → `Timeline`: events with `kind` OBSERVED | FARMER_REPORTED | HYPOTHESIS | MISSING_DATA, `event_type`, `start`, `end`, `provenance`, `limitations`, and the descriptive severity rule `abb10-departure-vs-reference-sd-1`.
- `GET|POST /api/v1/cases/{case_id}/hypotheses`, `POST …/hypotheses/templates`, `GET|PATCH|DELETE …/hypotheses/{id}`, `POST …/hypotheses/{id}/status` (OWNER/EDITOR/REVIEWER; `OPEN | COMPATIBLE | CONTRADICTED | NOT_EVALUABLE`), `GET /api/v1/hypothesis-templates`.
- Shared `Hypothesis.status` additively includes `COMPATIBLE | CONTRADICTED | NOT_EVALUABLE` (contract 1.0); the case API never sets SUPPORTED/CHALLENGED/REJECTED. No hypothesis carries a probability or score. Evidence links must reference observations, anomalies or evidence claims of the same case.

## Proposed release 1.0 routes (NOT IMPLEMENTED)

Formalize versioned `/api/v1` resources through their owning roadmap Issues (cases, observations, timeline, hypotheses and claims are implemented, see above):
- `/api/v1/evidence/search` — DOI discovery (today `GET /api/literature`); `/api/v1/evidence/findings` is superseded by the ABB-14 claims routes above.
- `/api/v1/cases/{case_id}/rotations/compare` — three+ feasible options with explicit scenarios (the stateless `/api/v1/rotations/compare` exists; the case-bound route waits for persisted profiles, ABB-06).
- `/api/v1/cases/{case_id}/reviews` — reviewer comments and decisions with access control.
- `/api/v1/cases/{case_id}/reports` — versioned human-readable case reports.

Do not migrate existing consumers without coordination with affected domains. Breaking changes require a compatibility plan, contract tests, updated docs and a new contract version when compatibility cannot be preserved.

## Shared response requirements

Use strongly typed fields for `provenance`, `units`, `spatial_resolution`, `temporal_resolution`, `source_kind`, `limitations`, `created_at`, `processing_version` where applicable. Observations are data; hypotheses must never present a numeric causal score without a validated method.
