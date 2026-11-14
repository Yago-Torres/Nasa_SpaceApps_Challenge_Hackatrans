# Frontend integration guide (for A and B)

Owner: C (frontend). Status of each item is explicit: **IMPLEMENTED** means it exists in `frontend/src` and has tests; **REQUESTED** is a proposal for the backend owner to accept, change or reject in the linked Issue. Nothing marked REQUESTED is implemented by the backend, and the frontend does not fake it.

## 1. How the frontend consumes the API today (IMPLEMENTED, ABB-20)

- All HTTP calls live in `frontend/src/api/client.ts`; response types in `frontend/src/api/types.ts`, transcribed from `backend/agroblackbox/app.py` and `services/*.py`. When you change a response shape, update `types.ts` in the same PR (or tell C) so `npm run build` keeps catching drift.
- Errors: non-2xx responses become `ApiError(status, "HTTP <status>: <detail>")`. The UI shows the backend `detail` string verbatim in the error state, so keep `detail` short and human-readable. Network failures show a fixed sentence.
- Screens and endpoints:

| Screen (`#/route`) | Endpoint | Evidence label shown |
|---|---|---|
| Investigation (`#/investigation`) | `GET /api/climate` (reference fixed to 2010–2021) | Observed · NASA POWER |
| Evidence (`#/evidence`) | `GET /api/literature` | Metadata only (never Reviewed literature) |
| Rotations (`#/rotations`) | `GET /api/v1/crop-catalog`, `POST /api/v1/rotations/scenarios`, `/sensitivity` | Backend-returned MODEL_SCENARIO, with declared inputs and limitations |
| Report (`#/report`) | `POST /api/report` | Preliminary |
| Cases (`#/cases`, `#/cases/new`, `#/cases/<id>`) | `/api/v1/auth/*`, `/api/v1/cases*` (see §6) | Farmer reported (wizard answers); status/role as returned |
| Collaboration | none yet | "Not built yet" state, no sample data |

- The frontend computes no statistics. It only scales returned values for drawing (`features/chartScale.ts`).

## 2. Requests to A (backend, NASA, contracts)

| # | Request | Why the UI needs it | Issue |
|---|---|---|---|
| A1 | Add `spatial_resolution` (e.g. `"0.5° × 0.625°"`) and `retrieved_at` (ISO 8601 UTC) to `/api/climate` | The Source label shows both; today they render as *Missing data · not returned by the API yet* | ABB-07 |
| A2 | A shared provenance object on every observation: `source_kind`, `dataset`, `endpoint`, `request_params`, `units`, `spatial_resolution`, `temporal_resolution`, `retrieved_at`, `sha256`, `limitations[]`, `processing_version` | One `SourceLabel` component renders all sources the same way (POWER, GPM, HLS) | ABB-02, ABB-07 |
| A3 | Per-month quality flags (`complete` / `partial` / `missing` + reason) instead of only `null` | The partial state could say *why* a month is missing | ABB-08 |
| A4 | ~~`/api/v1/cases` CRUD with a `location` object~~ **Done differently in ABB-05/06** (`CaseFieldView` with server-side redaction); the frontend adapted, see §6 | ABB-21 wizard and the "guests never see exact location" acceptance test | ABB-02, ABB-05, ABB-06 |
| A8 | Optional: case attributes for the wizard answers that today travel in the `incident_notes` block (incident year, symptom months, affected share, water/soil/priorities, crop-row notes) | Lets reviewers and the report read them as typed fields instead of a JSON block | ABB-06, ABB-11 |
| A9 | Optional: a single request that updates case attributes and one field with one version bump | A title change now sends two PATCHes (case title + field label) | ABB-06 |
| A5 | Timeline endpoint with layers `observed` / `farmer_reported` / `hypothesis`, each event with `kind`, `start`, `end`, `provenance` | ABB-22 timeline lanes | ABB-10 |
| A6 | Decide whether `backend/.cache/` (now in `.gitignore`) should be untracked; one cache file is still versioned | Avoid committing runtime data | ABB-01 |
| A7 | Generate and publish the OpenAPI schema in CI so the frontend can switch to generated types | Replace hand-written `types.ts` | ABB-02, ABB-29 |

## 3. Requests to B (science, evidence, rotations)

| # | Request | Why the UI needs it | Issue |
|---|---|---|---|
| B1 | Configure `OPENALEX_API_KEY` (or polite-pool `mailto` set by the team, not by an agent) | OpenAlex answers `429 Too Many Requests` to shared egress; the Evidence screen currently shows the error state | ABB-13 |
| B2 | Reviewed-claim object: `claim`, `doi`, `study_context` (region, crop, method), `limitations`, `reviewer`, `reviewed_at`, `status` | Promote a paper from *Metadata only* to *Reviewed literature* | ABB-14 |
| B3 | Evidence-graph payload: nodes `{id, kind ∈ OBSERVED…MISSING_DATA, label, provenance}` and edges `{from, to, relation ∈ supports/contradicts, note}` | ABB-23 graph and its accessible list view | ABB-16 |
| B4 | ~~Rotation comparison payload~~ **Implemented in ABB-17/18**: `/api/v1/rotations/scenarios` returns rule-generated strategies, ordinal ordering, trade-offs, exposure, explanations and limitations. No numeric yield/water claims or impact score. UI sends farmer-declared inputs and renders the response. | ABB-24 comparator | ABB-17, ABB-18 |
| B5 | Uncertainty Hunter items: `{question, why_it_matters, measurement, would_change}` | "Would settle it" column of hypotheses | ABB-19 |

## 4. Design system rules that affect backend payloads

