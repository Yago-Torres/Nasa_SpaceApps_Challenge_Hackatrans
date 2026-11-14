# Product UX flows and screen contract

Design desktop and mobile from the same data model. Never show fictional NASA observations without a conspicuous demo label.

0. **Account**: sign in or create an account (name, e-mail, password of 12–256 characters) from the Cases screen; the rail shows who is signed in and a sign-out link. The session lasts up to 12 hours in the current tab only. Wrong credentials, an existing account, a lockout (with the wait the server sent) and "server storage not available" each get their own message; typed input is never cleared by an error.
1. **Cases dashboard**: owned, shared or public cases, status, reviewer, last update. Implemented (signed in) as a table: case, workflow status, your role, location as reviewers see it, incident year, last update; edit for owners/editors, open (read-only) for reviewers/viewers, delete for owners with confirmation. Public cases and reviewer names are not built.
2. **Incident intake**: location privacy tier; geometry optional; crop rotation, year, symptoms and local constraints; consent. Implemented as a five-step wizard (Where, What was grown, What happened, Constraints, Review and share) with per-step validation that never discards input, autosave, a to-scale preview of what reviewers see (exact point for the owner; rounded 0.1/0.5/1° cell centre, region label or nothing for guests; exact point only with explicit consent), and a list of non-blocking missing inputs. Saving requires sign-in and goes to `/api/v1/cases`: the case is created once it has a name, a valid location and the incident year, then every change autosaves with the version that was read. If someone else saved first, the user chooses between loading the saved version and saving over it. Reviewers and viewers see the case read-only with the location the server redacted. Existing cases open with the case title block (ID, location, status, role, owner, update time). Mapping details: `docs/architecture/FRONTEND_INTEGRATION.md` §6.
3. **Forensics cockpit**: map, NASA source selector, time series, anomalies, weather episode, evidence provenance drawer, hypothesis labels.
4. **Science desk**: search verified literature metadata, DOI, evidence snippets or verified quotes within rights, study-method/scope and conflicting findings.
5. **Rotation lab**: current + at least two alternatives, assumptions, sensitivity, water/soil tradeoffs and uncertainties; no unjustified percentages.
6. **Collaborative review**: user roles, attribution, comments/objections, status, moderation; protect private field data.
7. **Case report**: all outputs traceable to sources and to case snapshot; download/export with timestamps and limitations.
8. **Admin / settings**: language, unit preferences, data permissions, case sharing and audit events.

Consistent tag vocabulary: `OBSERVED`, `FARMER_REPORTED`, `LITERATURE_REVIEWED`, `HYPOTHESIS`, `MODEL_SCENARIO`, `ILLUSTRATIVE`, `MISSING_DATA`.

Every async widget includes loading, failure, empty, partial and stale states; every chart includes readable units/description; form interactions keyboard-accessible.
