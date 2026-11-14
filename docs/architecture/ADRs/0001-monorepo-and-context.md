# ADR-0001 — Monorepo and provider-neutral AI context

- Status: accepted as initial team architecture proposal, to be ratified by all three members on GitHub before repository rules become binding
- Date: 2026-11-14

## Decision

One repo for React TypeScript frontend, Python FastAPI backend, tests, docs, GitHub workflows and domain-level agent instructions. `AGENTS.md` is authoritative instructions; `CLAUDE.md` imports same. The repository and reviewed Issues/PRs, not individual assistant chat histories, are the shared source of truth.

## Rationale

Three maintainers need to make fast compatible changes with different AI models, retain common contracts and avoid synchronization complexity of multiple service repositories.

## Consequences

Domain stewards review changes but do not gate who can implement an approved Issue. Any architectural change requires unanimous approval recorded in a new ADR.
