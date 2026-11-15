import { describe, expect, it } from 'vitest';
import type { CaseCreate, CaseView } from '../api/types';
import { emptyCase, type IncidentCase } from './model';
import { NOTES_MARKER, REGION_NOT_SHARED, decodeNotes, fromCaseView, incidentDates, readyForServer, toCaseCreate, toFieldInput } from './mapping';

// TEST-ONLY synthetic case. Not a real farm.
const NOW = new Date('2026-11-14T10:00:00Z');
function filled(): IncidentCase {
  const c = emptyCase(NOW);
  c.title = 'Synthetic test plot';
  c.location = { ...c.location, latitude: '41.6537', longitude: '-0.8773' };
  c.locations = [c.location];
  c.crops = [
    { id: 'y1', year: '2021', crop: 'barley', notes: 'early sowing' },
    { id: 'y2', year: '2022', crop: 'durum wheat', notes: '' },
  ];
  c.incidentYear = '2022';
  c.symptomsStart = '2022-05';
  c.symptomsEnd = '2022-08';
  c.symptoms = 'Yellowing from the edges.\nWorse near the ditch.';
  c.affectedShare = '30';
  c.constraints = { water: 'rainfed', soilKnown: true, soilNotes: 'clay loam', priorities: 'less water' };
  return c;
}

/** What the backend would answer for the owner after storing `body` (synthetic). */
function asView(body: CaseCreate, role: CaseView['my_role'] = 'OWNER'): CaseView {
  const f = body.fields[0];
  return {
    schema_version: '1.0', id: '00000000-0000-4000-8000-000000000001', title: body.title,
    incident_start: body.incident_start, incident_end: body.incident_end ?? null,
    fields: [{
      schema_version: '1.0', id: '00000000-0000-4000-8000-000000000002', label: f.label, privacy_tier: f.privacy_tier,
      latitude: f.latitude ?? null, longitude: f.longitude ?? null, region_label: f.region_label, area_hectares: null, limitations: [],
      location_precision: 'EXACT', rounding_deg: f.rounding_deg ?? null, precise_location_consent: f.precise_location_consent ?? false,
    }],
    crop_history: body.crop_history ?? [], incident_notes: body.incident_notes ?? null, visibility: 'PRIVATE',
    created_at: NOW.toISOString(), updated_at: NOW.toISOString(), version: 1, status: 'DRAFT', archived_at: null,
    owner: { id: '00000000-0000-4000-8000-000000000003', display_name: 'Test owner' }, my_role: role,
  };
}

describe('privacy tiers map to the server contract', () => {
  it('rounded → APPROXIMATE with the chosen rounding and no farmer-typed region', () => {
    const c = filled();
    c.location = { ...c.location, tier: 'rounded', rounding: 0.5, regionLabel: 'typed earlier' };
    expect(toFieldInput(c)).toMatchObject({ privacy_tier: 'APPROXIMATE', rounding_deg: 0.5, region_label: REGION_NOT_SHARED, latitude: 41.6537, longitude: -0.8773, precise_location_consent: false });
  });
  it('region → REGION_ONLY with the region label', () => {
    const c = filled();
    c.location = { ...c.location, tier: 'region', regionLabel: ' Ebro valley ' };
    expect(toFieldInput(c)).toMatchObject({ privacy_tier: 'REGION_ONLY', region_label: 'Ebro valley' });
  });
  it('private → REGION_ONLY with a non-revealing label, never WITHHELD (the owner keeps the point)', () => {
    const c = filled();
    c.location = { ...c.location, tier: 'private', regionLabel: 'Ebro valley' };
    const f = toFieldInput(c);
    expect(f.privacy_tier).toBe('REGION_ONLY');
    expect(f.region_label).toBe(REGION_NOT_SHARED);
    expect(f.latitude).toBe(41.6537);
  });
  it('consent maps to precise_location_consent', () => {
    const c = filled();
    c.location.consentPrecise = true;
    expect(toFieldInput(c).precise_location_consent).toBe(true);
  });
  it('each tier survives a round trip through the API shape', () => {
    for (const tier of ['private', 'rounded', 'region'] as const) {
      const c = filled();
      c.location = { ...c.location, tier, regionLabel: tier === 'region' ? 'Ebro valley' : '', rounding: 1 };
      const back = fromCaseView(asView(toCaseCreate(c, NOW)));
      expect(back.location).toEqual(c.location);
    }
  });
});

describe('dates, crops and notes', () => {
  it('symptom months become incident_start/incident_end', () => {
    expect(incidentDates(filled(), NOW)).toEqual({ incident_start: '2022-05-01', incident_end: '2022-08-31' });
  });
  it('without months the incident year starts the case and the end stays open', () => {
    const c = filled();
    c.symptomsStart = '';
    c.symptomsEnd = '';
    expect(incidentDates(c, NOW)).toEqual({ incident_start: '2022-01-01', incident_end: null });
  });
  it('an end month that has not finished yet is capped at today', () => {
    const c = filled();
    c.symptomsEnd = '2026-11';
    expect(incidentDates(c, NOW).incident_end).toBe('2026-11-14');
  });
  it('crop rows become short crop_history strings', () => {
    const body = toCaseCreate(filled(), NOW);
    expect(body.crop_history).toEqual(['2021: barley', '2022: durum wheat']);
    expect(body.crop_history!.every((s) => s.length >= 1 && s.length <= 120)).toBe(true);
  });
  it('fields the API has no column for travel in a readable, reversible notes block', () => {
    const notes = toCaseCreate(filled(), NOW).incident_notes!;
    expect(notes.startsWith('Yellowing from the edges.')).toBe(true);
    expect(notes).toContain(NOTES_MARKER);
    expect(notes).not.toContain('41.6537');
    expect(decodeNotes(notes).text).toBe(filled().symptoms);
  });
  it('the whole wizard case survives create → view → wizard', () => {
    const c = filled();
    const back = fromCaseView(asView(toCaseCreate(c, NOW)));
    const strip = (x: IncidentCase) => ({ ...x, id: '', createdAt: '', updatedAt: '', version: 0, server: undefined, crops: x.crops.map((r) => ({ ...r, id: '' })) });
    expect(strip(back)).toEqual(strip(c));
    expect(back.server).toMatchObject({ status: 'DRAFT', myRole: 'OWNER', fieldCount: 1, privacyTier: 'APPROXIMATE' });
  });
  it('notes written by other API clients are kept as plain text', () => {
    const view = asView(toCaseCreate(filled(), NOW));
    view.incident_notes = 'Free text from another client';
    view.crop_history = ['2020: maize', 'sunflower'];
    const back = fromCaseView(view);
    expect(back.symptoms).toBe('Free text from another client');
    expect(back.crops.map((r) => [r.year, r.crop])).toEqual([['2020', 'maize'], ['', 'sunflower']]);
    expect(back.symptomsStart).toBe('2022-05');
  });
});

describe('readiness for the API', () => {
  it('needs a name, a valid location and the incident year, not the optional answers', () => {
    const c = emptyCase(NOW);
    expect(readyForServer(c, NOW)).toBe(false);
    c.title = 'Synthetic';
    c.location = { ...c.location, latitude: '41.6', longitude: '-0.9' };
    expect(readyForServer(c, NOW)).toBe(false);
    c.incidentYear = '2022';
    expect(readyForServer(c, NOW)).toBe(true);
  });
});
