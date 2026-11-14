---
name: agro-design-system
description: The "Solar Industrial" design language for AGRO BLACK BOX — industrial web design (instrument panels, data plates, honest structure, high legibility) with a solarpunk layer (daylight-first palette, sun-arc journey, organic shapes for living and human data). Use this skill whenever you create, restyle or extend anything visual in frontend/ — React components, CSS, layouts, the landing page, charts, icons, empty/error states, copy on screens — and whenever someone asks about colours, fonts, spacing, theming, "the look", industrial or solarpunk style, or how a screen from docs/product/UX_FLOWS.md should look, even if they don't mention the design system by name.
---

# AGRO BLACK BOX — Solar Industrial design system

> **Status: PROPOSED.** This is the team's draft design language. It becomes binding once the frontend design-system Issue is `team-approved` (see `docs/governance/FEATURE_POLICY.md`). Until then, follow it for consistency but don't describe it as an approved product decision.

The product is a forensic lab for agricultural incidents. People open it after something went wrong in their field. The interface has two jobs at once: be as **trustworthy and legible as an instrument** (industrial), and feel like **a tool for a hopeful, repairable future** built with communities (solarpunk). The two layers aren't decoration on top of each other — each one encodes meaning.

## Before you design anything

1. Read `docs/product/UX_FLOWS.md`, `frontend/AGENTS.md` and `docs/science/SCIENTIFIC_POLICY.md`. The design system serves those rules; it never overrides them.
2. Check `docs/operations/CURRENT_STATE.md` / `docs/architecture/API_CONTRACTS.md` for what the backend actually provides. A screen for an endpoint that doesn't exist must show a conspicuous *pending* state, not fake content.
3. Make sure `frontend/src/design/tokens.css` exists. If it doesn't, copy `assets/tokens.css` there (that's part of the design-system Issue). Never re-declare colours locally.
4. Open `assets/specimen.html` in a browser (or read it) to see every primitive rendered. It's the visual reference — when in doubt, match it.

## The core idea: structure is meaning

| Layer | What it represents | Visual vocabulary |
|---|---|---|
| **Industrial** | Machines, measurements, NASA observations, computations, provenance | Rectilinear panels with 2px radius, visible structural lines, data plates (equipment nameplates), dark instrument readouts, condensed grotesque labels, tabular numerals, safety-coded status |
| **Solarpunk** | Living systems, people, communities, farmer knowledge, hope/repair | Daylight palette, sun-arc journey, chlorophyll and solar-gold accents, organic radii (leaf, seed), serif "human voice", curved mycelium connectors |

So a satellite reading *looks* like an instrument and a farmer's note *looks* like a person wrote it. This is what keeps the product honest: OBSERVED data and FARMER_REPORTED data must never be visually confusable (product invariant: "never confuse observed satellite/regional data with parcel ground truth").

### Shape grammar

- **Instrument** (`--radius-instrument`, 2px): panels, charts, data plates, observed values, tables.
- **Control** (`--radius-control`, 6px): buttons, inputs, selects.
- **Leaf** (`--radius-leaf`, two opposite rounded corners): FARMER_REPORTED chips, local notes.
- **Organic** (`--radius-organic`, 20px): people, community review cards, avatars containers, invitations.
- **Dashed outline**: unproven things — HYPOTHESIS, pending features.
- **Hatched fill**: MODEL_SCENARIO (computed under assumptions).
- **Striped "survey tape" border**: ILLUSTRATIVE / demo data. Loud on purpose.
- **Empty hatched outline**: MISSING_DATA.

Don't use one radius for everything. Hierarchy and meaning come from varying it.

## Tokens (summary — full source in `assets/tokens.css`)

**Colour roles** (semantic tokens only in components):

- Chassis: `--surface-base` (galvanized steel in daylight), `--surface-raised` (panels), `--surface-sunken` (wells), `--surface-readout` (instrument displays — dark in both themes, like real gauges).
- Ink: `--ink-strong`, `--ink`, `--ink-muted`, `--ink-readout` (phosphor green on readouts), `--ink-link`.
- **Recorder orange** `--action-bg` / `--brand`: real flight recorders are painted international orange. Use it for the brand mark and **one primary action per view** (e.g. "Investigate with NASA"). Text on it is always `--action-ink` (dark), like a safety label. Never orange body text.
- **Solar gold** `--sun`: the sun-arc, highlights of the incident window, HYPOTHESIS. Never for text on light backgrounds.
- **Chlorophyll** `--growth`: healthy/complete state, living data, FARMER_REPORTED.
- **Sky** `--focus-ring`, `--ink-link`, OBSERVED, water/precipitation.
- Status pairs `--status-{ok,caution,danger,info,stale}-{bg,ink}` — always with an icon *and* a text label.

