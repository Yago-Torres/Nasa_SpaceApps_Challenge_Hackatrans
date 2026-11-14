# Uncertainty Hunter: gaps, useful local checks and what they could change (ABB-19)

Status: implemented in the API (`backend/agroblackbox/uncertainty.py` rules, `backend/agroblackbox/api/uncertainty.py` routes, `api/uncertainty_dto.py`, migration `a19f3b7c2d64`); no UI yet. Tests: `backend/tests/test_uncertainty.py` (rules, no database) and `backend/tests/test_api_uncertainty.py` (PostgreSQL). Method version `abb19-uncertainty-0.1.0`, ordering rule `abb19-question-order-0.1.0`. Applies `SCIENTIFIC_POLICY.md`.

The Uncertainty Hunter lists what a case does not know, asks concrete local questions that address those gaps, and shows which recorded items could change if a question were answered. It does **not** estimate how much an answer is worth: there is no value-of-information model, no score, weight, probability or confidence anywhere in the responses (a test checks every response and schema for such keys).

## 1. Where gaps come from

Gaps are built only from structured records. Free text is never interpreted; the one text rule is an exact match (ignoring case, accents and repeated spaces) against the static wording of the ABB-10 hypothesis templates.

| Source | Gap | Cause |
|---|---|---|
| Timeline `NO_LOCAL_MEASUREMENTS` (ABB-10) | no rain-gauge, soil-moisture, irrigation or crop-stage records | `MISSING_CASE_DATA` |
| Timeline `NO_OBSERVATIONS` | a year of the incident period without NASA POWER data | `MISSING_CASE_DATA` (analysis task) |
| Timeline `DATA_GAP` | an event-year month with no anomaly (ABB-08 QC: partial/missing month or too few reference years) | `INCOMPLETE_SOURCE_DATA` |
| Hypotheses (any status) | each `missing_evidence` entry and each verification question | `MISSING_CASE_DATA` |
| Evidence claims (not REJECTED) | not reviewed (`PENDING`, `CHANGES_REQUESTED`) | `NOT_REVIEWED` |
| ABB-15 applicability, per claim | an `UNKNOWN` dimension: study side not recorded → claim gap; case side missing → one case gap per dimension | `MISSING_STUDY_DATA` / `MISSING_CASE_DATA` |
| Claims without intervention / outcome / comparable direction | not compared for disagreements | `MISSING_STUDY_DATA` |
| Farm profile, POST only (ABB-11) | every `MISSING_DATA` issue; the warnings `NO_LOCAL_SOIL_MEASUREMENT`, `SOIL_ORIGIN_UNKNOWN`, `REGIONAL_RESOLUTION_MISSING`, `MEASUREMENT_METADATA_MISSING`, `SOIL_DEPTH_MISSING`, `CROP_NOT_IN_CATALOGUE`; every `ERROR` | `MISSING_CASE_DATA`, `ESTIMATED_NOT_MEASURED`, `INCONSISTENT_INPUT` |
| Rotation comparison, POST only (ABB-17) | `INSUFFICIENT_INPUT` / `BLOCKED_BY_PROFILE_ERRORS`; candidate crops `NOT_EVALUABLE` (no window, not in catalogue); `NOT_EVALUABLE` constraint checks | `MISSING_CASE_DATA` or `NO_METHOD` (see below) |
| Ordering by farmer rank, POST only (ABB-18) | `criteria_not_used`; ordering steps where a strategy has no value | `MISSING_ANALYSIS_INPUT`, `NO_METHOD`, `MISSING_CASE_DATA` |

Other ABB-11 warnings (e.g. season-year mismatch) are consistency notes shown by the profile assessment and are not repeated here. Exposure to climate scenarios and sensitivity `pair_changes` are not used: they need a scenario or change request that this endpoint does not take.

**`NO_METHOD` gaps cannot be closed by local data** and get no question. A `NOT_EVALUABLE` rotation check is `NO_METHOD` when the rule set has no reviewed parameters for it: `SOIL` and `CLIMATE` always; `WATER_REGIME` on an irrigated farm (no water-demand model); `LOCAL_CALENDAR` when no crop of the strategy lacks a declared window (the cause is double cropping, which is not modelled). The priorities `WATER_USE`, `INCOME_STABILITY`, `WORKLOAD`, `INPUT_COSTS` and `OTHER` are also `NO_METHOD`. A soil analysis, for example, does **not** make the rotation soil check evaluable, and the response says so.

