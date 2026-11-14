---
name: agro-design-system
description: The "Field Survey" design language for AGRO BLACK BOX — light mode only, in the team's bright "hopecore" palette (Celestial Blue, Cal Poly Pomona Green, May Green, Yellow-Green, Pearl Aqua), with structure borrowed from survey-map legends, technical-drawing title blocks and herbarium labels, and explicit rules against AI-generated-looking UI (adapted from impeccable and taste-skill). Use this skill whenever you create, restyle or extend anything visual in frontend/ — React components, CSS, layouts, the landing page, charts, icons, empty/error states, UI copy — and whenever someone asks about colours, fonts, spacing, "the look", industrial or solarpunk style, or how a screen from docs/product/UX_FLOWS.md should look, even if they don't name the design system.
---

# AGRO BLACK BOX — Field Survey design system

> **Status: PROPOSED.** Binding once the frontend design-system Issue is `team-approved` (`docs/governance/FEATURE_POLICY.md`). Until then follow it for consistency, but don't call it an approved decision.

**What it must feel like:** a clear, hopeful working tool. Industrial in the sense of honest, legible and operable; solarpunk in the sense of bright, alive and on the side of the people who farm. It must not look generated: no template scaffolds, no costumes, no decoration without a job.

## Before you design anything

1. Read `docs/product/UX_FLOWS.md`, `frontend/AGENTS.md` and `docs/science/SCIENTIFIC_POLICY.md`. This skill serves them and never overrides them.
2. Check `docs/operations/CURRENT_STATE.md` / `docs/architecture/API_CONTRACTS.md`. A screen for an endpoint that doesn't exist shows a *not built yet* state, never invented content.
3. Make sure `frontend/src/design/tokens.css` exists; if not, copy `assets/tokens.css` there (part of the design-system Issue). Never declare colours locally.
4. Open `assets/specimen.html` in a browser. It shows two real screens (forensics workspace, landing) and the system sheet. Match it.
5. Decide the **mode** of the surface (from impeccable): **Operate** for app screens (cases, cockpit, science desk, rotation lab, review, settings): scanability and standard controls beat expression. **Persuade** for the landing page: the world can speak louder. **Read** for the case report and docs.

## The world, in one paragraph

The visual world comes from graphic traditions the audience already knows, not from instruments: **survey-map legends** (a small symbol per kind of thing, explained once, used everywhere), **technical-drawing title blocks** (one ruled block that states what this sheet is, its ID, scale and date), and **herbarium labels and determination slips** (a provenance label on every specimen, and later reviewers adding signed notes). Those give us type rhythm, density and one signature move. The palette is the team's hopecore set. Layout, navigation and controls stay the standard web ones. Full rationale and the ban list: `references/world.md`.

## Tokens (full source: `assets/tokens.css`)

**Palette** — team colours, light mode only:

| Colour | Hex | Role |
|---|---|---|
| Cal Poly Pomona Green | `#144425` | App rail (`--surface-shell`), primary button text, literature symbol |
| Yellow-Green | `#b5d98a` | **The one primary action per view** (`--action`), current-step marker on the rail |
| May Green | `#46953d` | Farmer-reported symbol and success (text uses the darker `--c-may-ink`) |
| Celestial Blue | `#4b9dd2` | Observed data, links, focus, info, landing hero band (text uses `--c-celestial-ink`) |
| Pearl Aqua | `#88dbc0` | Grounds and tints (`--surface-sunken`, `--surface-tint`), model scenarios (`--c-aqua-ink` for text) |

Rules: components use **semantic tokens only** (`--surface*`, `--ink*`, `--action*`, `--ev-*`, `--viz-*`, status pairs). The light brand hues fail contrast as text on white, so text always uses the `-ink` steps the tokens provide. Red and amber exist **only for status** (error, warning, hypothesis). Contrast check after any change:

```bash
node .claude/skills/agro-design-system/scripts/check-contrast.mjs
```

