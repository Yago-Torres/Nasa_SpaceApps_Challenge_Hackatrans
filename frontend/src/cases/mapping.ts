/**
 * Wizard form state (IncidentCase) <-> case API (CaseView / CaseCreate), ABB-21 + ABB-06.
 * Documented in docs/architecture/FRONTEND_INTEGRATION.md §6. Pure functions, no I/O.
 *
 * Privacy tiers:
 *   rounded → APPROXIMATE + rounding_deg (0.1 / 0.5 / 1)
 *   region  → REGION_ONLY with the farmer's region label
 *   private → REGION_ONLY with the fixed label REGION_NOT_SHARED (never WITHHELD, which
 *             cannot store the owner's coordinates)
 *   consentPrecise → precise_location_consent
 * Reviewers/viewers receive region_label for every tier, so non-"region" tiers always send
 * REGION_NOT_SHARED and never a label the farmer typed for another tier.
 *
 * Wizard answers the API has no column for (incident year, symptom months, affected share,
 * constraints, crop-row details) travel in a structured block appended to incident_notes
 * after NOTES_MARKER; the farmer's symptom text stays readable before it.
 */
import type { CaseCreate, CaseView, FieldInput, FieldPrivacyTier, RoundingDeg } from '../api/types';
import { MAX_CROP_ROWS, newId, parseNumber, validateStep, type CropYear, type IncidentCase, type PrivacyTier, type Rounding } from './model';

export const REGION_NOT_SHARED = 'Not shared by the owner';
// Stored data-format marker inside `incident_notes`. It keeps the project's former name on purpose:
// changing it would make previously saved cases unreadable. Not user-facing branding.
export const NOTES_MARKER = '--- AGRO BLACK BOX wizard answers v1 (structured; edit them in the wizard) ---';
const ROUNDINGS: Rounding[] = [0.1, 0.5, 1];

type WizardBlock = {
  v: 1;
  incidentYear: string;
  symptomsStart: string;
  symptomsEnd: string;
  affectedShare: string;
  constraints: IncidentCase['constraints'];
  crops: { year: string; crop: string; notes: string }[];
};

/* ── Location ───────────────────────────────────────────────────── */

export function serverTier(tier: PrivacyTier): FieldPrivacyTier {
  return tier === 'rounded' ? 'APPROXIMATE' : 'REGION_ONLY';
}

export function toFieldInput(c: IncidentCase): FieldInput {
  const lat = parseNumber(c.location.latitude);
  const lon = parseNumber(c.location.longitude);
  const hasPoint = Number.isFinite(lat) && Number.isFinite(lon);
  return {
    label: c.title.trim().slice(0, 160),
    privacy_tier: serverTier(c.location.tier),
    latitude: hasPoint ? lat : null,
    longitude: hasPoint ? lon : null,
    region_label: c.location.tier === 'region' ? c.location.regionLabel.trim().slice(0, 160) : REGION_NOT_SHARED,
    precise_location_consent: c.location.consentPrecise,
    rounding_deg: c.location.rounding as RoundingDeg,
  };
}

/* ── Dates ──────────────────────────────────────────────────────── */

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

function lastDayOfMonth(ym: string): string {
  const [y, m] = ym.split('-').map(Number);
  return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
}

/**
 * incident_start = first day of the symptom start month, else 1 January of the incident year.
 * incident_end = last day of the symptom end month, capped at today (the API rejects future
 * dates), else null. The exact months are kept in the structured block.
 */
export function incidentDates(c: IncidentCase, now = new Date()): { incident_start: string; incident_end: string | null } {
  const today = now.toISOString().slice(0, 10);
  const start = MONTH.test(c.symptomsStart) ? `${c.symptomsStart}-01` : `${c.incidentYear.trim()}-01-01`;
  let end: string | null = MONTH.test(c.symptomsEnd) ? lastDayOfMonth(c.symptomsEnd) : null;
  if (end && end > today) end = today;
  return { incident_start: start, incident_end: end };
}

/* ── Crops ──────────────────────────────────────────────────────── */

/** "2022: durum wheat" (1–120 characters, at most 50); rows without a crop are skipped. */
export function cropHistory(crops: CropYear[]): string[] {
  return crops
    .filter((r) => r.crop.trim())
    .slice(0, MAX_CROP_ROWS)
    .map((r) => {
      const year = r.year.trim();
      return (/^\d{4}$/.test(year) ? `${year}: ${r.crop.trim()}` : r.crop.trim()).slice(0, 120);
    });
}

function parseCropHistory(entries: string[]): CropYear[] {
  return entries.map((entry) => {
    const m = /^(\d{4}): (.+)$/.exec(entry);
    return { id: newId('y'), year: m ? m[1] : '', crop: m ? m[2] : entry, notes: '' };
  });
}

/* ── Notes block ────────────────────────────────────────────────── */

export function encodeNotes(c: IncidentCase): string {
  const block: WizardBlock = {
    v: 1,
    incidentYear: c.incidentYear.trim(),
    symptomsStart: c.symptomsStart,
    symptomsEnd: c.symptomsEnd,
    affectedShare: c.affectedShare.trim(),
    constraints: c.constraints,
    crops: c.crops.map(({ year, crop, notes }) => ({ year, crop, notes })),
  };
  const text = c.symptoms.trim();
  return `${text ? `${text}\n\n` : ''}${NOTES_MARKER}\n${JSON.stringify(block)}`;
}

