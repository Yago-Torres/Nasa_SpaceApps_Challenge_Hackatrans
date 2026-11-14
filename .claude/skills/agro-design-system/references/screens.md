# Screens — layouts and wireframes

Derived from `docs/product/UX_FLOWS.md`. Desktop wireframes assume ≥1024px; mobile 390px. Every screen shares the **shell**: top bar (brand mark, case switcher, language EN/ES, theme, account) + sun-arc journey band when a case is open. Content is **left-aligned** on a 12-column grid inside `--container-max`; only the landing hero may centre a single statement.

Backend reality check (Nov 2026, see CURRENT_STATE): only `/api/climate`, `/api/literature`, `/api/rotations/demo`, `/api/report`, `/api/health` exist. Screens 1, 6, 8 and persistence in 2 need APIs that aren't built — design them, but render their data regions with the `pending` StateView, never with fake records.

## Contents

0. Landing (hackathon / public)
1. Cases dashboard
2. Incident intake
3. Forensics cockpit
4. Science desk
5. Rotation lab
6. Collaborative review
7. Case report
8. Admin / settings
9. Responsive rules

---

## 0. Landing

Purpose: in 10 seconds a judge or farmer understands what the tool does, sees it's honest about data, and can start an investigation. The most characteristic thing in this subject is **the moment of investigation**: a location + a year turning into observed evidence. So the hero is a live instrument, not a stock photo.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ■ AGRO BLACK BOX                          EN|ES   ◐   [Open the lab] │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Every failed harvest leaves a record.      ┌─ instrument (live) ──┐ │
│  (Archivo expanded, heavy)                  │ 41.6°N 0.9°W · 2022  │ │
│                                             │ ▁▂▅▇▅▂▁ rain anomaly │ │
│  Read it with NASA observations, verified   │ [OBSERVED] POWER     │ │
│  science and the knowledge of the people    │ [Investigate ▸]      │ │
│  who farm it. (Fraunces, human voice)       └──────────────────────┘ │
│                                                                      │
│  [Start an investigation]  [See how evidence is labelled]            │
│ ════════════════════════════ structural beam ═══════════════════════ │
│  The path of a case  (sun-arc, static, 7 stations, short captions)   │
│     ◯───◯───◯───☀───◯───◯───◯                                        │
├──────────────────────────────────────────────────────────────────────┤
│  What a label means: the 7 epistemic tags, each with one sentence    │
│  [OBSERVED] [FARMER_REPORTED] [LITERATURE_REVIEWED] [HYPOTHESIS]…    │
├──────────────────────────────────────────────────────────────────────┤
│  Data sources: data plates for NASA POWER, OpenAlex (+GPM/HLS        │
│  marked "planned")    ·   Team / Space Apps 2026 / no NASA endorsement│
└──────────────────────────────────────────────────────────────────────┘
```

- The hero instrument calls the real `/api/climate` when the user presses Investigate. Before that it shows an **empty instrument** with the prompt, not a pre-rendered chart. If the team wants a static preview image, it carries the `ILLUSTRATIVE` tape.
- "See how evidence is labelled" scrolls to the tag legend — this section is a differentiator for judges (scientific honesty).
- Mobile: hero text first, instrument below, sun-arc becomes a vertical list of 7 stations with one line each.

## 1. Cases dashboard

```
┌ shell ───────────────────────────────────────────────────────────────┐
│ My cases            [Filter: Owned|Shared|Public] [Search…] [New case]│
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ Case                Region (rounded)  Step      Reviewer  Updated │ │
│ │ Ebro wheat 2022     Aragón, ES        ☀ 4/7     —         2 d ago │ │
│ │ …                                                                  │ │
│ └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

A table, not a card grid: people scan and sort cases. Step column shows a mini sun-arc progress (text "4 of 7" for screen readers). Privacy tier icon + text next to region. Filters live in URL params. Until F-01/F-02 exist: `pending` state with explanation and a "Start a one-off investigation" action that goes to intake without persistence.

## 2. Incident intake

Single column form, max width ~40rem, grouped in fieldsets that mirror the journey: **Where** (privacy tier first, then location — map optional), **What was grown** (crop history per year as a repeatable row), **What happened** (symptoms, dates; free text in Fraunces preview as "your words"), **Constraints** (water, soil, priorities), **Consent**. Each farmer-provided group gets the `FARMER_REPORTED` leaf tag in its legend, so users see from the start how their input will be labelled. Inline validation on blur, errors announced, first error focused on submit. Primary action: "Investigate with NASA".

Mobile: same form, sticky bottom action bar with safe-area padding.

