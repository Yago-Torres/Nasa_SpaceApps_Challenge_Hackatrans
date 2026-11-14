# Data visualisation rules

Charts in AGRO BLACK BOX are evidence. A chart that overstates, hides units or blends observed with modelled values is a scientific error, not a style issue. The backend computes every value; the frontend only draws what the API returns (frontend/AGENTS.md: no scientific computations in TS — scaling for pixels is fine, deriving new statistics is not).

Until a chart library is approved by Issue, draw with plain SVG in React (the current anomaly chart needs nothing more).

## Universal rules

1. **Title says what is compared**: "Monthly rain in 2022 compared with 2010–2021". Not "Precipitation anomaly".
2. **Units in the axis title or value labels** (`mm`, `°C`), formatted with `Intl.NumberFormat` and an explicit sign for anomalies (`+12 mm`, `−3.1 °C`; use the real minus sign U+2212).
3. **Zero baseline always drawn** in `--viz-baseline` (2px) for anomaly charts; bars grow from it.
4. **Honest scale**: one shared linear scale per chart, computed from the data range (symmetric around zero for anomalies). No visual caps that make values incomparable — if an outlier dominates, annotate it rather than clipping silently. (The current baseline UI caps bar widths; replace that.)
5. **Missing values are visible**: a hatched empty cell with `n/a` and a `MISSING_DATA` note, never a zero-height bar.
6. **Evidence label on every chart** (■ Observed for POWER, ▨ Model scenario, ◇ Illustrative…), placed in the section heading. Mixed charts (observed + modelled) use solid marks for observed and hatched/dashed for modelled, with legend entries saying so.
7. **Incident window** highlighted with `--viz-event` (pale yellow-green band) and labelled ("Damage reported, April–June").
8. **Accessible**: `<figure>` + `<figcaption>`; SVG with `role="img"` and `aria-labelledby` pointing to a title and a one-sentence summary written from data the API returned ("Rain was below the reference in 5 of 6 months from April to September"); provide a "Show as table" toggle with the same values. Tooltips also reachable by keyboard focus.
9. **Colour never alone**: diverging ramps are paired with sign and position (bars left/right or up/down of zero).
10. **Tabular numerals** for all labels; axis ticks `--text-2xs` in `--viz-axis`; gridlines `--viz-grid` 1px, horizontal only.

## Palettes

| Use | Tokens | Notes |
|---|---|---|
| Precipitation anomaly | `--viz-dry-3…1`, `--viz-neutral`, `--viz-wet-1…3` | ColorBrewer BrBG. Brown = drier than reference, teal = wetter. |
| Temperature anomaly | `--viz-cold-3…1`, `--viz-neutral`, `--viz-hot-1…3` | ColorBrewer RdBu reversed. |
| Rotation scenarios | `--viz-cat-1…4` | Team palette (ink steps). Current rotation always `--viz-cat-1`. Max 4 series. |
| Event window | `--viz-event` | Pale yellow-green band. |

Bin anomaly magnitude into the 3 steps per side using thresholds **provided by the backend** (or plain sign + magnitude as length if none) — don't invent significance thresholds in the UI.

## Chart patterns

- **Monthly anomalies** (`/api/climate`): rain bars (BrBG) with a Tmax difference row of 12 labelled cells (RdBu) aligned under the months. Vertical bars on desktop; under 48rem switch to horizontal bars (one row per month) so labels stay at 12px, and wrap the Tmax row into 6 columns.
- **Timeline** (F-04): horizontal time axis with one lane per evidence kind, each using its legend symbol as the marker (■ observed values, ● farmer events, dashed spans for hypotheses). Lanes make the separation of kinds structural.
- **Rotation comparison** (F-07): crop-calendar strips (season cells) + a qualitative comparison matrix. No radar charts, no fabricated scores.
- **Evidence graph** (F-06): nodes carry their legend symbol and label; edges are labelled lines, solid for "supports", dashed for "argues against". Provide an equivalent nested list (same as the hypotheses table) for keyboard and screen-reader users.
- **Headline numbers**: put each number in the sentence or heading it supports ("Rain was 142 mm below average from April to June"), with unit and comparison basis. No big-number tiles or stat strips.

## Anti-patterns

Pie/donut charts for anomalies, 3D, dual y-axes with different units on one plot, rainbow ramps, gradients inside bars, animated count-ups of scientific values, percentages without validated uncertainty, sparklines without axes used as evidence.
