# Legal notice, agronomic disclaimer and third-party data policy

Status: **specified, partially enforced in code** (see "What the software actually enforces" under each section; checked against the repository on 2026-11-14). This document is written for a NASA Space Apps hackathon prototype, not a reviewed legal or regulatory filing; before any real deployment it needs review by qualified legal counsel in the jurisdiction of deployment, consistent with `docs/governance/FEATURE_POLICY.md` and `docs/science/SCIENTIFIC_POLICY.md`.

## 1. Legal notice

CropStory ("the software") is a prototype built for the NASA International Space Apps Challenge. It is provided **as-is, without warranty of any kind**, express or implied, including without limitation warranties of merchantability, fitness for a particular purpose, accuracy or non-infringement. The authors and contributors are not liable for any loss arising from use of the software, its data, or its outputs.

The software is not a certified agricultural, financial, insurance, or legal advisory product. It does not establish any professional relationship between its operators and its users. Nothing in the software constitutes legal, financial, insurance, or regulatory advice.

**What the software actually enforces:** nothing in code depends on or asserts a specific legal status; this section is informational text for operators/users, not an API behavior.

## 2. Agronomic disclaimer

CropStory presents Earth observation data, farmer-reported information, scientific literature metadata/claims, hypotheses and rule-based rotation comparisons. Per `docs/science/SCIENTIFIC_POLICY.md`:

- **Observed data** (NASA POWER, future GPM/HLS) is regional/gridded, not a field-scale measurement; see each response's `spatial_resolution`/`temporal_resolution`. It does not by itself prove a cause of crop damage.
- **Hypotheses** are possible explanations with stated pros/cons, never a causal or quantified certainty. Co-occurrence of a weather anomaly and a reported incident is never presented as proof of cause (`docs/science/TIMELINE_HYPOTHESES.md`).
- **Rotation comparisons and scenarios** (`docs/science/ROTATIONS.md`, `SCENARIOS_SENSITIVITY.md`) are descriptive and rule-based. They never produce a yield, water-saving or income figure, weight, probability or score unless backed by a validated, calibrated model with an uncertainty interval — which does not exist in this product yet (`verified_impact` stays `null` everywhere it appears).
- **Literature claims** are only presented as reviewed evidence (`LITERATURE_REVIEWED`) after a human full-text check recorded in `evidence_claim_events`; metadata alone (`LITERATURE_METADATA`) never implies the article supports a given claim.
- Historical climate scenario replay is observed past weather, not a forecast (`SCENARIOS_SENSITIVITY.md`).
- **This software does not replace consultation with a qualified agronomist, extension service or locally licensed professional before acting on any finding it presents**, especially before a purchasing, planting or insurance decision.

**What the software actually enforces:** the `source_kind`/`status`/`verified_impact: null` fields described above are real, typed response fields produced by the backend (`services/metrics.py`, `services/rotations.py`, `services/scenarios.py`, `uncertainty.py`, `evidence.py`), covered by the tests listed in `docs/operations/CURRENT_STATE.md`. The disclaimer text itself is not yet rendered as UI copy in every screen; that is tracked as frontend work, not a backend gap.

## 3. Third-party data policy

| Source | What CropStory does with it | Terms CropStory follows |
|---|---|---|
| **NASA POWER** (`GET /api/climate`, `/api/v1/cases/{id}/observations/nasa-power`) | Fetches daily meteorological parameters over HTTPS for a specific point and date range; stores a `SourceManifest` (endpoint, query parameters, checksum, retrieval time, resolution, license field) alongside derived monthly values and anomalies. | NASA POWER data is public domain US Government data; CropStory always attributes the dataset (`POWER Daily API` + version from the upstream response header) and never claims it as CropStory's own measurement. Precise field coordinates are sent to NASA POWER over HTTPS to run the query — this is disclosed to the user as an open privacy decision (ADR-0004/ADR-0005); nothing else about the query (case identity, farmer identity) is sent upstream. |
| **OpenAlex** (`GET /api/literature`, `POST /api/v1/evidence/papers`) | Fetches bibliographic metadata (title, authors, venue, licenses, OpenAlex ID) for works matching a search query or identifier. | OpenAlex metadata is CC0; CropStory stores and serves only metadata it retrieved from OpenAlex itself, never a scraped or user-submitted substitute, and records `retrieved_at`/`processing_version` for traceability (`docs/science/EVIDENCE_CLAIMS.md`). |
| **Crossref** | Cross-checks each DOI's metadata against the Crossref record (`doi_status`). | Used only to verify identity (title/author/year match), consistent with Crossref's public metadata API terms; no full text is fetched from Crossref. |
| **Full-text of a paper, when a reviewer records a claim as `FULL_TEXT`** | The reviewer must record a legitimate `access_basis` (`OPEN_ACCESS_LICENSE`, `PUBLISHER_FREE_TO_READ`, `INSTITUTIONAL_SUBSCRIPTION`, `AUTHOR_PROVIDED_COPY`) and the `content_license`/terms under which they read it (`docs/science/EVIDENCE_CLAIMS.md`). | CropStory never stores or redistributes the paper's full text itself — only a short attributed quotation (`quoted_fragment`) and the claim text the reviewer wrote, with the recorded license. A claim claiming `OPEN_ACCESS_LICENSE` is checked against a license OpenAlex/Crossref actually reported for that work; it is rejected otherwise. |

