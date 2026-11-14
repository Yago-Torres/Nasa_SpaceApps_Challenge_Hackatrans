/**
 * Response shapes of the endpoints that exist today (docs/architecture/API_CONTRACTS.md),
 * transcribed from backend/agroblackbox/app.py and services/*.py. Replace with types
 * generated from the OpenAPI contract once ABB-02 freezes /api/v1.
 */

export type ClimateMonth = {
  month: number;
  precipitation_mm: number | null;
  reference_precipitation_mm: number | null;
  precipitation_anomaly_mm: number | null;
  max_temperature_c: number | null;
  reference_max_temperature_c: number | null;
  max_temperature_anomaly_c: number | null;
  /** ABB-08 per-variable quality flags (always returned by the backend since ABB-07/08). */
  quality?: ClimateMonthQuality;
};

/** Shared 1.0 `Resolution` contract (backend/agroblackbox/schemas.py). */
export type Resolution = { value: number | null; unit: string; description: string };

/** ABB-08: event-year daily coverage of one variable in one month, plus its reference sample. */
export type ClimateVariableMonthQuality = {
  status: 'complete' | 'partial' | 'missing';
  /** Plain sentence with day counts; null when complete. */
  reason: string | null;
  expected_days: number;
  valid_days: number;
  missing_days: number;
  fill_value_days: number;
  absent_days: number;
  invalid_days: number;
  /** EVENT_MONTH_PARTIAL | EVENT_MONTH_MISSING | FILL_VALUES_PRESENT | REFERENCE_YEARS_EXCLUDED | REFERENCE_INSUFFICIENT */
  flags: string[];
  reference: {
    status: 'complete' | 'reduced' | 'insufficient';
    years_expected: number;
    sample_count: number;
    years_excluded: number[];
    standard_deviation: number | null;
    minimum: number | null;
    maximum: number | null;
    reason: string | null;
  };
  anomaly_computed: boolean;
  anomaly_reason: string | null;
  units: string;
};

export type ClimateMonthQuality = {
  precipitation: ClimateVariableMonthQuality;
  max_temperature: ClimateVariableMonthQuality;
};

/** Shared 1.0 `SourceManifest` contract as returned by /api/climate (`provenance`). */
export type SourceManifest = {
  schema_version: '1.0';
  id: string;
  provider: string;
  dataset: string;
  source_uri: string;
  query_parameters: Record<string, string | number>;
  /** ISO 8601 UTC */
  retrieved_at: string;
  checksum_sha256: string;
  dataset_version: string | null;
  processing_version: string;
  license: string | null;
  spatial_resolution: Resolution;
  temporal_resolution: Resolution;
  limitations: string[];
};

export type ClimateQuality = {
  status: 'complete' | 'partial' | 'insufficient';
  fill_value: number;
  variables: Record<string, {
    complete_months: number;
    partial_months: number;
    missing_months: number;
    anomalies_computed: number;
    months_with_reference_years_excluded: number;
    months_with_insufficient_reference: number;
  }>;
  /** Plain sentences, always displayable. */
  warnings: string[];
};

export type AnomalyMethod = {
  id: string;
  description: string;
  anomaly_formula: string;
  event_year: number;
  reference_start: number;
  reference_end: number;
  reference_years: number;
  minimum_reference_years: number;
  reference_is_climatological_normal: boolean;
  reference_label: string;
  completeness_rule: string;
  daily_time_standard: 'UTC';
  aggregations: Record<string, string>;
  valid_ranges: Record<string, { min: number; max: number; units: string }>;
  uncertainty: string;
  processing_version: string;
};

/** GET /api/climate */
export type ClimateResponse = {
  kind: 'observation';
  dataset: string;
  source_url: string;
  data_sha256: string;
  request_params: Record<string, string | number>;
  event_year: number;
  reference_start: number;
  reference_end: number;
  monthly: ClimateMonth[];
  disclaimer: string;
  // ABB-07/08 additive fields. Always returned by the backend; optional here so older
  // fixtures and payloads keep type-checking.
  source_kind?: 'OBSERVED';
  /** ISO 8601 UTC time NASA POWER was queried (original time when served from cache). */
  retrieved_at?: string;
  spatial_resolution?: Resolution;
  temporal_resolution?: Resolution;
  provenance?: SourceManifest;
  upstream?: {
    title: string | null;
    api_name: string | null;
    api_version: string | null;
    sources: string[];
    fill_value: number | null;
    time_standard: string | null;
    start: string | null;
    end: string | null;
    messages: string[];
  };
  cache?: { served_from_cache: boolean; cache_age_seconds: number | null; ttl_seconds: number; upstream_attempts: number };
  variables?: {
    key: string;
    source_parameter: string;
    source_longname: string | null;
    source_units: string;
    units_reported_by_source: boolean;
    monthly_aggregation: string;
    monthly_units: string;
    anomaly_units: string;
  }[];
  method?: AnomalyMethod;
  quality?: ClimateQuality;
  limitations?: string[];
};

/** Item of GET /api/literature → { results } */
export type Paper = {
  title: string;
  year: number | null;
  doi: string | null;
  openalex_id: string | null;
  kind: 'literature';
  source: string;
  caveat: string;
};

