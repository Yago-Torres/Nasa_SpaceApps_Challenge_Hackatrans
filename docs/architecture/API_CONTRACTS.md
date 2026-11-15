# API contracts — implemented vs target

**Live source of truth for currently implemented endpoints:** FastAPI OpenAPI at `http://localhost:8000/openapi.json` after backend startup. The existing baseline uses `/api/*`, not yet `/api/v1/*`.

## Implemented (as of initial archive)

- `GET /api/health` — liveness: `{status: "ok", version}`; `version` is the release tag baked into the image (`APP_VERSION`), else the package version. Does not touch the database.
- `GET /api/ready` (ABB-30) — readiness: 200 `{status: "ready", version, checks: {database: "ok", migrations: "at_head"}}` when PostgreSQL answers and its schema is at this build's Alembic head; 503 `{status: "not_ready", …, checks}` with `database` = `not_configured` | `unreachable_or_not_migrated` or `migrations` = `not_at_head` | `unknown`. Never returns connection details.
- `GET /api/metrics` (ABB-30, not in OpenAPI) — Prometheus text; 404 unless `METRICS_TOKEN` (16+ characters) is configured, 401 without `Authorization: Bearer <token>`. Counters by route **template** (never raw URLs), unhandled errors by type, external-source calls by `source` (`nasa_power`, `openalex_search`, `openalex_lookup`, `crossref`) and `outcome`, last failure time per source. Every response carries `X-Request-ID` (a safe incoming value is kept); unhandled errors answer 500 `{detail: "Internal error.", request_id}`.
- `GET /api/climate?latitude=&longitude=&event_year=&reference_start=&reference_end=` (ABB-07/08) — typed `ClimateResponse` (see OpenAPI). Baseline keys `kind, dataset, source_url, data_sha256, request_params, event_year, reference_start, reference_end, monthly[], disclaimer` are kept. Additive: `source_kind=OBSERVED`, `retrieved_at` (UTC, original retrieval time when cached), `spatial_resolution`/`temporal_resolution` (`Resolution`), `provenance` (`SourceManifest` 1.0), `upstream` (POWER header: API version, sources, fill value, time standard, messages), `cache` (`served_from_cache`, `cache_age_seconds`, `ttl_seconds`, `upstream_attempts`), `variables[]`, `method` (formula, reference label, `reference_is_climatological_normal=false`, completeness rule), `quality` (status, counts, warnings), `limitations[]`, and `monthly[].quality.{precipitation,max_temperature}` (status complete/partial/missing, reason, day counts, flags, reference coverage with sample count/excluded years/SD/min/max). Partial months and fill values give `null`, never values. Upstream failure, timeout, rate limit or invalid payload returns 502 with a generic message (no URL/query); invalid inputs return 422 without calling POWER. Small reference windows are not climatological normals. See `docs/science/CLIMATE_ANOMALIES.md`.
- `GET /api/vegetation/hls?latitude=&longitude=&start=&end=` (ABB-12) — typed `VegetationResponse`. Dates are UTC days, inclusive, at most 92 days, from 2013-04-11, not in the future; |latitude| ≤ 80 (422 otherwise, before any upstream call). Returns `kind=observation`, `source_kind=OBSERVED`, `dataset`, `source_url`, `request_params`, `start`, `end`, `retrieved_at`, `spatial_resolution` (30 m, 3 × 3 window), `temporal_resolution` (per overpass), `provenance` (`SourceManifest`, checksum over the observations), `observations[]` (one per overpass: `date`, `acquired_at`, `product` HLSL30|HLSS30, `sensor`, `granule_id`, `mgrs_tile`, `scene_cloud_cover`, `status` VALID|OBSCURED|NO_DATA|NOT_READ, `reason`, `window_pixels`, `pixels` Fmask class counts, `ndvi`/`ndvi_min`/`ndvi_max` and `red_reflectance`/`nir_reflectance` only when VALID, bands, `epsg`, `pixel_size_m`, `data_sha256`), `gaps[]` (`start`, `end`, `days` without a VALID observation), `summary`, `method`, `cache`, `limitations[]`, `disclaimer`. 503 when the server has no `EARTHDATA_TOKEN`; 502 when NASA rejects the credentials, fails, or every scene fails (no URL, coordinate or upstream body in the message). Nothing is interpolated. See `docs/science/HLS_VEGETATION.md`, ADR-0009.
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

## Claim disagreements and applicability (IMPLEMENTED — ABB-15)

Same auth, 503 and error rules as ABB-14; requires migration `c4d82e1f9a37`. See `docs/science/CONTRADICTIONS_APPLICABILITY.md`.

