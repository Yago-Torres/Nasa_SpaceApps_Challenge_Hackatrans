# UI review checklist

Check in order; A and B matter most in this product. IDs are cited in findings (`[MAJOR C6]`).

## A. Scientific honesty & privacy (project-specific, highest priority)

- **A1** No hardcoded, sample or simulated scientific values rendered as if live. Fixtures/demo data only behind a conspicuous `ILLUSTRATIVE` label (survey-tape style + explanation). A failed request never falls back to fixture data.
- **A2** Every scientific value/chart/card shows its epistemic kind with the controlled vocabulary: `OBSERVED`, `FARMER_REPORTED`, `LITERATURE_REVIEWED`, `HYPOTHESIS`, `MODEL_SCENARIO`, `ILLUSTRATIVE`, `MISSING_DATA`. OpenAlex search results are "Metadata only", never `LITERATURE_REVIEWED`.
- **A3** Values carry units and comparison basis ("vs 2010–2021"); anomalies show sign with a true minus (−).
- **A4** Provenance reachable from every observation: dataset, parameters, period, resolution, retrieval time, checksum, limitations — only fields the API actually returns; absent fields shown as `MISSING_DATA`, not invented.
- **A5** No causal language beyond the evidence ("caused by drought"), no confidence percentages for hypotheses, no yield/water-saving percentages without a validated model + uncertainty from the backend.
- **A6** Observed regional data and farmer reports are visually distinct (shape grammar) and never merged into one undifferentiated series.
- **A7** Rotation comparisons show ≥3 options including current, with assumptions, limitations and uncertainties visible (not hidden behind a toggle).
- **A8** Limitations/disclaimers from the API are rendered, not dropped or truncated.
- **A9** No scientific computation in TypeScript (aggregations, anomalies, scores). Pixel scaling is fine.
- **A10** Privacy: precise coordinates aren't put in URLs, logs, analytics or shared/review views; privacy tier shown beside locations; private by default.
- **A11** UI for endpoints that don't exist yet is marked pending, not backed by mock data.

## B. States & failure

- **B1** Every async region handles loading, empty, error, partial and stale (UX_FLOWS). Each state says what happened and what to do next.
- **B2** Errors: specific (source + status), no apology, offer retry/fix, preserve user input.
- **B3** Loading text ends with "…" and names the source ("Fetching NASA POWER data…"); busy buttons keep their width and are disabled only while the request runs.
- **B4** Live regions: `aria-live="polite"` for loading/partial updates, `role="alert"` for errors.
- **B5** Empty states invite the next action; no broken UI for empty arrays/strings or very long text.

## C. Accessibility (adapted from Vercel Web Interface Guidelines)

- **C1** Semantic HTML first: `<button>` for actions, `<a>` for navigation, `<label>` for inputs, `<table>` for tabular data; no clickable `<div>`/`<span>`.
- **C2** Icon-only buttons have `aria-label`; decorative icons `aria-hidden="true"`.
- **C3** Visible focus on every interactive element (`:focus-visible`, 3px `--focus-ring`); never `outline: none` without a replacement; sticky bars/drawers don't cover focused elements.
- **C4** Full keyboard operation; drawers/dialogs trap and return focus, close on Esc; skip link to main content; logical heading hierarchy.
- **C5** Colour is never the only cue (status = icon + text; tags = code + shape; series = label + position/pattern). Text contrast ≥4.5:1, UI/focus ≥3:1.
- **C6** Charts: `<figure>`/`<figcaption>`, SVG `role="img"` + title/summary from real data, table alternative, keyboard-reachable tooltips.
- **C7** Forms: label per control, `name`, correct `type`/`inputmode`, `autocomplete` (off for non-auth fields), errors inline with `aria-invalid` + `aria-describedby`, focus first error on submit, never block paste.
- **C8** Touch targets ≥44px; no hover-only affordances; zoom not disabled (`user-scalable=no`, `maximum-scale=1` are blockers).
- **C9** `prefers-reduced-motion` respected (tokens do this; check custom animations).
- **C10** `lang` attribute matches the active locale; brand names and tag codes use `translate="no"`.

## D. Design-system adherence (Solar Industrial)

- **D1** Only semantic tokens (`--surface-*`, `--ink-*`, `--tag-*`, `--viz-*`, `--space-*`, `--radius-*`…) in components; no raw hex/rgb, no primitives (`--c-*`), no magic px for spacing/type.
- **D2** Shape grammar respected: instruments 2px, controls 6px, leaf for farmer data, organic for people, dashed for hypotheses/pending, hatch for model, tape only for illustrative.
- **D3** One primary (recorder orange) action per view; orange never used for body text.
- **D4** Fonts by voice: Archivo for UI, Fraunces only for human voice, Plex Mono only for machine values; tabular numerals for numbers.
- **D5** Boldness spent once (sun-arc or the one hero element); no gradient washes, identical shadowed cards everywhere, ALL-CAPS eyebrows, `01/02` numbering on non-sequences, `→` glued to buttons. Solarpunk motifs within the per-screen budget in `solarpunk-motifs.md`.
- **D6** Both themes work (daylight default, night shift); readouts dark in both.
- **D7** Shared components reused from `frontend/src/design/`; a new shared component or token change is called out in the PR for the other two developers.
- **D8** Charts follow `dataviz.md`: BrBG precipitation, RdBu temperature, zero baseline, one honest scale (no visual caps), units in axis titles.

## E. Interaction, content, performance, i18n (adapted from Vercel Web Interface Guidelines)

- **E1** URL reflects shareable state (tab, filters, selected step) — never private coordinates.
- **E2** Destructive actions need confirmation or undo.
- **E3** Animate only `transform`/`opacity`; list transition properties (no `transition: all`); animations interruptible.
- **E4** Typography: "…" not "...", curly quotes, non-breaking space between number and unit (`12&nbsp;mm`), `text-wrap: balance` on headings.
- **E5** Long content handled: `min-width: 0` on flex/grid children with text, `overflow-wrap: anywhere` for hashes/DOIs, no horizontal page scroll at 390px.
- **E6** Images have `width`/`height` and `alt`; below-fold images lazy.
- **E7** Lists >50 items virtualised or paginated; no layout reads during render.
- **E8** Copy: active voice, sentence case, specific button labels ("Download case report"), same action name throughout a flow, second person.
- **E9** i18n: no hardcoded user-facing strings; EN and ES keys both present; dates/numbers/units via `Intl.*`; layouts tolerate ~30% longer Spanish strings.
- **E10** `color-scheme` set per theme; `<meta name="theme-color">` matches `--surface-base`; native `<select>` has explicit colours.
