# Evidence claims and human review (ABB-14)

Status: implemented in the API (`backend/agroblackbox/api/evidence.py`, migration `e3c91f5a7d24`); no UI yet (ABB-23). This document defines what a claim records, how it is reviewed and what "reviewed" does and does not mean. It applies `SCIENTIFIC_POLICY.md`.

## 1. Two separate records

| Record | Scope | Source classification | Who creates it |
|---|---|---|---|
| **Paper** (`/api/v1/evidence/papers`) | global, public bibliographic record | always `LITERATURE_METADATA`, `evidence_status = BIBLIOGRAPHIC_MATCH_ONLY` | any signed-in user, by DOI or OpenAlex ID |
| **Claim** (`/api/v1/cases/{case_id}/claims`) | one case, private like the case | `LITERATURE_METADATA` unless ACCEPTED, then `LITERATURE_REVIEWED` | case OWNER/EDITOR |

A paper only shows that a work with this identity exists. Registration accepts an identifier, never metadata: the server queries OpenAlex (`/works/doi:…` or `/works/W…`) and checks the DOI in Crossref with the ABB-13 rules (title agreement, canonical DOI, statuses `VERIFIED_CROSSREF | METADATA_MISMATCH | NOT_FOUND_IN_CROSSREF | VERIFICATION_UNAVAILABLE | MALFORMED_DOI | NO_DOI`). Each upstream request is kept in `retrievals` (source, endpoint without credentials, time, HTTP status, outcome). If no source knows the work the API answers 404; if the sources are down, 502. In both cases nothing is stored. Papers are deduplicated by DOI and OpenAlex ID. A stored paper is fetched again only while its DOI status can still change (`METADATA_MISMATCH`, `NOT_FOUND_IN_CROSSREF`, `VERIFICATION_UNAVAILABLE`) and only if no accepted claim cites it.

No abstract or full text is fetched or stored by the system.

## 2. Fields of a claim

| Field | Meaning | Rule |
|---|---|---|
| `claim_text` | the statement attributed to the paper | ≤ 2 000 characters |
| `study_context` | free-text summary of the study context | required |
| `study_design` | `META_ANALYSIS`, `SYSTEMATIC_REVIEW`, `FIELD_EXPERIMENT`, `CONTROLLED_EXPERIMENT`, `OBSERVATIONAL_STUDY`, `MODELLING_STUDY`, `NARRATIVE_REVIEW`, `OTHER`, `UNKNOWN` | not guessed: unknown stays `UNKNOWN` |
| `context` | population, crops, soils, region, climate, management/intervention **of the study**; ABB-15 structured conditions (water regime, USDA texture classes, pH range, geographic scope/countries, Köppen–Geiger classes) | describes the paper, not the farm |
| `intervention`, `comparator`, `outcome_variable`, `effect_direction` | ABB-15 comparability fields, see `CONTRADICTIONS_APPLICABILITY.md` | entered by a person; a direction needs the abstract or full text |
| `reported_outcome` | `outcome`, `comparison`, `effect_as_stated`, `units_as_stated`, `uncertainty_as_stated`, `sample_as_stated` | text copied as stated in the source; never parsed, converted, pooled or recomputed |
| `source_locator` | page, section, figure/table | required whenever there is a quotation |
| `quoted_fragment` | short quotation | ≤ 500 characters, attributed by `source_locator`, only if the abstract or full text was read |
| `evidence_basis` | what the author read: `METADATA_ONLY`, `ABSTRACT`, `FULL_TEXT` | see §3 |
| `access_basis` | `NONE`, `PUBLIC_ABSTRACT`, `OPEN_ACCESS_LICENSE`, `PUBLISHER_FREE_TO_READ`, `INSTITUTIONAL_SUBSCRIPTION`, `AUTHOR_PROVIDED_COPY` | see §3 |
| `content_license` | licence or access terms of the text read | required for `FULL_TEXT` |
| `limitations` | at least one sentence | always shown |
| `origin`, `origin_ref` | `MANUAL` or `PILOT_SEED_UNVERIFIED` + seed id | set by the server |

The response adds `source_kind`, `is_reviewed`, `review_status`, `reviewed_by`/`reviewer`/`reviewed_at` (the latest decision), `created_by`, `version`, the paper summary (title, DOI, DOI status, licences, caveat), `warnings[]`, `can_edit` and `can_review`.

## 3. Licence and legitimate access

- `FULL_TEXT` requires a legitimate full-text access basis (`OPEN_ACCESS_LICENSE`, `PUBLISHER_FREE_TO_READ`, `INSTITUTIONAL_SUBSCRIPTION`, `AUTHOR_PROVIDED_COPY`) and a recorded licence/terms (`content_license`). The database enforces this too.
- `OPEN_ACCESS_LICENSE` is only accepted when the licence named matches one that OpenAlex or Crossref recorded for that paper. If none is recorded, the person must choose another basis and write its terms.
- `ABSTRACT` requires `PUBLIC_ABSTRACT` or a full-text basis.
- `METADATA_ONLY` claims cannot carry quotations or any effect, unit, uncertainty or sample size (they cannot come from a title).
- The same rules apply to what a reviewer says they consulted.
- The system never downloads, stores or processes full texts. These fields record what people did, under which terms.

