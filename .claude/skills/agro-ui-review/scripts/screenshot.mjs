#!/usr/bin/env node
// Screenshots a page at desktop + mobile (light mode only) and
// reports console errors and horizontal overflow. For self-critique, not CI.
//
// Usage (from repo root, with the dev server running: cd frontend && npm run dev):
//   node .claude/skills/agro-ui-review/scripts/screenshot.mjs [url-or-file] [out-dir]
// Defaults: http://localhost:5173  ./.ui-shots
//
// Requires the `playwright` package. Claude Code cloud sessions have it
// preinstalled; on a laptop install it outside the repo (npx -y playwright@1 …)
// or ask the team before adding it as a frontend devDependency (needs an Issue).
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright')); }
catch { console.error('playwright is not installed. See the header of this script.'); process.exit(2); }

const arg = process.argv[2] ?? 'http://localhost:5173';
const url = /^https?:|^file:/.test(arg) ? arg : pathToFileURL(resolve(arg)).href;
const out = resolve(process.argv[3] ?? '.ui-shots');
mkdirSync(out, { recursive: true });

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
];
const themes = ['light'];

const browser = await chromium.launch();
let problems = 0;
for (const vp of viewports) {
  for (const theme of themes) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, colorScheme: theme, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    const errors = [];
    page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(url, { waitUntil: 'networkidle' }).catch((e) => errors.push(`navigation: ${e.message}`));
    await page.waitForTimeout(250);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    const file = `${out}/${vp.name}.png`;
    await page.screenshot({ path: file, fullPage: true });
    const flags = [];
    if (overflow > 0) flags.push(`horizontal overflow ${overflow}px`);
    if (errors.length) flags.push(`${errors.length} console error(s): ${errors.slice(0, 3).join(' | ')}`);
    problems += flags.length;
    console.log(`${flags.length ? 'WARN' : 'ok  '} ${file}${flags.length ? '  — ' + flags.join('; ') : ''}`);
    await ctx.close();
  }
}
await browser.close();
process.exit(problems ? 1 : 0);
