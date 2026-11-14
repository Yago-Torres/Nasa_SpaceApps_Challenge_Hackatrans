# Disagreements between claims and applicability of studies (ABB-15)

Status: implemented in the API (`backend/agroblackbox/comparability.py` rules, `backend/agroblackbox/api/comparability.py` routes, migration `c4d82e1f9a37`); no UI yet. Tests: `backend/tests/test_comparability.py` (rules) and `backend/tests/test_api_comparability.py` (PostgreSQL). Method version `abb15-comparability-0.1.0`. This builds on the claim record of `EVIDENCE_CLAIMS.md` and the farm profile of `FARM_PROFILE.md`, and applies `SCIENTIFIC_POLICY.md`.

The system does two things:

1. It finds **candidate disagreements**: pairs of claims in a case whose structured fields say the same intervention moved the same outcome in different directions. A person decides what each candidate is.
2. It writes **transferability notes**: for one claim and one case, it compares the study's recorded conditions with the case's, dimension by dimension.

It does not judge which study is right. It does not produce a numeric applicability score, and it does not predict what will happen on the farm.

## 1. What is compared: only fields entered by people

The system never reads free text to work out an intervention, an outcome, a direction or a study condition. `claim_text`, `study_context`, `reported_outcome` and the free-text `context.region`, `context.climate`, `context.soils` and `context.management` are shown to people but never parsed. ABB-15 adds structured fields that the claim author fills in from the paper:

| Field | Values | Meaning |
|---|---|---|
| `intervention` | text ≤ 300 | practice or treatment studied, e.g. "legume pre-crop" |
| `comparator` | text ≤ 300 | what it was compared with, e.g. "cereal pre-crop" |
| `outcome_variable` | text ≤ 300 | variable the direction refers to, e.g. "main-crop yield" |
| `effect_direction` | `INCREASE`, `DECREASE`, `NO_CLEAR_EFFECT`, `MIXED`, `NOT_STATED` | direction **as stated by the authors** for that outcome; default `NOT_STATED` |
| `context.water_regime` | `RAINFED`, `IRRIGATED`, `SUPPLEMENTAL_IRRIGATION`, `MIXED`, `NOT_REPORTED` | water regime of the study sites |
| `context.soil_texture_classes` | USDA texture classes (12) | texture classes reported for the study sites |
| `context.soil_ph_min` / `soil_ph_max` | 0–14, given together, min ≤ max | soil pH range reported |
| `context.geographic_scope` | `GLOBAL`, `MULTI_COUNTRY`, `NATIONAL`, `SUBNATIONAL`, `SITE`, `NOT_REPORTED` | spatial scope |
| `context.countries` | ISO 3166-1 alpha-2 codes | countries of the study sites |
| `context.climate_classes` | Köppen–Geiger classes (31) | climate classes of the study sites |

Rules enforced by the API and, for the first two, by the database:

- A direction other than `NOT_STATED` needs `intervention` and `outcome_variable`.
- A direction cannot come from metadata alone (`evidence_basis = METADATA_ONLY`), like any other effect information in ABB-14.
- Editing any of these fields is a content edit: the claim returns to `PENDING` and the change is kept in the claim history.
- Existing claims start as `NOT_STATED` / `NOT_REPORTED`. They take no part in either comparison until someone fills these fields in.

Terms are matched **exactly** after ignoring case, accents, underscores and repeated spaces ("Legume  PRE-CROP" = "legume pre-crop"). There are no synonyms, no translations and no broader categories: "legume pre-crop" and "legume precrop" are different terms. Teams should agree on and reuse their terms.

## 2. Candidate disagreements

### Detection rule

Two claims of the same case form a candidate when **all** of these hold:

- neither is `REJECTED`;
- both have an `intervention` and an `outcome_variable`, and these terms match exactly;
- their stated directions are opposed:

| Direction A | Direction B | `kind` |
|---|---|---|
| INCREASE | DECREASE | `OPPOSITE_DIRECTION` |
| INCREASE or DECREASE | NO_CLEAR_EFFECT | `EFFECT_VS_NO_CLEAR_EFFECT` |

`MIXED` and `NOT_STATED` never produce a candidate. Claims that cannot be compared are listed in `claims_not_compared` with the reasons, so missing fields are visible.

