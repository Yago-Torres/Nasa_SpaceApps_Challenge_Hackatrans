# Component recipes — Field Survey

Reference implementations for `frontend/src/design/components/`. All strings go through i18n (`t('…')`); they're inlined here for readability. UI icons: `lucide-react` (already a dependency) at `strokeWidth={2}`, `aria-hidden="true"` next to text. Evidence symbols: the SVG sprite below. `assets/specimen.html` renders every recipe.

## Contents

1. Base CSS
2. Button
3. Field
4. Legend sprite and EvidenceLabel
5. TitleBlock (signature)
6. StepRail
7. SourceLabel
8. ReviewSlip
9. StatusMessage
10. Hypotheses table
11. Section heading

---

## 1. Base CSS

`frontend/src/design/base.css`, imported after `tokens.css`.

```css
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; accent-color: var(--c-may-ink);
  scrollbar-color: var(--rule-2) var(--surface-sunken); }
body { margin: 0; background: var(--surface-sunken); color: var(--ink); font-family: var(--font-sans);
  font-size: var(--text-md); line-height: var(--leading-body); caret-color: var(--c-may-ink); }
::selection { background: var(--highlight); color: var(--ink); }
h1, h2, h3, h4 { margin: 0; line-height: var(--leading-tight); text-wrap: balance; }
p { margin: 0; max-width: var(--measure); text-wrap: pretty; }
a { color: var(--ink-link); text-underline-offset: 0.2em; text-decoration-thickness: 1px; }
a:hover { text-decoration-thickness: 2px; }
:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
.num { font-variant-numeric: tabular-nums; }
.mono { font-family: var(--font-mono); font-size: 0.875em; overflow-wrap: anywhere; }
.voice { font-family: var(--font-serif); font-style: italic; line-height: var(--leading-serif); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
```

Grid containers that hold tables or charts need `grid-template-columns: minmax(0, 1fr)`; an implicit column grows to the table's min width and breaks mobile.

## 2. Button

Variants: `primary` (yellow-green, max one per view), `secondary` (white, green outline), `text` (link-styled, tertiary). Height ≥ `--tap`.

```tsx
type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'text'; busy?: boolean };
export function Button({ variant = 'secondary', busy, children, ...rest }: Props) {
  return (
    <button className={`btn btn--${variant}`} aria-busy={busy || undefined} disabled={busy || rest.disabled} {...rest}>
      {busy && <span className="spin" aria-hidden="true" />}
      {children}
    </button>
  );
}
```

```css
.btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); min-height: var(--tap);
  padding: 0 var(--space-5); border-radius: var(--radius-m); border: 1px solid transparent; cursor: pointer;
  font: var(--weight-bold) var(--text-md)/1 var(--font-sans); touch-action: manipulation;
  transition: background-color var(--dur-1) var(--ease-out), border-color var(--dur-1) var(--ease-out); }
.btn--primary { background: var(--action); color: var(--action-ink); border-color: var(--action-edge); }
.btn--primary:hover { background: var(--action-hover); }
.btn--secondary { background: var(--action-2); color: var(--action-2-ink); border-color: var(--action-2-edge); }
.btn--secondary:hover { background: var(--surface-tint); }
.btn--text { background: none; color: var(--ink-link); padding-inline: var(--space-2); font-weight: var(--weight-medium); }
.btn--text:hover { text-decoration: underline; }
.spin { width: 1em; height: 1em; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(1turn); } }
@media (prefers-reduced-motion: reduce) { .spin { animation: none; opacity: .6; } }
```

Labels are verb + object: "Investigate with NASA data", "Download case report". Busy label ends with "…": "Fetching NASA data…". A trailing arrow icon only on the button that moves to the next step.

## 3. Field

Label above, hint below, error inline. Units in a suffix cell, not in the label.

```tsx
<div className={`field${error ? ' bad' : ''}`}>
  <label htmlFor="lat">{t('intake.latitude')}</label>
  <div className="ctl">
    <input id="lat" name="latitude" inputMode="decimal" autoComplete="off"
           aria-invalid={!!error || undefined} aria-describedby={error ? 'lat-err' : 'lat-hint'} />
    <span className="unit" aria-hidden="true">°N</span>
  </div>
  {error ? <span id="lat-err" className="err"><AlertTriangle aria-hidden="true" />{error}</span>
         : <span id="lat-hint" className="hint">{t('intake.roundedHint')}</span>}
</div>
```

