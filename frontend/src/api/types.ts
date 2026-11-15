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
  /** ABB-13 Crossref verification of the DOI (additive field). */
  doi_status?: DoiStatus;
  doi_id?: string | null;
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
export type SessionSummary = { id: string; created_at: string; expires_at: string; revoked: boolean; current: boolean };
export type AccountExport = { profile: UserOut; cases: CaseView[]; sessions: SessionSummary[]; exported_at: string };
export type AccountDeletionReceipt = {
  cases_deleted: number; memberships_revoked: number; sessions_revoked: number; anonymized: true; deleted_at: string;
};

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

/* ── Rotation comparator, /api/v1/rotations/* (ABB-24, request B4) ────────────────────────
 * Transcribed from backend/agroblackbox/farm_profile.py, services/rotations.py and
 * services/scenarios.py. Stateless: nothing here is persisted server-side. These endpoints
 * take no case_id/field_id; soil is deliberately omitted from this UI because the rotation
 * engine never evaluates it (ROTATIONS.md: "Soil, climate — Not evaluated"). */

/** ABB-11 `GET /api/v1/crop-catalog`. Identity only: no calendars or agronomic parameters. */
export type CropCatalogEntry = {
  schema_version: '1.0';
  code: string;
  common_name_en: string;
  common_name_es: string;
  scientific_name: string;
  botanical_family: string;
  crop_group: 'CEREAL' | 'GRAIN_LEGUME' | 'FORAGE_LEGUME' | 'OILSEED' | 'ROOT_TUBER' | 'INDUSTRIAL' | 'VEGETABLE';
  is_legume: boolean;
  review_status: 'PENDING' | 'ACCEPTED' | 'CHANGES_REQUESTED' | 'REJECTED';
  agronomic_parameters: null;
  sources: string[];
  limitations: string[];
};
export type CropCatalog = {
  schema_version: '1.0';
  catalog_version: string;
  entries: CropCatalogEntry[];
  sources: string[];
  limitations: string[];
};

export type DataOrigin = 'LOCAL_MEASUREMENT' | 'FARMER_ESTIMATE' | 'REGIONAL_ESTIMATE' | 'UNKNOWN';
export type WaterRegime = 'RAINFED' | 'IRRIGATED' | 'SUPPLEMENTAL_IRRIGATION' | 'UNKNOWN';
export type SeasonRole = 'MAIN_CROP' | 'INTERCROP' | 'COVER_CROP' | 'FALLOW';
export type PriorityCriterion =
  | 'SOIL_COVER' | 'WATER_USE' | 'INCOME_STABILITY' | 'WORKLOAD' | 'CROP_DIVERSITY' | 'INPUT_COSTS'
  | 'RISK_REDUCTION' | 'OTHER';
export type MarketStatus = 'CONTRACTED' | 'SELLABLE' | 'NO_MARKET' | 'UNKNOWN' | 'NOT_DECLARED';

/** `FarmerPriority`: ordinal rank (1 = most important), deliberately not a numeric weight. */
export type FarmerPriority = { criterion: PriorityCriterion; rank: number; note?: string | null };

export type IrrigationAllowance = {
  value: number;
  unit: 'mm/season' | 'mm/year' | 'm3/ha/season' | 'm3/ha/year';
  origin: DataOrigin;
  notes?: string | null;
};

export type MarketAccess = {
  crop_code?: string | null;
  crop_label: string;
  status: 'CONTRACTED' | 'SELLABLE' | 'NO_MARKET' | 'UNKNOWN';
  notes?: string | null;
};

export type FarmerConstraints = {
  water_regime: WaterRegime;
  irrigation_allowance?: IrrigationAllowance | null;
  excluded_crops: string[];
  available_equipment: string[];
  equipment_limitations?: string | null;
  market_access: MarketAccess[];
  labour_notes?: string | null;
  planning_horizon_years?: number | null;
  other_notes?: string | null;
};

/** One recorded season of the farmer's crop history. Defines the "current rotation". */
export type CropSeason = {
  crop_code?: string | null;
  crop_label: string;
  role: SeasonRole;
  season_year: number;
  sowing_date?: string | null;
  harvest_date?: string | null;
  water_regime: WaterRegime;
  origin: DataOrigin;
  notes?: string | null;
};

/** Farmer-declared typical month window for a crop at this farm (1-12; may wrap the year end). */
export type CalendarWindow = {
  crop_code?: string | null;
  crop_label: string;
  sowing_start_month: number;
  sowing_end_month: number;
  harvest_start_month?: number | null;
  harvest_end_month?: number | null;
  origin: DataOrigin;
  notes?: string | null;
};

/** ABB-11 `FarmProfile`. `soil` is always sent empty here (not evaluated by the rotation engine). */
export type FarmProfile = {
  schema_version: '1.0';
  soil: [];
  crop_history: CropSeason[];
  local_calendar: CalendarWindow[];
  constraints?: FarmerConstraints | null;
  priorities: FarmerPriority[];
};

export type ProfileIssue = {
  severity: 'ERROR' | 'WARNING' | 'MISSING_DATA';
  code: string;
  path: string;
  message: string;
  consequence?: string | null;
};

/* ── ABB-17 comparison contract (services/rotations.py) ── */

export type TransitionStatus = 'COMPATIBLE' | 'TIGHT' | 'INCOMPATIBLE' | 'NOT_EVALUABLE';
export type CheckStatus = 'SATISFIED' | 'VIOLATED' | 'REVIEW_REQUIRED' | 'NOT_EVALUABLE';
export type StrategyKind = 'CURRENT' | 'MINIMAL_CHANGE' | 'FAMILY_DIVERSIFICATION' | 'CALENDAR_COVER';

export type CropRef = { crop_code: string | null; crop_label: string; botanical_family: string | null; is_legume: boolean | null };

/** `min` assumes the latest sowing/earliest harvest; `max` the opposite. */
export type MonthRange = { min: number; max: number; unit: 'months' | 'months per year' };

export type TransitionCheck = {
  from_crop: string;
  to_crop: string;
  status: TransitionStatus;
  fallow_gap: MonthRange | null;
  same_family: boolean | null;
  message: string;
};

export type ConstraintCheck = {
  constraint: 'EXCLUDED_CROPS' | 'MARKET_ACCESS' | 'LOCAL_CALENDAR' | 'WATER_REGIME' | 'FAMILY_REPETITION'
    | 'EQUIPMENT' | 'SOIL' | 'CLIMATE';
  status: CheckStatus;
  detail: string;
};

export type MarketStatusItem = { crop_label: string; status: MarketStatus };

/** Facts derived from the declared inputs. Not a prediction and not a score. */
export type DescriptiveComparison = {
  basis: 'DECLARED_INPUTS_AND_RULES';
  cycle_years: number;
  distinct_crops: number;
  distinct_families: number;
  families: string[];
  includes_legume: boolean;
  legume_years_per_cycle: number;
  consecutive_same_family: number | null;
  months_with_crop: MonthRange | null;
  longest_fallow_gap: MonthRange | null;
  crops_new_to_farm: string[];
  market_status: MarketStatusItem[];
  not_evaluable: string[];
};