**Type** — one family for the interface:
- `--font-sans` **Atkinson Hyperlegible Next**: UI, headings, numbers. It was designed by the Braille Institute for low-vision readers (it fits older users reading phones outdoors), and it isn't on the "overused AI fonts" lists. Display (landing h1, case name) uses weight 800 with slight negative tracking.
- `--font-serif` **Source Serif 4 italic**: only for people's own words (farmer notes, review slips, verified quotes) and species names, the way maps set natural names in italic serif.
- `--font-mono` **Atkinson Hyperlegible Mono**: only for values people copy or compare (case IDs, variable codes, checksums, DOIs). Never as a "technical" costume for labels.
- Scale `--text-xs` … `--text-3xl`, `--text-display` (landing only). Body 16px minimum, prose ≤ 66ch, `tabular-nums` for numbers in tables and charts. Sentence case everywhere; no all-caps labels.
- Self-hosting via `@fontsource` needs the dependency approved in an Issue; fallbacks in the tokens keep the UI usable meanwhile.

**Space and shape:** 4px base (`--space-1…9`). Radii by role: `--radius-s` 3px (inputs, labels, table cells), `--radius-m` 8px (buttons, panels), `--radius-l` 14px (review slips, dialogs, screen frames). Structure comes from rules (`--rule`, `--rule-3`), not shadows; only floating layers use `--shadow-float`.

**Motion:** exponential ease-out (`--ease-out`), 120–320ms, only in answer to a user action (drawer opens, row expands). A spinner only while a request is in flight. No bounce, no pulsing dots, no entrance animations on scroll. Reduced motion zeroes the durations.

## The evidence legend (the system's backbone)

Every piece of evidence carries a legend symbol + its text label + its colour, drawn as inline SVG from one sprite (never Unicode glyphs or emoji):

| Kind (UX_FLOWS code) | Symbol | Why this symbol |
|---|---|---|
| `OBSERVED` | filled square, celestial | a measured value, like a survey benchmark |
| `FARMER_REPORTED` | filled circle, May green | a person on the land |
| `LITERATURE_REVIEWED` | filled triangle, Cal Poly green | a triangulation vertex: a verified reference point |
| `HYPOTHESIS` | dashed ring, amber | maps draw unconfirmed boundaries dashed |
| `MODEL_SCENARIO` | hatched square, aqua ink | a computed area |
| `ILLUSTRATIVE` | open diamond, red | not real data; always with a sentence saying so |
| `MISSING_DATA` | dotted square, grey | no data here |

OpenAlex search results are "Metadata only" (an info status), never `LITERATURE_REVIEWED`. The legend is explained once on the landing page and in the report, then used everywhere without explanation. Recipe: `references/components.md#legend`.

## Signature move: the case title block

Each case screen opens with a ruled title block, like the cartouche of a technical drawing: case name and one-line description (large cell), then case ID, location (privacy-rounded), status, data scale, period, reviewer. It answers "what am I looking at, at what resolution, how private, how sure" before any chart, and it's the one memorable element. Spend boldness there and keep the rest quiet. Recipe: `references/components.md#title-block`.

## Rules that are easy to get wrong

1. **Evidence honesty:** every scientific value has its legend symbol, unit, comparison basis and source. Provenance lives in a Sources panel of herbarium-style labels (dataset, variables, cell, resolution, retrieved, checksum, limitations): only fields the API returns; missing ones shown as `MISSING_DATA`.
2. **States:** every async region handles loading, empty, error, partial, stale, and "not built yet". Errors name the source and the status and keep the user's input. A failed request never shows sample numbers.
3. **ILLUSTRATIVE** data gets a red banner with the diamond symbol and a sentence. `/api/rotations/demo` output is illustrative today.
4. **One primary action per view** (yellow-green). Everything else is secondary (outlined) or text buttons.
5. **Colour is never the only cue:** status = icon + text; evidence = symbol + label; chart series = label + position.
6. **Charts:** `references/dataviz.md`. BrBG for rain, RdBu for temperature, zero line drawn, one honest scale, units in labels, text summary + table alternative.
7. **Privacy:** location shown with its rounding/privacy tier, never precise coordinates in shared views or URLs.
8. **Bilingual EN/ES:** no hardcoded strings; `Intl.*` for numbers, dates, units; allow ~30% longer Spanish.
9. **No new runtime dependency without an approved Issue** (fonts, MapLibre, chart libraries). Plain SVG until then.
10. **Theme browser surfaces too:** `::selection` (highlight), `caret-color`, `accent-color`, scrollbar colours, focus ring, link underline offset. This is the cheapest sign a UI was built rather than assembled.