```css
.field { display: grid; gap: var(--space-1); min-width: 0; }
.field label { font-weight: var(--weight-bold); font-size: var(--text-sm); }
.field .ctl { display: flex; min-height: var(--tap); background: var(--surface); border: 1px solid var(--rule-2); border-radius: var(--radius-s); }
.field .ctl:focus-within { outline: 3px solid var(--focus); outline-offset: 1px; border-color: var(--focus); }
.field input, .field select, .field textarea { flex: 1; min-width: 0; border: 0; background: none; font: inherit;
  color: var(--ink); padding: 0 var(--space-3); outline: none; }   /* focus shown on .ctl */
.field .unit { display: grid; place-items: center; padding: 0 var(--space-3); color: var(--ink-3); font-size: var(--text-sm); border-left: 1px solid var(--rule); }
.field .hint { color: var(--ink-3); font-size: var(--text-sm); }
.field.bad .ctl { border: 2px solid var(--error-ink); }
.field .err { color: var(--error-ink); font-size: var(--text-sm); font-weight: var(--weight-bold); display: flex; gap: var(--space-2); }
```

## 4. Legend sprite and EvidenceLabel

Put the sprite once in `design/icons.svg` (or inline it in the shell). Symbols use `currentColor`.

```html
<symbol id="s-observed" viewBox="0 0 12 12"><rect x="1" y="1" width="10" height="10" fill="currentColor"/></symbol>
<symbol id="s-farmer" viewBox="0 0 12 12"><circle cx="6" cy="6" r="5" fill="currentColor"/></symbol>
<symbol id="s-literature" viewBox="0 0 12 12"><path d="M6 1 11.2 10.5H.8z" fill="currentColor"/></symbol>
<symbol id="s-hypothesis" viewBox="0 0 12 12"><circle cx="6" cy="6" r="4.6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-dasharray="2.2 1.6"/></symbol>
<symbol id="s-model" viewBox="0 0 12 12"><rect x="1.2" y="1.2" width="9.6" height="9.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M1.5 7.5 7.5 1.5M1.5 11 11 1.5M5 11 11 5" stroke="currentColor" stroke-width="1.2"/></symbol>
<symbol id="s-illustrative" viewBox="0 0 12 12"><path d="M6 .8 11.2 6 6 11.2.8 6z" fill="none" stroke="currentColor" stroke-width="1.6"/></symbol>
<symbol id="s-missing" viewBox="0 0 12 12"><rect x="1.2" y="1.2" width="9.6" height="9.6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-dasharray="1.4 1.6"/></symbol>
```

```tsx
export type EvidenceKind = 'OBSERVED' | 'FARMER_REPORTED' | 'LITERATURE_REVIEWED' | 'HYPOTHESIS' | 'MODEL_SCENARIO' | 'ILLUSTRATIVE' | 'MISSING_DATA';
const SYM: Record<EvidenceKind, string> = { OBSERVED: 'observed', FARMER_REPORTED: 'farmer', LITERATURE_REVIEWED: 'literature',
  HYPOTHESIS: 'hypothesis', MODEL_SCENARIO: 'model', ILLUSTRATIVE: 'illustrative', MISSING_DATA: 'missing' };

/** Symbol + label. `symbolOnly` for dense lists: the label stays for screen readers. */
export function EvidenceLabel({ kind, detail, symbolOnly }: { kind: EvidenceKind; detail?: string; symbolOnly?: boolean }) {
  const t = useT();
  const label = t(`evidence.${kind}`) + (detail ? ` · ${detail}` : '');
  return (
    <span className={`ev ev--${SYM[kind]}`} data-kind={kind}>
      <svg className="sym" aria-hidden="true"><use href={`#s-${SYM[kind]}`} /></svg>
      {symbolOnly ? <span className="sr-only">{label}</span> : label}
    </span>
  );
}
```

```css
.ev { display: inline-flex; align-items: center; gap: .4em; font-size: var(--text-sm); font-weight: var(--weight-medium); }
svg.sym { width: .85em; height: .85em; flex: none; }
.ev--observed { color: var(--ev-observed); } .ev--farmer { color: var(--ev-farmer); }
.ev--literature { color: var(--ev-literature); } .ev--hypothesis { color: var(--ev-hypothesis); }
.ev--model { color: var(--ev-model); } .ev--illustrative { color: var(--ev-illustrative); } .ev--missing { color: var(--ev-missing); }
```

Labels EN/ES: Observed/Observado · Farmer reported/Reportado por el agricultor · Reviewed literature/Literatura revisada · Hypothesis/Hipótesis · Model scenario/Escenario modelado · Illustrative/Ilustrativo · Missing data/Dato ausente. In lists (hypotheses table) the symbol sits before each item's text, no pill backgrounds.

## 5. TitleBlock (signature)

A `<dl>` grid: a large name cell spanning two rows, then six fields. 2px ink rule under the block, `--rule-3` hairlines between cells.

```tsx
<dl className="titleblock">
  <div className="name"><h1>{c.title}</h1><p>{c.summary}</p></div>
  <div><dt>{t('case.id')}</dt><dd className="mono">{c.id}</dd></div>
  <div><dt>{t('case.location')}</dt><dd>{c.regionLabel} · {t('privacy.rounded', { deg: c.rounding })}</dd></div>
  <div><dt>{t('case.status')}</dt><dd><EvidenceLabel kind="HYPOTHESIS" symbolOnly /> {t(`status.${c.status}`)}</dd></div>
  <div><dt>{t('case.scale')}</dt><dd>{c.dataScale ?? <EvidenceLabel kind="MISSING_DATA" />}</dd></div>
  <div><dt>{t('case.period')}</dt><dd className="num">{c.period}</dd></div>
  <div><dt>{t('case.reviewer')}</dt><dd>{c.reviewer ?? t('case.notAssigned')}</dd></div>