function isBlock(value: unknown): value is WizardBlock {
  const b = value as WizardBlock | null;
  return !!b && b.v === 1 && typeof b.incidentYear === 'string' && typeof b.symptomsStart === 'string' && typeof b.symptomsEnd === 'string'
    && typeof b.affectedShare === 'string' && typeof b.constraints === 'object' && b.constraints !== null && Array.isArray(b.crops);
}

/** Split incident_notes into the farmer's text and the structured block (null if absent or unreadable). */
export function decodeNotes(notes: string | null): { text: string; block: WizardBlock | null } {
  const raw = notes ?? '';
  const at = raw.lastIndexOf(NOTES_MARKER);
  if (at < 0) return { text: raw.trim(), block: null };
  let block: WizardBlock | null = null;
  try {
    const parsed: unknown = JSON.parse(raw.slice(at + NOTES_MARKER.length).trim());
    block = isBlock(parsed) ? parsed : null;
  } catch {
    block = null;
  }
  return block ? { text: raw.slice(0, at).trim(), block } : { text: raw.trim(), block: null };
}

/* ── Whole case ─────────────────────────────────────────────────── */

export type CaseAttributes = Omit<CaseCreate, 'fields'>;

export function caseAttributes(c: IncidentCase, now = new Date()): CaseAttributes {
  return { title: c.title.trim(), ...incidentDates(c, now), crop_history: cropHistory(c.crops), incident_notes: encodeNotes(c) };
}

export function toCaseCreate(c: IncidentCase, now = new Date()): CaseCreate {
  return { ...caseAttributes(c, now), fields: [toFieldInput(c)] };
}

/** Keys whose value differs between two payloads (deep, via JSON). */
export function changedKeys<T extends object>(before: T | null, after: T): Partial<T> {
  const out: Partial<T> = {};
  for (const key of Object.keys(after) as (keyof T)[]) {
    if (!before || JSON.stringify(before[key]) !== JSON.stringify(after[key])) out[key] = after[key];
  }
  return out;
}

function wizardTier(tier: FieldPrivacyTier, label: string): PrivacyTier {
  if (tier === 'APPROXIMATE' || tier === 'EXACT') return 'rounded'; // EXACT only exists with consent; kept unless the owner changes the tier
  if (tier === 'REGION_ONLY' && label !== REGION_NOT_SHARED) return 'region';
  return 'private';
}

export function fromCaseView(v: CaseView): IncidentCase {
  const field = v.fields[0];
  const { text, block } = decodeNotes(v.incident_notes);
  const history = cropHistory((block?.crops ?? []).map((r) => ({ id: '', ...r })));
  // Use the block's rows only while they still match the server's crop_history.
  const crops: CropYear[] = block && JSON.stringify(history) === JSON.stringify(v.crop_history)
    ? block.crops.map((r) => ({ id: newId('y'), year: String(r.year ?? ''), crop: String(r.crop ?? ''), notes: String(r.notes ?? '') }))
    : parseCropHistory(v.crop_history);
  const rounding = ROUNDINGS.find((r) => r === field.rounding_deg) ?? 0.1;
  return {
    id: v.id,
    title: v.title,
    location: {
      latitude: field.latitude === null ? '' : String(field.latitude),
      longitude: field.longitude === null ? '' : String(field.longitude),
      regionLabel: field.region_label === REGION_NOT_SHARED ? '' : field.region_label,
      tier: wizardTier(field.privacy_tier, field.region_label),
      rounding,
      consentPrecise: field.precise_location_consent,
    },
    crops: crops.length ? crops : [{ id: newId('y'), year: '', crop: '', notes: '' }],
    incidentYear: block?.incidentYear ?? v.incident_start.slice(0, 4),
    symptomsStart: block ? block.symptomsStart : v.incident_start.slice(0, 7),
    symptomsEnd: block ? block.symptomsEnd : (v.incident_end?.slice(0, 7) ?? ''),
    symptoms: text,
    affectedShare: block?.affectedShare ?? '',
    constraints: {
      water: block?.constraints.water ?? '',
      soilKnown: block?.constraints.soilKnown ?? false,
      soilNotes: block?.constraints.soilNotes ?? '',
      priorities: block?.constraints.priorities ?? '',
    },
    createdAt: v.created_at,
    updatedAt: v.updated_at,
    version: v.version,
    server: {
      status: v.status,
      myRole: v.my_role,
      ownerName: v.owner.display_name,
      archived: v.archived_at !== null,
      fieldId: field.id,
      fieldCount: v.fields.length,
      privacyTier: field.privacy_tier,
      locationPrecision: field.location_precision,
    },
  };
}

/** What the API needs before a case can be created or saved; the wizard keeps everything else locally until then. */
const SERVER_REQUIRED = new Set(['title', 'latitude', 'longitude', 'regionLabel', 'incidentYear', 'symptomsStart', 'symptomsEnd', 'symptomsOrder', 'symptomsRange']);
export function readyForServer(c: IncidentCase, now = new Date()): boolean {
  return ![...validateStep(c, 'location', now), ...validateStep(c, 'incident', now)].some((p) => SERVER_REQUIRED.has(p));
}
