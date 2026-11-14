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