</dl>
```

```css
.titleblock { margin: 0; display: grid; grid-template-columns: minmax(16rem, 2.2fr) repeat(3, minmax(9rem, 1fr)); border-bottom: 2px solid var(--ink); background: var(--surface); }
.titleblock > div { padding: var(--space-3) var(--space-4); border-right: 1px solid var(--rule-3); min-width: 0; }
.titleblock > div:nth-child(-n+4) { border-bottom: 1px solid var(--rule-3); }
.titleblock > div:nth-child(4), .titleblock > div:nth-child(7) { border-right: 0; }
.titleblock .name { grid-row: span 2; display: grid; align-content: start; gap: var(--space-2); border-bottom: 0; }
.titleblock h1 { font-size: var(--text-2xl); font-weight: var(--weight-heavy); letter-spacing: -.01em; }
.titleblock .name p { color: var(--ink-2); font-size: var(--text-sm); }
.titleblock dt { font-size: var(--text-xs); color: var(--ink-3); }
.titleblock dd { margin: 2px 0 0; font-size: var(--text-sm); font-weight: var(--weight-medium); }
@media (max-width: 60rem) { .titleblock { grid-template-columns: repeat(2, minmax(0, 1fr)); } .titleblock .name { grid-column: 1 / -1; grid-row: auto; } }
```

Only fields the API returns. Before F-02 (persistent cases) exists, the one-off investigation shows the block with "Unsaved investigation" as the ID.

## 6. StepRail

Left rail in Cal Poly green: brand, open case, the 7 numbered steps (a real sequence), language switch at the bottom. Standard `<nav>` with links; `aria-current="step"` on the current one (yellow-green number). Done steps: filled light number. Not-built steps: dashed number + "not built". Under 60rem the rail becomes a top bar with the steps scrolling horizontally.

```css
.rail { background: var(--surface-shell); color: var(--ink-on-shell); display: flex; flex-direction: column; gap: var(--space-5); padding: var(--space-5) var(--space-3); }
.rail :focus-visible { outline-color: var(--focus-on-shell); }
.rail a { display: grid; grid-template-columns: 1.5rem 1fr auto; align-items: center; gap: var(--space-2); min-height: var(--tap);
  padding: 0 var(--space-2); border-radius: var(--radius-m); color: var(--ink-on-shell); text-decoration: none; }
.rail a:hover { background: var(--surface-shell-hover); }
.rail a[aria-current] { background: var(--surface-shell-active); font-weight: var(--weight-bold); }
.rail .n { width: 1.5rem; height: 1.5rem; border-radius: 50%; display: grid; place-items: center; font-size: var(--text-xs); font-weight: var(--weight-bold); border: 1.5px solid var(--ink-on-shell-2); }
.rail .done .n { background: var(--ink-on-shell); color: var(--surface-shell); }
.rail [aria-current] .n { background: var(--action); color: var(--action-ink); border-color: var(--action); }
.rail .pending a { color: var(--ink-on-shell-2); } .rail .pending .n { border-style: dashed; }
```

## 7. SourceLabel

The herbarium label for a data source, in the Sources side panel (bottom sheet on mobile).

```tsx
<article className="label">
  <header><b>NASA POWER</b><EvidenceLabel kind="OBSERVED" /></header>
  <dl>
    <dt>{t('src.product')}</dt><dd>{src.product}</dd>
    <dt>{t('src.variables')}</dt><dd className="mono">{src.variables.join(', ')}</dd>
    <dt>{t('src.cell')}</dt><dd className="num">{src.cell}</dd>
    <dt>{t('src.retrieved')}</dt><dd><time dateTime={src.retrievedAt}>{fmtDateTime(src.retrievedAt)}</time></dd>
    <dt>{t('src.checksum')}</dt><dd className="mono">{short(src.sha256)} <CopyButton value={src.sha256} /></dd>
    <dd className="lim">{src.limitations}</dd>
  </dl>