export type PriorityNote = {
  criterion: PriorityCriterion;
  rank: number;
  relation_to_current: 'REFERENCE' | 'MORE' | 'LESS' | 'SAME' | 'NOT_EVALUABLE';
  basis: string;
};

/** Bibliographic metadata only (topic match), pending human review — never a reviewed finding. */
export type RotationEvidenceRef = {
  id: string;
  doi: string;
  title: string;
  source_kind: 'LITERATURE_METADATA';
  review_status: 'HUMAN_REVIEW_REQUIRED';
  topic: string;
  limitation: string;
};

export type ScreeningReason = { code: string; message: string };

export type CandidateScreening = {
  crop: CropRef;
  status: 'ELIGIBLE' | 'EXCLUDED' | 'NOT_EVALUABLE';
  reasons: ScreeningReason[];
  declared_in: ('CROP_HISTORY' | 'LOCAL_CALENDAR' | 'MARKET_ACCESS')[];
  market_status: MarketStatus;
  grown_on_farm: boolean;
};

export type RotationStrategy = {
  schema_version: '1.0';
  id: string;
  name: string;
  strategy_kind: StrategyKind;
  is_current: boolean;
  source_kind: 'MODEL_SCENARIO';
  sequence_origin: 'FARMER_REPORTED' | 'RULE_GENERATED';
  selection_rule: string;
  cycle: CropRef[][];
  years: string[][];
  start_season_year: number | null;
  transitions: TransitionCheck[];
  entry_transition: TransitionCheck | null;
  screening_result: 'PASSES_DECLARED_CONSTRAINTS' | 'CONFLICTS_WITH_DECLARED_CONSTRAINTS' | 'NOT_FULLY_EVALUABLE';
  constraint_checks: ConstraintCheck[];
  comparison: DescriptiveComparison;
  priorities_addressed: PriorityNote[];
  possible_benefits: string[];
  risks: string[];
  assumptions: string[];
  conditions_requiring_review: string[];
  limitations: string[];
  evidence_refs: RotationEvidenceRef[];
  verified_impact: null;
};

export type GenerationSummary = { eligible_crops: string[]; cycle_lengths_considered: number[]; feasible_sequences: number; rules: string[] };

/** POST /api/v1/rotations/compare request body. */
export type RotationCompareRequest = { schema_version?: '1.0'; profile: FarmProfile; horizon_years?: number | null };

export type RotationComparison = {
  schema_version: '1.0';
  status: 'COMPARED' | 'FEWER_ALTERNATIVES' | 'INSUFFICIENT_INPUT' | 'BLOCKED_BY_PROFILE_ERRORS';
  source_kind: 'MODEL_SCENARIO';
  horizon_years: number;
  strategies: RotationStrategy[];
  explanation: string[];
  candidate_screening: CandidateScreening[];
  incompatible_transitions: TransitionCheck[];
  generation: GenerationSummary | null;
  profile_readiness: 'BLOCKED_BY_ERRORS' | 'LIMITED_BY_MISSING_DATA' | 'INPUTS_COMPLETE';
  profile_issues: ProfileIssue[];
  rule_set_version: string;
  catalog_version: string;
  limitations: string[];
};

/* ── ABB-18 scenarios/sensitivity contract (services/scenarios.py) ── */

export type Condition = 'DRIER' | 'WETTER' | 'HOTTER' | 'COOLER';
export type OrderingDirection = 'MORE_FIRST' | 'FEWER_FIRST' | 'PASSES_FIRST';

export type WaterAvailability = { water_regime: WaterRegime; irrigation_allowance?: IrrigationAllowance | null };

export type AnomalyFlagRule = { condition: Condition; threshold: number; unit: 'mm' | '°C' };

/** Keys copied unchanged from a `GET /api/climate` response; coordinates are never accepted here. */
export type ObservedClimateEpisode = {
  source_kind: 'OBSERVED';
  dataset: string;
  data_sha256: string;
  retrieved_at: string;
  event_year: number;
  reference_start: number;
  reference_end: number;
  spatial_resolution: Resolution;
  monthly: ClimateMonth[];
  limitations?: string[];
};

export type HistoricalEpisodeScenario = {
  scenario_type: 'HISTORICAL_EPISODE';
  id: string;
  label: string;
  episode: ObservedClimateEpisode;
  flag_rules: AnomalyFlagRule[];
};

export type HypotheticalMonths = { condition: Condition; months: number[] };

/** User-defined assumption, e.g. "dry spring": months 3-5 drier than the reference. Not a forecast. */
export type HypotheticalScenario = {
  scenario_type: 'HYPOTHETICAL';
  id: string;
  label: string;
  description?: string | null;
  flags: HypotheticalMonths[];
};

export type ClimateScenario = HistoricalEpisodeScenario | HypotheticalScenario;

export type ScenarioAnalysisRequest = {
  schema_version?: '1.0';
  profile: FarmProfile;
  horizon_years?: number | null;
  priorities_override?: FarmerPriority[] | null;
  water_override?: WaterAvailability | null;
  climate_scenarios: ClimateScenario[];
};

export type AppliedInputs = {
  horizon_years: number | null;
  priorities: FarmerPriority[];
  priorities_from: 'PROFILE' | 'OVERRIDE';
  water_regime: WaterRegime;
  irrigation_allowance: IrrigationAllowance | null;
  water_from: 'PROFILE' | 'OVERRIDE';
  scenario_ids: string[];
};

export type EpisodeProvenance = {
  dataset: string;
  data_sha256: string;
  retrieved_at: string;
  event_year: number;
  reference_start: number;
  reference_end: number;
  spatial_resolution: Resolution;
};

export type FlaggedMonth = { month: number; conditions: Condition[]; basis: string[]; quality_flags: string[] };
export type NotEvaluableMonth = { month: number; reason: string };

export type ScenarioSummary = {
  id: string;
  label: string;
  scenario_type: 'HISTORICAL_EPISODE' | 'HYPOTHETICAL';
  scenario_label: 'HISTORICAL_EPISODE_OBSERVED' | 'HYPOTHETICAL_SCENARIO';
  source_kind: 'OBSERVED' | 'MODEL_SCENARIO';
  is_forecast: false;
  statement: string;
  provenance: EpisodeProvenance | null;
  flag_rules: AnomalyFlagRule[];
  flagged_months: FlaggedMonth[];
  not_evaluable_months: NotEvaluableMonth[];
  limitations: string[];
};

export type FlaggedMonthInField = { month: number; conditions: Condition[]; in_field: 'CERTAIN' | 'POSSIBLE' };

export type CycleYearExposure = {
  cycle_year: number;
  crop_label: string | null;
  status: 'EVALUATED' | 'FALLOW' | 'NOT_EVALUABLE';
  months_in_field_certain: number[];
  months_in_field_possible: number[];
  flagged_months_in_field: FlaggedMonthInField[];
  not_evaluable_months_in_field: number[];
  reason?: string | null;
};

export type CountRange = { min: number; max: number; of: number; unit: 'cycle years' };

