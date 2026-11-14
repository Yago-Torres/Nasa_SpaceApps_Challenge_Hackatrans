# Screens — layouts and wireframes

From `docs/product/UX_FLOWS.md`. Desktop ≥ 60rem, mobile 390px. Content left-aligned. Light mode only.

**App shell (Operate screens):** Cal Poly green StepRail on the left (brand, open case, 7 steps, EN/ES), work area on white, Sources panel on the right on the pale aqua ground. Under 75rem the Sources panel drops below the content; under 60rem the rail becomes a top bar with horizontally scrolling steps.

**Backend reality (Nov 2026, CURRENT_STATE):** only `/api/climate`, `/api/literature`, `/api/rotations/demo`, `/api/report`, `/api/health` exist. Screens 1, 6, 8 and case persistence need APIs that aren't built: design them, but show a "not built yet" message in their data regions, never fake records.

## 0. Landing (Persuade)

```
┌ nav: ■ CropStory   How it works  Evidence labels  Data sources  Team        EN | ES ┐
├──────────────────────── celestial band (--surface-sky) ──────────────────────────────────┤
│ Investigate a failed harvest            ┌ Start an investigation ──────────┐             │
│ with NASA Earth data   (display 800)    │ Latitude [41.6 °N] Longitude [..]│             │
│                                         │ Year of the incident [2022]      │             │
│ Enter where and when it happened…       │ [ Investigate with NASA data ]   │ ← primary   │
│ ■ NASA POWER since 1981  ▲ OpenAlex     │ Rounded to 0.1° when shared.     │             │
│                                         └──────────────────────────────────┘             │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ How each piece of evidence is marked │ ■ Observed  ● Farmer reported  ▲ Reviewed lit. … │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ How it works (the 7 steps as a short numbered list)  ·  Data sources (source labels)     │
│ Team · Space Apps 2026 · no NASA endorsement implied                                     │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

- The h1 says what the tool does and for whom (taste-skill). The first screen is the tool itself: the form calls the real `/api/climate` and opens the workspace.
- No stat strip, no feature-card grid, no screenshots of fake results. If the team adds a preview of a finished case, it carries the ILLUSTRATIVE banner.

## 1. Cases dashboard

Table, not a card grid: Case · Region (rounded) · Step (n of 7) · Reviewer · Updated. Filters (Owned/Shared/Public) and search in the URL. Primary action: "New investigation". Until F-01/F-02: "not built yet" message plus a link to start a one-off investigation.

## 2. Incident intake

Single column, max ~40rem, fieldsets in journey order: **Where** (privacy level first, then location), **What was grown** (repeatable year rows; crop names in serif italic only when they are species names), **What happened** (symptoms, dates, free text), **Constraints**, **Consent**. Farmer-provided fieldsets show the farmer symbol in their legend ("This will be marked ● Farmer reported"). Validate on blur, focus the first error on submit. Primary: "Investigate with NASA data". Mobile: sticky bottom bar with the primary button and safe-area padding.

## 3. Forensics workspace

```
┌ rail ┐┌ ILLUSTRATIVE banner (only if demo data) ─────────────────────────────────────────┐
│ ■ ABB ││ Title block: name + summary │ Case │ Location (rounded) │ Status                │
│ Case  ││                             │ Data scale │ Period │ Reviewer                    │
│ 1 ✓   │├════════════════════════════════════════════════════════════╤══════════════════┤
│ 2 ✓   ││ Rain and heat in 2022, against 2010–2021   ■ Observed      │ Sources          │
│ 3 ●   ││ one-sentence scope note                                    │ ┌ NASA POWER ──┐ │
│ 4     ││ [rain anomaly bars, incident window, zero line]            │ │ label        │ │
│ 5     ││ [Tmax difference row]                                      │ └──────────────┘ │
│ 6 ┄   ││ caption                                                    │ review slips     │
│ 7     ││ Explanations that fit so far  (hypotheses table)           │                  │
│ EN|ES ││ [Continue to evidence] [Add a local measurement] Show table│                  │
└───────┘└────────────────────────────────────────────────────────────┴──────────────────┘
```

- Map (once MapLibre/Leaflet is approved): small locator at the top of the Sources panel showing the grid cell footprint, so users see the observation covers ~50 km, not their parcel. Graticule labels in the map frame are allowed there (it is a map).
- Hypotheses: competing explanations side by side, never one "cause", never a percentage. "Would settle it" links to the Uncertainty Hunter (F-08, not built).

## 4. Science desk

Search field pre-filled from the case → results list: title (DOI link), year, venue, "Metadata only" status. "Review this study" opens a structured form (claim, method, context, region, limitations, verified quote within rights); saving turns it into ▲ Reviewed literature with reviewer and date. Conflicting findings sit side by side with an explicit "conflicts with" link. Empty state shows an example query.

## 5. Rotation lab

Priorities row (editable chips: water, soil, income, workload). Then ≥3 rotation columns, current first ("Current rotation", "Alternative A/B"): a crop-calendar strip per year, then Assumptions, Trade-offs, Uncertainties as visible text (no toggles). Below, a comparison table: rows = criteria, columns = rotations, cells = short qualitative reasons with source links; no invented numbers. Today's data is illustrative: ILLUSTRATIVE banner over the lab. Mobile: columns stack; comparison table becomes one block per criterion.

## 6. Collaborative review

One thread per hypothesis or finding, made of ReviewSlips (role, date, status: open / addressed / objection). New slips answer old ones; nothing is edited in place; the audit trail (machine font) under the thread. Shared views show rounded locations only. Not built until F-09.

## 7. Case report (Read)

Print-first page: title block at the top (with snapshot time and version), sections in step order, every figure followed by its source label, a Limitations section that cannot be removed, references with DOIs, the evidence legend at the end. "Download Markdown" exists today (`/api/report`). `@media print`: no rail, black text on white, evidence symbols kept (they print in grey).

## 8. Settings

Plain form: language, units (metric default), data permissions, sharing defaults, audit log table. No ornament.

## Responsive rules

- Breakpoints: 30rem, 60rem (rail → top bar), 75rem (Sources panel moves below).
- Tap targets ≥ 44px; no hover-only affordances; tables either scroll in their own wrapper or stack under 48rem.
- Test at 390×844 and 1440×900, plus 200% zoom and Spanish strings.
