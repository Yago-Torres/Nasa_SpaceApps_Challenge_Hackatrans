# Component recipes — Solar Industrial

These are reference implementations, not a library to paste blindly. Adapt them inside `frontend/src/design/components/`. All strings go through i18n (`t('…')`); they're inlined here only for readability. Icons come from `lucide-react` (already a dependency) at `strokeWidth={1.75}`, `aria-hidden="true"` when next to text.

## Contents

1. [Base CSS](#base-css)
2. [Button](#button)
3. [Field](#field)
4. [Panel (instrument module)](#panel)
5. [EpistemicTag](#epistemictag)
6. [DataPlate](#data-plate)
7. [Readout](#readout)
8. [StateView](#state-views)
9. [SunArcJourney](#sun-arc-journey)
10. [ProvenanceDrawer](#provenancedrawer)
11. [RotationCard](#rotationcard)
12. [ReviewNote (human voice)](#reviewnote)

---

## Base CSS

`frontend/src/design/base.css`, imported once after `tokens.css`.

```css
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--surface-base);
  color: var(--ink);
  font-family: var(--font-industrial);
  font-size: var(--text-md);
  line-height: var(--leading-body);
  -webkit-font-smoothing: antialiased;
}
h1, h2, h3, h4 { color: var(--ink-strong); line-height: var(--leading-tight); text-wrap: balance; margin: 0; }
p { max-width: var(--measure); text-wrap: pretty; }
a { color: var(--ink-link); text-underline-offset: 0.18em; }
:focus-visible { outline: 3px solid var(--focus-ring); outline-offset: 2px; }
.num { font-variant-numeric: tabular-nums; }
.machine { font-family: var(--font-machine); font-size: 0.92em; overflow-wrap: anywhere; }
.human { font-family: var(--font-human); font-variation-settings: "SOFT" 100; line-height: var(--leading-human); }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.skip-link { position: absolute; left: var(--space-4); top: -100px; }
.skip-link:focus { top: var(--space-4); z-index: var(--z-toast); }
```

## Button

Three variants: `primary` (recorder orange, max one per view), `secondary` (outlined steel), `quiet` (text-only, for tertiary actions). Minimum height `--tap-min`.

```tsx
type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'quiet';
  busy?: boolean;           // request in flight: keeps width, shows recording dot
  icon?: React.ReactNode;
};
export function Button({ variant = 'secondary', busy, icon, children, ...rest }: ButtonProps) {
  return (
    <button className={`btn btn--${variant}`} aria-busy={busy || undefined} disabled={busy || rest.disabled} {...rest}>
      {busy ? <span className="rec-dot" aria-hidden="true" /> : icon}
      <span>{children}</span>
    </button>
  );
}
```

```css
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2);
  min-height: var(--tap-min); padding: 0 var(--space-5);
  border-radius: var(--radius-control); border: var(--line-structural) solid transparent;
  font: var(--weight-semibold) var(--text-sm)/1 var(--font-industrial);
  font-stretch: var(--stretch-condensed); letter-spacing: 0.02em;
  cursor: pointer; touch-action: manipulation;
  transition: background-color var(--dur-quick) var(--ease-mechanical), border-color var(--dur-quick) var(--ease-mechanical);
}
.btn--primary { background: var(--action-bg); color: var(--action-ink); border-color: var(--action-ink); }
.btn--primary:hover { background: var(--action-bg-hover); }
.btn--secondary { background: var(--action-secondary-bg); color: var(--action-secondary-ink); border-color: var(--action-secondary-line); }
.btn--secondary:hover { background: var(--surface-sunken); }
.btn--quiet { background: transparent; color: var(--ink-link); padding-inline: var(--space-2); }
.btn:disabled { cursor: not-allowed; opacity: 0.55; }
.btn[aria-busy="true"] { opacity: 1; cursor: progress; }

/* Recording indicator: pulses only while a request is in flight. */
.rec-dot { width: 0.6rem; height: 0.6rem; border-radius: 50%; background: currentColor; animation: rec 1.1s steps(2, jump-none) infinite; }
@keyframes rec { 50% { opacity: 0.25; } }
@media (prefers-reduced-motion: reduce) { .rec-dot { animation: none; } }
```

The primary button's dark border + orange fill is the "safety label" look. Busy label uses an ellipsis: "Fetching NASA data…".

## Field

Label above, hint below, error inline and announced. Units live in a suffix, not in the label.

```tsx
<div className="field" data-invalid={!!error || undefined}>
  <label htmlFor="lat">Latitude</label>
  <div className="field__control">
    <input id="lat" name="latitude" type="text" inputMode="decimal" autoComplete="off"
           aria-describedby="lat-hint lat-err" aria-invalid={!!error || undefined} />
    <span className="field__unit" aria-hidden="true">°N</span>
  </div>
  <p id="lat-hint" className="field__hint">Rounded to 0.1° when the case is shared.</p>
  {error && <p id="lat-err" className="field__error" role="alert">{error}</p>}
</div>
```

```css
.field { display: grid; gap: var(--space-1); }
.field label { font-size: var(--text-sm); font-weight: var(--weight-semibold); color: var(--ink-strong); }
.field__control { display: flex; align-items: stretch; border: var(--line-hairline) solid var(--line-strong);
  border-radius: var(--radius-control); background: var(--surface-raised); }
.field__control:focus-within { outline: 3px solid var(--focus-ring); outline-offset: 1px; }
.field input, .field select, .field textarea { flex: 1; min-width: 0; min-height: var(--tap-min);
  border: 0; background: transparent; color: var(--ink-strong); font: inherit; padding: 0 var(--space-3); outline: none; }
.field__unit { display: grid; place-items: center; padding: 0 var(--space-3); border-left: var(--line-hairline) solid var(--line);
  color: var(--ink-muted); font-family: var(--font-machine); font-size: var(--text-xs); }
.field__hint { margin: 0; font-size: var(--text-xs); color: var(--ink-muted); }
.field__error { margin: 0; font-size: var(--text-xs); color: var(--status-danger-ink); font-weight: var(--weight-semibold); }
.field[data-invalid] .field__control { border-color: var(--status-danger-ink); border-width: 2px; }
```

(`outline: none` on the inner input is fine because `:focus-within` on the wrapper replaces it.)

## Panel

The instrument module: header strip with a title and optional module tag, body, optional footer with provenance summary.

```tsx
<section className="panel" aria-labelledby="p-timeline">
  <header className="panel__head">
    <h2 id="p-timeline">Weather timeline</h2>
    <EpistemicTag kind="OBSERVED" />
    <button className="btn btn--quiet panel__aside" onClick={openProvenance}>Source details</button>
  </header>
  <div className="panel__body">…</div>
  <footer className="panel__foot">NASA POWER · daily · 0.5° × 0.625° grid · retrieved 14 Nov 2026</footer>
</section>
```

```css
.panel { background: var(--surface-raised); border: var(--line-hairline) solid var(--line); border-radius: var(--radius-instrument); min-width: 0; }
.panel__head { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-3);
  padding: var(--space-3) var(--space-5); border-bottom: var(--line-structural) solid var(--line-strong); }
.panel__head h2 { font-size: var(--text-lg); font-stretch: var(--stretch-condensed); font-weight: var(--weight-bold); }
.panel__aside { margin-left: auto; }
.panel__body { padding: var(--space-5); }
.panel__foot { padding: var(--space-3) var(--space-5); border-top: var(--line-hairline) solid var(--line-subtle);
  font-size: var(--text-xs); color: var(--ink-muted); }
```

Small corner registration ticks (like on engineering drawings) are allowed on the **one** hero panel of a screen via `.panel--registered::before/::after` with 8px L-shaped borders in `--line-strong`. Not on every panel.

## EpistemicTag

The controlled vocabulary from UX_FLOWS. Code (always visible) + localized human label (visible on wide layouts, `title`/sr-only otherwise) + shape + colour.

| kind | Shape | Human label EN / ES | Use for |
|---|---|---|---|
| `OBSERVED` | square, solid border | Observed / Observado | NASA POWER, GPM, HLS values |
| `FARMER_REPORTED` | leaf (`--radius-leaf`) | Farmer reported / Reportado por agricultor | intake symptoms, local notes |
| `LITERATURE_REVIEWED` | square with notched corner (bookplate) | Reviewed literature / Literatura revisada | human-verified findings only |
| `HYPOTHESIS` | dashed border | Hypothesis / Hipótesis | candidate explanations |
| `MODEL_SCENARIO` | diagonal hatch background | Model scenario / Escenario modelado | rotation comparisons, computed outputs |
| `ILLUSTRATIVE` | survey-tape striped border | Illustrative / Ilustrativo | demo/synthetic data |
| `MISSING_DATA` | empty hatched outline | Missing data / Dato ausente | gaps the Uncertainty Hunter lists |

Search results from OpenAlex are `LITERATURE_METADATA` in the scientific policy: render them with a plain "Metadata only" status chip (`--status-info-*`), never with the `LITERATURE_REVIEWED` tag.

```tsx
export type EpistemicKind = 'OBSERVED' | 'FARMER_REPORTED' | 'LITERATURE_REVIEWED' | 'HYPOTHESIS' | 'MODEL_SCENARIO' | 'ILLUSTRATIVE' | 'MISSING_DATA';
export function EpistemicTag({ kind, compact }: { kind: EpistemicKind; compact?: boolean }) {
  const t = useT();
  const label = t(`epistemic.${kind}`);
  return (
    <span className={`etag etag--${kind.toLowerCase()}`} title={compact ? label : undefined}>
      <span className="etag__code" translate="no">{kind}</span>
      {compact ? <span className="visually-hidden">{label}</span> : <span className="etag__label">{label}</span>}
    </span>
  );
}
```

```css
.etag { display: inline-flex; align-items: baseline; gap: var(--space-2); padding: 0.15rem var(--space-2);
  border: var(--line-hairline) solid currentColor; border-radius: var(--radius-instrument);
  font-size: var(--text-2xs); line-height: 1.4; white-space: nowrap; }
.etag__code { font-weight: var(--weight-bold); font-stretch: var(--stretch-condensed); letter-spacing: 0.06em; }
.etag__label { font-size: var(--text-2xs); opacity: 0.9; }
.etag--observed { background: var(--tag-observed-bg); color: var(--tag-observed-ink); }
.etag--farmer_reported { background: var(--tag-farmer-bg); color: var(--tag-farmer-ink); border-radius: var(--radius-leaf); }
.etag--literature_reviewed { background: var(--tag-literature-bg); color: var(--tag-literature-ink);
  clip-path: polygon(0 0, calc(100% - 7px) 0, 100% 7px, 100% 100%, 0 100%); }
.etag--hypothesis { background: var(--tag-hypothesis-bg); color: var(--tag-hypothesis-ink); border-style: dashed; }
.etag--model_scenario { color: var(--tag-model-ink);
  background: repeating-linear-gradient(135deg, var(--tag-model-bg) 0 4px, transparent 4px 7px), var(--surface-raised); }
.etag--illustrative { color: var(--tag-illustrative-ink); background: var(--tag-illustrative-bg);
  border: 2px solid transparent;
  border-image: repeating-linear-gradient(135deg, var(--c-recorder-500) 0 6px, var(--c-graphite-950) 6px 12px) 2; }
.etag--missing_data { color: var(--tag-missing-ink); border-style: dashed; background: transparent; }
```

## Data plate

Equipment nameplate for provenance. Every observation panel has one (collapsed summary in the panel footer, full plate in the drawer and in the report).

```tsx
<dl className="plate">
  <div><dt>Dataset</dt><dd>NASA POWER daily point</dd></div>
  <div><dt>Parameters</dt><dd className="machine">PRECTOTCORR, T2M_MAX</dd></div>
  <div><dt>Period</dt><dd className="num">2022 vs 2010–2021</dd></div>
  <div><dt>Spatial resolution</dt><dd>0.5° × 0.625° grid — regional, not your field</dd></div>
  <div><dt>Retrieved</dt><dd><time dateTime="2026-11-14T10:12:00Z">14 Nov 2026, 10:12 UTC</time></dd></div>
  <div><dt>SHA-256</dt><dd className="machine">3f9a…c21e <CopyButton value={sha} /></dd></div>
  <div className="plate__wide"><dt>Limitations</dt><dd>Short reference period; anomalies are descriptive and don't establish causes.</dd></div>
</dl>
```

Only show fields the API actually returns; if the API doesn't return a resolution yet, render the row with a `MISSING_DATA` tag rather than inventing one.

```css
.plate { display: grid; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); margin: 0;
  border: var(--line-structural) solid var(--line-strong); border-radius: var(--radius-instrument); background: var(--surface-sunken); }
.plate > div { padding: var(--space-3) var(--space-4); border-right: var(--line-hairline) solid var(--line); border-bottom: var(--line-hairline) solid var(--line); min-width: 0; }
.plate__wide { grid-column: 1 / -1; }
.plate dt { font-size: var(--text-2xs); font-stretch: var(--stretch-condensed); font-weight: var(--weight-semibold); color: var(--ink-muted); letter-spacing: 0.04em; }
.plate dd { margin: var(--space-1) 0 0; font-size: var(--text-sm); color: var(--ink-strong); }
```

## Readout

A dark instrument display for one headline number (e.g. "Rain, Apr–Jun: −142 mm vs reference"). Always: value, unit, comparison basis, tag.

```css
.readout { background: var(--surface-readout); color: var(--ink-readout); border-radius: var(--radius-instrument);
  box-shadow: var(--shadow-inset-readout); padding: var(--space-4) var(--space-5); display: grid; gap: var(--space-1); }
.readout__value { font-size: var(--text-3xl); font-weight: var(--weight-bold); font-variant-numeric: tabular-nums; font-stretch: var(--stretch-condensed); }
.readout__unit { font-size: var(--text-lg); margin-left: 0.15em; }
.readout__basis { font-size: var(--text-xs); color: var(--c-steel-300); }
```

Use at most 2–3 readouts per screen; they are the "gauges", not a KPI wall.

## State views

One component, six states. Each state has an icon, a title that says what's happening, a sentence that says what to do, and optionally an action.

| state | icon (lucide) | tone | example copy (EN) |
|---|---|---|---|
| `loading` | `rec-dot` | info | "Fetching NASA POWER data for 41.6°N, 0.9°W…" |
| `empty` | `Sprout` | neutral | "No literature yet. Search with a question about your crop and symptom." |
| `error` | `TriangleAlert` | danger | "NASA POWER didn't respond (502). No values are shown. Try again in a minute." + Retry |
| `partial` | `CircleDashed` | caution | "Temperature arrived; precipitation is missing for 3 months. Gaps are marked." |
| `stale` | `Clock` | stale | "Retrieved 9 days ago. Refresh to check for updated records." |
| `pending` | `Construction` | stale, dashed border | "Case sharing isn't built yet (F-09). This panel shows where it will live." |

```css
.state { display: grid; grid-template-columns: auto 1fr; gap: var(--space-2) var(--space-3); align-items: start;
  padding: var(--space-4) var(--space-5); border-radius: var(--radius-instrument); border: var(--line-hairline) solid transparent; }
.state--error { background: var(--status-danger-bg); color: var(--status-danger-ink); border-color: currentColor; }
.state--partial { background: var(--status-caution-bg); color: var(--status-caution-ink); }
.state--loading { background: var(--status-info-bg); color: var(--status-info-ink); }
.state--stale, .state--pending { background: var(--status-stale-bg); color: var(--status-stale-ink); }
.state--pending { border: var(--line-structural) dashed var(--line); }
.state--empty { background: var(--surface-sunken); color: var(--ink); }
```

Loading/partial regions use `aria-live="polite"`; errors use `role="alert"`. Skeletons, if used, mimic the final layout in `--surface-sunken` with no shimmer.

## Sun-arc journey

The signature element. SVG arc + ordered list for semantics (the list is what assistive tech reads).

```tsx
type StepState = 'done' | 'current' | 'todo' | 'pending';
const STEPS = ['intake', 'nasa', 'timeline', 'evidence', 'rotations', 'review', 'report'] as const;

export function SunArcJourney({ states, onSelect }: { states: Record<typeof STEPS[number], StepState>; onSelect: (s: string) => void }) {
  const t = useT();
  const n = STEPS.length;
  const current = Math.max(0, STEPS.findIndex((s) => states[s] === 'current'));
  // Points on a flattened half-ellipse: x in [4, 96], y peaks at noon.
  const pt = (i: number) => { const a = Math.PI * (1 - i / (n - 1)); return { x: 50 + 46 * Math.cos(a), y: 34 - 28 * Math.sin(a) }; };
  const sun = pt(current);
  return (
    <nav className="journey" aria-label={t('journey.label')}>
      <svg className="journey__arc" viewBox="0 0 100 38" preserveAspectRatio="none" aria-hidden="true">
        <path d="M4 34 A46 28 0 0 1 96 34" className="journey__path" />
        <circle className="journey__sun" cx={sun.x} cy={sun.y} r="3.2" />
      </svg>
      <ol className="journey__steps">
        {STEPS.map((s, i) => (
          <li key={s} data-state={states[s]}>
            <button onClick={() => onSelect(s)} aria-current={states[s] === 'current' ? 'step' : undefined}
                    disabled={states[s] === 'pending'}>
              <span className="journey__n num">{i + 1}</span>
              <span>{t(`journey.${s}`)}</span>
              {states[s] === 'pending' && <span className="visually-hidden">{t('state.pending')}</span>}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
```

```css
.journey { position: relative; padding-top: var(--space-6); }
.journey__arc { position: absolute; inset: 0 0 auto; width: 100%; height: 5.5rem; overflow: visible; }
.journey__path { fill: none; stroke: var(--line); stroke-width: 0.6; stroke-dasharray: 1.2 1.2; vector-effect: non-scaling-stroke; }
.journey__sun { fill: var(--sun); stroke: var(--surface-base); stroke-width: 1;
  transition: cx var(--dur-sunrise) var(--ease-mechanical), cy var(--dur-sunrise) var(--ease-mechanical); }
.journey__steps { position: relative; display: grid; grid-template-columns: repeat(7, 1fr); gap: var(--space-2); list-style: none; margin: 0; padding: 4.5rem 0 0; }
.journey__steps button { width: 100%; min-height: var(--tap-min); display: grid; justify-items: center; gap: var(--space-1);
  background: none; border: 0; color: var(--ink-muted); font: var(--weight-medium) var(--text-xs)/1.25 var(--font-industrial); cursor: pointer; }
.journey__n { width: 1.75rem; height: 1.75rem; display: grid; place-items: center; border-radius: 50%;
  border: var(--line-structural) solid var(--line-strong); background: var(--surface-raised); color: var(--ink-strong); font-weight: var(--weight-bold); }
[data-state="done"] .journey__n { background: var(--growth); border-color: var(--growth); color: var(--surface-raised); }
[data-state="current"] button { color: var(--ink-strong); font-weight: var(--weight-bold); }
[data-state="current"] .journey__n { background: var(--sun); border-color: var(--ink-strong); color: var(--c-graphite-950); }
[data-state="pending"] .journey__n { border-style: dashed; background: transparent; color: var(--ink-muted); }
@media (max-width: 48rem) {
  .journey { padding-top: 0; }
  .journey__arc { display: none; }
  .journey__steps { grid-template-columns: none; grid-auto-flow: column; grid-auto-columns: minmax(5.5rem, 1fr);
    overflow-x: auto; padding: var(--space-2) 0; scroll-snap-type: x mandatory;
    background: linear-gradient(var(--line), var(--line)) 0 calc(var(--space-2) + 0.875rem) / 100% 2px no-repeat; }
  .journey__steps li { scroll-snap-align: center; }
}
```

The numbers are justified because this *is* a sequence. Don't reuse numbered markers elsewhere unless the content is also a sequence.

## ProvenanceDrawer

Right-side drawer on desktop (`--drawer-width`), bottom sheet on mobile. Contains the full Data plate, request parameters (machine font), limitations, and a "copy citation" action. Opened from any panel's "Source details". Focus moves into the drawer on open and returns to the trigger on close; `Esc` closes; `overscroll-behavior: contain`. Use the native `<dialog>` element where possible.

```css
.drawer { position: fixed; inset: 0 0 0 auto; width: min(var(--drawer-width), 100vw); z-index: var(--z-drawer);
  background: var(--surface-raised); border-left: var(--line-structural) solid var(--line-strong); box-shadow: var(--shadow-lift);
  overflow-y: auto; overscroll-behavior: contain; padding: var(--space-5);
  transform: translateX(100%); transition: transform var(--dur-base) var(--ease-mechanical); }
.drawer[open] { transform: none; }
@media (max-width: 48rem) {
  .drawer { inset: auto 0 0 0; width: 100%; max-height: 85dvh; border-left: 0; border-top: var(--line-structural) solid var(--line-strong);
    border-radius: var(--radius-organic) var(--radius-organic) 0 0; transform: translateY(100%); padding-bottom: calc(var(--space-5) + env(safe-area-inset-bottom)); }
}
```

## RotationCard

One per scenario in the Rotation lab. The current rotation is always first and labelled "Current rotation"; alternatives are "Alternative A/B". Years run as a horizontal crop-calendar strip (one cell per season, crop name + small icon). Assumptions and limitations are always visible, not behind a toggle. Tag: `MODEL_SCENARIO` if computed from inputs, `ILLUSTRATIVE` for `/api/rotations/demo` output.

```css
.rotation { display: grid; gap: var(--space-3); padding: var(--space-5); background: var(--surface-raised);
  border: var(--line-hairline) solid var(--line); border-top: 4px solid var(--rot-color, var(--viz-cat-1)); border-radius: var(--radius-instrument); }
.rotation[data-current] { border-top-width: 6px; }
.rotation__years { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(6rem, 1fr); gap: 2px; overflow-x: auto; }
.rotation__year { background: var(--surface-sunken); padding: var(--space-2) var(--space-3); font-size: var(--text-sm); }
.rotation__year small { display: block; color: var(--ink-muted); font-size: var(--text-2xs); }
```

Never put percentages ("+18 % water saved") on a card unless the backend returns a validated value with uncertainty interval (SCIENTIFIC_POLICY).

## ReviewNote

The human voice: farmer notes and community review comments. Organic radius, Fraunces body, attribution and role always visible, timestamp, and status (open / addressed / objection).

```css
.note { border-radius: var(--radius-organic); background: var(--growth-soft); padding: var(--space-4) var(--space-5);
  border: var(--line-hairline) solid var(--line); }
.note__body { font-family: var(--font-human); font-variation-settings: "SOFT" 100; font-size: var(--text-md); line-height: var(--leading-human); color: var(--ink-strong); }
.note__meta { margin-top: var(--space-2); font-size: var(--text-xs); color: var(--ink-muted); }
.note[data-kind="objection"] { background: var(--status-caution-bg); border-style: dashed; }
```
