# Omarchy guide for people and AI agents

Moved from the root `README.md`. General agent rules live in `AGENTS.md` and `docs/ai/CONTEXT_MAP.md`; this page adds the setup and operating rules for Omarchy (Arch Linux) machines.

## Starting an AI session

```text
Act as a CropStory developer. Read AGENTS.md, CLAUDE.md (if you are Claude), docs/ai/CONTEXT_MAP.md, the 1.0 scope, CURRENT_STATE, the workflow and the relevant contracts. Identify the active Issue, what is implemented and what is missing. Do not invent data or features. Before editing, list the affected files, dependencies and planned tests. Implement only the Issue's scope and, at the end, document the verification and the handoff to another agent.
```

## Omarchy (Arch Linux)

Omarchy is based on Arch and uses **mise** to manage development tools. Its manual says that `uv`, `gh` and several coding agents may be available through deferred installation; do not assume the first command will work without downloading anything.

### Machine setup (done by the person, not by an agent without permission)

1. Open a terminal. If runtimes are missing, use `Super + Space → Install → Development` to install **Python** and **Node.js**, or manage them with `mise`.
2. Check tools and versions:

   ```bash
   mise --version
   mise ls --current
   uv --version
   node --version        # target: v24.x
   npm --version
   git --version
   gh --version
   ```

3. If Node 24 is missing, use `mise use -g node@24` after confirming with the person. For Python, use `uv python install 3.12`, not `pip`, `virtualenv` or manual activation.
4. Clone the repository with `gh repo clone <ORG>/agro-black-box` (after `gh auth login`) or `git clone <URL>`. Never store credentials in project files.
5. Run the backend with `cd backend && uv sync --locked --extra dev && uv run --locked uvicorn agroblackbox.app:app --reload --port 8000` and the frontend with `cd frontend && npm ci && npm run dev`.
6. If the Issue needs PostgreSQL/Redis, Omarchy usually includes Docker and Compose. Use `sudo docker compose up -d` from the root **only after consent**. Membership of the `docker` group grants root-equivalent privileges; do not change it automatically.

System documentation: [Omarchy — Development Tools](https://omarchy.org/manual/development-tools/). Python manager: [uv — Working on projects](https://docs.astral.sh/uv/guides/projects/).

### Operating rules for Claude Code and ChatGPT/Codex on Omarchy

- **Read the context first**, then the Issue and the code; never assume that an earlier chat instruction still applies if it contradicts the repository.
- Work in the current tree without creating branches, commits, pushes or PRs automatically; humans decide when to publish changes.
- Do not run `sudo`, `pacman`, `yay`, `mise use -g`, `omarchy update`, group changes, remote scripts, `gh auth login` or global installs without explicit human authorization.
- For Python dependencies, use `uv add`/`uv remove` **inside `backend/`** only when the active Issue requires them. Update and review `pyproject.toml` **and** `uv.lock` together.
- Prefer `uv run` for commands and tests; do not use `source .venv/bin/activate`, `python -m venv`, `pip install` or global Python tools.
- Keep local or private data out of Git; do not expose keys, private coordinates or personal records to external services without authorization.
- When finished: run the tests, update `CURRENT_STATE.md` only with tested features, and leave a handoff following `docs/ai/HANDOFF_TEMPLATE.md`.
- If context, permissions or connectivity are missing to verify an integration, **stop the affected step and state the blocker**; do not fabricate results or claim that something was verified when it was not tested.

### Short start-up prompt for Omarchy

```text
We are on Omarchy (Arch Linux). Use mise for system runtimes when authorized, and uv for all Python dependencies and runs in backend/. Do not use pip or manage Python environments by hand. Read AGENTS.md, docs/ai/CONTEXT_MAP.md, CURRENT_STATE and the active Issue; inspect the tests. Do not run privileged commands or change global tools without my authorization. After implementing the Issue, run the checks and prepare a verifiable summary for the handoff or PR.
```