export type StrategyExposure = {
  strategy_id: string;
  strategy_kind: string;
  scenario_id: string;
  basis: 'CALENDAR_OVERLAP_NOT_IMPACT';
  status: 'EVALUATED' | 'PARTIAL' | 'NOT_EVALUABLE';
  by_cycle_year: CycleYearExposure[];
  flagged_months_in_field_per_year: MonthRange | null;
  cycle_years_with_flagged_months: CountRange | null;
  explanation: string;
};

export type OrderingCriterion = {
  step: number;
  criterion_id: string;
  priority_criterion: PriorityCriterion | null;
  rank: number | null;
  direction: OrderingDirection;
  scenario_id?: string | null;
  description: string;
  unit: string | null;
};

export type CriterionValue = { strategy_id: string; value: number | string | null };

export type OrderingStep = {
  step: number;
  criterion_id: string;
  rank: number | null;
  values: CriterionValue[];
  groups_before: string[][];
  groups_after: string[][];
  explanation: string;
};

export type CriterionNotUsed = { criterion: PriorityCriterion; rank: number; reason: string };
export type OrderedPosition = { strategy_id: string; strategy_kind: string; position: number; tied_with: string[] };
export type AdjacentDecision = {
  first_strategy_id: string;
  second_strategy_id: string;
  decided_at_step: number | null;
  decided_by: string | null;
  explanation: string;
};

export type Ordering = {
  rule: 'LEXICOGRAPHIC_BY_FARMER_RANK';
  description: string;
  is_recommendation: false;
  criteria: OrderingCriterion[];
  criteria_not_used: CriterionNotUsed[];
  steps: OrderingStep[];
  positions: OrderedPosition[];
  adjacent_decisions: AdjacentDecision[];
  notes: string[];
};

export type CriterionComparison = {
  criterion_id: string;
  priority_criterion: PriorityCriterion;
  rank: number | null;
  direction: OrderingDirection;
  unit: string;
  value: number | null;
  most_favourable_value: number | null;
  most_favourable_strategy_ids: string[];
  relation_to_most_favourable: 'MOST_FAVOURABLE' | 'GIVES_UP' | 'NOT_EVALUABLE';
  relation_to_current: 'REFERENCE' | 'MORE' | 'LESS' | 'SAME' | 'NOT_EVALUABLE';
};

export type StrategyTradeOff = {
  strategy_id: string;
  strategy_kind: string;
  criteria: CriterionComparison[];
  gives_up: string[];
  gains_vs_current: string[];
  other_differences_vs_current: string[];
};

export type SeparationNote = {
  part: string;
  kind: 'OBSERVED' | 'MODEL_SCENARIO' | 'HYPOTHETICAL_SCENARIO' | 'FARMER_REPORTED' | 'VALIDATED_FIELD_RESULT';
  present: boolean;
  meaning: string;
};

export type ScenarioAnalysis = {
  schema_version: '1.0';
  status: 'ANALYSED' | 'NOT_ANALYSED';
  source_kind: 'MODEL_SCENARIO';
  input_sha256: string;
  applied_inputs: AppliedInputs;
  scenarios: ScenarioSummary[];
  comparison: RotationComparison;
  exposure: StrategyExposure[];
  ordering: Ordering | null;
  trade_offs: StrategyTradeOff[];
  separation: SeparationNote[];
  explanation: string[];
  rule_set_version: string;
  limitations: string[];
  verified_impact: null;
};

export type PrioritySwapChange = { change_type: 'PRIORITY_SWAP'; criterion_a: PriorityCriterion; criterion_b: PriorityCriterion };
export type PrioritiesChange = { change_type: 'PRIORITIES'; priorities: FarmerPriority[] };
export type WaterChange = { change_type: 'WATER'; water: WaterAvailability };
export type ScenariosChange = { change_type: 'CLIMATE_SCENARIOS'; climate_scenarios: ClimateScenario[] };
export type SensitivityChange = PrioritySwapChange | PrioritiesChange | WaterChange | ScenariosChange;

export type SensitivityRequest = { schema_version?: '1.0'; base: ScenarioAnalysisRequest; change: SensitivityChange };

export type PriorityRankChange = { criterion: PriorityCriterion; rank_before: number | null; rank_after: number | null };
export type ValueChange = { strategy_kind: string; before: number | string | null; after: number | string | null };
export type CriterionChange = {
  criterion_id: string;
  step_before: number | null;
  step_after: number | null;
  change: 'ADDED' | 'REMOVED' | 'MOVED_EARLIER' | 'MOVED_LATER' | 'SAME_STEP';
  values_changed: ValueChange[];
  explanation: string;
};
export type ScreeningChange = {
  crop_label: string;
  status_before: string | null;
  status_after: string | null;
  reasons_before: string[];
  reasons_after: string[];
};
export type StrategyChange = {
  strategy_kind: string;
  change: 'SAME_SEQUENCE' | 'DIFFERENT_SEQUENCE' | 'ONLY_IN_BASE' | 'ONLY_IN_VARIANT';
  years_before: string[][] | null;
  years_after: string[][] | null;
  constraint_changes: string[];
  explanation: string;
};
export type PositionChange = {
  strategy_kind: string;
  position_before: number | null;
  position_after: number | null;
  movement: 'UP' | 'DOWN' | 'SAME' | 'ADDED' | 'REMOVED';
  explanation: string;
};
export type PairRelation = 'FIRST_BEFORE_SECOND' | 'TIED' | 'SECOND_BEFORE_FIRST';
export type PairChange = {
  first_kind: string;
  second_kind: string;
  before: PairRelation;
  after: PairRelation;
  order_changed: boolean;
  decided_by_before: string | null;
  decided_by_after: string | null;
  explanation: string;
};
export type ExposureChange = {
  strategy_kind: string;
  scenario_id: string;
  status_before: string | null;
  status_after: string | null;
  before: MonthRange | null;
  after: MonthRange | null;
};

export type SensitivityAnalysis = {
  schema_version: '1.0';
  status: 'COMPARED' | 'NOT_COMPARABLE';
  source_kind: 'MODEL_SCENARIO';
  request_sha256: string;
  base_input_sha256: string;
  variant_input_sha256: string;
  change_type: 'PRIORITY_SWAP' | 'PRIORITIES' | 'WATER' | 'CLIMATE_SCENARIOS';
  change_summary: string[];
  priority_changes: PriorityRankChange[];
  criteria_changes: CriterionChange[];
  screening_changes: ScreeningChange[];
  strategy_changes: StrategyChange[];
  position_changes: PositionChange[];
  pair_changes: PairChange[];
  exposure_changes: ExposureChange[];
  explanation: string[];
  base_ordering: Ordering | null;
  variant_ordering: Ordering | null;
  rule_set_version: string;
  limitations: string[];
  verified_impact: null;
};

/* ── Case timeline and hypotheses, /api/v1/cases/{id}/{timeline,hypotheses} (ABB-10/ABB-22) ──
 * Transcribed from backend/agroblackbox/api/forensics_dto.py. Field names are kept snake_case
 * to match the wire format, as the rest of this file does for CaseView etc. The frontend never
 * computes severity, anomalies or statistics here: it only renders what the backend returned
 * (docs/science/TIMELINE_HYPOTHESES.md; frontend/AGENTS.md). */

