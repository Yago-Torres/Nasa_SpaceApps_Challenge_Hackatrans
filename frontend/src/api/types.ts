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
export type EvidenceRef = {
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
  evidence_refs: EvidenceRef[];
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
export type Direction = 'MORE_FIRST' | 'FEWER_FIRST' | 'PASSES_FIRST';

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
  direction: Direction;
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
  direction: Direction;
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
