import { describe, expect, it } from 'vitest';
import { niceCeil, rainStep, symmetricScale, tempClass } from './chartScale';

describe('chart scale', () => {
  it('rounds up to nice numbers', () => {
    expect(niceCeil(58)).toBe(100);
    expect(niceCeil(41)).toBe(50);
    expect(niceCeil(23)).toBe(25);
    expect(niceCeil(0)).toBe(1);
  });
  it('builds one symmetric scale that contains every value, ignoring nulls', () => {
    const s = symmetricScale([8, -58, null, 26]);
    expect(s.max).toBe(100);
    expect(s.ticks).toEqual([-100, -50, 0, 50, 100]);
    expect(symmetricScale([null, null]).max).toBe(1);
  });
  it('colour steps are relative to the scale and never decide the printed value', () => {
    expect(rainStep(-90, 100)).toBe('dry-3');
    expect(rainStep(-10, 100)).toBe('dry-1');
    expect(rainStep(50, 100)).toBe('wet-2');
    expect(tempClass(null)).toBe('tn');
    expect(tempClass(3.1)).toBe('t3');
  });
});
