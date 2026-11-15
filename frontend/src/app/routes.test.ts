import { describe, expect, it } from 'vitest';
import { hrefForCaseTab, parseCaseTab, parseHash, parseParam, ROUTES } from './routes';
import { referenceWindow, validateInput } from './investigation';

describe('routes', () => {
  it('has the seven screens required by ABB-20', () => {
    expect(ROUTES.map((r) => r.id)).toEqual(['dashboard', 'cases', 'investigation', 'evidence', 'rotations', 'collaboration', 'report']);
  });
  it('parses hashes and falls back to the dashboard', () => {
    expect(parseHash('#/evidence')).toBe('evidence');
    expect(parseHash('#report?x=1')).toBe('report');
    expect(parseHash('#/nope')).toBe('dashboard');
    expect(parseHash('')).toBe('dashboard');
  });
});

describe('case tab routing (ABB-22 extension point)', () => {
  it('keeps parseParam reading the case id unchanged with a third segment present', () => {
    expect(parseParam('#/cases/abc-123/timeline')).toBe('abc-123');
    expect(parseParam('#/cases/abc-123')).toBe('abc-123');
    expect(parseParam('#/cases/new')).toBe('new');
  });
  it('defaults the case tab to "details" when no third segment is present', () => {
    expect(parseCaseTab('#/cases/abc-123')).toBe('details');
    expect(parseCaseTab('#/cases/new')).toBe('details');
    expect(parseCaseTab('#/cases')).toBe('details');
  });
  it('reads the third segment as the tab id, ignoring a query string', () => {
    expect(parseCaseTab('#/cases/abc-123/timeline')).toBe('timeline');
    expect(parseCaseTab('#/cases/abc-123/timeline?x=1')).toBe('timeline');
  });
  it('hrefForCaseTab keeps "details" at the canonical two-segment URL and adds a third segment otherwise', () => {
    expect(hrefForCaseTab('abc-123', 'details')).toBe('#/cases/abc-123');
    expect(hrefForCaseTab('abc-123', 'timeline')).toBe('#/cases/abc-123/timeline');
  });
});

describe('validateInput (mirrors backend limits)', () => {
  it('accepts valid input, including comma decimals and a true minus sign', () => {
    expect(validateInput({ latitude: '41,6', longitude: '−0.9', year: '2022' }).value).toEqual({ latitude: 41.6, longitude: -0.9, year: 2022 });
  });
  it('rejects out-of-range coordinates, years without 3 reference years, and future years', () => {
    expect(validateInput({ latitude: '91', longitude: '0', year: '2022' }).errors).toEqual({ latitude: true });
    expect(validateInput({ latitude: '0', longitude: '-181', year: '2022' }).errors).toEqual({ longitude: true });
    expect(validateInput({ latitude: '0', longitude: '0', year: '1983' }).errors).toEqual({ year: true });
    expect(validateInput({ latitude: '0', longitude: '0', year: '2027' }, 2026).errors).toEqual({ year: true });
    expect(validateInput({ latitude: '', longitude: '', year: '2022.5' }).errors).toEqual({ latitude: true, longitude: true, year: true });
  });
  it('accepts the years of the former fixed reference window, 1984 and the current year', () => {
    for (const year of ['2010', '2015', '2021', '1984', '2026']) {
      expect(validateInput({ latitude: '0', longitude: '0', year }, 2026).errors).toEqual({});
    }
  });
});

describe('referenceWindow (same rule as the backend default)', () => {
  it('takes the 10 years before the event year, from 1981', () => {
    expect(referenceWindow(2015)).toEqual({ start: 2005, end: 2014 });
    expect(referenceWindow(2026)).toEqual({ start: 2016, end: 2025 });
    expect(referenceWindow(1988)).toEqual({ start: 1981, end: 1987 });
    expect(referenceWindow(1984)).toEqual({ start: 1981, end: 1983 });
  });
});
