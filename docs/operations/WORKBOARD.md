# Development board bootstrap

GitHub Issues + Projects are the live source of truth once connected; this file supplies the initial planning context and dependency map, not a second task tracker.

## Live board (ABB-04, configured 2026-11-14)

- Project: **CropStory 1.0 roadmap** — https://github.com/users/M-a-t-e-o/projects/2 (linked to the repository). Every roadmap Issue ABB-01…ABB-34 is an item.
- Column field `Stage`: `Backlog`, `Ready`, `In Progress`, `In Review`, `Done`, `Blocked`, `Rejected` (matches `FEATURE_POLICY.md`).
- Each open Issue has an assignee (owner) and keeps its acceptance criteria in the Issue body; `lead:*`, `phase:*` and `priority:*` labels give routing and order.
- Review labels: `science-review`, `breaking-contract`, `security-review`, `blocked`, `needs-spec`. The obsolete `needs-vote` label was removed from all Issues after the governance simplification (ABB-01).
- Blocked items carry the `blocked` label and a comment stating exactly what unblocks them (e.g. ABB-09/ABB-12 need an Earthdata Login token; ABB-31/32/34 need real human participants).

### How agents use the board

1. Pick a `Ready` Issue whose technical dependencies are merged (see "Shared dependencies" below); set `Stage = In Progress`.
2. Work on `feat/<issue>-<slug>` from current `main`; open a PR with `Closes #<n>`, exact verification outputs and the template checklist; set `Stage = In Review`.
3. After green CI (`api-tests`, `web-build`, `context-policy`) and merge, set `Stage = Done`; leave a handoff comment on the Issue if follow-up work remains.

## Initial parallel workstreams

- Stream A — NASA & Forensics: `F-03 NASA adapters -> F-04 timelines -> F-08 uncertainty -> integration`.
- Stream B — Science & Scenarios: `F-05 reviewed scientific findings -> F-07 rotations -> F-06 evidence graph data -> F-10 reporting`.
- Stream C — Product & Collaboration: `F-01 accounts -> F-02 cases -> F-11 UX -> F-09 reviews -> F-12 deploy/hardening`.

## Shared dependencies

- F-02 case ID/auth required before persistent observation, review or report storage.
- F-05 reviewed claims schema precedes full evidence graph and evidence-based rotation explanations.
- F-03 provenance schema precedes final timeline and report.
- F-07 full constraints must be scientifically reviewed before publishing comparative claims.
- All feature APIs need coordinated typed DTO contracts before frontend integration.

## Integration milestones (not partial product releases)

- Foundation synchronized: all three can develop on Linux/WSL, contracts agreed, CI green.
- Full case lifecycle wired: create case, ingest source evidence, show persisted timeline.
- Science integrated: review literature, compare three credible rotations, audit claims and gaps.
- Collaboration + export integrated: multiuser review and complete reproducible case report.
- Release 1.0 gates: security, scientific review, production deployment, recovery, multilingual/accessibility and local external validation.
