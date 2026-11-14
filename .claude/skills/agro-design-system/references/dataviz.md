# Data visualisation rules

Charts in AGRO BLACK BOX are evidence. A chart that overstates, hides units or blends observed with modelled values is a scientific error, not a style issue. The backend computes every value; the frontend only draws what the API returns (frontend/AGENTS.md: no scientific computations in TS — scaling for pixels is fine, deriving new statistics is not).

Until a chart library is approved by Issue, draw with plain SVG in React (the current anomaly chart needs nothing more).

## Universal rules

1. **Title says what is compared**: "Monthly rain in 2022 compared with 2010–2021". Not "Precipitation anomaly".
2. **Units in the axis title or value labels** (`mm`, `°C`), formatted with `Intl.NumberFormat` and an explicit sign for anomalies (`+12 mm`, `−3.1 °C`; use the real minus sign U+2212).
3. **Zero baseline always drawn** in `--viz-baseline` (2px) for anomaly charts; bars grow from it.
4. **Honest scale**: one shared linear scale per chart, computed from the data range (symmetric around zero for anomalies). No visual caps that make values incomparable — if an outlier dominates, annotate it rather than clipping silently. (The current baseline UI caps bar widths; replace that.)
5. **Missing values are visible**: a hatched empty cell with `n/a` and a `MISSING_DATA` note, never a zero-height bar.
6. **Epistemic tag on every chart** (`OBSERVED` for POWER, `MODEL_SCENARIO`, `ILLUSTRATIVE`…). Mixed charts (observed + modelled) use solid marks for observed and hatched/dashed for modelled, with legend entries saying so.
7. **Incident window** highlighted with `--viz-event-band` (a solar band) and labelled.
8. **Accessible**: `<figure>` + `<figcaption>`; SVG with `role="img"` and `aria-labelledby` pointing to a title and a one-sentence summary written from data the API returned ("Rain was below the reference in 5 of 6 months from April to September"); provide a "Show as table" toggle with the same values. Tooltips also reachable by keyboard focus.
9. **Colour never alone**: diverging ramps are paired with sign and position (bars left/right or up/down of zero).
10. **Tabular numerals** for all labels; axis ticks `--text-2xs` in `--viz-axis`; gridlines `--viz-grid` 1px, horizontal only.

## Palettes

| Use | Tokens | Notes |
|---|---|---|
| Precipitation anomaly | `--viz-dry-3…1`, `--viz-neutral`, `--viz-wet-1…3` | ColorBrewer BrBG. Brown = drier than reference, teal = wetter. |
| Temperature anomaly | `--viz-cold-3…1`, `--viz-neutral`, `--viz-hot-1…3` | ColorBrewer RdBu reversed. |
| Rotation scenarios | `--viz-cat-1…5` | Current rotation always `--viz-cat-1`. Max 5 series. |
| Event window | `--viz-event-band` | Solar gold at low opacity. |

Bin anomaly magnitude into the 3 steps per side using thresholds **provided by the backend** (or plain sign + magnitude as length if none) — don't invent significance thresholds in the UI.

## Chart patterns

- **Monthly anomalies** (`/api/climate`): two aligned small multiples sharing the month axis — rain bars (BrBG) and Tmax dot/lollipop (RdBu). Vertical on desktop (months on x), horizontal rows on mobile (months on y) so labels stay readable.
- **Timeline** (F-04): horizontal time axis with lanes per epistemic kind: Observed lane (instrument styling), Farmer-reported lane (leaf markers), Hypothesis lane (dashed spans). Lanes make the separation of kinds structural.
- **Rotation comparison** (F-07): crop-calendar strips (season cells) + a qualitative comparison matrix. No radar charts, no fabricated scores.
- **Evidence graph** (F-06): nodes shaped by epistemic kind (square = observed, leaf = farmer, notched = literature, dashed = hypothesis); edges are curved "mycelium" connectors, solid for supports, dashed for contradicts, labelled. Provide an equivalent nested list view for keyboard and screen-reader users.
- **Headline numbers**: Readout component (see components.md), max 2–3 per screen, each with unit, comparison basis and tag.

## Anti-patterns

Pie/donut charts for anomalies, 3D, dual y-axes with different units on one plot, rainbow ramps, gradients inside bars, animated count-ups of scientific values, percentages without validated uncertainty, sparklines without axes used as evidence.