export type TimelineKind = 'OBSERVED' | 'FARMER_REPORTED' | 'HYPOTHESIS' | 'MISSING_DATA';
export type TimelineEventType =
  | 'CLIMATE_ANOMALY' | 'INCIDENT_PERIOD' | 'CROP_HISTORY' | 'HYPOTHESIS'
  | 'DATA_GAP' | 'NO_OBSERVATIONS' | 'NO_LOCAL_MEASUREMENTS';
export type Severity = 'WITHIN_REFERENCE_SPREAD' | 'MODERATE_DEPARTURE' | 'LARGE_DEPARTURE' | 'NOT_CLASSIFIED';
export type Direction = 'ABOVE_REFERENCE' | 'BELOW_REFERENCE' | 'EQUAL_TO_REFERENCE';
export type EvaluationStatus = 'OPEN' | 'COMPATIBLE' | 'CONTRADICTED' | 'NOT_EVALUABLE';

/** Descriptive label from rule `rule_id` (e.g. abb10-departure-vs-reference-sd-1); never a probability. */
export type DepartureView = {
  rule_id: string;
  severity: Severity;
  direction: Direction | null;
  departure_in_reference_sd: number | null;
  outside_reference_range: boolean | null;
  reason: string | null;
};

export type ObservedValue = {
  variable: string;
  variable_label: string;
  source_parameter: string;
  value: number | null;
  units: string;
  reference_value: number | null;
  anomaly: number | null;
  reference_start: number;
  reference_end: number;
  reference_sample_count: number;
  reference_standard_deviation: number | null;
  reference_minimum: number | null;
  reference_maximum: number | null;
};

export type TimelineDataQuality = {
  status: 'complete' | 'partial' | 'missing';
  reference_status: 'complete' | 'reduced' | 'insufficient';
  flags: string[];
  reason: string | null;
};

export type HypothesisLinks = {
  status: string;
  supporting_event_ids: string[];
  contradicting_event_ids: string[];
  evidence_not_on_timeline: string[];
};

/** Provenance of one timeline event. Never carries request coordinates (ADR-0004). */
export type TimelineProvenance = {
  source_kind: string;
  description: string;
  case_id: string;
  case_version: number | null;
  source_manifest_id: string | null;
  observation_id: string | null;
  anomaly_id: string | null;
  hypothesis_id: string | null;
  field_id: string | null;
  field_label: string | null;
  provider: string | null;
  dataset: string | null;
  dataset_version: string | null;
  source_uri: string | null;
  retrieved_at: string | null;
  checksum_sha256: string | null;
  processing_version: string | null;
  spatial_resolution: Resolution | null;
  temporal_resolution: Resolution | null;
};

export type TimelineEvent = {
  id: string;
  kind: TimelineKind;
  event_type: TimelineEventType;
  start: string | null;
  end: string | null;
  title: string;
  description: string;
  overlaps_incident: boolean | null;
  observed?: ObservedValue | null;
  departure?: DepartureView | null;
  data_quality?: TimelineDataQuality | null;
  hypothesis?: HypothesisLinks | null;
  crops?: string[];
  provenance: TimelineProvenance;
  limitations: string[];
};

export type TimelineLayer = { kind: TimelineKind; description: string; event_count: number };

/** GET /api/v1/cases/{id}/timeline */
export type Timeline = {
  case_id: string;
  case_version: number;
  generated_at: string;
  incident_start: string;
  incident_end: string | null;
  layers: TimelineLayer[];
  events: TimelineEvent[];
  severity_rule: Record<string, unknown>;
  limitations: string[];
};

export type EvidenceRef = {
  id: string;
  evidence_type: 'ANOMALY' | 'OBSERVATION' | 'EVIDENCE_CLAIM' | 'LOCAL_ANSWER';
  kind: string;
  label: string;
  start?: string | null;
  end?: string | null;
  active: boolean;
};

export type VerificationQuestionView = { question: string; why_it_matters: string };

/** `HypothesisView`: shared `Hypothesis` plus case-API fields. No probability or score field exists. */
export type HypothesisView = {
  id: string;
  case_id: string;
  statement: string;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  missing_evidence: string[];
  limitations: string[];
  status: EvaluationStatus | 'SUPPORTED' | 'CHALLENGED' | 'REJECTED';
  title: string | null;
  origin: 'USER' | 'TEMPLATE';
  template_code: string | null;
  verification_questions: VerificationQuestionView[];
  evaluation_note: string | null;
  evaluated_by: UserSummary | null;
  evaluated_at: string | null;
  version: number;
  created_by: UserSummary | null;
  created_at: string;
  updated_at: string;
  evidence: EvidenceRef[];
};

export type HypothesisList = { items: HypothesisView[]; limitations: string[] };

export type HypothesisTemplateView = {
  code: string;
  source_kind: 'HYPOTHESIS';
  title: string;
  statement: string;
  related_variables: string[];
  missing_evidence: string[];
  verification_questions: VerificationQuestionView[];
  limitations: string[];
};

export type HypothesisTemplateCatalog = { items: HypothesisTemplateView[]; limitations: string[] };

/** POST /api/v1/cases/{id}/hypotheses. New hypotheses are always OPEN. */
export type HypothesisCreate = {
  title?: string | null;
  statement: string;
  supporting_evidence_ids?: string[];
  contradicting_evidence_ids?: string[];
  missing_evidence?: string[];
  limitations?: string[];
  verification_questions?: { question: string; why_it_matters: string }[];
};

/** POST /api/v1/cases/{id}/hypotheses/templates */
export type HypothesisTemplateRequest = { codes?: string[] | null };

/** POST /api/v1/cases/{id}/hypotheses/{hid}/status. A note is required for every status but OPEN. */
export type HypothesisStatusChange = { version: number; status: EvaluationStatus; note?: string | null };

/* ── Collaboration, /api/v1/cases/{id}/{invitations,comments,activity,share-links}, /api/v1/invitations,
 * /api/v1/shared/{token} (ABB-25) ──────────────────────────────────────────────────────────────
 * Transcribed from backend/agroblackbox/api/collaboration_dto.py (docs/architecture/COLLABORATION.md).
 * Every free-text field here (comment bodies, invitation notes, share labels) is plain text written by
 * people: render it as a text node, never as HTML or Markdown. */
export type InvitationStatus = 'PENDING' | 'ACCEPTED' | 'DECLINED' | 'REVOKED' | 'EXPIRED';
/** POST /cases/{id}/invitations (OWNER). expires_in_days 1–30, default 14; note ≤ 500 characters. */
export type InvitationCreate = { email: string; role: GrantableRole; note?: string | null; expires_in_days?: number };
export type InvitationView = {
  id: string;
  case_id: string;
  email: string;
  role: GrantableRole;
  note: string | null;
  status: InvitationStatus;
  invited_by: UserSummary | null;
  created_at: string;
  expires_at: string;
  responded_at: string | null;
  revoked_at: string | null;
};
export type InvitationList = { items: InvitationView[] };
/** GET /api/v1/invitations: pending invitations addressed to the signed-in account's e-mail. */
export type ReceivedInvitationView = {
  id: string;
  case: { id: string; title: string };
  role: GrantableRole;
  note: string | null;
  invited_by: UserSummary | null;
  created_at: string;
  expires_at: string;
};
export type ReceivedInvitationList = { items: ReceivedInvitationView[] };
export type InvitationDecision = { invitation_id: string; case_id: string; status: 'ACCEPTED' | 'DECLINED'; role: Role | null };

