# Feature approval & change-control policy

## Proposals, approval and coding are separate

1. Anyone (human, or AI on behalf of human) can open a **Feature proposal** GitHub Issue using the provided template.
2. Define user problem, full-release fit, user story, behavior, API/schema impact, NASA/scientific implications, tests and acceptance criteria.
3. Discuss tradeoffs openly. **At least 2 of 3 human maintainers** explicitly approve routine features via Issue comments (e.g., `APPROVE FEATURE: ...`). If the change affects scientific methodology, architecture, privacy/security, licensing, product scope or external provider cost, **all 3 must approve**.
4. A designated human maintainer applies GitHub label **`team-approved`** and records who approved + the decision link in the Issue. **AI agents cannot cast votes or add approval labels.** Label alone without approval comments is insufficient.
5. Add Issue to GitHub Project column `Approved` and assign one implementing maintainer. The assignee can be anyone, regardless of their normal domain.
6. Start branch `feat/<issue-number>-<slug>` and implement the approved acceptance criteria. Scope changes require returning to Issue approval. Bugs may be fixed via `fix/` branch with an Issue; emergency security fixes follow incident protocol.
7. Open PR linking Issue, request review from **a different human**, run CI, update docs/status and demonstrate actual behavior. Domain steward must review affected domain; two approvals are required only where branch rules/team decision demand it.
8. After merge, human moves Issue to `Done` and updates `docs/operations/CURRENT_STATE.md`. Close only after acceptance tests pass.

## GitHub Project columns

`Proposed -> Needs Specification -> Voting -> Approved -> In Progress -> In Review -> Done` plus `Blocked` and `Rejected`.

## Non-negotiable review events

- API changes: backend and frontend coordinate on schema + migration.
- Scientific logic: A and B review; all three approve material methodology changes.
- Data privacy/auth: C reviews; all three approve material privacy changes.
- CI/deployment: one other human review, rollback notes.
- `docs/architecture/ADRs`: unanimous signoff before changing architecture.

## Governance is not implemented by Markdown alone

Configure GitHub protected `main`, labels, collaborators, code owners and Project board manually. PR approval verifies code; it is **not automatically the same** as Issue feature approval. Automated CI checks tests, not whether a human approved the concept.