**What the software actually enforces:** the database CHECK constraints `ck_claim_full_text_access`, `ck_claim_quote_needs_source_text` and the API-level license match in `evidence.py`/`api/evidence.py` are real and tested (`backend/tests/test_evidence_claims.py`). Upstream failures (rate limits, outages) return a generic 502 and never fall back to fabricated data (`services/power.py`, `services/literature.py`).

## 4. Data minimisation, retention, export, deletion and consent (ABB-28)

This section is the policy that `docs/architecture/ADRs/0004-authentication-and-case-permissions.md` and `0005-account-data-export-and-deletion.md` implement.

### What is collected and why

- **Account:** e-mail (login identity, shown to case owners who grant you access), display name, a salted password hash (never the password itself), and session metadata (never the raw token). See `backend/agroblackbox/security.py`.
- **Case data:** everything the user explicitly enters about an incident (title, dates, crop history, notes) and each field's location at a privacy tier the user chooses (`EXACT` only with explicit consent, `APPROXIMATE` grid-rounded, `REGION_ONLY`, or `WITHHELD` — nothing stored). See `backend/agroblackbox/privacy.py` and ADR-0004.
- **Collaboration:** who has what role on a case, and an append-only history of changes (who, when, before/after) for audit and scientific traceability. Reviewers and viewers never receive a field's exact coordinates in any response or history entry unless the owner gave consent (`redact_coordinates`, tested in `backend/tests/test_auth_privacy.py` and `test_api_cases.py`).

### Consent

- Sharing a case with another account (editor/reviewer/viewer) is an explicit action by the owner (`POST /api/v1/cases/{id}/permissions`), revocable at any time (`DELETE .../permissions/{user_id}`) and effective on the member's very next request — permissions are read from the database every time, never cached (ADR-0004).
- Sharing a field's **exact** location with a reviewer/viewer beyond the chosen privacy tier requires a separate, revocable `precise_location_consent` flag per field (`PATCH .../fields/{id}`).

### Retention

- Case content, history and evidence are kept indefinitely while the case (or the account that owns it) exists — this is the working record the product's audit/review model depends on.
- Session rows past their expiry or revocation are not useful once that happens; `backend/agroblackbox/retention.py#purge_stale_sessions` removes them after a 30-day forensic window. It is a maintenance function run manually or by a future scheduled job, not yet wired to an automatic scheduler (no job runner is deployed; see the Redis row in `docs/operations/CURRENT_STATE.md`).

### Export

`GET /api/v1/account/export` returns, for the authenticated account only: its profile, every case it is a member of (through the same role-aware location redaction as every other case response — a reviewer's export shows exactly what that reviewer already sees, never more), and its own session metadata (timestamps and revocation state, never a token or its digest).

### Deletion ("right to erasure", scoped honestly)

`POST /api/v1/account/delete` (password re-confirmation required; same lockout as login after 5 wrong attempts) is **irreversible** and:

1. permanently erases every case the account **owns** — its fields, permissions, history, NASA POWER observations/anomalies, hypotheses, evidence claims and review history, uncertainty answers, evidence-graph conclusions/edges, rotations, reviews and reports;
2. revokes the account's access to every case owned by someone else;
3. revokes every session;
4. scrubs the account's e-mail and display name and disables login, while **keeping an anonymised account row** so that another user's case — where this account only ever reviewed or authored evidence, never owned it — keeps a valid, unambiguous record of who did what. That is a deliberate choice, not an oversight: several review/audit tables reference the acting user with a foreign key that forbids silently losing that reference (`ON DELETE RESTRICT`; see ADR-0005 for the full list and rationale). **Deleting your account does not remove your name from evidence you reviewed on a case you did not own** — it removes your e-mail, display name and ability to log in, and erases everything you owned outright.

The deletion response states exactly what was deleted (counts of cases erased, memberships revoked, sessions revoked) rather than a bare confirmation, so the user is told the true scope of the action.

### Known gaps (not yet built — do not claim otherwise)

- No e-mail verification, password reset, multi-factor authentication or invitation-acceptance flow (ADR-0004).
- No IP-based rate limiting; brute-force protection is per-account lockout only (ADR-0004; still true after ABB-28).
- Session purge is a manual/maintenance function, not an automatic scheduled job.
- NASA POWER's raw response payload (including the queried coordinates) is cached on the server's local filesystem under `backend/.cache/power/` for 24 hours (`services/power.py`), **without the case-level role/consent redaction** that protects coordinates everywhere else in the API. This cache is never committed to the repository (`backend/.cache/` is git-ignored) and is keyed only by a hash of the query parameters, but it is a real at-rest exposure on a running server that should be addressed (e.g. encryption at rest, access-controlled storage, or a shorter TTL) before handling real farm locations in production; filed for the team owning caching/resilience work (ABB-27) rather than fixed here, since it is outside this change's scope.
- No data-processing agreement, cross-border transfer assessment or named regulatory basis (GDPR/CCPA/local law) has been written; this document is a product-level policy, not a compliance filing.