## Not allowed (AI-generated tells, from impeccable/taste-skill, adapted)

- Eyebrow/kicker labels above headings; section numbers (01/02/03) unless the content is a real sequence (the 7 case steps are).
- The hero-metric template (big number + small label + stat strip); rows of identical icon-heading-text cards; nested cards.
- Gradient text, glassmorphism, decorative gradients or repeating stripes, hard offset shadows, coloured `border-left`/`border-top` accents on cards.
- Monospace as a costume, pulsing "live" dots, bounce easing, entrance animations on every section.
- Instrument/cockpit costumes on working screens (dark gauges, fake bezels, terminal styling).
- Overused faces (Inter, Roboto, Fraunces, Geist, Space Grotesk, Plus Jakarta Sans) unless the team decides otherwise.
- Copy tells: "seamless", "empower", "unlock", "revolutionary", "In today's world…", stat strips, "X. Y." two-fragment headings, em-dash-heavy prose, arrows glued to every link. Write plainly: buttons are a verb + object ("Download case report").

## Frontend file layout (proposed, so three people can work in parallel)

```
frontend/src/
  design/     tokens.css, base.css, icons.svg (legend + UI sprite), components/
              (Button, Field, EvidenceLabel, TitleBlock, SourceLabel, ReviewSlip, StatusMessage, StepRail)
  features/   landing/ cases/ intake/ forensics/ science/ rotations/ review/ report/ settings/
  i18n/       en.json, es.json, useT.ts
  api/        typed client (generated from OpenAPI when schemas stabilise)
  app/        App.tsx, routes, shell
```

Feature folders own their screens; shared visuals live only in `design/`. Changing a shared component or token is a cross-team change: say so in the PR.

## Workflow for any UI task

1. **Plan** in the PR description: surface and mode, which evidence kinds appear, which states, which components, and the copy. Start from the wireframes in `references/screens.md`.
2. **Check the plan** against the "Not allowed" list. If any element would look the same on any other product, rewrite it from this product's content.
3. **Build** with semantic tokens and shared components.
4. **Look and check:** run the `agro-ui-review` skill. It screenshots desktop and mobile, runs the impeccable detector and the contrast check, and applies the checklist. Fix what one look shows, then look again once.

## Reference files

- `assets/tokens.css` — all tokens (copy to `frontend/src/design/tokens.css`).
- `assets/specimen.html` — rendered reference: forensics workspace, landing page, system sheet.
- `references/components.md` — recipes: base CSS, Button, Field, EvidenceLabel/legend sprite, TitleBlock, StepRail, SourceLabel, ReviewSlip, StatusMessage, hypotheses table.
- `references/screens.md` — layouts and wireframes for the landing page and the 8 UX_FLOWS screens.
- `references/dataviz.md` — chart rules.
- `references/world.md` — where the world comes from, how industrial and solarpunk show up, the full ban list and its sources.
- `scripts/check-contrast.mjs` — WCAG check of every documented token pair.

## Sources

impeccable by Paul Bakaus (Apache-2.0): Operate/Persuade modes, the craft floor and anti-pattern bans, the rule that a working screen's world lends only type, palette, density and one signature move. taste-skill by Leonxlnx (MIT): copy tells and plain-copy rules. Anthropic's frontend-design skill: plan → review → build → critique. Vercel Web Interface Guidelines (MIT): used in `agro-ui-review`. ColorBrewer (BrBG, RdBu), WCAG 2.2. Ideas are paraphrased; no text is copied from those projects.
