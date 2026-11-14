# GitHub initial setup — step-by-step

1. Create team-owned organization/repository `agro-black-box`; select appropriate privacy (public is useful for hackathon, but do not expose real private cases).
2. Upload/unzip this folder to repo. `git init -b main; git add .; git commit -m 'chore: set up shared AI-ready monorepo'; git remote add origin <real-origin-url>; git push -u origin main`.
3. Invite all three maintainers with write; enable Issues and Projects.
4. Add labels: `roadmap`, `phase:*`, `lead:*`, `priority:*`, `science-review`, `breaking-contract`, `security-review`, `blocked`, `needs-spec`.
5. GitHub Project columns `Backlog`, `Ready`, `In Progress`, `In Review`, `Done`, `Blocked`, `Rejected`.
6. Configure **branch ruleset for `main`**: PRs required, one human review, dismiss stale approvals, resolved conversations, green checks `api-tests`, `web-build`, `context-policy`, no force pushes/deletion, no bypass if available. Required check names appear only after the first CI run.
7. Create `.github/CODEOWNERS` with **real** usernames/teams once known (example in docs below). Enable code owner review if desired.
8. Roadmap Issues are directly executable. Use Issue comments for coordination and link the Issue from the PR template when publishing changes.
9. Set repo secrets for deployment/external API keys; never check them into source.
10. Decide official code license and data licensing with the group before publishing sensitive materials. No license is preselected here.

Example CODEOWNERS AFTER substituting actual handles:

```text
/backend/ @real-user-a
/docs/science/ @real-user-b
/frontend/ @real-user-c
/.github/ @real-user-a @real-user-b @real-user-c
```

`@real-user-*` is explanatory text only and is **not** installed as an active CODEOWNERS file.

For development environment onboarding, use the `uv` and **Omarchy agent guide** sections in the root README. Backend CI uses the official `astral-sh/setup-uv` action.
