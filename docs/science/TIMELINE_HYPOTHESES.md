# Forensic timeline and rival hypotheses — rules and limitations (ABB-10)

Status: **implemented in the case API, pending scientific review (B)**. Code: `backend/agroblackbox/services/forensics.py` (severity rule, templates, identity checksums), `backend/agroblackbox/api/observations.py` (case-bound NASA POWER ingestion), `backend/agroblackbox/api/timeline.py`, `backend/agroblackbox/api/hypotheses.py`. Tests: `backend/tests/test_forensics.py` (no database), `backend/tests/test_api_timeline_hypotheses.py` (PostgreSQL). Migration `e3a9c71f5b20`.

The timeline puts evidence side by side. It never connects events causally, never computes a probability and never labels any explanation as a demonstrated cause.

## Case-bound observations

`POST /api/v1/cases/{case_id}/observations/nasa-power` (OWNER/EDITOR, case DRAFT or INVESTIGATING, not archived).

- The server reads the coordinates stored on the case field. The request carries only `field_id` (optional when exactly one field has coordinates), `event_year` (default: year of `incident_start`) and an optional reference window (default: the 12 calendar years before the event year, clipped at 1981). Coordinates in the body are rejected (422).
- Retrieval and monthly quality control are the ABB-07/ABB-08 pipeline unchanged (`services/power.py`, `services/metrics.py`, see `CLIMATE_ANOMALIES.md`). Values are stored as one `Observation` per variable and event-year month (24 rows: monthly precipitation sum in mm, monthly mean daily maximum temperature in °C), each with its period, daily coverage counts, quality flags and limitations, plus one `Anomaly` row with reference mean, sample SD, minimum, maximum, sample count, excluded years and reference status. Partial or missing months keep a `null` value; nothing is substituted.
- A `SourceManifest` keeps the request parameters (including the coordinates), retrieval time, raw-byte SHA-256, POWER API version, processing version, method, quality summary and upstream header.
- **Failure:** NASA POWER failure, rate limit, timeout or an unusable payload → HTTP 502 with a generic message; nothing is written. Permissions, editability and the field location are checked again after the retrieval (409 if the field changed meanwhile).
- **Re-ingestion:** one active manifest per (field, event year, reference window). `content_sha256` is a SHA-256 of the returned daily values only (canonical JSON, no coordinates), because the raw-byte checksum changes between retrievals (POWER `times` block). Same values and same processing version → HTTP 200, `created=false`, nothing written. Different values or a new processing version → new revision (HTTP 201) and the previous manifest is marked `superseded_at` / `superseded_by_id`. Superseded rows are never deleted, so hypotheses that cite them keep valid links.

## Timeline layers

`GET /api/v1/cases/{case_id}/timeline` (every member). Events are sorted by start date; undated events come last.

| Layer (`kind`) | `event_type` | Source | Dates |
|---|---|---|---|
| `OBSERVED` | `CLIMATE_ANOMALY` | event-year month with a computed anomaly (active manifests only) | first–last day of the month |
| `FARMER_REPORTED` | `INCIDENT_PERIOD` | case `incident_start` / `incident_end` / `incident_notes` | reported period |
| `FARMER_REPORTED` | `CROP_HISTORY` | case `crop_history` | undated (the case model has no crop dates) |
| `HYPOTHESIS` | `HYPOTHESIS` | case hypotheses with status and links to the observed events they cite | incident period |
| `MISSING_DATA` | `DATA_GAP` | month whose value or anomaly is `null`, with the coverage/reference reason | the month |
| `MISSING_DATA` | `NO_OBSERVATIONS` | incident-period year without an active NASA POWER retrieval | that part of the incident period |
| `MISSING_DATA` | `NO_LOCAL_MEASUREMENTS` | always present: the case stores no rain-gauge, soil-moisture, irrigation or crop-stage records | incident period |

Every event has `id`, `kind`, `event_type`, `start`, `end`, `title`, `description`, `provenance` and at least one limitation. `overlaps_incident` is a calendar overlap with the reported incident period (start date only when no end date was reported); it is not evidence of a cause. OBSERVED and DATA_GAP event ids equal the anomaly id, so hypothesis links to an anomaly (or its observation) resolve to timeline events. Observed events also carry `observed` (value, units, reference mean, anomaly, reference window, sample count, SD, min, max), `data_quality` (coverage status, reference status, flags, reason) and `departure`.

Provenance for observed events names the manifest, provider, dataset, API version, retrieval time, raw checksum, processing version and resolutions. It never includes request parameters or coordinates.

## Severity rule `abb10-departure-vs-reference-sd-1`

For a month with a computed anomaly *a* (event value − reference mean) and reference sample standard deviation *s* (n − 1, n ≥ 3 complete reference years):

| Condition | `severity` |
|---|---|
| \|a\| / s < 1 | `WITHIN_REFERENCE_SPREAD` |
| 1 ≤ \|a\| / s < 2 | `MODERATE_DEPARTURE` |
| \|a\| / s ≥ 2 | `LARGE_DEPARTURE` |
| no anomaly, no SD, n < 3, or s = 0 | `NOT_CLASSIFIED` (with `reason`) |

