import { describe, expect, it } from 'vitest';
import { en, es } from './messages';
import { interpolate } from './I18n';

describe('messages', () => {
  it('Spanish has exactly the English keys and no empty strings', () => {
    expect(Object.keys(es).sort()).toEqual(Object.keys(en).sort());
    for (const [key, value] of Object.entries(es)) expect(value.trim(), key).not.toBe('');
  });
  it('placeholders match between languages', () => {
    const vars = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort();
    for (const key of Object.keys(en) as (keyof typeof en)[]) expect(vars(es[key]), key).toEqual(vars(en[key]));
  });
  it('interpolates named variables and leaves unknown ones', () => {
    expect(interpolate('Year {n} of {m}', { n: 2 })).toBe('Year 2 of {m}');
  });
});
