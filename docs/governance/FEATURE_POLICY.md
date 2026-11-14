# Feature delivery and change-control policy

## Roadmap Issues are executable

1. A roadmap GitHub Issue with scope, acceptance criteria and affected domains is available for implementation immediately. It does not require votes, `team-approved` or another administrative approval label.
2. Dependencies describe technical integration order, not permission to begin. Work may proceed on isolated components, tests, fixtures or contracts while dependencies are incomplete, provided unfinished integration is stated clearly.
3. Each active task has one primary implementer. A/B/C are domain stewards, not exclusive owners; any contributor may implement any roadmap Issue.
4. Before editing, inspect the current source, tests and contracts. Identify shared files, data/science/privacy impact, dependencies and the checks that will prove the change.
5. Coordinate shared API/schema changes with affected consumers. Record durable architecture or methodology decisions in an ADR or the Issue, including alternatives, consequences and rollback.
6. New dependencies, endpoints, migrations and external services must remain within Issue scope and include deterministic tests, secure defaults and failure handling.
7. Humans decide when to create branches, commits, pushes and PRs. Agents do not publish Git operations unless explicitly requested.
8. Update `CURRENT_STATE.md` only after integration has been exercised. Never infer completion from documentation or an untested implementation.

## Work states

`Backlog -> Ready -> In Progress -> In Review -> Done` plus `Blocked` and `Rejected`.

## Required coordination and review

- API/schema changes: communicate the contract to backend and frontend consumers; provide compatibility and contract tests.
- Scientific logic: document assumptions, provenance, limitations and uncertainty; obtain domain review before presenting results as validated.
- Data privacy/auth: threat-model access boundaries and run negative permission tests before integration.
- CI/deployment: document rollback and require another person to review published changes.
- Architecture: record the decision in an ADR with options and consequences; coordinate with every affected domain.

Review protects integration quality but is not a vote granting permission to start implementation. CI verifies code and tests; it does not establish scientific validity or product completion.