`direction` is `ABOVE_REFERENCE`, `BELOW_REFERENCE` or `EQUAL_TO_REFERENCE`; `departure_in_reference_sd` is *a / s* rounded to 0.01; `outside_reference_range` is true when the event value is below the smallest or above the largest reference monthly value. Inputs are the stored values rounded to 0.01. Thresholds are inclusive at 1 and 2.

What it is not: a probability, percentile, return period, significance test, agronomic damage threshold or evidence that weather caused the damage.

## Rival hypotheses

`/api/v1/cases/{case_id}/hypotheses` uses the shared `Hypothesis` contract (statement, supporting/contradicting evidence ids, missing evidence, limitations, status) plus `title`, `origin` (`USER` | `TEMPLATE`), `template_code`, `verification_questions[{question, why_it_matters}]`, `evaluation_note`, `evaluated_by`, `evaluated_at`, `version`, authorship and resolved `evidence[]`.

**Status (additive contract change).** The shared set keeps `OPEN | SUPPORTED | CHALLENGED | REJECTED` and adds `COMPATIBLE | CONTRADICTED | NOT_EVALUABLE`. The case API only sets:

| Status | Meaning | Precondition |
|---|---|---|
| `OPEN` | not evaluated (default for every new or template hypothesis) | — |
| `COMPATIBLE` | consistent with the linked evidence; **not proven** | ≥ 1 supporting link and a note |
| `CONTRADICTED` | at least one linked item argues against it | ≥ 1 contradicting link and a note |
| `NOT_EVALUABLE` | the evidence needed to judge it is missing | ≥ 1 `missing_evidence` entry and a note |

`SUPPORTED`, `CHALLENGED` and `REJECTED` are never set by this API (422) and remain only for compatibility; `SUPPORTED` would read as proof. No status is assigned automatically, no hypothesis is ranked, and no numeric score exists. Editing the statement, evidence links or missing evidence resets an evaluation to `OPEN`, because the evaluation referred to the previous content.

**Evidence links** must reference evidence of the same case: observation ids, anomaly ids, evidence-claim ids or ABB-19 local answer ids (`evidence_type: LOCAL_ANSWER`, `kind: FARMER_REPORTED`; see `UNCERTAINTY_HUNTER.md`). Unknown ids and ids from another case are rejected with the same 422; an id cannot both support and contradict one hypothesis. Links to superseded retrievals stay valid and are shown with `active=false`.

**Templates.** `GET /api/v1/hypothesis-templates` lists six starting points — water deficit, excess water/waterlogging, heat stress, pest or disease, management or irrigation-system failure, soil limitation — each phrased "may have contributed", with missing evidence and verification questions. `POST /api/v1/cases/{case_id}/hypotheses/templates` adds them (all or `codes`) as `OPEN`, origin `TEMPLATE`; already-added templates are skipped. Templates are not derived from case evidence.

## Roles and audit

| Action | OWNER | EDITOR | REVIEWER | VIEWER | No permission |
|---|---|---|---|---|---|
| Ingest NASA POWER | yes | yes | 403 | 403 | 404 |
| Read observations, timeline, hypotheses | yes | yes | yes (coordinates redacted) | yes (coordinates redacted) | 404 |
| Create / edit / delete hypotheses, add templates | yes | yes | 403 | 403 | 404 |
| Change hypothesis status | yes | yes | yes | 403 | 404 |

Reviewers may evaluate hypotheses because evaluating evidence is their role in the review workflow; they cannot change the hypothesis content or the evidence links. All writes require the case to be `DRAFT` or `INVESTIGATING` and not archived (409), hypothesis writes carry the hypothesis `version` (409 on conflict), and every change appends a `case_history` row (`OBSERVATIONS_INGESTED`, `HYPOTHESIS_CREATED`, `HYPOTHESIS_UPDATED`, `HYPOTHESIS_EVALUATED`, `HYPOTHESIS_DELETED`) with actor, time and before/after values. These rows do not bump the case version, so evidence work does not conflict with concurrent case edits.

**Location privacy.** For REVIEWER and VIEWER, `latitude`/`longitude` in manifest `query_parameters` are `"REDACTED"` (even when the owner consented to share the precise point, because the request point is provenance, not the shared location) and upstream free-text messages are withheld (`messages_withheld` count). Timeline provenance never contains request parameters. `content_sha256` is computed without coordinates so it cannot be brute-forced back to the stored point.

## Limitations

- OBSERVED values describe a ½° × ⅝° NASA POWER grid cell, not the field; their values let collaborators infer that grid cell, not the stored point.
- The severity thresholds are conventions, not calibrated damage thresholds. Monthly precipitation is skewed and bounded at zero and the reference sample is small (often 12 years, minimum 3), so an SD scale is a coarse label; in dry months a small absolute difference can be labelled a large departure. Pending scientific review.
- Only two variables (precipitation, daily maximum temperature) and monthly aggregation; no daily episodes, frost, evapotranspiration, soil moisture, GPM or HLS yet.
- The precise field coordinates are sent to NASA POWER over HTTPS (as `/api/climate` already does) and appear in the on-disk POWER cache of the server; removing a field keeps evidence already retrieved for it (`field_id` becomes null), and only deleting the case erases it.
- Crop history is undated, so it cannot be placed on the time axis.
- Evidence claims (ABB-14) can be linked once they exist; no route creates them yet.