## 3. Forensics cockpit

The densest screen. Industrial layer dominates.

```
┌ shell + sun-arc ─────────────────────────────────────────────────────┐
│ ┌ rail (case) ─┐ ┌ main ───────────────────────────────┐ ┌ drawer ──┐│
│ │ Location     │ │ [Readout: rain Apr–Jun −142 mm]     │ │ Data     ││
│ │ privacy tier │ │ [Readout: Tmax Jul +3.1 °C]         │ │ plate    ││
│ │ Source ▾     │ │ ┌ Weather timeline [OBSERVED] ────┐ │ │ request  ││
│ │ POWER ✓      │ │ │ diverging bars, event band,      │ │ │ params   ││
│ │ GPM (planned)│ │ │ baseline, units, legend          │ │ │ limits   ││
│ │ HLS (planned)│ │ └──────────────────────────────────┘ │ │ copy cite││
│ │ Reference    │ │ ┌ Hypotheses [HYPOTHESIS] ─────────┐ │ └──────────┘│
│ │ 2010–2021    │ │ │ each with for/against/missing    │ │             │
│ │ (short!)     │ │ └──────────────────────────────────┘ │             │
│ └──────────────┘ └──────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────────────────┘
```

- Map (once MapLibre/Leaflet is approved) goes at the top of the rail as a small locator with the grid cell footprint drawn — showing that the observation covers ~50 km, not the parcel.
- Hypotheses list competing explanations side by side; never a single "cause" or a confidence %. Each hypothesis links to supporting/contradicting evidence and the measurements that would change the decision (Uncertainty Hunter, F-08 — pending).
- Drawer is closed by default on <1280px.

## 4. Science desk

Search bar with the case question pre-filled → results list. Each result: title (links to DOI), year, venue, `Metadata only` chip until a human reviews it. Review action opens a structured form (claim, method, study context, region, limitations, verified quote within rights) → on save the finding becomes `LITERATURE_REVIEWED` with reviewer attribution. Contradicting findings are shown next to each other with a "conflict" connector, not hidden. Empty state teaches how to phrase a question.

## 5. Rotation lab

```
│ Your priorities: [water ▮▮▮▯] [soil ▮▮▯▯] [income ▮▮▮▮]  (chips, editable) │
│ ┌ Current rotation ──┐ ┌ Alternative A ────┐ ┌ Alternative B ────┐      │
│ │ wheat│barley│fallow│ │ wheat│pea│barley  │ │ wheat│vetch│sunfl. │      │
│ │ assumptions        │ │ assumptions       │ │ assumptions       │      │
│ │ tradeoffs (text)   │ │ tradeoffs         │ │ tradeoffs         │      │
│ │ uncertainties      │ │ uncertainties     │ │ uncertainties     │      │
│ └────────────────────┘ └───────────────────┘ └───────────────────┘      │
│ Comparison matrix (rows = criteria, cols = rotations, qualitative cells  │
│ with reasons + source links; no unjustified numbers)                     │
```

Always ≥3 options including current, same scenario for all. Today's data is `ILLUSTRATIVE` (demo endpoint): survey tape around the whole lab + banner explaining it. Mobile: cards stack, comparison matrix becomes per-criterion accordions.

## 6. Collaborative review

Thread per hypothesis/finding. ReviewNote components (organic, Fraunces) with role badge (Farmer / Agronomist / Community reviewer), status (open, addressed, objection), and an audit trail in machine font. Shared views show rounded location only. Moderation actions for admins are secondary buttons with confirmation. Pending until F-09.

## 7. Case report

A print-first document view: case snapshot header (data plate of the case: ID, snapshot time, version), sections in journey order, every figure with its source plate, a "Limitations" section that can't be removed, references with DOIs. Actions: "Download Markdown" (exists today via `/api/report`), later PDF. `@media print` stylesheet: no shell, no journey, black on white, tags rendered as bracketed codes `[OBSERVED]`.

## 8. Admin / settings

Plain settings form: language, units (metric default; °C/mm), theme (Daylight / Night shift / System), data permissions, sharing defaults, audit log table. Industrial and quiet — no motifs.

## 9. Responsive rules

- Breakpoints: 48rem (tablet), 64rem (desktop), 80rem (wide cockpit with drawer pinned).
- Cockpit: 3 columns ≥80rem → 2 columns + overlay drawer ≥64rem → single column with rail as collapsible summary and drawer as bottom sheet <64rem.
- Tap targets ≥44px; no hover-only affordances; tables become stacked definition lists under 48rem.
- Test at 390×844 and 1440×900 in both themes, plus 200% zoom.
