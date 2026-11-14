# Development board bootstrap

GitHub Issues + Projects are the live source of truth once connected; this file supplies the initial planning context and dependency map, not a second task tracker.

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
