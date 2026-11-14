/**
 * Pixel scaling helpers for anomaly charts. They only map values the API returned to
 * drawing space; they compute no new statistics (frontend/AGENTS.md).
 */

const NICE = [1, 2, 2.5, 5, 10];

/** Smallest "nice" number ≥ x (1, 2, 2.5, 5 × 10^n). */
export function niceCeil(x: number): number {
  if (!(x > 0)) return 1;
  const exp = Math.floor(Math.log10(x));
  const base = 10 ** exp;
  const step = NICE.find((n) => n * base >= x - 1e-9) ?? 10;
  return step * base;
}

/**
 * One shared, symmetric linear scale for a diverging chart. Every value is drawn to it;
 * there is no visual cap, so bars stay comparable (the old UI capped widths at 100%).
 */
export function symmetricScale(values: (number | null | undefined)[]): { max: number; ticks: number[] } {
  const finite = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  const max = niceCeil(Math.max(0, ...finite.map(Math.abs)));
  return { max, ticks: [-max, -max / 2, 0, max / 2, max] };
}

/** Colour step for a rain anomaly bar relative to the chart scale (visual only, value is always printed). */
export function rainStep(value: number, max: number): 'dry-3' | 'dry-2' | 'dry-1' | 'wet-1' | 'wet-2' | 'wet-3' {
  const r = Math.min(1, Math.abs(value) / max);
  const level = r > 2 / 3 ? 3 : r > 1 / 3 ? 2 : 1;
  return `${value < 0 ? 'dry' : 'wet'}-${level}` as const;
}

/** Colour class for a temperature-difference cell (visual only; the value is printed in the cell). */
export function tempClass(value: number | null): string {
  if (value === null) return 'tn';
  if (value <= -1.5) return 't00';
  if (value < 0) return 't0';
  if (value < 1.5) return 't1';
  if (value < 2.8) return 't2';
  return 't3';
}
