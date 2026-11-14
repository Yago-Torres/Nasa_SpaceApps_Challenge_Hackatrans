import { beforeEach, describe, expect, it } from 'vitest';
import { displayedLocation, emptyCase, guestCopy, missingItems, roundToCell, validateStep, type IncidentCase } from './model';
import { LocalDevCaseRepository } from './repository';

function filled(): IncidentCase {
  const c = emptyCase(new Date('2026-11-14T10:00:00Z'));
  c.title = 'Wheat loss, north plot';
  c.location = { ...c.location, latitude: '41.6537', longitude: '-0.8773' };
  c.crops = [{ id: 'y1', year: '2021', crop: 'barley', notes: '' }, { id: 'y2', year: '2022', crop: 'durum wheat', notes: '' }];
  c.incidentYear = '2022';
  c.symptoms = 'Yellowing from the edges in May.';
  return c;
}

describe('location privacy (ABB-21 acceptance: guests never see the exact plot)', () => {
  it('owner sees the exact point', () => {
    expect(displayedLocation(filled().location, 'owner')).toEqual({ kind: 'precise', latitude: 41.6537, longitude: -0.8773 });
  });
  it('guest sees only the rounded cell centre by default', () => {
    const shown = displayedLocation(filled().location, 'guest');
    expect(shown).toEqual({ kind: 'rounded', latitude: 41.65, longitude: -0.85, rounding: 0.1 });
  });
  it('coarser rounding moves the shared point further from the real one', () => {
    expect(roundToCell(41.6537, 0.5)).toBe(41.75);
    expect(roundToCell(-0.8773, 1)).toBe(-0.5);
  });
  it('private tier hides location from guests; region tier shows only the label', () => {
    const c = filled();
    expect(displayedLocation({ ...c.location, tier: 'private' }, 'guest')).toEqual({ kind: 'hidden' });
    expect(displayedLocation({ ...c.location, tier: 'region', regionLabel: 'Ebro valley' }, 'guest')).toEqual({ kind: 'region', label: 'Ebro valley' });
  });
  it('exact point reaches guests only with explicit consent', () => {
    const c = filled();
    expect(displayedLocation({ ...c.location, consentPrecise: true }, 'guest').kind).toBe('precise');
  });
  it('the guest payload contains no precise coordinates anywhere', () => {
    const json = JSON.stringify(guestCopy(filled()));
    expect(json).not.toContain('41.6537');
    expect(json).not.toContain('0.8773');
  });
});

describe('validation keeps data and reports useful errors', () => {
  it('flags each invalid field per step', () => {
    const c = emptyCase();
    expect(validateStep(c, 'location')).toEqual(['title', 'latitude', 'longitude']);
    c.location.tier = 'region';
    expect(validateStep(c, 'location')).toContain('regionLabel');
    expect(validateStep(c, 'crops')).toEqual(['crop.0.year', 'crop.0.crop']);
    c.symptomsStart = '2022-06';
    c.symptomsEnd = '2022-04';
    c.affectedShare = '140';
    expect(validateStep(c, 'incident')).toEqual(['incidentYear', 'symptomsOrder', 'symptoms', 'affectedShare']);
  });
  it('accepts a complete case and lists non-blocking gaps', () => {
    const c = filled();
    expect(validateStep(c, 'location')).toEqual([]);
    expect(validateStep(c, 'crops')).toEqual([]);
    expect(validateStep(c, 'incident')).toEqual([]);
    expect(missingItems(c)).toEqual(['symptomDates', 'affectedShare', 'water', 'soil', 'priorities']);
  });
});

describe('development repository', () => {
  beforeEach(() => localStorage.clear());
  it('creates, reads back, edits and versions a case', async () => {
    const repo = new LocalDevCaseRepository();
    expect(repo.developmentOnly).toBe(true);
    const saved = await repo.save(filled());
    expect(saved.version).toBe(1);
    const again = await repo.save({ ...saved, title: 'Edited' });
    expect(again.version).toBe(2);
    expect((await repo.get(saved.id))?.title).toBe('Edited');
    expect(await repo.list()).toHaveLength(1);
    await repo.clear();
    expect(await repo.list()).toHaveLength(0);
  });
});