- `ClaimView`/`ClaimCreate`/`ClaimPatch` add `intervention`, `comparator`, `outcome_variable`, `effect_direction` (`INCREASE | DECREASE | NO_CLEAR_EFFECT | MIXED | NOT_STATED`, default `NOT_STATED`; a direction requires intervention, outcome variable and more than metadata). `context` adds `water_regime`, `soil_texture_classes`, `soil_ph_min`/`soil_ph_max`, `geographic_scope`, `countries` (ISO alpha-2), `climate_classes` (Köppen–Geiger). Additive.
- `GET /api/v1/cases/{case_id}/claims/disagreements` → `DisagreementList` (`items: DisagreementView[]` with both claim references and paper summaries, `comparability_notes`, `status CANDIDATE | CONFIRMED_CONTRADICTION | NOT_COMPARABLE | INCONCLUSIVE`, review history; `claims_not_compared`).
- `POST …/claims/disagreements/{disagreement_id}/review` `{decision, note, claim_a_version, claim_b_version}`; OWNER/EDITOR/REVIEWER who did not write either claim; CONFIRMED_CONTRADICTION needs both claims ACCEPTED; a decision stops applying when either claim version changes.
- `POST …/claims/{claim_id}/applicability` `{farm_profile?, country_code?, koppen_climate?}` → `ApplicabilityReport` (per-dimension MATCH/PARTIAL/MISMATCH/UNKNOWN with reasons, `transfer_status`, `stored: false`). No numeric score, weight, probability or confidence.

## Uncertainty Hunter (IMPLEMENTED — ABB-19)

Same auth, 503 and error rules as the cases API; requires migration `a19f3b7c2d64` (after `f4b81d2c6e93`). See `docs/science/UNCERTAINTY_HUNTER.md`.

- `GET /api/v1/cases/{case_id}/uncertainty` (all members) and `POST` with `{farm_profile?, country_code?, koppen_climate?, horizon_years?}` (nothing stored) → `UncertaintyReport` (`gaps[]` with deterministic id, category, cause, sources, question_ids, would_change; `questions[]` with `question, why_it_matters, measurement, units, would_change[{target_type, target_id, label, current_state, how}]`, link counts, `position`/`tied_with`, `resolution`; `prioritisation` `ORDERED_BY_LINK_COUNTS | NO_BASIS_TO_PRIORITISE | NO_OPEN_QUESTIONS`, `is_value_of_information: false`).
- `POST …/uncertainty/questions/{question_id}/answers` (OWNER/EDITOR) `{value_text?, value_number?+unit, observed_from?, observed_to?, origin, method?, source_reference?, note?, replaces_answer_id?}` → `AnswerView` (FARMER_REPORTED; corrections supersede, 409 when stale; analysis tasks 422).
- `POST …/uncertainty/answers/{answer_id}/review` `{version, decision: REVIEWED|REJECTED, note}` (OWNER/EDITOR/REVIEWER, not the author: 403). `POST …/questions/{question_id}/dismiss|reopen` `{note}` (OWNER/EDITOR). `GET …/uncertainty/answers`, `GET …/questions/{question_id}/history`, `GET /api/v1/uncertainty/question-catalogue`.
- Hypothesis evidence links additively accept local answer ids (`EvidenceRef.evidence_type: LOCAL_ANSWER`, `kind: FARMER_REPORTED`). No score, weight, probability, confidence or value-of-information field exists.

## Case observations, timeline and hypotheses (IMPLEMENTED — ABB-10)

Same authentication and 401/403/404/409/422/503 rules as the cases API; requires migration `e3a9c71f5b20` (chained after `e3c91f5a7d24`). See `docs/science/TIMELINE_HYPOTHESES.md`.