export type CommentTargetKind =
  | 'CASE' | 'FIELD' | 'OBSERVATION' | 'ANOMALY' | 'HYPOTHESIS' | 'CLAIM' | 'CONCLUSION' | 'GRAPH_EDGE' | 'TIMELINE_EVENT';
/** A reply (parent_id) inherits its parent's target: send neither target_kind nor target_id with it. */
export type CommentCreate =
  | { body: string; target_kind?: CommentTargetKind; target_id?: string | null }
  | { body: string; parent_id: string };
export type CommentEdit = { version: number; body: string };
export type CommentView = {
  id: string;
  case_id: string;
  target: { kind: CommentTargetKind; id: string | null };
  parent_id: string | null;
  author: UserSummary | null;
  /** Plain text; null once deleted. */
  body: string | null;
  body_format: 'text/plain';
  created_at: string;
  edited_at: string | null;
  version: number;
  revision_count: number;
  reply_count: number;
  deleted: boolean;
  deleted_at: string | null;
  deleted_by: UserSummary | null;
  can_edit: boolean;
  can_delete: boolean;
};
export type CommentList = { items: CommentView[]; total: number; limit: number; offset: number };
export type CommentRevisionView = { revision: number; body: string; body_format: 'text/plain'; replaced_at: string; edited_by: UserSummary | null };

export type ActivitySource = 'CASE_HISTORY' | 'CLAIM_EVENT' | 'DISAGREEMENT_REVIEW' | 'COMMENT';
export type ActivityCategory = 'CASE' | 'WORKFLOW' | 'PERMISSION' | 'INVITATION' | 'SHARING' | 'EVIDENCE' | 'REVIEW' | 'COMMENT';
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type ActivityEntry = {
  id: string;
  source: ActivitySource;
  kind: string;
  category: ActivityCategory;
  actor: UserSummary | null;
  created_at: string;
  target: { kind: string; id: string | null } | null;
  note: string | null;
  /** What the source recorded with the action; null when it recorded none. */
  evidence: Record<string, JsonValue> | null;
  /** Before/after values from the case history; coordinates "REDACTED" for reviewers/viewers. */
  changes: Record<string, JsonValue> | null;
};
export type ActivityPage = {
  items: ActivityEntry[];
  total: number;
  limit: number;
  offset: number;
  order: 'asc' | 'desc';
  sources: ActivitySource[];
};

export type ShareLocationDetail = 'NONE' | 'REGION' | 'APPROXIMATE';
/** Every key is required: consent covers exactly what is listed, nothing is implied. */
export type ShareSections = {
  incident_notes: boolean;
  field_labels: boolean;
  location_detail: ShareLocationDetail;
  hypotheses: boolean;
  evidence_claims: boolean;
  conclusions: boolean;
  member_names: boolean;
  comments: boolean;
};
export type ShareLinkCreate = { consent: true; sections: ShareSections; label?: string | null; expires_in_days?: number };
export type ShareStatus = 'ACTIVE' | 'EXPIRED' | 'REVOKED';
export type ShareLinkView = {
  id: string;
  case_id: string;
  label: string | null;
  sections: ShareSections;
  consent_statement: string;
  status: ShareStatus;
  created_by: UserSummary | null;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
};
/** Only the create response carries the token; the server keeps its SHA-256 digest only. */
export type ShareLinkCreated = ShareLinkView & { token: string; path: string };
export type ShareLinkList = { items: ShareLinkView[] };

export type SharedField = {
  label: string;
  region_label: string | null;
  location_precision: 'APPROXIMATE' | 'REGION_ONLY' | 'NONE';
  latitude: number | null;
  longitude: number | null;
  rounding_deg: number | null;
};
export type SharedHypothesis = {
  title: string | null;
  statement: string;
  status: string;
  evaluation_note: string | null;
  supporting_evidence_count: number;
  contradicting_evidence_count: number;
  missing_evidence: string[];
  limitations: string[];
};
export type SharedClaim = {
  claim_text: string;
  review_status: string;
  source_kind: string;
  study_design: string;
  paper: { title: string; year: number | null; doi: string | null };
  limitations: string[];
};
export type SharedConclusion = { title: string | null; statement: string; review_status: string; limitations: string[] };
export type SharedComment = {
  ref: string;
  reply_to: string | null;
  author: string;
  target_kind: CommentTargetKind;
  body: string;
  body_format: 'text/plain';
  created_at: string;
  edited: boolean;
};
/** GET /api/v1/shared/{token}: no account; never exact coordinates, e-mails, user ids or the case id. */
export type SharedCaseView = {
  kind: 'CROPSTORY_SHARED_CASE';
  generated_at: string;
  link_expires_at: string;
  sections: ShareSections;
  case: {
    title: string;
    status: string;
    incident_start: string;
    incident_end: string | null;
    crop_history: string[];
    incident_notes: string | null;
    case_version: number;
    updated_at: string;
  };
  fields: SharedField[];
  hypotheses: SharedHypothesis[] | null;
  evidence_claims: SharedClaim[] | null;
  conclusions: SharedConclusion[] | null;
  comments: SharedComment[] | null;
  limitations: string[];
};

/* ── Case evidence: claims, disagreements, applicability, graph and trace (ABB-14/15/16, ABB-23 UI) ──
 * Transcribed from backend/agroblackbox/api/evidence_dto.py, comparability_dto.py, graph_dto.py and
 * comparability.py. A claim is reviewed literature only when `is_reviewed` (ACCEPTED); everything else
 * is shown as not reviewed. DOIs are only ever the backend's registered https://doi.org/ URL. */
/** schemas.SourceKind (shared 1.0 contract). */
export type SharedSourceKind = 'OBSERVED' | 'FARMER_REPORTED' | 'LITERATURE_METADATA' | 'LITERATURE_REVIEWED' | 'HYPOTHESIS' | 'MODEL_SCENARIO' | 'ILLUSTRATIVE';
export type DoiStatus = 'VERIFIED_CROSSREF' | 'METADATA_MISMATCH' | 'NOT_FOUND_IN_CROSSREF' | 'VERIFICATION_UNAVAILABLE' | 'MALFORMED_DOI' | 'NO_DOI';
export type StudyDesign =
  | 'META_ANALYSIS' | 'SYSTEMATIC_REVIEW' | 'FIELD_EXPERIMENT' | 'CONTROLLED_EXPERIMENT' | 'OBSERVATIONAL_STUDY'
  | 'MODELLING_STUDY' | 'NARRATIVE_REVIEW' | 'OTHER' | 'UNKNOWN';
