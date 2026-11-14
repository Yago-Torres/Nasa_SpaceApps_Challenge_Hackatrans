import { describe, expect, it } from 'vitest';
import { parseHash, ROUTES } from './routes';
import { validateInput } from './investigation';

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

describe('validateInput (mirrors backend limits)', () => {
  it('accepts valid input, including comma decimals and a true minus sign', () => {
    expect(validateInput({ latitude: '41,6', longitude: '−0.9', year: '2022' }).value).toEqual({ latitude: 41.6, longitude: -0.9, year: 2022 });
  });
  it('rejects out-of-range coordinates, years outside POWER and years inside the reference window', () => {
    expect(validateInput({ latitude: '91', longitude: '0', year: '2022' }).errors).toEqual({ latitude: true });
    expect(validateInput({ latitude: '0', longitude: '-181', year: '2022' }).errors).toEqual({ longitude: true });
    expect(validateInput({ latitude: '0', longitude: '0', year: '1980' }).errors).toEqual({ year: true });
    expect(validateInput({ latitude: '0', longitude: '0', year: '2015' }).errors).toEqual({ year: true });
    expect(validateInput({ latitude: '', longitude: '', year: '2022.5' }).errors).toEqual({ latitude: true, longitude: true, year: true });
  });
});