- `POST /api/v1/cases/{case_id}/observations/nasa-power` (OWNER/EDITOR), body `{field_id?, event_year?, reference_start?, reference_end?}`; coordinates are never accepted from the client (the field's stored location is used server-side). Returns `IngestionResult`: 201 new data, 200 `created=false` when identical, 502 on upstream failure with nothing stored.
- `GET /api/v1/cases/{case_id}/observations?include_superseded=` → `{items: IngestionView[]}` (`SourceManifestView`, `ObservationView` with `AnomalyView` and `departure`). For REVIEWER/VIEWER, `query_parameters` latitude/longitude are `"REDACTED"` and upstream messages are withheld.
- `GET /api/v1/cases/{case_id}/timeline` → `Timeline`: events with `kind` OBSERVED | FARMER_REPORTED | HYPOTHESIS | MISSING_DATA, `event_type`, `start`, `end`, `provenance`, `limitations`, and the descriptive severity rule `abb10-departure-vs-reference-sd-1`.
- `GET|POST /api/v1/cases/{case_id}/hypotheses`, `POST …/hypotheses/templates`, `GET|PATCH|DELETE …/hypotheses/{id}`, `POST …/hypotheses/{id}/status` (OWNER/EDITOR/REVIEWER; `OPEN | COMPATIBLE | CONTRADICTED | NOT_EVALUABLE`), `GET /api/v1/hypothesis-templates`.
- Shared `Hypothesis.status` additively includes `COMPATIBLE | CONTRADICTED | NOT_EVALUABLE` (contract 1.0); the case API never sets SUPPORTED/CHALLENGED/REJECTED. No hypothesis carries a probability or score. Evidence links must reference observations, anomalies or evidence claims of the same case.

## Case evidence graph, conclusions and edges (IMPLEMENTED — ABB-16)

Same authentication and 401/403/404/409/422/503 rules as the cases API; requires migration `f4b81d2c6e93` (after `c4d82e1f9a37`). See `docs/science/EVIDENCE_GRAPH.md`.

- `GET /api/v1/cases/{case_id}/evidence-graph?include_superseded=` → `EvidenceGraphView` {nodes `{id, node_type, kind, label, entity_id, status, active, original_evidence, linkable, start, end, provenance, limitations, details}`, edges `{id, from, to, relation (SUPPORTS|CONTRADICTS|LIMITS|ADDRESSES|DERIVED_FROM|CITES), origin (STRUCTURAL|HYPOTHESIS_LINK|DISAGREEMENT_REVIEW|MANUAL), note, review_status, record_id, conclusion_id, version, author, reviewed_by, reviewed_at, review_note, can_edit, can_review}`, counts, relations, orphan_references, limitations}. `kind` adds `CONCLUSION`. Provenance never carries query parameters or coordinates.
- `GET …/evidence-graph/trace/{node_id}` → `EvidenceTraceView` (complete, paths, original_evidence, dead_ends, nodes, edges, limiting_edges, contradiction_edges, summary, review_blockers).
- `GET|POST …/evidence-graph/conclusions`, `GET|PATCH|DELETE …/conclusions/{id}`, `POST …/conclusions/{id}/review` (OWNER/EDITOR/REVIEWER non-contributor; ACCEPTED needs a complete trace, reviewed literature and evaluated hypotheses).
- `GET|POST …/evidence-graph/edges`, `PATCH|DELETE …/edges/{id}`, `POST …/edges/{id}/review`. Endpoints must exist in the same case (422); DERIVED_FROM/CITES and SUPPORTS/CONTRADICTS into hypotheses cannot be added by hand. Deleting a hypothesis, claim or field that is still referenced returns 409.

## Account data export and deletion (IMPLEMENTED — ABB-28)

Same authentication and 401/503 rules as the cases API. See ADR-0005 and `docs/operations/LEGAL_AND_DATA_POLICY.md`.

- `GET /api/v1/account/export` → `AccountExport` {`profile` (`UserOut`), `cases` (`CaseView[]`, same role-aware coordinate redaction as `GET /api/v1/cases`), `sessions` (`SessionSummary[]`: `id`, `created_at`, `expires_at`, `revoked`, `current`; never a token or its digest), `exported_at`}.
- `POST /api/v1/account/delete` `{password}` → `AccountDeletionReceipt` {`cases_deleted`, `memberships_revoked`, `sessions_revoked`, `anonymized: true`, `deleted_at`}. 401 wrong password; 429 after 5 wrong confirmations (`Retry-After`, shares the account's existing login-lockout counters). Irreversible: erases every case the account owns (cascading fields/permissions/history/evidence exactly like `DELETE /api/v1/cases/{id}`), revokes membership on cases owned by others, revokes every session, and anonymises (does not row-delete) the account so `ON DELETE RESTRICT` references from other members' case evidence (`evidence_claims.created_by`, review/author columns on claims, disagreement reviews, uncertainty answers, graph conclusions/edges) stay valid.

## Collaboration: invitations, comments, activity, share links (IMPLEMENTED — ABB-25)

Same auth, 404/403, 503 and error rules as the cases API; requires migration `a7c2e9d4b158` (after `a19f3b7c2d64`). Full rules, roles and limitations: `docs/architecture/COLLABORATION.md`. Free text (comments, notes, labels) is plain text returned verbatim with `body_format: "text/plain"`; clients render it as text, never HTML.

- `POST|GET /api/v1/cases/{case_id}/invitations` (OWNER) `{email, role EDITOR|REVIEWER|VIEWER, note?, expires_in_days 1–30}` → `InvitationView` / `InvitationList`; `DELETE …/invitations/{id}` revokes a PENDING invitation (409 otherwise). No e-mail is sent; no account enumeration.
- `GET /api/v1/invitations` → `ReceivedInvitationList` (pending invitations for the signed-in e-mail); `POST /api/v1/invitations/{id}/accept|decline` → `InvitationDecision`. Anything that is not a pending, unexpired invitation for the caller returns 404.
- `GET|POST /api/v1/cases/{case_id}/comments` (every member, VIEWER included; 409 on archived cases), `GET|PATCH|DELETE …/comments/{id}` (edit: author with `version`; delete: author or OWNER, tombstone), `GET …/comments/{id}/revisions` (410 once deleted).
- `GET /api/v1/cases/{case_id}/activity?limit=&offset=&order=` → `ActivityPage` (case history, claim events, disagreement reviews and comments merged; actor, instant, target, `evidence`, `changes`; coordinates REDACTED for guests).
- `POST|GET /api/v1/cases/{case_id}/share-links` (OWNER) `{consent: true, sections{incident_notes, field_labels, location_detail NONE|REGION|APPROXIMATE, hypotheses, evidence_claims, conclusions, member_names, comments}, label?, expires_in_days 1–30}` → `ShareLinkCreated` (token shown once) / `ShareLinkList`; `DELETE …/share-links/{id}`.
- `GET /api/v1/shared/{token}` (no account) → `SharedCaseView`: never exact coordinates, case id, e-mails, user ids, observations, invitations, member lists or history; same 404 for unknown, revoked and expired tokens; `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex`.
- `POST /api/v1/account/delete` (ABB-28) additionally revokes pending invitations addressed to the deleted account's e-mail and scrubs that address from every invitation row.

## Case reports (IMPLEMENTED — ABB-26)

`POST /api/v1/cases/{case_id}/reports` also accepts `language: "en" | "es"`
(default `en`). The chosen language is stored in the immutable snapshot and reported
as `ReportView.language`; new Markdown, HTML and PDF versions use it for report
headings and labels. Existing versions retain their original bytes and language.

Same auth, 404/403 and 503 rules as the cases API; requires migrations `d5f3a8b21c64` (after `a7c2e9d4b158`) and `e8a4c1d7f905` (PDF). Method, privacy rules and limits: `docs/science/CASE_REPORT.md`.

- `POST /api/v1/cases/{case_id}/reports` (OWNER, EDITOR, REVIEWER) `{rotation?: RotationCompareRequest}` → 201 `ReportView` `{id, version, generated_at, status PRELIMINARY, case_version, generated_by, formats, checksum_sha256 (Markdown), html_sha256, snapshot_sha256, sources_sha256, source_manifest_ids, changes{initial, previous_version, case_version, items[{section, change ADDED|REMOVED|CHANGED, id, label}]}, limitations, downloads}`. Unknown body fields → 422. The server computes the optional rotation comparison itself; client-computed rotations are not accepted. Records `REPORT_GENERATED` in the case history without bumping the case version. At most 200 versions per case (409).
- `GET /api/v1/cases/{case_id}/reports` (every member) → `{items: ReportView[]}`, newest first; `GET …/reports/{version}` → `ReportView`.
- `GET …/reports/{version}/download?format=markdown|html|json` (every member) → the stored bytes with `Content-Disposition: attachment`, `X-Report-SHA256`, `no-store`, `nosniff` and a sandboxing CSP. No role receives coordinates, notes, e-mails, names or comment text. `format=pdf` serves the stored PDF (ADR-0007, `pdf_sha256`); 404 for versions stored before migration `e8a4c1d7f905`; unknown formats → 422. `ReportView.formats`/`downloads` list `pdf` only when one is stored.
- `GET …/reports/{version}/verify` → `{version, valid, checks{markdown_sha256, html_sha256, snapshot_sha256, sources_sha256, markdown_matches_snapshot, source_ids_match}, detail}`.
- Stored versions are write-once: a database trigger rejects any later UPDATE of their content.

## Proposed release 1.0 routes (NOT IMPLEMENTED)

Formalize versioned `/api/v1` resources through their owning roadmap Issues (cases, observations, timeline, hypotheses and claims are implemented, see above):
- `/api/v1/evidence/search` — DOI discovery (today `GET /api/literature`); `/api/v1/evidence/findings` is superseded by the ABB-14 claims routes above.
- `/api/v1/cases/{case_id}/rotations/compare` — three+ feasible options with explicit scenarios (the stateless `/api/v1/rotations/compare` exists; the case-bound route waits for persisted profiles, ABB-06).
- `/api/v1/cases/{case_id}/reviews` — superseded: comments are `…/comments` (ABB-25) and decisions stay on each record's review route (ABB-10/14/15/16/19).

Do not migrate existing consumers without coordination with affected domains. Breaking changes require a compatibility plan, contract tests, updated docs and a new contract version when compatibility cannot be preserved.

## Shared response requirements

Use strongly typed fields for `provenance`, `units`, `spatial_resolution`, `temporal_resolution`, `source_kind`, `limitations`, `created_at`, `processing_version` where applicable. Observations are data; hypotheses must never present a numeric causal score without a validated method.
