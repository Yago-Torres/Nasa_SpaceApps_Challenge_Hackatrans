# Product release 1.0 — complete required scope

**Target definition, not a claim of completion.** All items in this document are intended to be delivered before designating a stable full 1.0 release. A documented roadmap change may change details with an ADR and updated acceptance criteria.

| ID | Module | Required acceptance criteria | Status (source: CURRENT_STATE) |
|---|---|---|---|
| F-01 | Accounts & permissions | sign in; cases private by default; role-aware review and consent | NOT BUILT |
| F-02 | Case management | create/edit/version case with location precision, crop history and incident notes | NOT BUILT |
| F-03 | NASA connector layer | POWER working; chosen additional GPM/HLS source integrated with provenance, caching, rate/error handling | PARTIAL |
| F-04 | Forensic timeline | meaningful baseline, observation quality flags and hypotheses with competing explanations | PARTIAL |
| F-05 | Scientific evidence | OpenAlex/Crossref search, DOI verification, study-context records, manual review and contradictions | PARTIAL |
| F-06 | Evidence graph | case evidence -> hypotheses -> citations -> conclusions, interactive traceability | NOT BUILT |
| F-07 | Rotations & constraints | >=3 rotations including current; crop calendars, soil, farmer priorities, water, risks, explicit comparisons | PARTIAL |
| F-08 | Uncertainty hunter | missing-data checklist; reasons measurement might alter decision; never fake certainty | NOT BUILT |
| F-09 | Collaboration | invitations and reviewed comments/changes between communities, permissioned | NOT BUILT |
| F-10 | Case report/export | downloadable report with real results, DOIs, methods, provenance and caveats | PARTIAL |
| F-11 | Product UX | end-to-end responsive, accessible map/time series/evidence exploration, multilingual support EN/ES | PARTIAL |
| F-12 | Operations & QA | PostgreSQL persistence, async job processing, API schema, tests, CI, secure deploy, metrics/logging, recovery | PARTIAL |

## Release acceptance gates

- E2E: a real user goes through case -> NASA -> evidence -> rotation comparisons -> external review -> generated report without manual API calls.
- Sources: no user-facing scientific finding without identifiable provenance and limitations.
- Permissions: private locations and user data protected. Negative auth tests pass.
- Reliability: upstream NASA/OpenAlex outage gives honest recoverable error, never mock values presented as real.
- Tests: backend, frontend typecheck/build, integration tests, and one documented real NASA retrieval executed in an Internet-enabled environment.
- Pilot: at least one specific local use case reviewed by a relevant human; one genuine external collaboration to substantiate Global Connection.
- Docs: CURRENT_STATE reflects true implementation, runbooks, clean install, scientific methods and known risks.
- Demo and deployment: externally accessible, stable 1.0 release tag, easy contributor onboarding.

## Integration strategy

Not a reduced MVP. All modules above are part of the 1.0 scope. Develop in **vertical, testable slices**: infrastructure/conventions, case/data integration, science/rotations, collaboration, reporting, hardening. You may merge incomplete modules behind clearly labeled disabled flags; **do not ship a feature as completed until its acceptance criteria pass**.

