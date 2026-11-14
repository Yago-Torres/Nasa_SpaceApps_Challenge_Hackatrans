import { describe, expect, it } from 'vitest';
import { dayNumber, dayScale, monthTicks, packRows, severitySize, timelineSpan } from './timelineLayout';

describe('dayScale (pixel layout only, no new statistics)', () => {
  it('maps the span endpoints to the given pixel range and clamps outside values', () => {
    const scale = dayScale('2022-01-01', '2022-12-31', 0, 100);
    expect(scale('2022-01-01')).toBeCloseTo(0, 5);
    expect(scale('2022-12-31')).toBeCloseTo(100, 5);
    expect(scale('2021-01-01')).toBe(0); // before the span: clamped
    expect(scale('2023-01-01')).toBe(100); // after the span: clamped
  });
  it('never divides by zero for a single-day span', () => {
    const scale = dayScale('2022-06-01', '2022-06-01', 0, 100);
    expect(Number.isFinite(scale('2022-06-01'))).toBe(true);
  });
  it('orders two dates the same way dayNumber does', () => {
    expect(dayNumber('2022-02-01') > dayNumber('2022-01-01')).toBe(true);
  });
});

describe('monthTicks', () => {
  it('returns one tick per month in a short span', () => {
    const ticks = monthTicks('2022-01-15', '2022-04-02');
    expect(ticks.map((t) => t.iso)).toEqual(['2022-01-01', '2022-02-01', '2022-03-01', '2022-04-01']);
  });
  it('thins ticks so a long span never exceeds maxTicks', () => {
    const ticks = monthTicks('1981-01-01', '2024-12-31', 12);
    expect(ticks.length).toBeLessThanOrEqual(12);
  });
});

describe('timelineSpan', () => {
  it('covers every dated event plus the incident window', () => {
    const events = [
      { start: '2022-03-01', end: '2022-03-31' },
      { start: null, end: null }, // undated: ignored
      { start: '2022-05-01', end: '2022-05-31' },
    ];
    expect(timelineSpan(events, '2022-04-01', '2022-04-30')).toEqual(['2022-03-01', '2022-05-31']);
  });
  it('falls back to the incident window alone when nothing else is dated', () => {
    expect(timelineSpan([], '2022-04-01', null)).toEqual(['2022-04-01', '2022-04-01']);
  });
});

describe('packRows (greedy interval packing for overlapping lane marks)', () => {
  it('keeps non-overlapping events on the same row', () => {
    expect(packRows([{ start: '2022-01-01', end: '2022-01-31' }, { start: '2022-02-01', end: '2022-02-28' }])).toEqual([0, 0]);
  });
  it('stacks overlapping events onto separate rows', () => {
    expect(packRows([
      { start: '2022-01-01', end: '2022-06-30' },
      { start: '2022-01-01', end: '2022-06-30' },
      { start: '2022-01-01', end: '2022-06-30' },
    ])).toEqual([0, 1, 2]);
  });
  it('reuses a row once its previous occupant has ended', () => {
    expect(packRows([
      { start: '2022-01-01', end: '2022-01-31' },
      { start: '2022-01-15', end: '2022-02-15' }, // overlaps the first: row 1
      { start: '2022-02-01', end: '2022-02-28' }, // starts after row 0 freed up: row 0
    ])).toEqual([0, 1, 0]);
  });
});

describe('severitySize (backend-assigned category -> relative mark size, invents no thresholds)', () => {
  it('orders the three named severities by size', () => {
    expect(severitySize('LARGE_DEPARTURE')).toBeGreaterThan(severitySize('MODERATE_DEPARTURE'));
    expect(severitySize('MODERATE_DEPARTURE')).toBeGreaterThan(severitySize('WITHIN_REFERENCE_SPREAD'));
  });
  it('gives NOT_CLASSIFIED and an absent severity the same neutral size', () => {
    expect(severitySize('NOT_CLASSIFIED')).toBe(severitySize(undefined));
  });
});
