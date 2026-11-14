/**
 * Editable row shapes for the rotation comparator form (ABB-24) and the pure functions that
 * turn them into the backend's `FarmProfile` (ABB-11) / request contracts, plus client-side
 * structural checks that mirror the Pydantic constraints the backend would otherwise reject
 * with 422 (docs/architecture/API_CONTRACTS.md). Agronomic consistency (e.g. a rotation with
 * fewer than two seasons, or no local calendar) is deliberately NOT re-implemented here: the
 * backend already reports those as `profile_issues` and the UI renders them from the response,
 * so the farmer always sees the backend's own reasoning rather than a client-side guess.
 */
import type {
  CalendarWindow, CropSeason, FarmerConstraints, FarmerPriority, FarmProfile, MarketAccess, PriorityCriterion,
  SeasonRole, WaterRegime,
} from '../../api/types';

let seq = 0;
/** Stable row ids for React keys and error targeting. Not sent to the backend. */
export function newRowId(prefix: string): string {
  seq += 1;
  return `${prefix}-${seq}-${Math.random().toString(36).slice(2, 8)}`;
}

export type CropRow = {
  id: string;
  cropCode: string | null;
  cropLabel: string;
  role: SeasonRole;
  seasonYear: string;
  sowingDate: string;
  harvestDate: string;
  waterRegime: WaterRegime;
};

export type CalendarRow = {
  id: string;
  cropCode: string | null;
  cropLabel: string;
  sowingStartMonth: string;
  sowingEndMonth: string;
  harvestStartMonth: string;
  harvestEndMonth: string;
};

export type MarketRow = { id: string; cropLabel: string; status: MarketAccess['status'] };

export type ConstraintsState = {
  waterRegime: WaterRegime;
  irrigationValue: string;
  irrigationUnit: 'mm/season' | 'mm/year' | 'm3/ha/season' | 'm3/ha/year';
  excludedCrops: string[];
  availableEquipment: string[];
  equipmentLimitations: string;
  market: MarketRow[];
};

export const ALL_PRIORITY_CRITERIA: PriorityCriterion[] = [
  'SOIL_COVER', 'CROP_DIVERSITY', 'RISK_REDUCTION', 'WATER_USE', 'INCOME_STABILITY', 'WORKLOAD', 'INPUT_COSTS', 'OTHER',
];

export function emptyCropRow(): CropRow {
  return { id: newRowId('crop'), cropCode: null, cropLabel: '', role: 'MAIN_CROP', seasonYear: '', sowingDate: '', harvestDate: '', waterRegime: 'UNKNOWN' };
}

export function emptyCalendarRow(): CalendarRow {
  return { id: newRowId('cal'), cropCode: null, cropLabel: '', sowingStartMonth: '', sowingEndMonth: '', harvestStartMonth: '', harvestEndMonth: '' };
}

export function emptyConstraints(): ConstraintsState {
  return {
    waterRegime: 'UNKNOWN', irrigationValue: '', irrigationUnit: 'mm/season', excludedCrops: [], availableEquipment: [],
    equipmentLimitations: '', market: [],
  };
}

export type ProfileFormState = {
  cropHistory: CropRow[];
  calendar: CalendarRow[];
  constraints: ConstraintsState;
  priorities: FarmerPriority[];
  horizonYears: string;
};

export function emptyProfileForm(): ProfileFormState {
  return { cropHistory: [emptyCropRow()], calendar: [emptyCalendarRow()], constraints: emptyConstraints(), priorities: [], horizonYears: '4' };
}

export type FieldErrors = Record<string, string>;

const YEAR_MIN = 1950;
const YEAR_MAX = 2100;

function isIsoDate(s: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s));
}

/** Structural checks only (what the backend would reject as 422), never agronomic judgement. */
export function validateProfileForm(state: ProfileFormState): FieldErrors {
  const errors: FieldErrors = {};

  const mainCrops = state.cropHistory.filter((r) => r.role !== 'FALLOW' && r.cropLabel.trim());
  if (mainCrops.length === 0 && state.cropHistory.some((r) => r.cropLabel.trim() || r.seasonYear.trim())) {
    // rows exist but none usable yet; per-row errors below will already explain why
  }
  state.cropHistory.forEach((row) => {
    const label = row.cropLabel.trim();
    const hasAnyInput = label || row.seasonYear.trim() || row.sowingDate || row.harvestDate;
    if (!hasAnyInput) return;
    if (row.role !== 'FALLOW' && !label) errors[`crop.${row.id}.cropLabel`] = 'required';
    const year = Number(row.seasonYear);
    if (!row.seasonYear.trim() || !Number.isInteger(year) || year < YEAR_MIN || year > YEAR_MAX) {
      errors[`crop.${row.id}.seasonYear`] = 'range';
    }
    if (row.sowingDate && !isIsoDate(row.sowingDate)) errors[`crop.${row.id}.sowingDate`] = 'invalid';
    if (row.harvestDate && !isIsoDate(row.harvestDate)) errors[`crop.${row.id}.harvestDate`] = 'invalid';
    if (row.sowingDate && row.harvestDate && isIsoDate(row.sowingDate) && isIsoDate(row.harvestDate)) {
      if (Date.parse(row.harvestDate) <= Date.parse(row.sowingDate)) errors[`crop.${row.id}.harvestDate`] = 'order';
    }
  });

  state.calendar.forEach((row) => {
    const label = row.cropLabel.trim();
    const hasAnyInput = label || row.sowingStartMonth || row.sowingEndMonth || row.harvestStartMonth || row.harvestEndMonth;
    if (!hasAnyInput) return;
    if (!label) errors[`cal.${row.id}.cropLabel`] = 'required';
    for (const [field, value] of [['sowingStartMonth', row.sowingStartMonth], ['sowingEndMonth', row.sowingEndMonth]] as const) {
      const n = Number(value);
      if (!value.trim() || !Number.isInteger(n) || n < 1 || n > 12) errors[`cal.${row.id}.${field}`] = 'range';
    }
    const hStart = row.harvestStartMonth.trim();
    const hEnd = row.harvestEndMonth.trim();
    if (Boolean(hStart) !== Boolean(hEnd)) {
      errors[`cal.${row.id}.harvestStartMonth`] = 'pair';
      errors[`cal.${row.id}.harvestEndMonth`] = 'pair';
    } else if (hStart && hEnd) {
      for (const [field, value] of [['harvestStartMonth', hStart], ['harvestEndMonth', hEnd]] as const) {
        const n = Number(value);
        if (!Number.isInteger(n) || n < 1 || n > 12) errors[`cal.${row.id}.${field}`] = 'range';
      }
    }
  });

  if (state.constraints.irrigationValue.trim()) {
    const v = Number(state.constraints.irrigationValue);
    if (Number.isNaN(v) || v < 0) errors['constraints.irrigationValue'] = 'range';
  }

  const horizon = Number(state.horizonYears);
  if (!state.horizonYears.trim() || !Number.isInteger(horizon) || horizon < 2 || horizon > 10) {
    errors.horizonYears = 'range';
  }

  return errors;
}