## 4. Review protocol

States: `PENDING` → `ACCEPTED` | `REJECTED` | `CHANGES_REQUESTED`; `ACCEPTED` → `REJECTED` | `CHANGES_REQUESTED` (withdrawal, e.g. a retraction). Any content edit returns the claim to `PENDING`: an earlier decision no longer applies to the new text.

Who may do what (case roles from ADR-0004):

| Action | OWNER | EDITOR | REVIEWER | VIEWER | no permission |
|---|---|---|---|---|---|
| read claims and their history | yes | yes | yes | yes | 404 |
| create, edit, delete, import pilot cards | yes | yes | 403 | 403 | 404 |
| record a review decision | yes* | yes* | yes* | 403 | 404 |

\* Never on a claim the person created, edited or imported (403). The database also rejects `reviewed_by = created_by`. All writes need an editable case (not archived, status `DRAFT` or `INVESTIGATING`; otherwise 409). Writes use the claim `version` (409 when stale).

A decision always records: the reviewer, the time, a note, the source consulted (`basis`, `access_basis`, `license`, `locator`, optional `consulted_url`) and a snapshot of the paper identity (DOI, DOI status, title, OpenAlex ID, metadata retrieval time). These go to the append-only `evidence_claim_events` table, together with every creation and edit (with before/after values). The reviewer link uses `ON DELETE RESTRICT`, so the reviewer of a decision cannot silently disappear.

`ACCEPTED` additionally requires:

1. the reviewer checked the **full text** with legitimate access and a licence (an abstract is never enough);
2. a resolved paper identity (DOI status is not `METADATA_MISMATCH` or `VERIFICATION_UNAVAILABLE`);
3. `study_design` is not `UNKNOWN`;
4. `reported_outcome.outcome` is filled in.

Claims that already have a review decision cannot be deleted; they are kept for audit and can be edited or rejected. Deleting an unreviewed claim is written to the case history.

## 5. What "reviewed" means

`ACCEPTED` / `LITERATURE_REVIEWED` means: **a named case member who did not write the claim checked it against the full text of the cited, identified paper, and recorded what they consulted.**

It does **not** mean:

- that the result applies to this farm, region, soil or season (see the ABB-15 transferability notes in `CONTRADICTIONS_APPLICABILITY.md`);
- that the study is free of bias, or that the effect is causal;
- that the outcome numbers were recomputed or validated (they are copied as stated);
- that the case or its hypotheses are scientifically validated;
- that the claim is endorsed by the authors or by an external body.

Unreviewed claims (`PENDING`, `CHANGES_REQUESTED`, `REJECTED`) keep `source_kind = LITERATURE_METADATA`, `is_reviewed = false` and a warning. Claims based on the abstract carry the warning *"Derived from the abstract only; it is not a verified study or trial result"* until accepted. Abstracts are never turned into claims automatically; every claim is written by a person.

## 6. Pilot cards

`docs/science/evidence_seed_UNVERIFIED.json` holds three pilot cards (E-001…E-003) whose text was written before anyone read the papers. `POST /api/v1/cases/{case_id}/claims/pilot-import` (OWNER/EDITOR, only on request) imports them into a case:

- each DOI is registered through OpenAlex/Crossref; the seed's own title is only used to check that the registered work is the intended one (otherwise that card is not imported and the reason is returned);
- each card becomes a `PENDING`, `METADATA_ONLY`, `PILOT_SEED_UNVERIFIED` claim with the seed limitation plus an explicit "not checked against the paper" limitation; no effect sizes or quotations are created;
- `study_type` is mapped to `study_design` only when it literally says "meta-analysis"; the reported outcome is left empty, so a card cannot be accepted until a person reads the paper and completes it;
- the import is idempotent per case, and the importing user counts as a contributor (cannot review these cards).

No code path marks a pilot card as reviewed. A backend copy of the seed is kept identical to the documentation file by a test.

## 7. Known limitations

- Only Crossref is used to check DOIs; DataCite DOIs show `NOT_FOUND_IN_CROSSREF`.
- Licence matching compares the licence strings that sources report; it does not interpret licence terms.
- "Contributor" is defined by the claim's creation and edit events; comments by other means are not tracked.
- The system cannot verify that a reviewer actually read what they say they read; it records the statement and the person.
- Claims are not yet linked to hypotheses or the evidence graph (ABB-16). Candidate disagreements and applicability notes (ABB-15) are described in `CONTRADICTIONS_APPLICABILITY.md`.
