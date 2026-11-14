# Context map — mandatory reading order for every AI coding session

The repository, not a chat transcript or a model's local memory, is the canonical product context. Use `uv` for all backend Python work; on Omarchy follow the agent setup guide in the root `README.md`.

## Read in this order

1. `AGENTS.md` (global rules) and the applicable nested `AGENTS.md`.
2. `docs/product/PRODUCT.md` (purpose, user personas, constraints).
3. `docs/product/RELEASE_1_0.md` (full 1.0 release requirements and acceptance criteria).
4. `docs/operations/CURRENT_STATE.md` (verified, actually implemented behavior and blockers).
5. `docs/architecture/ARCHITECTURE.md` (target structure, source of truth).
6. `docs/architecture/API_CONTRACTS.md` (implemented routes vs proposed routes).
7. `docs/governance/FEATURE_POLICY.md` (what is authorized).
8. `docs/science/SCIENTIFIC_POLICY.md` (scientific claims / evidence).
9. **The specific approved GitHub Issue**, its acceptance criteria, and any affected ADR.
10. Relevant source files, tests, latest change log, and PRs if accessible.

Never assume these files are automatically loaded in full just because their names appear in this map. Open the relevant documents before implementing.

## Session contract

At session start, briefly state: task/Issue, approval evidence, current product state, relevant modules, expected contract changes and test plan. If no authorized task is identified, limit work to investigation, documentation proposals or questions. At session end, report the implemented delta, tests, remaining gaps and needed updates to CURRENT_STATE. Do not self-approve features.

## Four permitted types of claims

- **Implemented & tested:** supported by code + a runnable check and status ledger.
- **In progress:** partial code or incomplete integration.
- **Approved not built:** Issue approved, design agreed, no working implementation yet.
- **Proposed:** candidate feature only, requires votes.

Do not copy chat history into the repository as a source of truth. Distill decisions into an ADR/approved Issue. Don't commit long AI conversation logs, private context or credentials.

## Model-specific behavior

- OpenAI Codex recognizes `AGENTS.md`, including nested files.
- Claude Code recognizes `CLAUDE.md` and its project imports.
- ChatGPT in an ordinary chat requires explicit repo upload, GitHub connection or a development environment with repo access. It does **not** automatically synchronize with private GitHub repositories.

See `docs/ai/PROMPTS.md` for reusable prompts.
