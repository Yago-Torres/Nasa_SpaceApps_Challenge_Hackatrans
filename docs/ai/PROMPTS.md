# Cross-model prompt cards (Claude Code / ChatGPT Codex)

## Universal start prompt

> You are working on CropStory. Read the repository `AGENTS.md`, applicable nested instructions, `docs/ai/CONTEXT_MAP.md`, relevant product/architecture/science documents and `docs/operations/CURRENT_STATE.md`. Confirm which features are implemented, which are only specified, and which roadmap GitHub Issue is active. Inspect source/tests before planning. First show a concise plan and affected files; then implement only that Issue, add tests, update contracts/status docs and describe exact checks performed. Do not invent NASA data or scientific claims.

## Person A — Earth observation

> Implement roadmap Issue #___ in the NASA ingestion / forensic metrics domain. Read `backend/AGENTS.md`, `docs/science/SCIENTIFIC_POLICY.md`, current API contracts and tests. Handle missing data, provenance, units, geospatial resolution and caches; produce deterministic tests with verified fixtures. Coordinate schema changes with affected consumers before modifying shared endpoints.

## Person B — Scientific evidence & rotations

> Implement roadmap Issue #___ in evidence/claims/rotation domain. Read scientific policy and the Issue. Bibliographic search results are metadata, not verified findings; only attribute scientific conclusions after validation. Separate observation, hypothesis, literature finding and simulated scenario. Add tests and update evidence records.

## Person C — Product UX & integration

> Implement roadmap Issue #___ in frontend/cases/collaboration. Read UX flows and API contracts. No hardcoded scientific outputs disguised as live data. Use actual endpoint responses, render uncertainty and failures, add type checks, and ensure mobile/keyboard usability. If API support is missing, document dependency instead of inventing backend behavior.

## Code review prompt

> Review this PR against the linked roadmap Issue, AGENTS.md, applicable domain instructions, scientific policy and API contracts. Identify contract-breaking changes, unsupported scientific claims, fake live data, privacy risks, missing tests or absent status-ledger updates. Report precise blocking findings with file paths and lines.

## Handoff prompt for changing models

> Read this branch, its Issue and CURRENT_STATE. Summarize only verified changes and outstanding work as a PR comment/handoff: branch, changed files, checks run, data contract changes, blocked dependencies and next step. Don't rely on previous model chat memory.