A candidate is **not** a contradiction. Opposed results often come from different comparators, designs, crops, soils or climates. To help the reviewer, each candidate carries `comparability_notes`: for comparator, study design, crops, water regime, soil texture, soil pH, region and climate, the two recorded values and a status (`MATCH`, `PARTIAL`, `MISMATCH`, `UNKNOWN`, rules as in §3 but symmetric). These notes inform the decision; they never dismiss or confirm a candidate on their own.

Each candidate has a stable `id` derived from the two claim ids (UUIDv5), so decisions follow the pair.

### Human decision

| Decision | Meaning | Precondition |
|---|---|---|
| `CONFIRMED_CONTRADICTION` | the two claims, as recorded and reviewed, disagree on the same intervention and outcome under conditions the reviewer considers comparable | **both claims `ACCEPTED`** (reviewed against the full text) |
| `NOT_COMPARABLE` | the claims do not address the same question (e.g. different comparators, populations or outcome definitions) | — |
| `INCONCLUSIVE` | the reviewer cannot tell from what is available | — |

- Who: case OWNER, EDITOR or REVIEWER who did **not** create or edit either claim (403 otherwise); VIEWER 403; non-members 404. The case must be editable (`DRAFT` or `INVESTIGATING`, not archived; 409 otherwise).
- Each decision records the reviewer, time, a note and the versions of both claims, plus a snapshot of both claims' comparability fields, review status and paper identity. Decisions are appended to `claim_disagreement_reviews`; they are never overwritten.
- A decision applies only while both claims keep the recorded versions. Any later edit or claim review changes a version; the candidate then returns to `CANDIDATE` with a warning that the previous decision no longer applies (the history stays visible). This is deliberate: a decision about one text does not carry over to a changed text.
- If an edit removes the conditions for a candidate (e.g. the direction becomes `MIXED`), the candidate disappears from the list; its decisions stay in the database, and a claim with disagreement decisions cannot be deleted (409), like a reviewed claim.

A `CONFIRMED_CONTRADICTION` is shown with both references (claim text, comparability fields, review status and paper title/DOI for each side). It says that two reviewed claims disagree **as recorded**. It does not say which study is right or why they differ.

## 3. Applicability (transferability notes)

`POST /api/v1/cases/{case_id}/claims/{claim_id}/applicability` compares one claim's structured study conditions with the case. Every case member may call it; nothing is stored.

Case-side inputs (all optional):

- `farm_profile`: an ABB-11 profile (`FARMER_REPORTED`). Crops come from its crop history (fallow excluded); the water regime comes from its constraints, or from the crop history when every season gives the same regime; soil pH comes from `PH` values in pH units; texture is derived from clay/silt/sand percentages of one layer (see below). Each value keeps its origin (`LOCAL_MEASUREMENT`, `FARMER_ESTIMATE`, …) in `case_value_source`.
- `country_code` (ISO 3166-1 alpha-2) and `koppen_climate` (Köppen–Geiger class), stated by the person. They are not derived from the field location; coordinates are never used.
- Stored case data: the case's recorded crop history is used when the profile has no crop history. The parcels' free-text region labels are shown but not compared.

### Per-dimension rules

Each dimension gets one status and a written reason. **Missing data on either side is always `UNKNOWN`.**

| Dimension | MATCH | PARTIAL | MISMATCH | UNKNOWN |
|---|---|---|---|---|
| CROPS | the study crops are exactly the case crops | some case crops studied, or the study also pools other crops | no case crop studied, all names resolved in the crop catalogue | either side empty; or no exact match while a name is not in the catalogue (e.g. ambiguous "wheat") |
| WATER_REGIME | same regime | study `MIXED` | different regimes | study `NOT_REPORTED`; case regime missing or conflicting across seasons |
| SOIL_TEXTURE | the case class(es) are exactly the study's | overlap only | no overlap | study has no structured classes (free-text soils are shown, not read); no complete case layer |
| SOIL_PH | every case pH within the study range | some inside | none inside | study range or case pH missing |
| REGION | single-country study in the case country | multi-country study including it; any `GLOBAL` study | study countries exclude the case country | no case country; study countries not recorded |
| CLIMATE | same single Köppen–Geiger class | the study pools the case class with others; or same main group and precipitation letter (e.g. Csa vs Csb) | otherwise (e.g. Csa vs Cfa) | either side missing |

Comparisons are exact: no tolerance around pH limits, no fuzzy names, no inferred similarity between crops of the same family.