**Type:**

- `--font-industrial` (Archivo, variable width): UI, headings, numbers. Use `font-stretch: var(--stretch-condensed)` for instrument labels and dense tables, `--stretch-expanded` + heavy weight for display headings on the landing page.
- `--font-human` (Fraunces, soft): only for human voice — farmer reports, community comments, quotes from verified literature, the hero statement. It signals "a person said this".
- `--font-machine` (IBM Plex Mono): only for machine values a person may copy/compare — SHA-256, coordinates, request params, DOIs, IDs. Not for decorative labels.
- Numbers in tables, readouts and charts: `font-variant-numeric: tabular-nums`.
- Scale: major third on 16px (`--text-2xs` … `--text-4xl`). Prose max width `--measure` (68ch).
- Sentence case everywhere. The only uppercase text allowed is the controlled epistemic vocabulary codes (`OBSERVED`, `HYPOTHESIS`…), because they are literal identifiers.

**Space:** 4px base (`--space-1` … `--space-11`). Panels pad `--space-5`, dense instruments `--space-4`. Grid gutter `--gutter`.

**Elevation:** structure comes from lines, not shadows. Panels: 1px `--line` border. Section dividers: 2px `--line-strong` ("structural beam"). Only floating layers (drawer, menus, toasts) use `--shadow-lift`. Readouts use `--shadow-inset-readout`.

**Themes:** *Daylight* is default (farmers read screens outdoors in strong sun). *Night shift* (dark) via `prefers-color-scheme` or `data-theme="dark"` on `<html>`. Both themes pass WCAG AA — verify after any colour change:

```bash
node .claude/skills/agro-design-system/scripts/check-contrast.mjs
```

## Signature element: the sun-arc journey

Spend the boldness here and keep the rest disciplined. The canonical journey (PRODUCT.md) is a real sequence, so it earns numbered steps:

`1 Intake → 2 NASA data → 3 Timeline → 4 Evidence → 5 Rotations → 6 Review → 7 Report`

It's drawn as the sun's path across a day: a thin arc with a station per step; the sun (solar gold disc) sits on the current step; completed steps are solid chlorophyll stations, future ones are hollow; a step blocked by missing backend support is dashed with a "pending" label. On desktop it's a header band above the cockpit; on mobile it collapses to a compact horizontal stepper with the arc as a progress line. When a step completes, the sun advances once with `--dur-sunrise` / `--ease-mechanical` — that's the one orchestrated motion moment in the app. Recipe in `references/components.md#sun-arc-journey`.

## Rules that are easy to get wrong

1. **Every scientific value carries its epistemic tag** (`<EpistemicTag kind="OBSERVED">`), its unit and its source. A number without unit + provenance is a bug.
2. **Provenance is a first-class object, not a footnote.** Use the Data plate component (dataset, endpoint, period, spatial/temporal resolution, retrieved at, SHA-256, limitations) and the provenance drawer. See `references/components.md#data-plate`.
3. **Five states for every async widget**: loading, empty, error, partial, stale (+ "pending: not built yet"). Recipes in `references/components.md#state-views`. Failure copy says what happened and how to fix it; never substitute sample data.
4. **ILLUSTRATIVE data is loud.** Survey-tape border + `ILLUSTRATIVE` tag + one-sentence explanation. E.g. `/api/rotations/demo` output is illustrative today.
5. **Colour is never the only cue.** Status = icon + text + colour. Tags = code + shape + colour. Chart series = label + pattern/position + colour.
6. **Charts** follow `references/dataviz.md`: diverging BrBG for precipitation anomaly, RdBu for temperature anomaly, zero baseline always visible, units in axis titles, incident window as a solar band, text description for screen readers.
7. **Privacy shows in the UI.** Precise coordinates are private by default: show the privacy tier next to any location, round coordinates in shared/review contexts, and never put them in URLs.
8. **Bilingual EN/ES from day one** (F-11). No hardcoded user-facing strings in components; units/dates/numbers through `Intl.*`. Spanish runs ~20–30% longer — design labels to wrap, not truncate.
9. **No new runtime dependency without an approved Issue** (fonts via @fontsource, MapLibre, chart libs included). Until approved, use the fallback font stacks and plain SVG.
10. **Motion**: one orchestrated moment (sun-arc). Otherwise only motion that answers a user action (drawer opening, row expanding). Animate `transform`/`opacity`, list properties explicitly (never `transition: all`). The recording indicator pulses only while a request is actually in flight. Reduced motion zeroes the duration tokens automatically.