Each gap has a deterministic `id` (UUIDv5 of the case and a key such as `profile:SOIL_MISSING:soil` or `hypothesis:<id>:missing_evidence:<digest>`), a `category`, a `cause`, `answerable_locally`, `sources` (entity type, id, field, and `stored: false` when the value came from the request body) and `would_change`.

## 2. Questions

A catalogue of 28 questions (`GET /api/v1/uncertainty/question-catalogue`). Each has the question, `why_it_matters` (the uncertainty it addresses, extended per case with the titles of the gaps it addresses), `measurement` (what to record and in which units) and `units`.

- **`LOCAL_INFORMATION`** (answered here): soil analysis, irrigation records, local rain gauge or soil moisture, local temperature, crop stage at the event, symptom onset, dated photos of symptoms, pest/disease diagnosis, regional pest alerts, damage map, standing water, drainage condition, management log, neighbouring fields, crop history with dates, farm crop calendar, crop identity, water availability, farm constraints, equipment, market access, farmer priorities, country and Köppen–Geiger class.
- **`ANALYSIS_TASK`** (resolved in another CropStory workflow, `answer_route` names it; a local answer is refused with 422): NASA POWER retrieval, claim review, study record (structured claim fields), farm-profile correction, climate scenario.
- **Questions written in hypotheses.** Missing-evidence entries and verification questions that are not template wording become questions with id `H-<uuid5 hex>` (same text → same id, so the same request in two hypotheses is one question). Their measurement says it was not specified by the hypothesis author.

The template mapping (e.g. *"Irrigation dates and volumes for the season"* → `IRRIGATION_RECORDS`) is defined by position in the template lists; a test fails if a template changes without updating the mapping.

### `would_change`

For every question, `would_change` lists the recorded items linked to its gaps, each with `target_type`, `target_id`, `label`, `current_state` and `how` (a sentence on what could change, never by how much):

| `target_type` | Example | `how` (abridged) |
|---|---|---|
| `HYPOTHESIS` | WATER_DEFICIT, `NOT_EVALUABLE` | could make it evaluable; a person then decides COMPATIBLE or CONTRADICTED |
| `APPLICABILITY_DIMENSION` | claim X · SOIL_PH, `UNKNOWN` | could become MATCH, PARTIAL or MISMATCH; not a prediction for the farm |
| `ROTATION_CHECK` | CURRENT · LOCAL_CALENDAR, `NOT_EVALUABLE` | could become SATISFIED, VIOLATED or REVIEW_REQUIRED |
| `CANDIDATE_SCREENING` | sunflower, `NOT_EVALUABLE` | would be screened again and could enter alternative generation |
| `ORDERING_STEP` / `ORDERING_CRITERION` | step 0 for CURRENT, `NOT_FULLY_EVALUABLE`; RISK_REDUCTION `NOT_USED` | the strategy's place at that step could change; the priority would become a step |
| `DISAGREEMENT_DETECTION` | candidate disagreement, `CANDIDATE` | cannot be confirmed until both claims are ACCEPTED |
| `PROFILE_ANALYSIS`, `ROTATION_COMPARISON` | ABB-11 `consequence`; `INSUFFICIENT_INPUT` | the analysis the profile issue limits; whether the comparison can run |

Links are only made where a structured relation exists: a hypothesis lists the evidence; a template names the weather variable (`DATA_GAP` and `NO_OBSERVATIONS` link only to template hypotheses whose template names that variable, and a `DATA_GAP` only when its month overlaps the incident); a hypothesis cites the claim; a check, screening or step is `NOT_EVALUABLE` in the rotation output. When a question has no link, `would_change_statement` says that an answer adds local context only.

## 3. Ordering rule `abb19-question-order-0.1.0` and "no basis to prioritise"

1. Only `OPEN` questions get a `position`; answered, reviewed and dismissed questions follow without one.
2. More distinct **unresolved hypotheses** (status `OPEN` or `NOT_EVALUABLE`) in `would_change` first.
3. Then more distinct **other linked items** first.
4. Remaining ties share a position (`tied_with`) and are listed in catalogue order (hypothesis-written questions after catalogue questions), which is not a preference.

