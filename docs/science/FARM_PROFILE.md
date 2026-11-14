# Farm profile: soil, crops, local calendar, constraints and priorities (ABB-11)

Code: `backend/agroblackbox/farm_profile.py`, `backend/agroblackbox/crop_catalog.py`. Tests: `backend/tests/test_farm_profile.py`.

## What it is

A farmer-supplied profile (`source_kind = FARMER_REPORTED`) that later Issues (ABB-17 rotations, ABB-18 scenarios, ABB-19 Uncertainty Hunter) consume. `POST /api/v1/farm-profiles/assess` checks consistency and completeness and returns issues. It **stores nothing** and **computes no agronomic outcome**: no yield, water saving, soil benefit, suitability score or confidence.

## Data origin is explicit

Every soil value and every crop season carries an `origin`:

| Origin | Meaning | Rule |
|---|---|---|
| `LOCAL_MEASUREMENT` | Lab or field measurement on this field | Warn if method or sampling date is missing |
| `FARMER_ESTIMATE` | Farmer knowledge without a measurement | Accepted, never presented as measured |
| `REGIONAL_ESTIMATE` | Soil map, gridded or regional product | Must name the product (`source_reference`); warn without spatial resolution |
| `UNKNOWN` | Origin not known | Warned; never treated as a measurement |

If no soil value is a local measurement, the assessment says so explicitly.

## Crop catalogue policy

- Identity data only: code, EN/ES names, scientific name, botanical family and a coarse group. Legume status is derived from the family (Fabaceae).
- **No agronomic parameters**: no sowing windows, crop coefficients, water demand, yield or nitrogen values. Sowing and harvest windows come from the farmer's `local_calendar`.
- Every entry is `PENDING` review until a person confirms it against a taxonomic authority (e.g. GBIF or POWO).
- Name resolution is exact (case- and accent-insensitive on code, EN/ES or scientific name). Ambiguous names such as "wheat" (soft or durum) are not guessed.

## Checks

| Kind | Examples |
|---|---|
| Rejected structurally (HTTP 422) | unknown fields (e.g. `expected_yield_t_ha`), months outside 1–12, inverted soil depth interval, negative irrigation allowance |
| `ERROR` (profile inconsistent) | unit not accepted for a soil property; value outside its definitional range (pH 0–14, fractions 0–100 %); clay + silt + sand differing from 100 % by more than 2 points; harvest before sowing; overlapping main crops or fallow; unknown catalogue code; rainfed farm with an irrigation allowance; duplicate priority rank or criterion; regional soil value without a named source |
| `WARNING` | crop not in catalogue; season year mismatch; overlapping intercrop or cover crop; missing depth or measurement metadata; no local soil measurement; sowing and harvest windows sharing months; excluded crop with a market |
| `MISSING_DATA` | Each comes with the analysis it limits (`consequence`): soil, texture, crop history (fewer than 2 main-crop seasons), season dates, water regime, local calendar, harvest window, constraints, equipment, market access, irrigation allowance, priorities |

Bounds are definitional (scales and fractions), not agronomic thresholds. The 2-point texture tolerance is an assumption that only absorbs rounding in reported fractions.

`rotation_input_status` is `BLOCKED_BY_ERRORS`, `LIMITED_BY_MISSING_DATA` or `INPUTS_COMPLETE`. `INPUTS_COMPLETE` means only that the required inputs are present, not that any rotation is validated.

Priorities are **ordinal ranks**, not numeric weights, to avoid false precision.

## Limitations and pending work

- No persistence or case linkage yet (ABB-03/ABB-06); `case_id` and `field_id` are optional references.
- The catalogue needs human taxonomic review, plus reviewed calendar or parameter sources before any are added.
- Soil properties use fixed units with no conversion; regional soil products are not fetched automatically.
- Consecutive-crop rules (family repetition, legume presence, calendar gaps between crops) are applied by ABB-17; see `ROTATIONS.md`.
