# Scenarios, priorities and sensitivity (ABB-18)

Code: `backend/agroblackbox/services/scenarios.py`, routes in `backend/agroblackbox/rotation_api.py`. Tests: `backend/tests/test_scenarios.py` (synthetic fixtures only). Rule set `abb18-scenarios-0.1.0`.

## What it is

Two stateless endpoints build on the ABB-17 comparison (`ROTATIONS.md`). They do not change its rules or its output.

- `POST /api/v1/rotations/scenarios` runs a what-if. It modifies the farmer's priorities and/or water availability, runs the ABB-17 comparison on the modified profile, and adds three things: the calendar exposure of each strategy to labelled climate scenarios, an ordering of the strategies by the farmer's ranks with every step explained, and the trade-offs between strategies.
- `POST /api/v1/rotations/sensitivity` runs a base request and the same request with one change. The change can be a priority swap, new priorities, a water change or a new set of climate scenarios. It reports which criteria, values, strategies and positions changed, and why.

Nothing is stored. The same request always gives the same response. Each response carries `input_sha256` (sensitivity: `request_sha256`, `base_input_sha256` and `variant_input_sha256`). This is the SHA-256 of the request as canonical JSON, with defaults included and keys sorted. List order is part of the input.

## What each part of the response is

| Part | Kind | Meaning |
|---|---|---|
| `comparison` (ABB-17 strategies) | `MODEL_SCENARIO` | Rule-based options built from declared inputs. Not observed outcomes. |
| `applied_inputs` | `FARMER_REPORTED` (or what-if override) | The priorities and water availability actually used, and whether each came from the profile or an override. |
| `scenarios[]` with `HISTORICAL_EPISODE` | `OBSERVED` (`scenario_label = HISTORICAL_EPISODE_OBSERVED`) | Observed regional monthly anomalies passed in from `GET /api/climate`, with provenance. |
| `scenarios[]` with `HYPOTHETICAL` | `MODEL_SCENARIO` (`scenario_label = HYPOTHETICAL_SCENARIO`) | A user assumption about months. Not observed. |
| `exposure`, `ordering`, `trade_offs` | `MODEL_SCENARIO` | Calendar overlap and rule-based ordering computed here. |
| `verified_impact` | none | Always `null`. No validated field result exists. |

`separation[]` lists these parts in the payload itself. Every scenario has `is_forecast: false`. In line with the scientific policy, historical scenario replay is not a future weather forecast.

## What-if inputs

- `priorities_override`: ordinal ranks, which replace `profile.priorities`. A duplicate rank or a duplicate criterion is rejected with 422. An empty list means no priorities.
- `water_override`: `water_regime` and an optional `irrigation_allowance`, which replace both declared values. A rainfed regime with an allowance above zero is rejected with 422. The ABB-17 rules then apply as usual. For example, on a rainfed farm a crop grown only under irrigation is excluded, and the `WATER_REGIME` check changes. No water demand or water use is computed.
- `climate_scenarios` (at most 6, with unique `id`):
  - `HISTORICAL_EPISODE`: `episode` copies these keys unchanged from a `/api/climate` response: `source_kind` (must be `OBSERVED`), `dataset`, `data_sha256`, `retrieved_at`, `event_year`, `reference_start`, `reference_end`, `spatial_resolution`, `monthly` and optionally `limitations`. `request_params` and coordinates are **not accepted**, so private farm locations are never echoed. `flag_rules` (1–4, one per condition) set the anomaly `threshold` that flags a month. Units are explicit: `mm` for `DRIER`/`WETTER` (monthly precipitation anomaly) and `°C` for `HOTTER`/`COOLER` (monthly mean daily maximum temperature anomaly). A month is flagged `DRIER` when its anomaly is ≤ −threshold, and `WETTER`/`HOTTER`/`COOLER` work the same way. **No default threshold exists.** The threshold is the user's choice, not an agronomic or statistical threshold.
  - `HYPOTHETICAL`: `flags` give a condition and its months, for example "dry spring": `DRIER` in months 3–5. A month cannot be both drier and wetter, or both hotter and cooler. The flags have no magnitude, and no weather data is generated.
- Episode months whose anomaly is `null` (an incomplete month or insufficient reference years under ABB-08 QC) are listed as `not_evaluable_months`. They are never treated as unflagged. The ABB-08 quality flags of each flagged month are carried in `quality_flags`.

## Calendar exposure (`exposure[]`, one per strategy and scenario)

For each cycle year, the crop's months in the field come from the farmer-declared windows, using the same calendar model as ABB-17:

- `months_in_field_certain`: from the latest sowing month to the earliest harvest month.
- `months_in_field_possible`: from the earliest sowing month to the latest harvest month.

`flagged_months_in_field` marks each flagged month as `CERTAIN` or `POSSIBLE`. `flagged_months_in_field_per_year` gives `min` (certain months) and `max` (possible months), summed over the cycle and divided by the cycle length. `cycle_years_with_flagged_months` gives the number of cycle years with at least one flagged month. `basis` is always `CALENDAR_OVERLAP_NOT_IMPACT`.

Status:

- `EVALUATED`: every cycle year can be checked and no month in the field is unknown.
- `PARTIAL`: a cycle year has no complete window or is double-cropped, or a month in the field has no evaluable anomaly. Per-year counts are then `null`, because they would understate exposure. `by_cycle_year` still shows what is known.
- `NOT_EVALUABLE`: no cycle year can be checked, or no month of the scenario is evaluable.

