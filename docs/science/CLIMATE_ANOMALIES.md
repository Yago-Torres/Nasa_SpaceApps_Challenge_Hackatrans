# Climate anomalies — method, quality control and limitations (ABB-07, ABB-08)

Status: **implemented in `GET /api/climate`, pending scientific review (B)**. Code: `backend/agroblackbox/services/power.py` (source, provenance), `backend/agroblackbox/services/metrics.py` (method, QC), `backend/agroblackbox/climate.py` (typed response). Tests: `backend/tests/test_power.py`, `backend/tests/test_metrics.py`.

All results are `OBSERVED` regional meteorology plus a descriptive difference. They describe exposure; they never establish why a crop failed.

## Source

| Item | Value | Where it comes from |
|---|---|---|
| Endpoint | `https://power.larc.nasa.gov/api/temporal/daily/point` | request built in `power.build_params` |
| Parameters | `PRECTOTCORR` (mm/day), `T2M_MAX` (C) | units checked against the response `parameters` block; a different unit is rejected |
| Community / time standard | `AG`, `time-standard=UTC` | request; a response header with a non-UTC time standard is rejected |
| Fill value | header `fill_value` (live response: `-999.0`), default `-999.0` when absent | response header |
| Version | header `api.name` + `api.version` (live response: `POWER Daily API v2.10.3`) → `provenance.dataset_version` | response header. This is the API version; the response does not report a data release version |
| Sources | header `sources` (live response: `MERRA2`, `POWER`) | response header, recorded verbatim in `upstream.sources` |
| Spatial resolution | ½° latitude × ⅝° longitude (0.5° × 0.625°) | NASA POWER methodology, meteorology page (consulted 2026-11-14): "The primary meteorological data source is ½° latitude by ⅝° longitude grid from GMAO MERRA-2." Not reported in the API response |
| Temporal resolution | 1 day (UTC days), aggregated here to calendar months | request + method |

Every answer carries `data_sha256` / `provenance.checksum_sha256` (SHA-256 of the exact bytes received), `retrieved_at` (UTC, the original retrieval time even when served from cache), `request_params`, `processing_version` and `cache` (`served_from_cache`, `cache_age_seconds`, `ttl_seconds`, `upstream_attempts`).

The checksum identifies the exact bytes received, not the data content alone: the POWER response includes a `times` block (server processing durations), so two retrievals of identical values have different checksums. Comparing data content across retrievals needs a checksum of the canonicalised `properties.parameter` block (follow-up).

Live check (2026-11-14T13:39Z, lat 41.6, lon −0.9, 2010–2022): HTTP 200 after 1 attempt; header `POWER Daily API v2.10.3`, sources `MERRA2`, `POWER`, fill value −999.0, time standard UTC; units `mm/day` and `C`; all 12 months complete for both variables with 12 of 12 reference years; the repeat request was served from cache.

## Retrieval robustness

- Timeout 55 s (connect 10 s). At most 3 attempts; retries only for timeouts, network errors, HTTP 429 and 5xx, waiting 1 s then 2 s. A 429 `Retry-After` of up to 10 s is honoured; a longer one ends the request without retrying earlier than asked.
- Other 4xx answers are not retried.
- The JSON shape is validated before use or caching: `properties.parameter.PRECTOTCORR` and `.T2M_MAX` must be objects keyed by `YYYYMMDD` with numeric or null values. Invalid payloads are never cached.
- Failures return HTTP 502 with a short generic `detail` (no URL, query or upstream body). No value is ever simulated or substituted.
- Cache: one file per request (SHA-256 of the parameters) plus a sidecar with retrieval time and checksum; TTL 24 h. Entries without a sidecar, expired, with a checksum mismatch or that fail validation are refetched.
- Not implemented: a process-wide request throttle or a serve-stale-on-error mode.

## Daily quality classification

Each calendar day of a month (leap days included) is one of:

| Class | Rule | Counted in |
|---|---|---|
| valid | finite number, not the fill value, within the gross physical range | `valid_days` |
| fill value | equals the header fill value | `fill_value_days` |
| not returned | date absent from the response or `null` | `absent_days` |
| invalid | non-finite, or outside the range below | `invalid_days` |

Gross-error ranges (not climatological thresholds): precipitation 0 – 2000 mm/day; daily maximum temperature −95 – 65 °C.

## Monthly status (per variable, per month)

- `complete`: every calendar day is valid.
- `partial`: some days valid, some not. `reason` lists day counts by class, e.g. `28 of 31 days valid: 3 days not returned by the source.`
- `missing`: no valid day.

**Only complete months are aggregated.** A partial month gives a `null` value, because a precipitation total with missing days would look drier than it was. This is stricter than accepting a few missing days for temperature means; any relaxation needs scientific review.

Aggregation: precipitation = sum of daily `PRECTOTCORR` (mm/day × 1 day) → mm; maximum temperature = arithmetic mean of daily `T2M_MAX` → °C.

## Reference value and anomaly

- Reference years: `reference_start`…`reference_end`, which must exclude the event year and span at least 3 years. When `/api/climate` receives neither, it uses the 10 years before the event year, clipped at 1981 (so the first event year with a valid default is 1984); the Investigation page sends that same window. Saved-case ingestion (ABB-10) keeps its own 12-year default. The event year may be the current year: months that are not complete yet have no value and no anomaly.
- For each calendar month, only reference years where that month is complete are used. `reference.sample_count`, `years_excluded` and `reason` say which.
- `reference.status`: `complete` (all years used), `reduced` (some excluded, ≥ 3 left), `insufficient` (< 3 left: the reference value and anomaly are `null`).
- Anomaly = event-year monthly value − mean of the usable reference monthly values, in the variable's units (mm or °C). It is computed from unrounded values and rounded to 0.01.
- Spread: sample standard deviation (n−1), minimum and maximum of the reference monthly values with their sample count. No confidence interval, standardisation, percentile or significance test is computed.

### Reference period labelling

A reference window shorter than 30 years is labelled *short reference window … not a 30-year climatological normal*. Longer windows are labelled *multi-decadal … not an official WMO climatological standard normal*. `method.reference_is_climatological_normal` is always `false`. The UI default (2010–2021) is a 12-year descriptive comparison.

## Quality flags (`monthly[].quality.<variable>.flags`)

| Flag | Meaning |
|---|---|
| `EVENT_MONTH_PARTIAL` | event-year month has some invalid/missing days; no value |
| `EVENT_MONTH_MISSING` | event-year month has no valid day |
| `FILL_VALUES_PRESENT` | fill values appeared in the event month or its reference months |
| `REFERENCE_YEARS_EXCLUDED` | at least one reference year was dropped for incomplete data |
| `REFERENCE_INSUFFICIENT` | fewer than 3 complete reference years; no reference value or anomaly |

The top-level `quality` gives per-variable month counts, an overall `status` (`complete`, `partial`, `insufficient`) and `warnings` written as plain sentences for display.

## Verification

Deterministic synthetic tests check known results with explicit tolerances (`1e-9` for exact arithmetic, `0.005`–`0.006` after rounding), an independent recomputation on a seeded random series, leap years, partial and missing months, fill values (header-defined), out-of-range values, excluded and insufficient reference years, retries, timeouts, rate limits, invalid payloads and 502 paths. No test calls the network.

## Limitations

- A ½° × ⅝° grid cell is regional; it is not a field, station or rain-gauge measurement.
- `PRECTOTCORR` is a bias-corrected reanalysis estimate (MERRA-2).
- UTC days may not match local calendar days.
- NASA POWER recommends ending climate analyses about two months behind near real time, because recent days come from a near-real-time product (GEOS-IT). The response adds this limitation when the requested period ends less than about two months before retrieval.
- Anomalies describe a difference from a short comparison period. Co-occurrence with crop damage is not evidence of a cause; competing explanations (pests, management, soil, irrigation) remain unmeasured.