`prioritisation.status` is `ORDERED_BY_LINK_COUNTS`, `NO_OPEN_QUESTIONS` or **`NO_BASIS_TO_PRIORITISE`**, the last when every open question has the same pair of counts (for example a new case with only the `NO_LOCAL_MEASUREMENTS` gap). Then the response states: *"There is no basis to prioritise these questions … They are listed in catalogue order, which is not a preference."* `is_value_of_information` is always `false`. Counting links is a transparent convention, not a measure of how informative an answer is: one measurement can settle more than its count suggests, or nothing. Evaluated hypotheses (`COMPATIBLE`, `CONTRADICTED`) appear in `would_change` but are not counted.

## 4. Local answers and resolution

An answer is **`FARMER_REPORTED`** evidence: `value_text` and/or `value_number` (a number needs `unit`), `observed_from`/`observed_to`, `origin` (`FARMER_REPORTED`, `LOCAL_MEASUREMENT` — requires `method` —, `FIELD_RECORD`, `ADVISOR_REPORT`), `method`, `source_reference` (where the record is kept; no file is stored) and `note`. The origin records what the author says; CropStory cannot verify the instrument or document.

Question resolution: `OPEN` → `ANSWERED` → `REVIEWED`, or `DISMISSED` (with a note) → `REOPENED` to `OPEN`. A `REJECTED` answer returns the question to `OPEN`.

- **Content is immutable.** A correction is a new answer with `replaces_answer_id` = the current answer (409 if stale); the old one becomes `SUPERSEDED` with `superseded_by_id` and is kept. At most one current (`ANSWERED`/`REVIEWED`) answer per question, enforced by a partial unique index.
- **Review** by an OWNER, EDITOR or REVIEWER **other than the author** (403 for the author; the database also rejects `reviewed_by = answered_by`): `REVIEWED` (checked against the documentation available to the reviewer) or `REJECTED`, with a note and the answer `version` (409 when stale). A `REVIEWED` answer can later be `REJECTED`. REVIEWED does not make the answer an independent measurement, and CropStory cannot check the reviewer's expertise.
- **History**: every action is appended to `uncertainty_question_events` (actor, time, from/to status, note, question snapshot, changes). The snapshot keeps the question text even if a hypothesis-written question later disappears; such questions stay listed with `currently_generated: false`.
- **No silent overwrite.** Answers never change observations, hypotheses, claims, profiles or rotation results. People can link an answer to a hypothesis as evidence (`supporting_evidence_ids`/`contradicting_evidence_ids` accept answer ids of the same case; it resolves as `evidence_type: LOCAL_ANSWER`, `kind: FARMER_REPORTED`, `active: false` once superseded) or copy it into the farm profile. The timeline's `NO_LOCAL_MEASUREMENTS` marker is unchanged by answers (ABB-10 behaviour).

| Action | OWNER | EDITOR | REVIEWER | VIEWER | no permission |
|---|---|---|---|---|---|
| Read report, answers, history | yes | yes | yes | yes | 404 |
| POST report with a farm profile (nothing stored) | yes | yes | yes | yes | 404 |
| Answer, dismiss, reopen | yes | yes | 403 | 403 | 404 |
| Review an answer | yes* | yes* | yes* | 403 | 404 |

\* Not on an answer they recorded. Writes need an editable case (`DRAFT`/`INVESTIGATING`, not archived; 409 otherwise).

## 5. Limitations

- The gap inventory is only as complete as the structured records; issues written only in free text (incident notes, claim summaries) are not found.
- `would_change` shows links, not effects. It cannot say whether an answer would support or weaken a hypothesis, and a linked rotation check may stay unchanged after the profile is updated.
- The link count ordering is a convention pending scientific review; ties are frequent.
- Answers are not fed into the profile, applicability or rotation analyses automatically, because profiles are not stored yet (ABB-03/06) and because a person should decide how a local answer enters an analysis.
- Template wording is matched exactly; an edited template question becomes a hypothesis-written question.
- Country and Köppen–Geiger class are not derived from the field location; they come from the request or remain gaps.
- The ABB-16 evidence graph does not yet have a node type for local answers: a hypothesis link to an answer is listed there as an orphan reference (follow-up). Graph `review_blockers` and dead ends are not used as gap sources yet.
