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
| Rotations (`#/rotations`) | `GET /api/rotations/demo` | Illustrative (per CURRENT_STATE), although payload says `modelled_scenario` |
| Report (`#/report`) | `POST /api/report` | Preliminary |
| Cases, Collaboration | none yet | "Not built yet" state, no sample data |

- The frontend computes no statistics. It only scales returned values for drawing (`features/chartScale.ts`).

## 2. Requests to A (backend, NASA, contracts)

| # | Request | Why the UI needs it | Issue |
|---|---|---|---|
| A1 | Add `spatial_resolution` (e.g. `"0.5° × 0.625°"`) and `retrieved_at` (ISO 8601 UTC) to `/api/climate` | The Source label shows both; today they render as *Missing data · not returned by the API yet* | ABB-07 |
| A2 | A shared provenance object on every observation: `source_kind`, `dataset`, `endpoint`, `request_params`, `units`, `spatial_resolution`, `temporal_resolution`, `retrieved_at`, `sha256`, `limitations[]`, `processing_version` | One `SourceLabel` component renders all sources the same way (POWER, GPM, HLS) | ABB-02, ABB-07 |
| A3 | Per-month quality flags (`complete` / `partial` / `missing` + reason) instead of only `null` | The partial state could say *why* a month is missing | ABB-08 |
| A4 | `/api/v1/cases` CRUD with a `location` object: `precise {lat, lon}` (owner only), `shared {lat, lon, rounding_deg}`, `privacy_tier` (`private`/`rounded`/`region`), `consent_shared_precise: bool` | ABB-21 wizard and the "guests never see exact location" acceptance test | ABB-02, ABB-05, ABB-06 |
| A5 | Timeline endpoint with layers `observed` / `farmer_reported` / `hypothesis`, each event with `kind`, `start`, `end`, `provenance` | ABB-22 timeline lanes | ABB-10 |
| A6 | Decide whether `backend/.cache/` (now in `.gitignore`) should be untracked; one cache file is still versioned | Avoid committing runtime data | ABB-01 |
| A7 | Generate and publish the OpenAPI schema in CI so the frontend can switch to generated types | Replace hand-written `types.ts` | ABB-02, ABB-29 |

## 3. Requests to B (science, evidence, rotations)

| # | Request | Why the UI needs it | Issue |
|---|---|---|---|
| B1 | Configure `OPENALEX_API_KEY` (or polite-pool `mailto` set by the team, not by an agent) | OpenAlex answers `429 Too Many Requests` to shared egress; the Evidence screen currently shows the error state | ABB-13 |
| B2 | Reviewed-claim object: `claim`, `doi`, `study_context` (region, crop, method), `limitations`, `reviewer`, `reviewed_at`, `status` | Promote a paper from *Metadata only* to *Reviewed literature* | ABB-14 |
| B3 | Evidence-graph payload: nodes `{id, kind ∈ OBSERVED…MISSING_DATA, label, provenance}` and edges `{from, to, relation ∈ supports/contradicts, note}` | ABB-23 graph and its accessible list view | ABB-16 |
| B4 | Rotation comparison payload: ≥3 options (current first), each with `years[][]`, `assumptions[]`, `tradeoffs[]` (qualitative, with source refs), `uncertainties[]`, `kind` (`MODEL_SCENARIO` or `ILLUSTRATIVE`), and **no numeric yield/water claims without a validated model + interval** | ABB-24 comparator | ABB-17, ABB-18 |
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
