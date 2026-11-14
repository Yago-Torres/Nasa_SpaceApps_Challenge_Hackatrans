#!/usr/bin/env node
// WCAG 2.2 contrast check for every documented fg/bg token pair (light mode only).
// Zero dependencies. Usage (from repo root):
//   node .claude/skills/agro-design-system/scripts/check-contrast.mjs [path/to/tokens.css]
// Defaults to frontend/src/design/tokens.css if present, else the skill's copy.
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const file = [process.argv[2], 'frontend/src/design/tokens.css', join(here, '../assets/tokens.css')].find((p) => p && existsSync(p));
const css = readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

// [foreground, background, minimum, why] — 4.5 text, 3 large text / UI / focus.
const PAIRS = [
  ['--ink', '--surface', 4.5, 'body text'],
  ['--ink-2', '--surface', 4.5, 'secondary text'],
  ['--ink-2', '--surface-sunken', 4.5, 'secondary text in wells'],
  ['--ink-3', '--surface', 4.5, 'metadata'],
  ['--ink-3', '--surface-sunken', 4.5, 'metadata in wells'],
  ['--ink-link', '--surface', 4.5, 'links'],
  ['--ink-on-shell', '--surface-shell', 4.5, 'rail text'],
  ['--ink-on-shell-2', '--surface-shell', 4.5, 'rail secondary text'],
  ['--ink-on-shell', '--surface-shell-active', 4.5, 'rail active item'],
  ['--ink-on-shell', '--surface-shell-hover', 4.5, 'rail hover item'],
  ['--action-ink', '--action', 4.5, 'primary button'],
  ['--action-ink', '--action-hover', 4.5, 'primary button hover'],
  ['--action-edge', '--surface', 3, 'primary button edge'],
  ['--action-2-ink', '--action-2', 4.5, 'secondary button'],
  ['--action-2-edge', '--surface', 3, 'secondary button edge'],
  ['--rule-2', '--surface', 3, 'input border'],
  ['--focus', '--surface', 3, 'focus ring'],
  ['--focus-on-shell', '--surface-shell', 3, 'focus ring on rail'],
  ['--rule-3', '--surface', 3, 'strong separators'],
  ['--ink', '--highlight', 4.5, 'text on highlight'],
  ['--ok-ink', '--ok-bg', 4.5, 'status ok'],
  ['--warn-ink', '--warn-bg', 4.5, 'status warning'],
  ['--error-ink', '--error-bg', 4.5, 'status error'],
  ['--info-ink', '--info-bg', 4.5, 'status info'],
  ['--neutral-ink', '--neutral-bg', 4.5, 'status neutral'],
  ['--ev-observed', '--surface', 4.5, 'legend OBSERVED'],
  ['--ev-farmer', '--surface', 4.5, 'legend FARMER_REPORTED'],
  ['--ev-literature', '--surface', 4.5, 'legend LITERATURE_REVIEWED'],
  ['--ev-hypothesis', '--surface', 4.5, 'legend HYPOTHESIS'],
  ['--ev-model', '--surface', 4.5, 'legend MODEL_SCENARIO'],
  ['--ev-illustrative', '--surface', 4.5, 'legend ILLUSTRATIVE'],
  ['--ev-missing', '--surface', 4.5, 'legend MISSING_DATA'],
  ['--viz-axis', '--surface', 4.5, 'chart labels'],
  ['--viz-cat-1', '--surface', 3, 'series 1'],
  ['--viz-cat-2', '--surface', 3, 'series 2'],
  ['--viz-cat-3', '--surface', 3, 'series 3'],
  ['--viz-cat-4', '--surface', 3, 'series 4'],
];

const vars = {};
for (const m of css.matchAll(/:root\s*\{([^}]*)\}/g)) {
  for (const d of m[1].split(';')) {
    const i = d.indexOf(':');
    if (i > 0 && d.slice(0, i).trim().startsWith('--')) vars[d.slice(0, i).trim()] = d.slice(i + 1).trim();
  }
}
const resolve = (v, n = 0) => {
  if (n > 10) throw new Error(`cycle at ${v}`);
  const m = v?.match(/^var\((--[\w-]+)\)$/);
  return m ? resolve(vars[m[1]], n + 1) : v;
};
const rgb = (c) => {
  const m = c?.match(/^#([0-9a-f]{6})$/i);
  if (!m) throw new Error(`unsupported colour "${c}" (use 6-digit hex for checked tokens)`);
  return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16));
};
const lum = (c) => {
  const f = (x) => ((x /= 255) <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4);
  const [r, g, b] = c.map(f);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

let failures = 0;
for (const [fg, bg, min, why] of PAIRS) {
  const [a, b] = [lum(rgb(resolve(vars[fg]))), lum(rgb(resolve(vars[bg])))].sort((x, y) => y - x);
  const r = (a + 0.05) / (b + 0.05);
  const ok = r >= min;
  if (!ok) failures++;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${r.toFixed(2).padStart(5)} ≥ ${String(min).padEnd(3)} ${why.padEnd(28)} ${fg} on ${bg}`);
}
console.log(`\n${file}: ${failures ? `${failures} failing pair(s)` : 'all pairs pass'}`);
process.exit(failures ? 1 : 0);
