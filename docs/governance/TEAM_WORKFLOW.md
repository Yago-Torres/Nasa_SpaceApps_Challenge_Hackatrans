# Three-person workflow — coordinated delivery without implementation gates

## Roles (domain stewards, not assigned-exclusive owners)

- A: NASA sources, quantitative analysis, source quality and climate forensics.
- B: scientific claims, verified literature findings, agronomic constraints and rotation logic.
- C: UX, case persistence/auth, shared review, accessibility and release engineering.

Anyone can claim any roadmap Issue. The relevant domain steward reviews integration-sensitive work. Each task has one primary implementer, explicit acceptance criteria and a documented handoff. Avoid simultaneous edits to the same files.

## Daily team cadence

- **Kickoff (10 min)**: check `CURRENT_STATE`, select Ready Issues, assign implementers and surface dependencies.
- **Development**: work from the Issue scope, communicate shared-contract changes and run focused checks continuously.
- **Integration checkpoint (15 min)**: review diffs, API compatibility, scientific reproducibility and blockers; keep `main` demonstrable.
- **Before ending session**: record verified results, limitations, affected contracts and the next action in the Issue, PR or handoff.

## Agent handoff procedure

1. Record the Issue, base revision, files changed, checks run, API/schema impact, limitations and next action.
2. Humans decide whether and when to create a branch, commit, push or PR.
3. The next user/model reads `AGENTS.md`, the context map, `CURRENT_STATE`, the Issue and changed code.
4. A new model does not use previous model summaries to override repository tests or facts.

## GitHub settings checklist

- Three collaborators with least-privilege access; enable Issues and Projects as needed.
- Use labels such as `roadmap`, `phase:*`, `lead:*`, `priority:*`, `breaking-contract`, `science-review`, `security-review` and `blocked`.
- Project states: `Backlog`, `Ready`, `In Progress`, `In Review`, `Done`, `Blocked`, `Rejected`.
- Protect `main`: PR required when publishing, one human approving reviewer, passing `api-tests`, `web-build` and `context-policy`, resolved conversations, no force pushes; dismiss stale reviews when code changes.
- Prefer squash merges and short-lived branches when the team chooses to publish work.
- Optional CODEOWNERS after real GitHub usernames are known. Do not put fake handles into a live CODEOWNERS file.
- Releases use tags such as `v1.0.0` only when all release gates have actually passed.

## Team task ownership examples

- A owns first real NASA data source integration and quality testing.
- B owns evidence schema, DOI checks and rotation constraints.
- C owns case workflow, API-client integration and UI shell.
- Cross-cutting work has one implementer and explicit reviewers from affected domains; ownership may change through an Issue handoff.
