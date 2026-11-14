#!/usr/bin/env node
// Validates WCAG 2.2 contrast for every documented fg/bg token pair in both
// themes. Zero dependencies. Usage (from repo root):
//   node .claude/skills/agro-design-system/scripts/check-contrast.mjs [path/to/tokens.css]
// Defaults to frontend/src/design/tokens.css if it exists, else the skill copy.
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const candidates = [process.argv[2], 'frontend/src/design/tokens.css', join(here, '../assets/tokens.css')];
const file = candidates.find((p) => p && existsSync(p));
const css = readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

// [foreground, background, minimum ratio, why]
// 4.5 = body text (AA), 3 = large/bold text, UI components and focus indicators.
const PAIRS = [
  ['--ink-strong', '--surface-base', 4.5, 'headings'],
  ['--ink', '--surface-base', 4.5, 'body text'],
  ['--ink', '--surface-raised', 4.5, 'body on panels'],
  ['--ink-muted', '--surface-base', 4.5, 'metadata'],
  ['--ink-muted', '--surface-raised', 4.5, 'metadata on panels'],
  ['--ink-muted', '--surface-sunken', 4.5, 'metadata in wells'],
  ['--ink-link', '--surface-raised', 4.5, 'links'],
  ['--ink-readout', '--surface-readout', 4.5, 'instrument readouts'],
  ['--ink-inverse', '--surface-inverse', 4.5, 'inverse bands'],
  ['--action-ink', '--action-bg', 4.5, 'primary button label'],
  ['--action-ink', '--action-bg-hover', 4.5, 'primary button hover'],
  ['--action-secondary-ink', '--action-secondary-bg', 4.5, 'secondary button'],
  ['--action-secondary-line', '--surface-base', 3, 'secondary button outline'],
  ['--line-strong', '--surface-raised', 3, 'input borders'],
  ['--focus-ring', '--surface-base', 3, 'focus ring'],
  ['--focus-ring', '--surface-raised', 3, 'focus ring on panels'],
  ['--status-ok-ink', '--status-ok-bg', 4.5, 'status ok'],
  ['--status-caution-ink', '--status-caution-bg', 4.5, 'status caution'],
  ['--status-danger-ink', '--status-danger-bg', 4.5, 'status danger'],
  ['--status-info-ink', '--status-info-bg', 4.5, 'status info'],
  ['--status-stale-ink', '--status-stale-bg', 4.5, 'status stale'],
  ['--tag-observed-ink', '--tag-observed-bg', 4.5, 'tag OBSERVED'],
  ['--tag-farmer-ink', '--tag-farmer-bg', 4.5, 'tag FARMER_REPORTED'],
  ['--tag-literature-ink', '--tag-literature-bg', 4.5, 'tag LITERATURE_REVIEWED'],
  ['--tag-hypothesis-ink', '--tag-hypothesis-bg', 4.5, 'tag HYPOTHESIS'],
  ['--tag-model-ink', '--tag-model-bg', 4.5, 'tag MODEL_SCENARIO'],
  ['--tag-illustrative-ink', '--tag-illustrative-bg', 4.5, 'tag ILLUSTRATIVE'],
  ['--tag-missing-ink', '--surface-raised', 4.5, 'tag MISSING_DATA'],
  ['--viz-axis', '--surface-raised', 4.5, 'chart axis labels'],
  ['--viz-baseline', '--surface-raised', 3, 'chart zero line'],
  ['--viz-cat-1', '--surface-raised', 3, 'series 1'],
  ['--viz-cat-2', '--surface-raised', 3, 'series 2'],
  ['--viz-cat-3', '--surface-raised', 3, 'series 3'],
  ['--viz-cat-4', '--surface-raised', 3, 'series 4'],
  ['--viz-cat-5', '--surface-raised', 3, 'series 5'],
];

function blocks(selectorTest) {
  const out = {};
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m;
  while ((m = re.exec(css))) {
    const sel = m[1].trim();
    if (!selectorTest(sel)) continue;
    for (const d of m[2].split(';')) {
      const i = d.indexOf(':');
      if (i < 0) continue;
      const k = d.slice(0, i).trim();
      if (k.startsWith('--')) out[k] = d.slice(i + 1).trim();
    }
  }
  return out;
}
const base = blocks((s) => s === ':root');
const light = { ...base, ...blocks((s) => s.includes('[data-theme="light"]') && !s.includes(':not(')) };
const dark = { ...light, ...blocks((s) => s === ':root[data-theme="dark"]') };

function resolve(vars, value, depth = 0) {
  if (depth > 10) throw new Error(`cycle resolving ${value}`);
  const v = value.match(/^var\((--[\w-]+)\)$/);
  return v ? resolve(vars, vars[v[1]] ?? '', depth + 1) : value;
}
function parse(c) {
  c = c.trim();
  if (c === 'transparent') return [0, 0, 0, 0];
  let m = c.match(/^#([0-9a-f]{6})$/i);
  if (m) return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)).concat(1);
  m = c.match(/^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)(?:\s*[/,]\s*([\d.]+))?\s*\)$/);
  if (m) return [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]];
  throw new Error(`unsupported colour "${c}"`);
}
const over = (fg, bg) => fg.slice(0, 3).map((ch, i) => ch * fg[3] + bg[i] * (1 - fg[3])).concat(1);
const lum = ([r, g, b]) => {
  const f = (x) => ((x /= 255) <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const ratio = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

let failures = 0;
for (const [theme, vars] of [['daylight', light], ['night-shift', dark]]) {
  const page = parse(resolve(vars, vars['--surface-base']));
  const panel = parse(resolve(vars, vars['--surface-raised']));
  console.log(`\n${theme}`);
  for (const [fgK, bgK, min, why] of PAIRS) {
    // Translucent backgrounds sit on a panel; translucent foregrounds sit on their bg.
    const bg = over(parse(resolve(vars, vars[bgK])), bgK === '--surface-base' ? page : panel);
    const fg = over(parse(resolve(vars, vars[fgK])), bg);
    const r = ratio(fg, bg);
    const ok = r >= min;
    if (!ok) failures++;
    console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${r.toFixed(2).padStart(5)} ≥ ${min}  ${why.padEnd(28)} ${fgK} on ${bgK}`);
  }
}
console.log(`\n${file}: ${failures ? `${failures} failing pair(s)` : 'all pairs pass'}`);
process.exit(failures ? 1 : 0);
