# Three-person workflow — no permanently siloed development

## Roles (domain stewards, not assigned-exclusive owners)

- A: NASA sources, quantitative analysis, source quality and climate forensics.
- B: scientific claims, verified literature findings, agronomic constraints and rotation logic.
- C: UX, case persistence/auth, shared review, accessibility and release engineering.

Anyone can claim any approved GitHub Issue. The domain steward reviews across boundaries. Each task has exactly one implementer, one human reviewer, and clear acceptance criteria. Don't simultaneously edit the same files in parallel branches if avoidable.

## Daily team cadence

- **Kickoff (10 min)**: source-of-truth check `CURRENT_STATE`, vote on proposals, assign approved Issues, surface dependencies.
- **Development**: commit small changes on `feat/<issue>-<slug>` branches, run local checks, integrate every few hours.
- **Integration checkpoint (15 min)**: PR review, API compatibility, reproducibility, resolve blockers; `main` remains demonstrable.
- **Before ending session**: update Issue/PR handoff and current-state ledger upon merge. No critical decisions only in a voice call/DM.

## Agent handoff procedure

1. Commit and push stable changes on the task branch.
2. Record Issue number, base commit, files changed, tests run, new API/schema, limitations and next action in the PR or a GitHub Issue comment.
3. Next user/model reads repo `AGENTS.md`, context map, current state, Issue and changed code.
4. New model **does not** use previous model's subjective summaries to override repository tests or facts.

## GitHub settings checklist (team must configure)

- Organization-owned repo, 3 collaborators with write access; least privilege for external collaborators.
- Enable Issues, Projects, Discussions only if needed; provide `team-approved`, `needs-vote`, `breaking-contract`, `science-review`, `security-review` labels.
- Protect `main`: PR required, **1 human approving reviewer minimum**, pass `api-tests`, `web-build`, `context-policy`, conversations resolved, no direct pushes/force pushes; dismiss stale approvals when code changes.
- Use squash merges and short-lived branches; require review from domain steward on affected changes.
- Optional CODEOWNERS after real GitHub usernames are known. Do not put fake handles into a live CODEOWNERS file. Remember GitHub's CODEOWNERS accepts approval from **any one** listed owner, not everyone.
- Releases use version tags like `v1.0.0` only when all release gates have actually passed.

## Team task ownership examples

- A owns first real NASA data source integration and quality testing.
- B owns evidence schema, DOI checks and rotation constraints.
- C owns case workflow, API-client integration and UI shell.
- Cross-cutting integration has one issue assigned to C with A/B as reviewers; members may swap ownership after a group decision.
