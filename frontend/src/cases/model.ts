/**
 * Incident case model for the ABB-21 wizard (form state). The server contract is
 * `CaseView` in api/types.ts; `cases/mapping.ts` converts between the two. Privacy helpers
 * here decide what the UI DISPLAYS. Real protection is enforced by the server (ADR-0004):
 * reviewers and viewers never receive precise coordinates unless the owner consented.
 */
import type { CaseStatus, FieldPrivacyTier, LocationPrecision, Role } from '../api/types';

/** Server-side facts about a persisted case. Absent for a new case not yet saved. */
export type ServerMeta = {
  status: CaseStatus;
  myRole: Role;
  ownerName: string;
  archived: boolean;
  /** The parcel the wizard edits (the first field of the case). */
  fieldId: string;
  fieldIds: string[];
  fieldCount: number;
  /** Stored tier of that field, and what the caller received after redaction. */
  privacyTier: FieldPrivacyTier;
  locationPrecision: LocationPrecision;
};

export type PrivacyTier = 'private' | 'rounded' | 'region';
export type Rounding = 0.1 | 0.5 | 1;
export type Viewer = 'owner' | 'guest';

export type CaseLocation = {
  latitude: string;
  longitude: string;
  /** Free-text region shown to others when tier is "region" (e.g. "Ebro valley, Aragón"). */
  regionLabel: string;
  tier: PrivacyTier;
  rounding: Rounding;
  /** Explicit consent to show the exact point to invited reviewers. Default false. */
  consentPrecise: boolean;
};

export type CropYear = { id: string; year: string; crop: string; notes: string };

export type IncidentCase = {
  id: string;
  title: string;
  location: CaseLocation;
  /** All parcels in the case. `location` is kept as the active/first parcel for compatibility. */
  locations: CaseLocation[];
  crops: CropYear[];
  incidentYear: string;
  symptomsStart: string; // YYYY-MM
  symptomsEnd: string; // YYYY-MM
  symptoms: string;
  affectedShare: string; // % of the field, as the farmer estimates it
  constraints: { water: '' | 'irrigated' | 'rainfed' | 'mixed'; soilKnown: boolean; soilNotes: string; priorities: string };
  createdAt: string;
  updatedAt: string;
  version: number;
  server?: ServerMeta;
};

export const MAX_CROP_ROWS = 50;

/** Roles and statuses that may edit (ADR-0004): owners/editors while DRAFT or INVESTIGATING and not archived. */
export function canEdit(c: IncidentCase): boolean {
  if (!c.server) return true;
  const { myRole, status, archived } = c.server;
  return (myRole === 'OWNER' || myRole === 'EDITOR') && (status === 'DRAFT' || status === 'INVESTIGATING') && !archived;
}

export const STEPS = ['location', 'crops', 'incident', 'constraints', 'review'] as const;
export type Step = (typeof STEPS)[number];

export function newId(prefix = 'c'): string {
  const rand = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID().slice(0, 8) : Math.random().toString(36).slice(2, 10);
  return `${prefix}-${rand}`;
}

export function emptyCase(now = new Date()): IncidentCase {
  const iso = now.toISOString();
  return {
    id: newId('local'),
    title: '',
    location: { latitude: '', longitude: '', regionLabel: '', tier: 'rounded', rounding: 0.1, consentPrecise: false },
    locations: [{ latitude: '', longitude: '', regionLabel: '', tier: 'rounded', rounding: 0.1, consentPrecise: false }],
    crops: [{ id: newId('y'), year: '', crop: '', notes: '' }],
    incidentYear: '',
    symptomsStart: '',
    symptomsEnd: '',
    symptoms: '',
    affectedShare: '',
    constraints: { water: '', soilKnown: false, soilNotes: '', priorities: '' },
    createdAt: iso,
    updatedAt: iso,
    version: 0,
  };
}

/** Returns all fields while preserving compatibility with callers that edit `location` directly. */
export function caseLocations(c: IncidentCase): CaseLocation[] {
  const locations = c.locations.length ? [...c.locations] : [c.location];
  if (JSON.stringify(locations[0]) !== JSON.stringify(c.location)) locations[0] = c.location;
  return locations;
}

/* ── Parsing and validation ─────────────────────────────────────── */

export function parseNumber(s: string): number {
  const t = s.trim().replace('−', '-').replace(',', '.');
  return t === '' ? NaN : Number(t);
}

export type FieldError =
  | 'title' | 'latitude' | 'longitude' | 'regionLabel'
  | `crop.${number}.year` | `crop.${number}.crop`
  | 'incidentYear' | 'symptomsStart' | 'symptomsEnd' | 'symptomsOrder' | 'symptomsRange' | 'symptoms' | 'affectedShare';

/** "YYYY-MM" of `now` in UTC. */
export function currentMonth(now = new Date()): string {
  return now.toISOString().slice(0, 7);
}

/** A well-formed month the case API would reject (it accepts incident dates from 1900-01-01 to today). */
export function monthOutOfRange(m: string, now = new Date()): boolean {
  return /^\d{4}-(0[1-9]|1[0-2])$/.test(m) && (m < '1900-01' || m > currentMonth(now));
}