</article>
```

```css
.label { background: var(--surface); border: 1px solid var(--rule-2); border-radius: var(--radius-s); }
.label header { display: flex; justify-content: space-between; flex-wrap: wrap; gap: var(--space-2); padding: var(--space-3) var(--space-4); border-bottom: 1px solid var(--rule-2); }
.label dl { margin: 0; padding: var(--space-3) var(--space-4); display: grid; grid-template-columns: auto 1fr; gap: var(--space-1) var(--space-3); font-size: var(--text-sm); }
.label dt { color: var(--ink-3); } .label dd { margin: 0; min-width: 0; }
.label .lim { grid-column: 1 / -1; color: var(--ink-2); border-top: 1px solid var(--rule); padding-top: var(--space-2); }
```

## 8. ReviewSlip

A determination slip: a person's words, signed and dated. Never edited in place; a new slip answers an old one.

```css
.slip { background: var(--surface); border: 1px solid var(--rule-2); border-radius: var(--radius-l); padding: var(--space-4); display: grid; gap: var(--space-2); }
.slip blockquote { margin: 0; font: italic var(--text-lg)/var(--leading-serif) var(--font-serif); }
.slip .who { font-size: var(--text-xs); color: var(--ink-3); }
.slip .who b { color: var(--ink-2); }
```

Attribution line: evidence symbol (farmer) or role · name or role · date · status (objection / addressed).

## 9. StatusMessage

| State | Icon (lucide) | Tokens | Example copy |
|---|---|---|---|
| loading | spinner | info | "Fetching NASA POWER data…" + what is being fetched |
| empty | `Info` | neutral | "No studies yet. Search with your crop and the symptom, for example “wheat yellowing drought”." |
| error | `TriangleAlert` | error | "NASA POWER didn't respond (502). No values are shown. Try again in a minute; your inputs are kept." + Retry |
| partial | `TriangleAlert` | warn | "Rain has no data for September. The gap is marked on the chart." |
| stale | `Clock` | neutral | "Retrieved 9 days ago. Refresh to check for newer records." |
| not built | `Construction` | neutral, dashed border | "Case sharing (F-09) isn't built yet." |
| success | `Check` | ok | "Report downloaded." |

```css
.msg { display: grid; grid-template-columns: auto 1fr; gap: var(--space-1) var(--space-3); padding: var(--space-3) var(--space-4); border-radius: var(--radius-m); font-size: var(--text-sm); }
.msg svg { width: 1.15rem; height: 1.15rem; margin-top: .15rem; grid-row: span 2; }
.msg b { font-size: var(--text-md); } .msg p { grid-column: 2; }
.msg--info { background: var(--info-bg); color: var(--info-ink); } .msg--ok { background: var(--ok-bg); color: var(--ok-ink); }
.msg--warn { background: var(--warn-bg); color: var(--warn-ink); } .msg--error { background: var(--error-bg); color: var(--error-ink); }
.msg--neutral { background: var(--neutral-bg); color: var(--neutral-ink); }
.msg--pending { background: var(--neutral-bg); color: var(--neutral-ink); border: 1.5px dashed var(--rule-2); }
```

`role="status"` for loading/partial, `role="alert"` for errors. Skeletons, if any, match the final layout in `--surface-tint`, without shimmer.

## 10. Hypotheses table

Columns: Explanation · Supports it · Argues against · Would settle it. Each item is a symbol + short text; the explanation cell carries the `HYPOTHESIS` label. A real `<table>` with `scope="col"` headers inside an `overflow-x: auto` wrapper; under 48rem it becomes one stacked block per hypothesis (headers become small labels). Never a confidence percentage or a ranking score.

## 11. Section heading

`h2` + optional evidence label on the right + one sentence of context under it. No eyebrow above the heading, no numbering.

```css
.section-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: var(--space-2) var(--space-4); margin-bottom: var(--space-4); }
.section-head h2 { font-size: var(--text-xl); font-weight: var(--weight-bold); }
.section-head p { color: var(--ink-2); font-size: var(--text-sm); flex-basis: 100%; }
```