/** Item of GET /api/rotations/demo → { rotations } */
export type Rotation = {
  id: string;
  kind: 'modelled_scenario';
  name: string;
  years: string[][];
  crop_diversity_count: number;
  includes_legume: boolean;
  includes_cover_crop: boolean;
  interpretation: string;
  verified_impact: null;
  warning: string;
};

/** POST /api/report */
export type ReportRequest = {
  location_label: string;
  climate: ClimateResponse | Record<string, never>;
  literature: Paper[];
  rotations: Rotation[];
};
export type ReportResponse = { filename: string; markdown: string; status: string };

/* ── Accounts and cases, /api/v1 (ABB-05/ABB-06, ADR-0004) ─────────────────────────────
 * Transcribed from backend/agroblackbox/api/dto.py and schemas.py (Case, Field). Keep in
 * sync with the OpenAPI schema until the client is generated (request A7). */

export type Role = 'OWNER' | 'EDITOR' | 'REVIEWER' | 'VIEWER';
export type GrantableRole = Exclude<Role, 'OWNER'>;
export type CaseStatus = 'DRAFT' | 'INVESTIGATING' | 'REVIEWED' | 'PUBLISHED';
/** What the caller receives for a field after server-side redaction. */
export type LocationPrecision = 'EXACT' | 'APPROXIMATE' | 'REGION_ONLY' | 'NONE';
/** Stored privacy tier of a field (shared `PrivacyTier`). */
export type FieldPrivacyTier = 'EXACT' | 'APPROXIMATE' | 'REGION_ONLY' | 'WITHHELD';
export type RoundingDeg = 0.1 | 0.5 | 1;

export type UserOut = { id: string; email: string; display_name: string; created_at: string };
export type UserSummary = { id: string; display_name: string };
/** POST /api/v1/auth/login. `access_token` is opaque, valid 12 h; never log or persist it beyond the tab. */
export type SessionOut = { access_token: string; token_type: 'bearer'; expires_at: string; user: UserOut };
/** POST /api/v1/auth/register (201 → UserOut). Password 12–256 characters. */
export type RegisterRequest = { email: string; password: string; display_name: string };
export type LoginRequest = { email: string; password: string };

/** Request body for a field (`FieldInput`). APPROXIMATE without `rounding_deg` defaults to 0.1 server-side. */
export type FieldInput = {
  label: string;
  privacy_tier: FieldPrivacyTier;
  latitude?: number | null;
  longitude?: number | null;
  region_label: string;
  area_hectares?: number | null;
  precise_location_consent?: boolean;
  rounding_deg?: RoundingDeg | null;
  limitations?: string[];
};

/** `CaseFieldView`: shared `Field` plus redaction metadata. Coordinates are already redacted for the caller's role. */
export type CaseFieldView = {
  schema_version: '1.0';
  id: string;
  label: string;
  privacy_tier: FieldPrivacyTier;
  latitude: number | null;
  longitude: number | null;
  region_label: string;
  area_hectares: number | null;
  limitations: string[];
  location_precision: LocationPrecision;
  rounding_deg: number | null;
  precise_location_consent: boolean;
};

/** `CaseView`: shared `Case` plus workflow, optimistic `version` and the caller's role. */
export type CaseView = {
  schema_version: '1.0';
  id: string;
  title: string;
  /** ISO date (YYYY-MM-DD), 1900-01-01 … today */
  incident_start: string;
  incident_end: string | null;
  fields: CaseFieldView[];
  crop_history: string[];
  incident_notes: string | null;
  visibility: 'PRIVATE' | 'SHARED' | 'PUBLIC_ROUNDED';
  created_at: string;
  updated_at: string;
  version: number;
  status: CaseStatus;
  archived_at: string | null;
  owner: UserSummary;
  my_role: Role;
};

export type CaseList = { items: CaseView[] };

/** POST /api/v1/cases. crop_history ≤ 50 entries of 1–120 characters; incident_notes ≤ 10 000. */
export type CaseCreate = {
  title: string;
  incident_start: string;
  incident_end?: string | null;
  crop_history?: string[];
  incident_notes?: string | null;
  fields: FieldInput[];
};

type CaseAttributes = Pick<CaseCreate, 'title' | 'incident_start' | 'incident_end' | 'crop_history' | 'incident_notes'>;
/** PATCH /api/v1/cases/{id}: every mutation carries the version the client read (409 if stale). */
export type CaseUpdate = { version: number } & Partial<CaseAttributes>;
/** PATCH /api/v1/cases/{id}/fields/{field_id}: partial; the merged field is re-validated. */
export type FieldPatch = { version: number } & Partial<FieldInput>;
export type FieldCreate = { version: number; field: FieldInput };
export type StatusChange = { version: number; status: CaseStatus; note?: string | null };
export type ArchiveRequest = { version: number; archived: boolean };
export type PermissionGrant = { email: string; role: GrantableRole };
export type PermissionView = { user_id: string; display_name: string; email: string | null; role: Role };
/** GET /api/v1/cases/{id}/history. Coordinates inside `changes` are "REDACTED" for reviewers/viewers. */
export type HistoryEntry = {
  id: string;
  version: number;
  action: string;
  actor: UserSummary | null;
  created_at: string;
  changes: Record<string, unknown>;
  note: string | null;
};
