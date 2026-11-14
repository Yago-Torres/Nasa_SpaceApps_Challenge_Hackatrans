# How three humans use ChatGPT and Claude without losing context

## Central truth

Git repository + roadmap GitHub Issues/PRs = authoritative. No model's private memory is authoritative. Context must be stored as versioned, reviewed artifacts (product specs, API, ADRs, status ledger), not duplicated chat transcripts.

## Worktree isolation

Every person has a local checkout (or separate git worktree if sharing one computer). Each **AI session** works only on the authorized branch/task. Running multiple agents that modify the same checkout concurrently risks overwrites. For parallel agents on one machine:

```bash
git worktree add ../abb-issue-42 -b feat/42-feature main
```

Never let two autonomous agents rewrite shared API schemas concurrently without prior reviewed contract.

## Before AI coding

Ask the model to read `AGENTS.md`, its nested instruction, context map, CURRENT_STATE, contract docs, roadmap Issue, relevant source and tests. Ask for a short implementation plan and dependencies. Roadmap Issues can be implemented directly; coordinate shared files and interfaces before integration.

## After AI coding

Require tests, a diff summary and linked PR. Independently review statements about NASA, agronomy and scientific claims. Add actual decisions to ADRs and status ledger. Switch models by reading the branch/PR and docs, not by copying old AI conversation into prompts.

## Sensitive data

Never commit API tokens, personal farm contacts, private field coordinates, raw user incident records or credentials. Use environment secrets and sanitized fixtures. Review model/connector permissions before uploading private data.
