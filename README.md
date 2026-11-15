# CropStory: The Agricultural Blackbox

**NASA Space Apps Challenge 2026 · Agricultural tool · Monorepo for three developers working with Claude Code and OpenAI Codex.**

> Formerly **AGRO BLACK BOX**. Internal identifiers keep the old name so that code, links and data do not break: the Python package `agroblackbox`, the repository name, the `ABB-*` Issue IDs, the `agro-design-system`/`agro-ui-review` skills and the wizard data marker in `incident_notes`.

CropStory investigates agricultural incidents with Earth observation data, tests hypotheses against verifiable scientific literature, compares **three or more rotation strategies (including the current one)**, and supports review across communities and the export of **case reports**.

> **Code status:** the repository contains a working development baseline and the full specifications for version 1.0. **It is not yet a finished 1.0 release.** See `docs/operations/CURRENT_STATE.md` to tell implemented features from pending ones. Do not present simulations as real NASA observations.

## 1. Required context for people and AI agents

The repository and the roadmap Issues on GitHub are the source of truth. **Do not rely on the memory of a Claude or ChatGPT conversation.**

Read, in this order:

1. `AGENTS.md` (Claude Code also loads `CLAUDE.md`) and the `AGENTS.md` of the folder you are going to edit.
2. `docs/ai/CONTEXT_MAP.md`.
3. `docs/product/PRODUCT.md` and `docs/product/RELEASE_1_0.md`.
4. `docs/operations/CURRENT_STATE.md`.
5. `docs/architecture/ARCHITECTURE.md` and `docs/architecture/API_CONTRACTS.md`.
6. `docs/governance/FEATURE_POLICY.md` and `docs/science/SCIENTIFIC_POLICY.md`.
7. The active GitHub Issue and the current code/tests of the affected modules.

**Starting an AI session:**

```text
Act as a CropStory developer. Read AGENTS.md, CLAUDE.md (if you are Claude), docs/ai/CONTEXT_MAP.md, the 1.0 scope, CURRENT_STATE, the workflow and the relevant contracts. Identify the active Issue, what is implemented and what is missing. Do not invent data or features. Before editing, list the affected files, dependencies and planned tests. Implement only the Issue's scope and, at the end, document the verification and the handoff to another agent.
```

## 2. Stack and dependency manager

| Component | Technology | Tool |
|---|---|---|
| Backend and scientific analysis | Python 3.12 + FastAPI | **uv** (the project's only Python manager) |
| Frontend | React + TypeScript + Vite | Node.js 24 + npm |
| Persistence (1.0 target) | PostgreSQL | Docker Compose for development |
| Queues (planned) | Redis | Docker Compose for development |
| Automation | GitHub Actions | `uv` for the backend, npm for the frontend |

**Do not create or activate virtual environments by hand, and do not install dependencies with pip.** `uv` manages its own isolated environment; always work with `uv sync`, `uv add`, `uv run` and `uv lock`. The file `backend/.python-version` pins Python 3.12.

## 3. Installation and running — Linux / WSL2

Requirements: `git`, `uv`, Node.js 24 and npm. On WSL2, keep the repository under `~/projects/` (the Linux file system), not under `/mnt/c/`.

```bash
# From the repository root: set up the Python dependencies with uv
cd backend
uv python install 3.12        # Only needed the first time
uv sync --locked --extra dev  # Installs exactly backend/uv.lock
uv run --locked uvicorn agroblackbox.app:app --reload --port 8000
```

In **another terminal**, from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

- Web app: http://localhost:5173
- API and OpenAPI documentation: http://localhost:8000/docs
- Live NASA and OpenAlex data need an Internet connection; **never** replace a failed response with invented data.

Local checks:

```bash
# From the root
uv run --no-project python scripts/check_context.py
cd backend && uv lock --check && uv run --locked --extra dev pytest -q
cd ../frontend && npm run build
```

**Dependency locking:** `backend/uv.lock` and `frontend/package-lock.json` are versioned and required. Check Python with `cd backend && uv lock --check` and install with `uv sync --locked --extra dev`. In the frontend use `npm ci`; do not replace the lock files with floating resolutions in CI.

ABB-03 uses PostgreSQL for the internal persistence layer; Redis is still not connected. For an empty local database, run `docker compose up -d db`, copy `DATABASE_URL` from `.env.example` into your environment and apply `make db-upgrade`. Integration tests need an explicit disposable database through `TEST_DATABASE_URL`; never point that variable at a database whose data must be kept, because the suite tests migrations and empties tables. The authenticated routes that use this layer are added in later Issues.

## 4. Guide for AI agents on Omarchy (Arch Linux)

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

## 5. Team, feature governance and GitHub

| Technical steward | Preferred reviewer for | Can they implement features from another domain? |
|---|---|---|
| Person A | NASA / observations / metrics | **Yes**, from a roadmap Issue |
| Person B | Scientific evidence / rotations | **Yes**, from a roadmap Issue |
| Person C | Frontend / integration / authentication | **Yes**, from a roadmap Issue |

- Every feature is linked to a **GitHub roadmap Issue** with a verifiable scope and acceptance criteria; it does not need votes or approval labels to start.
- The domain says who reviews, not who has exclusive permission to write the code.
- A task has one main implementer and explicit coordination when it touches contracts or shared files. Humans decide when to create a branch and a PR; CI must pass before merging.
- AI agents implement and verify the Issue's scope, but they do not replace technical, scientific or security review.
- Lasting decisions are recorded in Issues/ADRs, not in chat memories.

See `docs/governance/GITHUB_SETUP.md`, `FEATURE_POLICY.md`, `TEAM_WORKFLOW.md` and `docs/ai/HANDOFF_TEMPLATE.md`.

## 6. Scientific integrity and privacy

Space-based observations alone do not identify the cause of a crop failure. NASA POWER data have a different resolution from a local measurement; an article's metadata do not prove its findings. Illustrative rotations are not validated predictions of yield or water savings. Every important conclusion needs its source, assumptions and limitations to be visible. Private cases are private by default.

## 7. Next work — the scientific paper (future)

Once the **1.0 tool is stable** and the team approves it, the team may write and publish its own scientific paper with methodology, validated results and limitations. **It is not part of the current development tasks.**