## Solarpunk without kitsch

Solarpunk here is about **values made visible** — transparency (evidence brought into the light), community knowledge treated with the same dignity as satellites, repairability (every error explains its fix), and hope (the path from incident to a better rotation). It is *not* leaf clip-art, neon green gradients, or glassmorphism. Read `references/solarpunk-motifs.md` before adding any ornament; every motif there has a job and a place it's allowed.

## Industrial without coldness

Industrial here is **clarity, honesty of materials and operability** — visible structure, labelled controls, big tap targets (`--tap-min`), predictable placement, data plates that tell you exactly what a number is. It is *not* fake rivets, metal textures, hazard stripes everywhere, or dark-mode-only "hacker" UIs.

## Frontend file layout (proposed, so three people can work in parallel)

```
frontend/src/
  design/        tokens.css, base.css, motifs/*.tsx (SVG), components/* (Button, Field,
                 Panel, EpistemicTag, DataPlate, StateView, SunArcJourney, ProvenanceDrawer)
  features/      landing/ cases/ intake/ forensics/ science/ rotations/ review/ report/ settings/
  i18n/          en.json, es.json, useT.ts
  api/           typed client (generated from OpenAPI when schemas stabilise)
  app/           App.tsx, routes, layout shell
```

Feature folders own their screens; shared visuals live only in `design/`. Changing a shared component or token is a cross-team change: mention it in the PR and ping the other two.

## Workflow for any UI task

1. **Plan** (write it in the PR description or as a comment before coding): which screen/flow, which epistemic kinds appear, which states, which tokens/components you'll reuse, ASCII wireframe for desktop and mobile. Wireframes for every screen are in `references/screens.md` — start from them.
2. **Check the plan against this skill**: is the boldness spent only on the sun-arc / the one memorable thing? Any generic default sneaking in (identical rounded cards everywhere, gradient washes, ALL-CAPS eyebrows above every heading, `01 / 02` numbering on things that aren't sequences, `→` glued to every button)? Revise.
3. **Build** with semantic tokens and shared components. No raw hex, no magic pixel values outside tokens.
4. **Critique**: screenshot desktop (1440) and mobile (390) in both themes and look at them. Run the `agro-ui-review` skill (it includes a screenshot script and the accessibility/scientific-honesty checklist). Remove one accessory before shipping.

## Copy voice

Plain, specific, calm — the tone of a good field technician. Name things as the user knows them ("rain compared with 2010–2021", not "PRECTOTCORR anomaly"); show the technical name in the data plate. Buttons say what happens ("Download case report", "Buscar artículos"). Errors don't apologise and always offer a next step. Uncertainty is stated, never hidden: "This is regional gridded weather, not a reading from your field."

## Reference files

- `assets/tokens.css` — the full token source. Copy to `frontend/src/design/tokens.css`.
- `assets/specimen.html` — rendered specimen of palette, type, tags, data plate, states, sun-arc, buttons. Open it to see the system.
- `references/components.md` — component recipes (TSX + CSS): Button, Field, Panel, EpistemicTag, DataPlate, StateView, SunArcJourney, ProvenanceDrawer, RotationCard, ReviewNote.
- `references/screens.md` — layouts and ASCII wireframes for the landing page and the 8 screens in UX_FLOWS, desktop + mobile.
- `references/dataviz.md` — chart rules for anomalies, timelines, rotation comparisons and the evidence graph.
- `references/solarpunk-motifs.md` — the allowed motifs, their meaning and where they may appear.
- `scripts/check-contrast.mjs` — WCAG contrast validation of all token pairs in both themes.

## Sources this skill builds on

Anthropic's `frontend-design` skill (plan → review against brief → build → critique, avoiding templated defaults), Vercel's Web Interface Guidelines (MIT; used in `agro-ui-review`), ColorBrewer diverging palettes (BrBG, RdBu) and WCAG 2.2.