/** Blocking errors for a step. Data is never discarded; the user fixes and continues. */
export function validateStep(c: IncidentCase, step: Step, now = new Date()): FieldError[] {
  const e: FieldError[] = [];
  if (step === 'location') {
    if (!c.title.trim() || c.title.length > 120) e.push('title');
    for (const location of caseLocations(c)) {
      const lat = parseNumber(location.latitude);
      const lon = parseNumber(location.longitude);
      if (!(lat >= -90 && lat <= 90)) e.push('latitude');
      if (!(lon >= -180 && lon <= 180)) e.push('longitude');
      if (location.tier === 'region' && !location.regionLabel.trim()) e.push('regionLabel');
    }
  }
  if (step === 'crops') {
    c.crops.forEach((row, i) => {
      const y = parseNumber(row.year);
      const filled = row.year.trim() || row.crop.trim() || row.notes.trim();
      if (!filled && c.crops.length > 1) return; // empty extra rows are ignored
      if (!(Number.isInteger(y) && y >= 1950 && y <= 2100)) e.push(`crop.${i}.year`);
      if (!row.crop.trim()) e.push(`crop.${i}.crop`);
    });
  }
  if (step === 'incident') {
    const y = parseNumber(c.incidentYear);
    if (!(Number.isInteger(y) && y >= 1981 && y <= new Date().getFullYear())) e.push('incidentYear');
    const month = /^\d{4}-(0[1-9]|1[0-2])$/;
    if (c.symptomsStart && !month.test(c.symptomsStart)) e.push('symptomsStart');
    if (c.symptomsEnd && !month.test(c.symptomsEnd)) e.push('symptomsEnd');
    if (month.test(c.symptomsStart) && month.test(c.symptomsEnd) && c.symptomsEnd < c.symptomsStart) e.push('symptomsOrder');
    if (monthOutOfRange(c.symptomsStart, now) || monthOutOfRange(c.symptomsEnd, now)) e.push('symptomsRange');
    if (!c.symptoms.trim()) e.push('symptoms');
    if (c.affectedShare.trim()) {
      const p = parseNumber(c.affectedShare);
      if (!(p >= 0 && p <= 100)) e.push('affectedShare');
    }
  }
  return e;
}

export type MissingItem = 'symptomDates' | 'affectedShare' | 'cropHistory' | 'water' | 'soil' | 'priorities';

/**
 * Non-blocking gaps the investigation would benefit from (shown as Missing data warnings).
 * These become questions for the Uncertainty Hunter later (ABB-19).
 */
export function missingItems(c: IncidentCase): MissingItem[] {
  const m: MissingItem[] = [];
  if (!c.symptomsStart || !c.symptomsEnd) m.push('symptomDates');
  if (!c.affectedShare.trim()) m.push('affectedShare');
  if (c.crops.filter((r) => r.crop.trim()).length < 2) m.push('cropHistory');
  if (!c.constraints.water) m.push('water');
  if (!c.constraints.soilKnown) m.push('soil');
  if (!c.constraints.priorities.trim()) m.push('priorities');
  return m;
}

/* ── Location privacy ───────────────────────────────────────────── */

/** Snap to the centre of a grid cell of `step` degrees, so the shared point never sits on the real one. */
export function roundToCell(value: number, step: Rounding): number {
  const cell = Math.floor(value / step) * step + step / 2;
  return Math.round(cell * 1000) / 1000;
}

export type DisplayedLocation =
  | { kind: 'precise'; latitude: number; longitude: number }
  | { kind: 'rounded'; latitude: number; longitude: number; rounding: Rounding }
  | { kind: 'region'; label: string }
  | { kind: 'hidden' };

/**
 * What a viewer may see. Owners see the exact point. Guests see the exact point only with
 * explicit consent; otherwise the rounded cell centre, the region label, or nothing.
 */
export function displayedLocation(loc: CaseLocation, viewer: Viewer): DisplayedLocation {
  const lat = parseNumber(loc.latitude);
  const lon = parseNumber(loc.longitude);
  const valid = Number.isFinite(lat) && Number.isFinite(lon);
  if (viewer === 'owner') return valid ? { kind: 'precise', latitude: lat, longitude: lon } : { kind: 'hidden' };
  if (loc.consentPrecise && valid) return { kind: 'precise', latitude: lat, longitude: lon };
  if (loc.tier === 'private') return { kind: 'hidden' };
  if (loc.tier === 'region') return loc.regionLabel.trim() ? { kind: 'region', label: loc.regionLabel.trim() } : { kind: 'hidden' };
  return valid ? { kind: 'rounded', latitude: roundToCell(lat, loc.rounding), longitude: roundToCell(lon, loc.rounding), rounding: loc.rounding } : { kind: 'hidden' };
}

/** The payload a guest view would receive: precise coordinates removed unless consented, for every parcel. */
export function guestCopy(c: IncidentCase): Omit<IncidentCase, 'location' | 'locations'> & { location: DisplayedLocation; locations: DisplayedLocation[] } {
  const { location, locations: _locations, ...rest } = c;
  return {
    ...rest,
    location: displayedLocation(location, 'guest'),
    locations: caseLocations(c).map((loc) => displayedLocation(loc, 'guest')),
  };
}