export type EvidenceBasis = 'METADATA_ONLY' | 'ABSTRACT' | 'FULL_TEXT';
export type AccessBasis = 'NONE' | 'PUBLIC_ABSTRACT' | 'OPEN_ACCESS_LICENSE' | 'PUBLISHER_FREE_TO_READ' | 'INSTITUTIONAL_SUBSCRIPTION' | 'AUTHOR_PROVIDED_COPY';
export type ClaimReviewStatus = 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'CHANGES_REQUESTED';
export type EffectDirection = 'INCREASE' | 'DECREASE' | 'NO_CLEAR_EFFECT' | 'MIXED' | 'NOT_STATED';
export type KoppenClass =
  | 'Af' | 'Am' | 'Aw' | 'As' | 'BWh' | 'BWk' | 'BSh' | 'BSk' | 'Csa' | 'Csb' | 'Csc' | 'Cwa' | 'Cwb' | 'Cwc'
  | 'Cfa' | 'Cfb' | 'Cfc' | 'Dsa' | 'Dsb' | 'Dsc' | 'Dsd' | 'Dwa' | 'Dwb' | 'Dwc' | 'Dwd' | 'Dfa' | 'Dfb' | 'Dfc'
  | 'Dfd' | 'ET' | 'EF';

/** POST /api/v1/evidence/papers: exactly one identifier; the server fetches and verifies the metadata. */
export type PaperRegistration = { doi: string } | { openalex_id: string };
export type PaperView = {
  schema_version: '1.0';
  id: string;
  source_kind: 'LITERATURE_METADATA';
  evidence_status: 'BIBLIOGRAPHIC_MATCH_ONLY';
  title: string;
  year: number | null;
  doi: string | null;
  doi_id: string | null;
  doi_status: DoiStatus;
  openalex_id: string | null;
  authors: { name: string; orcid: string | null }[];
  venue: string | null;
  publication_type: string | null;
  licenses: { value: string; reported_by: 'OpenAlex' | 'Crossref'; content_version: string | null }[];
  landing_page_url: string | null;
  is_open_access: boolean | null;
  metadata_discrepancies: string[];
  retrievals: { source: 'OpenAlex' | 'Crossref'; endpoint: string; record_id: string | null; retrieved_at: string; http_status: number | null; outcome: string }[];
  processing_version: string;
  source_manifest_id: string | null;
  limitations: string[];
  source: string;
  caveat: string;
};
export type PaperSummary = {
  id: string;
  title: string;
  year: number | null;
  doi: string | null;
  doi_id: string | null;
  doi_status: DoiStatus;
  openalex_id: string | null;
  is_open_access: boolean | null;
  licenses: string[];
  caveat: string;
};
export type ClaimContextView = {
  population: string | null;
  crops: string[];
  soils: string[];
  region: string | null;
  climate: string | null;
  management: string | null;
  water_regime: string;
  soil_texture_classes: string[];
  soil_ph_min: number | null;
  soil_ph_max: number | null;
  geographic_scope: string;
  countries: string[];
  climate_classes: string[];
};
export type ClaimView = {
  schema_version: '1.0';
  id: string;
  paper_id: string;
  /** Declared as the shared SourceKind in OpenAPI; a backend validator only ever sends LITERATURE_METADATA or LITERATURE_REVIEWED here. The UI decides on `is_reviewed`. */
  source_kind: SharedSourceKind;
  claim_text: string;
  study_context: string;
  review_status: ClaimReviewStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  limitations: string[];
  case_id: string;
  version: number;
  is_reviewed: boolean;
  reviewer: UserSummary | null;
  created_by: UserSummary | null;
  created_at: string;
  updated_at: string;
  paper: PaperSummary;
  study_design: StudyDesign;
  context: ClaimContextView;
  reported_outcome: {
    outcome: string | null; comparison: string | null; effect_as_stated: string | null; units_as_stated: string | null;
    uncertainty_as_stated: string | null; sample_as_stated: string | null;
  };
  source_locator: { page: string | null; section: string | null; figure_or_table: string | null };
  quoted_fragment: string | null;
  evidence_basis: EvidenceBasis;
  access_basis: AccessBasis;
  content_license: string | null;
  origin: 'MANUAL' | 'PILOT_SEED_UNVERIFIED';
  origin_ref: string | null;
  intervention: string | null;
  comparator: string | null;
  outcome_variable: string | null;
  effect_direction: EffectDirection;
  warnings: string[];
  can_edit: boolean;
  can_review: boolean;
};
export type ClaimList = { items: ClaimView[]; reviewed_count: number; unreviewed_count: number; limitations: string[] };
/** POST /cases/{id}/claims. A claim added from a search is never reviewed; ABSTRACT needs PUBLIC_ABSTRACT access or better. */
export type ClaimCreate = {
  paper_id: string;
  claim_text: string;
  study_context: string;
  evidence_basis: EvidenceBasis;
  access_basis?: AccessBasis;
  limitations: string[];
  study_design?: StudyDesign;
};
export type ClaimEventView = {
  id: string;
  claim_id: string;
  claim_version: number;
  action: 'CREATED' | 'UPDATED' | 'REVIEWED';
  actor: UserSummary | null;
  created_at: string;
  from_status: ClaimReviewStatus | null;
  to_status: ClaimReviewStatus;
  note: string | null;
  source_consulted: { basis: EvidenceBasis; access_basis: AccessBasis; license: string | null; locator: string | null; consulted_url: string | null } | null;
  paper_snapshot: Record<string, string | number | boolean | null>;
  changes: Record<string, JsonValue>;
};

