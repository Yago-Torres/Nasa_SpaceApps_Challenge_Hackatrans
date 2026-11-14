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