**Texture derivation.** For each depth interval with exactly one clay, one silt and one sand value in %, summing to 100 ± 2 points (the ABB-11 rounding tolerance), the USDA texture class is derived with the Soil Survey Manual texture-triangle rules (fractions normalised to 100). This is a definitional classification, not an agronomic inference. It assumes USDA particle-size limits (sand 0.05–2 mm, silt 0.002–0.05 mm); fractions measured with other limits (e.g. the 0.02 mm international silt/sand limit) would give a different class. Layers with missing, duplicated or inconsistent fractions are not classified, and the reason is reported.

### Overall result: categories, never a score

- `transfer_status`: `DIFFERENCES_FOUND` (at least one `MISMATCH` or `PARTIAL`), `INSUFFICIENT_DATA` (no difference found but at least one `UNKNOWN`), or `NO_DIFFERENCES_FOUND_IN_COMPARED_DIMENSIONS` (all `MATCH`).
- `differing_dimensions` and `unknown_dimensions` list the dimension names.
- Dimensions are not weighted or combined into a number, and there is no percentage, probability or confidence anywhere in the response. A test checks that no key resembling a score appears.
- `NO_DIFFERENCES_FOUND_IN_COMPARED_DIMENSIONS` means only that the recorded conditions agree on the six dimensions. Intervention details, management, cultivars, sowing dates and the weather of the study years are never compared automatically (stated in `notes`).
- `notes` also explain the study design (e.g. a meta-analysis is a pooled estimate whose response at one farm can differ in size and direction), say when the claim is not reviewed, and flag a farm profile with ABB-11 consistency errors.

## 4. Documented example: limited transfer (SYNTHETIC)

All values are invented for the example and the tests (`backend/tests/comparability_fixtures.py`); they are not attributed to any real paper or farm.

- **Claim:** a synthetic global meta-analysis of a practice on maize, rice and soybean. Recorded context: `geographic_scope = GLOBAL`, `water_regime = MIXED`, pH 5.5–7.5, climate classes Cfa, Dfa, Aw, no structured texture classes.
- **Case:** a synthetic rainfed Mediterranean farm in Spain (`ES`, Köppen–Geiger `Csa`). Durum wheat and chickpea, both rainfed. Topsoil 0–30 cm measured locally: clay 28 %, silt 32 %, sand 40 % (clay loam), pH 8.2.

| Dimension | Status | Why |
|---|---|---|
| CROPS | MISMATCH | durum wheat and chickpea were not studied (maize, rice, soybean) |
| WATER_REGIME | PARTIAL | the study pools several water regimes; its result is not specific to rainfed fields unless the paper reports them separately |
| SOIL_TEXTURE | UNKNOWN | the case is a clay loam (derived from local measurements), but the study texture is not recorded as classes |
| SOIL_PH | MISMATCH | pH 8.2 (local measurement) is outside the study's 5.5–7.5 |
| REGION | PARTIAL | global pooling: the case region may or may not be represented |
| CLIMATE | MISMATCH | Csa (dry summer) differs from Cfa, Dfa and Aw in main group or precipitation pattern |

Result: `transfer_status = DIFFERENCES_FOUND`, `differing_dimensions = [CROPS, WATER_REGIME, SOIL_PH, REGION, CLIMATE]`, `unknown_dimensions = [SOIL_TEXTURE]`, with the note that a pooled estimate can differ in size and direction at a single farm. Nothing in the response says how much of the effect would transfer. The person reading it sees the differences and what remains unknown.

With **no case data at all**, every dimension is `UNKNOWN` and `transfer_status = INSUFFICIENT_DATA`; no partial number is offered in place of missing data.

## 5. Known limitations

- Matching depends on consistent human terminology; different wordings for the same intervention or outcome are not linked, so real disagreements can be missed. Synonym handling would need a reviewed vocabulary (not built).
- Candidates are pairwise; no pooling or synthesis across more than two claims is attempted.
- Country codes are checked for format only, not against the ISO list; Köppen–Geiger classes and countries of the case are stated by people, not looked up from the field location.
- Partial Köppen–Geiger similarity (same main group and precipitation letter) and the treatment of `MIXED` water regimes and `GLOBAL` scope as `PARTIAL` are documented conventions, pending scientific review.
- Texture classes assume USDA particle-size limits; other particle-size systems are not converted.
- Applicability results are computed on request and not stored or versioned; a report that cites them must record the request inputs.
- Not linked to hypotheses or the evidence graph yet (ABB-16), and no UI yet (ABB-23).