- Every value shown must map to one evidence kind: `OBSERVED`, `FARMER_REPORTED`, `LITERATURE_REVIEWED`, `HYPOTHESIS`, `MODEL_SCENARIO`, `ILLUSTRATIVE`, `MISSING_DATA`. Please include the kind in payloads (field `kind`) using these exact codes; the UI labels them in EN/ES.
- Limitations are always displayed; send them as plain sentences.
- Hypotheses never carry a confidence percentage unless a validated method exists (SCIENTIFIC_POLICY).
- UI work itself must follow `.claude/skills/agro-design-system` (mandatory, see `AGENTS.md`).

## 5. Running and testing the frontend

```bash
cd frontend && npm ci
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000
npm test           # Vitest + Testing Library (jsdom)
npm run build      # tsc + vite
```

Tests use `fetch` mocks with synthetic fixtures **only inside `*.test.tsx`**; the app itself never ships sample data.

## 6. Accounts and cases in the web app (IMPLEMENTED, ABB-21 + ABB-06 UI)

Code: `frontend/src/api/session.ts`, `api/client.ts` (`authApi`, `casesApi`), `cases/mapping.ts`, `cases/repository.ts` (`HttpCaseRepository`), `features/account/*`, `features/Cases.tsx`, `features/cases/*`. Tests: `cases/mapping.test.ts`, `features/cases/IncidentWizard.test.tsx` (fetch mock of the documented contract, synthetic data only).

**Decision: saving a case requires sign-in.** The development browser storage used before ABB-06 is gone from the UI; a case is either on the server or not saved, never mixed. Old browser-only cases (`localStorage` key `abb-dev-cases-v1`) are not imported; the Cases screen counts them and offers "Delete browser copies" because they hold exact coordinates. Signed out, the list shows the sign-in panel; the wizard stays usable and keeps the answers on the page with "Sign in to save this case".

**Session.** `POST /api/v1/auth/login` → the opaque token is held in memory and in this tab's `sessionStorage` (`abb-session-v1`), never in `localStorage`, URLs or logs. Requests to `/api/v1/cases*` and `/auth/logout` send `Authorization: Bearer`. Any 401 on an authenticated request clears the session; open screens keep their input and show the sign-in panel ("Your session ended…"). Sign-up calls register then login. Sign-out calls logout and clears locally even if the server is unreachable.

**Errors shown.** 401 sign-in → "email or password is not correct"; 409 register → "account exists"; 429 → "try again in N minutes" from `Retry-After`; 503 → "Case storage is not available on this server" (no list, no sample data); 403 → role message; 404 → "does not exist or no access"; 409/422 on save → the server `detail`, input kept; network → fixed sentence.

**Wizard → API mapping** (`cases/mapping.ts`):

| Wizard | API |
|---|---|
| Case name | `title`; also the field `label` (one field per wizard case) |
| Approximate area + 0.1/0.5/1° | field `privacy_tier=APPROXIMATE`, `rounding_deg` |
| Region name only | `REGION_ONLY`, `region_label` = the farmer's text |
| Only me | `REGION_ONLY`, `region_label = "Not shared by the owner"` (never `WITHHELD`, which cannot store the owner's coordinates). Reviewers receive `region_label` for every tier, so non-region tiers always send this fixed label |
| Let reviewers see the exact point | `precise_location_consent` |
| Latitude / longitude | field `latitude` / `longitude` (owners and editors get them back; reviewers/viewers get the server-redacted value) |
| Symptom months | `incident_start` = first day of the start month, else 1 January of the incident year; `incident_end` = last day of the end month capped at today, else null. Months before 1900 or in the future are rejected in the form |
| Crop rows | `crop_history` = `"2022: durum wheat"` (1–120 chars, ≤ 50 rows; rows without a crop skipped) |
| Symptoms text | start of `incident_notes` |
| Incident year, symptom months, affected share, water, soil, priorities, full crop rows (with notes) | a JSON block appended to `incident_notes` after the line `--- AGRO BLACK BOX wizard answers v1 (structured; edit them in the wizard) ---`. Reversible; contains no coordinates. If `crop_history` was changed by another client, `crop_history` wins and the block's rows are ignored. Notes without the block are shown as plain symptom text |

Reading back: `APPROXIMATE`/`EXACT` → Approximate area (an `EXACT` field is not changed unless the owner changes the tier), `REGION_ONLY` with the fixed label or `WITHHELD` → Only me, other `REGION_ONLY` → Region name only. The wizard edits the first field only and says so when a case has more.

**Saving and versions.** A new case is created (`POST`) once it has a name, a valid location and the incident year; before that the form says "Not saved yet" and nothing leaves the browser tab. Afterwards autosave (600 ms) sends only changed attributes: `PATCH /cases/{id}` then `PATCH /cases/{id}/fields/{field_id}`, each with the version last read from the server. Saves are queued so a slow create is never sent twice. On 409 the adapter reloads the case: if the version moved, the user sees "Someone else saved this case first" with *Load the saved version* or *Save my version over it* (explicit overwrite with the new version); otherwise the server detail (archived / not editable) is shown. Delete (owner only) sends `?version=`; a 409 reloads the list.

**Roles and status.** List columns: Case · Status · Your role · Shared as · Incident year · Updated. Case screens open with the title block (ID, location as this user may see it, status, role, owner, updated). Reviewers and viewers, and cases that are REVIEWED, PUBLISHED or archived, open read-only; their location is exactly what the server returned (rounded cell, region label or "Not shared with you"). Status labels avoid implying scientific validation ("Reviewed by a team reviewer", "Final (team only, not public)").

**Not in this UI yet:** sharing/permissions management, workflow status changes, archive, history view, multiple fields per case, basemap (tile provider decision pending).