Windows are never invented for crops without one.

## Ordering rule (`ordering`)

The rule is `LEXICOGRAPHIC_BY_FARMER_RANK`, with `is_recommendation: false`.

0. `DECLARED_CONSTRAINTS`: strategies whose `screening_result` is `PASSES_DECLARED_CONSTRAINTS` come first, then `NOT_FULLY_EVALUABLE`, then `CONFLICTS_WITH_DECLARED_CONSTRAINTS`.
1. Each ranked priority that has a descriptive criterion is applied from rank 1 down. A later criterion only separates strategies that are still tied on every earlier one.

| Priority | Criterion | Direction |
|---|---|---|
| `SOIL_COVER` | `SOIL_COVER_MONTHS` = `comparison.months_with_crop.min` (calendar-based potential cover) | more first |
| `CROP_DIVERSITY` | `BOTANICAL_FAMILIES` = `comparison.distinct_families`; not evaluable if any crop has an unknown family | more first |
| `RISK_REDUCTION` | `SCENARIO_EXPOSURE:<id>` = `flagged_months_in_field_per_year.min`, one criterion per scenario in request order. This is a **labelled proxy**: calendar exposure, not a risk estimate. Without scenarios, the priority is not used. | fewer first |
| `WATER_USE`, `INCOME_STABILITY`, `WORKLOAD`, `INPUT_COSTS`, `OTHER` | not used, with the reason in `criteria_not_used` (no water model, prices, labour or cost data) | — |

- If a criterion cannot be evaluated for a strategy, that strategy is placed after the strategies where it can be. The step explanation says so.
- Values are compared exactly as shown, rounded to 0.1 month, with no tolerance band.
- Strategies still tied after the last criterion share a `position` and are listed in `tied_with`. They are displayed in input order, and the response states that this order is not a preference.
- `steps[]` gives, for each step, the values per strategy, the tie groups before and after, and a sentence. `adjacent_decisions[]` says for each neighbouring pair which step and criterion put one before the other, with the values.

There are no weights, no score and no sums across criteria.

## Trade-offs (`trade_offs[]`)

Each strategy is compared with all strategies on every available criterion, whether ranked or not (`rank` is `null` when not ranked):

- `relation_to_most_favourable` is `MOST_FAVOURABLE`, `GIVES_UP` or `NOT_EVALUABLE`;
- `relation_to_current` is `MORE`, `LESS`, `SAME` or `NOT_EVALUABLE`.

`gives_up` and `gains_vs_current` are sentences with the values. `other_differences_vs_current` lists neutral facts with no direction assumed: crops new to the farm, crops dropped, legume presence, TIGHT changeovers, the longest gap between harvest and next sowing, and changed constraint-check statuses.

## Sensitivity (`/sensitivity`)

`change` is one of:

- `PRIORITY_SWAP` {`criterion_a`, `criterion_b`}: both must be ranked in the base and be different, and `OTHER` is not allowed;
- `PRIORITIES` {`priorities`};
- `WATER` {`water`};
- `CLIMATE_SCENARIOS` {`climate_scenarios`}.

The response reports:

- `priority_changes`: rank before and after.
- `criteria_changes`: `ADDED`, `REMOVED`, `MOVED_EARLIER`, `MOVED_LATER` or `SAME_STEP`, with any changed values per strategy kind.
- `screening_changes`: crop eligibility and reason codes, for example `IRRIGATED_ONLY_ON_RAINFED_FARM` after a water change.
- `strategy_changes`: matched by `strategy_kind`. Either the same sequence, a different sequence or only on one side, plus constraint-check changes.
- `position_changes`.
- `pair_changes`: every pair whose order changed, or whose deciding criterion changed. Each has the deciding criterion and values before and after. This answers "which criterion changes and why".
- `exposure_changes`.
- `explanation[]`: a plain summary. If no position changed, the summary says so.

If either side has no strategies (blocked or insufficient profile), the status is `NOT_COMPARABLE`, and the side that could be computed is still returned.

## Limitations

- Exposure is a month-of-year overlay at monthly resolution, using farmer-declared windows. Crop sensitivity by growth stage, irrigation buffering, soil water and management are not evaluated. Exposure is not damage, yield or probability.
- For a crop in the field across the year end, an episode's flagged months come from one calendar year. They are overlaid by month of year, not as one continuous season.
- A historical episode describes one observed year at a ½° × ⅝° grid cell (see `CLIMATE_ANOMALIES.md`). It says nothing about how likely the episode is to recur.
- Using exposure as the descriptive proxy for `RISK_REDUCTION` is a declared simplification that needs scientific review. Small differences, for example 2.8 vs 3.0 months per year from a sowing window that only possibly overlaps a flagged month, can decide the order. Every step shows the values so that this stays visible.
- Applying declared constraints first is part of the rule. Treating unevaluable values as last within a step is an explicit convention, not a judgement about the missing data.
- The ABB-17 limitations apply unchanged: one main crop per year, no soil or climate suitability, and a catalogue pending review.

## Follow-up

- ABB-19 can use `criteria_not_used`, `NOT_EVALUABLE` exposure and `pair_changes` to point to the observations that would change an ordering.
- ABB-24 comparator: priorities form → `/scenarios`; "what if I swap these two priorities?" → `/sensitivity`.