export type MatchStatus = 'MATCH' | 'PARTIAL' | 'MISMATCH' | 'UNKNOWN';
export type ComparisonDimension = 'CROPS' | 'WATER_REGIME' | 'SOIL_TEXTURE' | 'SOIL_PH' | 'REGION' | 'CLIMATE' | 'COMPARATOR' | 'STUDY_DESIGN';
export type DisagreementStatus = 'CANDIDATE' | 'CONFIRMED_CONTRADICTION' | 'NOT_COMPARABLE' | 'INCONCLUSIVE';
export type DisagreementClaimRef = {
  claim_id: string;
  claim_version: number;
  claim_text: string;
  intervention: string | null;
  comparator: string | null;
  outcome_variable: string | null;
  effect_direction: EffectDirection;
  study_design: StudyDesign;
  review_status: ClaimReviewStatus;
  is_reviewed: boolean;
  /** Declared as the shared SourceKind in OpenAPI; a backend validator only ever sends LITERATURE_METADATA or LITERATURE_REVIEWED here. The UI decides on `is_reviewed`. */
  source_kind: SharedSourceKind;
  paper: PaperSummary;
};
export type DisagreementReviewView = {
  id: string;
  decision: Exclude<DisagreementStatus, 'CANDIDATE'>;
  note: string;
  reviewer: UserSummary | null;
  reviewed_at: string;
  claim_a_version: number;
  claim_b_version: number;
  applies_to_current_versions: boolean;
};
export type DisagreementView = {
  schema_version: '1.0';
  id: string;
  case_id: string;
  kind: 'OPPOSITE_DIRECTION' | 'EFFECT_VS_NO_CLEAR_EFFECT';
  status: DisagreementStatus;
  matched_on: { intervention?: string; outcome_variable?: string };
  claim_a: DisagreementClaimRef;
  claim_b: DisagreementClaimRef;
  both_claims_reviewed: boolean;
  comparability_notes: { dimension: ComparisonDimension; status: MatchStatus; claim_a_value: string | null; claim_b_value: string | null; reason: string }[];
  current_review: DisagreementReviewView | null;
  reviews: DisagreementReviewView[];
  warnings: string[];
  can_review: boolean;
};
export type DisagreementList = {
  schema_version: '1.0';
  case_id: string;
  items: DisagreementView[];
  claims_not_compared: { claim_id: string; reasons: string[] }[];
  method_version: string;
  limitations: string[];
};
/** POST /cases/{id}/claims/{claim_id}/applicability. Nothing stored; coordinates are never used. */
export type ApplicabilityRequest = { country_code?: string | null; koppen_climate?: KoppenClass | null };
export type TransferNote = {
  dimension: ComparisonDimension;
  status: MatchStatus;
  study_value: string | null;
  case_value: string | null;
  case_value_source: string | null;
  reason: string;
};
export type ApplicabilityReport = {
  schema_version: '1.0';
  case_id: string;
  claim_id: string;
  claim_version: number;
  claim_review_status: ClaimReviewStatus;
  is_reviewed: boolean;
  study_design: StudyDesign;
  paper: PaperSummary;
  dimensions: TransferNote[];
  transfer_status: 'DIFFERENCES_FOUND' | 'INSUFFICIENT_DATA' | 'NO_DIFFERENCES_FOUND_IN_COMPARED_DIMENSIONS';
  differing_dimensions: ComparisonDimension[];
  unknown_dimensions: ComparisonDimension[];
  notes: string[];
  stored: false;
  method_version: string;
  limitations: string[];
};

export type GraphNodeType =
  | 'SOURCE_MANIFEST' | 'OBSERVATION' | 'ANOMALY' | 'FARMER_REPORT' | 'FIELD' | 'PAPER' | 'EVIDENCE_CLAIM'
  | 'HYPOTHESIS' | 'CONCLUSION' | 'MISSING_DATA';
export type GraphNodeKind = 'OBSERVED' | 'FARMER_REPORTED' | 'LITERATURE_METADATA' | 'LITERATURE_REVIEWED' | 'HYPOTHESIS' | 'CONCLUSION' | 'MISSING_DATA';
export type GraphRelation = 'SUPPORTS' | 'CONTRADICTS' | 'LIMITS' | 'ADDRESSES' | 'DERIVED_FROM' | 'CITES';
export type GraphEdgeOrigin = 'STRUCTURAL' | 'HYPOTHESIS_LINK' | 'DISAGREEMENT_REVIEW' | 'MANUAL';
export type GraphEdgeReviewStatus = 'NOT_APPLICABLE' | 'PENDING' | 'EVALUATED' | 'ACCEPTED' | 'CHANGES_REQUESTED' | 'REJECTED';
/** Never carries request parameters or coordinates. `doi` is the registered https://doi.org/ URL, never inferred. */
export type GraphProvenance = {
  source_kind: string;
  description: string;
  case_id: string;
  case_version: number | null;
  source_manifest_id: string | null;
  observation_id: string | null;
  anomaly_id: string | null;
  claim_id: string | null;
  paper_id: string | null;
  hypothesis_id: string | null;
  conclusion_id: string | null;
  field_id: string | null;
  field_label: string | null;
  region_label: string | null;
  provider: string | null;
  dataset: string | null;
  dataset_version: string | null;
  source_uri: string | null;
  retrieved_at: string | null;
  checksum_sha256: string | null;
  content_sha256: string | null;
  processing_version: string | null;
  revision: number | null;
  spatial_resolution: Resolution | null;
  temporal_resolution: Resolution | null;
  doi: string | null;
  doi_id: string | null;
  doi_status: string | null;
  openalex_id: string | null;
  origin: string | null;
  created_by: UserSummary | null;
  created_at: string | null;
  reviewed_by: UserSummary | null;
  reviewed_at: string | null;
  evaluated_by: UserSummary | null;
  evaluated_at: string | null;
};
export type GraphNode = {
  id: string;
  node_type: GraphNodeType;
  kind: GraphNodeKind;
  label: string;
  entity_id: string | null;
  status: string | null;
  active: boolean;
  original_evidence: boolean;
  linkable: boolean;
  start: string | null;
  end: string | null;
  provenance: GraphProvenance;
  limitations: string[];
  details: Record<string, JsonValue>;
};
export type GraphEdge = {
  id: string;
  from: string;
  to: string;
  relation: GraphRelation;
  origin: GraphEdgeOrigin;
  note: string | null;
  review_status: GraphEdgeReviewStatus;
  record_id: string | null;
  conclusion_id: string | null;
  version: number | null;
  author: UserSummary | null;
  created_at: string | null;
  reviewed_by: UserSummary | null;
  reviewed_at: string | null;
  review_note: string | null;
  can_edit: boolean;
  can_review: boolean;
};
export type EvidenceGraph = {
  case_id: string;
  case_version: number;
  generated_at: string;
  include_superseded: boolean;
  nodes: GraphNode[];
  edges: GraphEdge[];
  counts: {
    total_nodes: number; total_edges: number; nodes_by_kind: Record<string, number>; nodes_by_type: Record<string, number>;
    edges_by_relation: Record<string, number>; edges_by_origin: Record<string, number>;
  };
  relations: { relation: GraphRelation; description: string; stored: boolean }[];
  orphan_references: { referenced_by: string; missing_node: string; relation: string; origin: string }[];
  limitations: string[];
};
export type EvidenceTrace = {
  case_id: string;
  generated_at: string;
  root: GraphNode;
  complete: boolean;
  original_evidence: string[];
  dead_ends: string[];
  paths: { steps: { node_id: string; edge_id: string | null; relation: GraphRelation | null }[]; ends_at_original_evidence: boolean }[];
  truncated: boolean;
  nodes: GraphNode[];
  edges: GraphEdge[];
  limiting_edges: GraphEdge[];
  contradiction_edges: GraphEdge[];
  summary: {
    reaches_observed_data: boolean; reaches_farmer_report: boolean; reaches_literature: boolean;
    reviewed_claim_ids: string[]; unreviewed_claim_ids: string[]; unevaluated_hypothesis_ids: string[];
    superseded_node_ids: string[]; missing_data_node_ids: string[];
  };
  review_blockers: string[];
  limitations: string[];
};