function toCropSeason(row: CropRow): CropSeason | null {
  const label = row.cropLabel.trim();
  if (!label) return null;
  const year = Number(row.seasonYear);
  if (!Number.isInteger(year)) return null;
  return {
    crop_code: row.cropCode,
    crop_label: label,
    role: row.role,
    season_year: year,
    sowing_date: row.sowingDate && isIsoDate(row.sowingDate) ? row.sowingDate : null,
    harvest_date: row.harvestDate && isIsoDate(row.harvestDate) ? row.harvestDate : null,
    water_regime: row.waterRegime,
    origin: 'FARMER_ESTIMATE',
    notes: null,
  };
}

function toCalendarWindow(row: CalendarRow): CalendarWindow | null {
  const label = row.cropLabel.trim();
  const sowStart = Number(row.sowingStartMonth);
  const sowEnd = Number(row.sowingEndMonth);
  if (!label || !Number.isInteger(sowStart) || !Number.isInteger(sowEnd)) return null;
  const harvestStart = row.harvestStartMonth.trim() ? Number(row.harvestStartMonth) : null;
  const harvestEnd = row.harvestEndMonth.trim() ? Number(row.harvestEndMonth) : null;
  return {
    crop_code: row.cropCode,
    crop_label: label,
    sowing_start_month: sowStart,
    sowing_end_month: sowEnd,
    harvest_start_month: harvestStart,
    harvest_end_month: harvestEnd,
    origin: 'FARMER_ESTIMATE',
    notes: null,
  };
}

function toMarketAccess(row: MarketRow): MarketAccess | null {
  const label = row.cropLabel.trim();
  if (!label) return null;
  return { crop_code: null, crop_label: label, status: row.status, notes: null };
}

function toConstraints(c: ConstraintsState): FarmerConstraints {
  const market = c.market.map(toMarketAccess).filter((m): m is MarketAccess => m !== null);
  const value = Number(c.irrigationValue);
  return {
    water_regime: c.waterRegime,
    irrigation_allowance: c.irrigationValue.trim() && !Number.isNaN(value)
      ? { value, unit: c.irrigationUnit, origin: 'FARMER_ESTIMATE', notes: null } : null,
    excluded_crops: c.excludedCrops,
    available_equipment: c.availableEquipment,
    equipment_limitations: c.equipmentLimitations.trim() || null,
    market_access: market,
    labour_notes: null,
    planning_horizon_years: null,
    other_notes: null,
  };
}

/** Builds the `FarmProfile` sent to the backend. Call only after `validateProfileForm` returns no errors. */
export function buildProfile(state: ProfileFormState): FarmProfile {
  const crop_history = state.cropHistory.map(toCropSeason).filter((s): s is CropSeason => s !== null);
  const local_calendar = state.calendar.map(toCalendarWindow).filter((w): w is CalendarWindow => w !== null);
  return {
    schema_version: '1.0',
    soil: [],
    crop_history,
    local_calendar,
    constraints: toConstraints(state.constraints),
    priorities: state.priorities,
  };
}

export function buildHorizonYears(state: ProfileFormState): number {
  return Number(state.horizonYears);
}

/** Ordinal rank helpers: add/remove/move a criterion while keeping ranks 1..n with no gaps or ties. */
export function addPriority(priorities: FarmerPriority[], criterion: PriorityCriterion): FarmerPriority[] {
  if (priorities.some((p) => p.criterion === criterion)) return priorities;
  return [...priorities, { criterion, rank: priorities.length + 1 }];
}

export function removePriority(priorities: FarmerPriority[], criterion: PriorityCriterion): FarmerPriority[] {
  return priorities.filter((p) => p.criterion !== criterion).map((p, i) => ({ ...p, rank: i + 1 }));
}

export function movePriority(priorities: FarmerPriority[], criterion: PriorityCriterion, delta: -1 | 1): FarmerPriority[] {
  const sorted = [...priorities].sort((a, b) => a.rank - b.rank);
  const index = sorted.findIndex((p) => p.criterion === criterion);
  const target = index + delta;
  if (index < 0 || target < 0 || target >= sorted.length) return priorities;
  [sorted[index], sorted[target]] = [sorted[target], sorted[index]];
  return sorted.map((p, i) => ({ ...p, rank: i + 1 }));
}
