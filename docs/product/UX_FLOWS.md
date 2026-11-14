# Product UX flows and screen contract

Design desktop and mobile from the same data model. Never show fictional NASA observations without a conspicuous demo label.

1. **Cases dashboard**: owned, shared or public cases, status, reviewer, last update.
2. **Incident intake**: location privacy tier; geometry optional; crop rotation, year, symptoms and local constraints; consent.
3. **Forensics cockpit**: map, NASA source selector, time series, anomalies, weather episode, evidence provenance drawer, hypothesis labels.
4. **Science desk**: search verified literature metadata, DOI, evidence snippets or verified quotes within rights, study-method/scope and conflicting findings.
5. **Rotation lab**: current + at least two alternatives, assumptions, sensitivity, water/soil tradeoffs and uncertainties; no unjustified percentages.
6. **Collaborative review**: user roles, attribution, comments/objections, status, moderation; protect private field data.
7. **Case report**: all outputs traceable to sources and to case snapshot; download/export with timestamps and limitations.
8. **Admin / settings**: language, unit preferences, data permissions, case sharing and audit events.

Consistent tag vocabulary: `OBSERVED`, `FARMER_REPORTED`, `LITERATURE_REVIEWED`, `HYPOTHESIS`, `MODEL_SCENARIO`, `ILLUSTRATIVE`, `MISSING_DATA`.

Every async widget includes loading, failure, empty, partial and stale states; every chart includes readable units/description; form interactions keyboard-accessible.