/* ── GET /api/vegetation/hls (ABB-12): NASA HLS v2.0 NDVI with Fmask QA at a point ── */
export type HlsStatus = 'VALID' | 'OBSCURED' | 'NO_DATA' | 'NOT_READ';
export type HlsPixelCounts = {
  clear: number; cloud: number; cloud_shadow: number; adjacent_cloud: number; cirrus: number; snow_ice: number;
  water: number; high_aerosol: number; fill: number; invalid_reflectance: number;
};
export type HlsObservation = {
  date: string;
  acquired_at: string;
  product: 'HLSL30' | 'HLSS30';
  sensor: string;
  granule_id: string;
  mgrs_tile: string;
  scene_cloud_cover: number | null;
  status: HlsStatus;
  reason: string | null;
  window_pixels: number;
  pixels: HlsPixelCounts;
  ndvi: number | null;
  ndvi_min: number | null;
  ndvi_max: number | null;
  red_reflectance: number | null;
  nir_reflectance: number | null;
  red_band: string;
  nir_band: string;
  epsg: number | null;
  pixel_size_m: number | null;
  data_sha256: string | null;
};
export type HlsGap = { start: string; end: string; days: number };
export type VegetationResponse = {
  kind: 'observation';
  source_kind: 'OBSERVED';
  dataset: string;
  source_url: string;
  request_params: Record<string, string | number>;
  start: string;
  end: string;
  retrieved_at: string;
  spatial_resolution: Resolution;
  temporal_resolution: Resolution;
  provenance: SourceManifest;
  observations: HlsObservation[];
  gaps: HlsGap[];
  summary: { acquisitions: number; valid: number; obscured: number; no_data: number; not_read: number; granules_found: number; gap_days: number; longest_gap_days: number };
  method: {
    id: string; window: string; clear_rule: string; ndvi_formula: string; bands: Record<string, Record<string, string>>;
    reflectance_scale: number; valid_reflectance_range: number[]; acquisition_rule: string; processing_version: string;
  };
  cache: { search_from_cache: boolean; scenes_from_cache: number; upstream_requests: number };
  limitations: string[];
  disclaimer: string;
};

export type ClaimReviewRequest = {
  version: number;
  decision: Exclude<ClaimReviewStatus, 'PENDING'>;
  note: string;
  source_consulted: { basis: EvidenceBasis; access_basis: AccessBasis; license?: string | null; locator?: string | null; consulted_url?: string | null };
};
export type DisagreementReviewRequest = {
  decision: Exclude<DisagreementStatus, 'CANDIDATE'>; note: string; claim_a_version: number; claim_b_version: number;
};
export type GraphReviewRequest = { version: number; decision: 'ACCEPTED' | 'REJECTED' | 'CHANGES_REQUESTED'; note: string };
export type GraphCitation = { node_id: string; note: string };
export type ConclusionCreate = {
  title?: string | null; statement: string; limitations: string[]; supporting: GraphCitation[];
  contradicting?: GraphCitation[]; limited_by?: GraphCitation[]; addresses_hypothesis_ids?: string[];
};
export type ConclusionView = {
  id: string; case_id: string; node_id: string; source_kind: 'CONCLUSION'; title: string | null; statement: string;
  limitations: string[]; review_status: ClaimReviewStatus; review_note: string | null; reviewer: UserSummary | null;
  reviewed_at: string | null; created_by: UserSummary | null; created_at: string; updated_at: string; version: number;
  citations: GraphEdge[]; trace_complete: boolean; review_blockers: string[]; warnings: string[]; can_edit: boolean; can_review: boolean;
};
export type ConclusionList = { items: ConclusionView[]; limitations: string[] };
export type EdgeCreate = { from: string; to: string; relation: 'SUPPORTS' | 'CONTRADICTS' | 'LIMITS' | 'ADDRESSES'; note: string };
export type EdgeList = { items: GraphEdge[]; limitations: string[] };

/* Uncertainty Hunter (ABB-19). Values and ordering come from the backend; the UI never scores them. */
export type QuestionStatus = 'OPEN' | 'ANSWERED' | 'REVIEWED' | 'DISMISSED';
export type QuestionResolution = { status: QuestionStatus; current_answer_id: string | null; updated_at: string | null; note: string | null };
export type UncertaintyTarget = { target_type: string; target_id: string; label: string; current_state: string; how: string };
export type UncertaintyQuestion = {
  id: string; kind: 'LOCAL_INFORMATION' | 'ANALYSIS_TASK'; category: string; question: string; why_it_matters: string;
  origin: 'CATALOGUE' | 'HYPOTHESIS_TEXT'; measurement: string; units: string[]; answer_route: string | null; answerable_here: boolean;
  addresses: string[]; addresses_gap_ids: string[]; would_change: UncertaintyTarget[]; would_change_statement: string;
  open_hypotheses_linked: number; other_items_linked: number; priority_basis: string; resolution: QuestionResolution;
  position: number | null; tied_with: string[]; currently_generated: boolean;
};
export type UncertaintyGap = {
  id: string; key: string; kind: 'MISSING_DATA'; category: string; cause: string; title: string; description: string; answerable_locally: boolean;
  sources: { entity_type: string; entity_id: string | null; field: string | null; label: string; stored: boolean }[];
  question_ids: string[]; would_change: UncertaintyTarget[]; limitations: string[];
};
export type UncertaintyReport = {
  case_id: string; case_version: number; generated_at: string; method_version: string; stored: false;
  inputs: { farm_profile_supplied: boolean; country_code: string | null; koppen_climate: string | null; rotation_status: string | null };
  summary: { gaps: number; gaps_by_cause: Record<string, number>; questions: number; open_questions: number; gaps_not_answerable_locally: number };
  gaps: UncertaintyGap[]; questions: UncertaintyQuestion[];
  prioritisation: { rule_id: string; status: 'ORDERED_BY_LINK_COUNTS' | 'NO_OPEN_QUESTIONS' | 'NO_BASIS_TO_PRIORITISE'; statement: string; steps: string[]; is_value_of_information: false };
  limitations: string[];
};
export type AnswerOrigin = 'FARMER_REPORTED' | 'LOCAL_MEASUREMENT' | 'FIELD_RECORD' | 'ADVISOR_REPORT';
export type AnswerCreate = {
  value_text?: string | null; value_number?: number | null; unit?: string | null; observed_from?: string | null; observed_to?: string | null;
  origin: AnswerOrigin; method?: string | null; source_reference?: string | null; note?: string | null; replaces_answer_id?: string | null;
};
export type UncertaintyAnswer = {
  id: string; case_id: string; question_id: string; question: string; kind: 'FARMER_REPORTED'; source_kind: 'FARMER_REPORTED';
  value_text: string | null; value_number: number | null; unit: string | null; observed_from: string | null; observed_to: string | null;
  origin: AnswerOrigin; method: string | null; source_reference: string | null; note: string | null;
  status: 'ANSWERED' | 'REVIEWED' | 'REJECTED' | 'SUPERSEDED'; is_reviewed: boolean; answered_by: UserSummary | null;
  answered_at: string; reviewed_by: UserSummary | null; reviewed_at: string | null; review_note: string | null;
  superseded_by_id: string | null; superseded_at: string | null; version: number; can_review: boolean; limitations: string[];
};
export type AnswerList = { items: UncertaintyAnswer[]; limitations: string[] };
export type QuestionEvent = { id: string; question_id: string; action: string; answer_id: string | null; actor: UserSummary | null; created_at: string; from_status: string; to_status: string; note: string | null; changes: Record<string, JsonValue> };
export type QuestionHistory = { case_id: string; question_id: string; question: string | null; resolution: QuestionResolution; events: QuestionEvent[]; answers: UncertaintyAnswer[] };
