# CropStory

**Find out what happened to a crop, with satellite data and real science.**

CropStory helps farmers and agronomists investigate a crop incident, such as a failed harvest, yellowing or a dry spell, as a case. It puts NASA Earth observation data for the field next to verifiable scientific literature, keeps rival explanations open, and compares crop rotation strategies for what comes next. Built for the **NASA Space Apps Challenge 2026**.

## What it does

- **Investigate a place and a year.** Monthly rain and temperature anomalies from NASA POWER, compared with the 10 years before; monthly satellite rainfall from GPM IMERG; and vegetation (NDVI) from Landsat and Sentinel-2 (HLS), with cloud-screened overpasses.
- **Build a case.** A guided wizard records the fields, crop history, symptoms and constraints. Each field has its own location privacy: exact, rounded, region only or hidden.
- **Weigh the evidence.** Search scientific papers (OpenAlex, DOI-checked with Crossref), turn them into reviewed claims, flag contradictions and check whether a study applies to your conditions. A timeline, rival hypotheses, an evidence graph and an "uncertainty hunter" show what is known and what is not.
- **Compare rotations.** At least three strategies, including the current one, checked against your water, market and equipment constraints and your priorities, with hypothetical climate scenarios and sensitivity to those priorities.
- **Work together.** Invite reviewers and editors, comment, and share a consented read-only link.
- **Report.** Export a versioned case report (Markdown, HTML, JSON or PDF, in English or Spanish) with sources and checksums.

The web app is available in English and Spanish.

## Principles

- **No invented data.** If NASA or another source fails, CropStory says so. It never fills the gap with sample values.
- **Every number carries its source:** dataset, resolution, retrieval time, checksum and limitations. A ½° NASA POWER cell is not a field measurement, and the app says so.
- **Explanations, not verdicts.** Satellite data alone do not prove why a crop failed. Hypotheses carry no probabilities, and rotation comparisons are descriptive, not yield forecasts.
- **Private by default.** Exact field locations are only shown to people the owner allows. The privacy map is drawn locally, with no third-party map tiles.

## Data sources

| Source | Used for | Access |
|---|---|---|
| [NASA POWER](https://power.larc.nasa.gov/) | Daily rain and maximum temperature, monthly anomalies | Open, no key |
| [NASA GPM IMERG](https://gpm.nasa.gov/data/imerg) (GES DISC) | Monthly satellite and gauge rainfall, 0.1° | NASA Earthdata token |
| [NASA HLS](https://www.earthdata.nasa.gov/data/projects/hls) (LP DAAC) | NDVI from Landsat 8/9 and Sentinel-2, 30 m | NASA Earthdata token |
| [OpenAlex](https://openalex.org/) and [Crossref](https://www.crossref.org/) | Scientific papers and DOI verification | Open |

## Tech stack

Python 3.12 · FastAPI · PostgreSQL 17 · SQLAlchemy/Alembic · React · TypeScript · Vite · Docker Compose · Caddy · GitHub Actions. Python dependencies are managed with [uv](https://docs.astral.sh/uv/) and frontend dependencies with npm (Node.js 24).

## Run it locally

You need `git`, [uv](https://docs.astral.sh/uv/), Node.js 24 and Docker.

```bash
# 1. Database (PostgreSQL in Docker)
docker compose up -d db

# 2. API on http://localhost:8000 (docs at /docs)
cd backend
export DATABASE_URL=postgresql+psycopg://agro:local_dev_only@127.0.0.1:5432/agroblackbox
export EARTHDATA_TOKEN=...   # optional: enables the GPM and HLS panels
uv sync --locked --extra dev
uv run --locked alembic upgrade head
uv run --locked uvicorn agroblackbox.app:app --reload --port 8000

# 3. Web app on http://localhost:5173 (in another terminal)
cd frontend
npm ci
npm run dev
```

Get a free Earthdata token at [urs.earthdata.nasa.gov](https://urs.earthdata.nasa.gov/). For GPM, the account must also approve the "NASA GESDISC DATA ARCHIVE" application. Without a token, those two panels say they are unavailable and everything else works.

On Windows, run the API and `npm run dev` in the same environment: both in WSL, or both on Windows.

**Demo data.** With the API running, `uv run --no-project python scripts/seed_demo_cases.py --base-url http://127.0.0.1:8000 --run-id demo` creates a synthetic owner, a reviewer and a filled-in case, and prints their sign-in details. See [`docs/operations/SYNTHETIC_DEMO_CASES.md`](docs/operations/SYNTHETIC_DEMO_CASES.md).

## Tests

```bash
make check    # context check, lock check, backend tests, frontend build
cd frontend && npm test
```

Backend tests run offline against recorded NASA response shapes. `make smoke-real` checks the live sources and needs `EARTHDATA_TOKEN`.

## Deploy

Tagged releases publish Docker images, and `deploy/bin/deploy.sh <tag>` runs the stack with backups, migrations, a readiness check and automatic rollback. See [`docs/operations/DEPLOYMENT.md`](docs/operations/DEPLOYMENT.md) and [`RUNBOOK.md`](docs/operations/RUNBOOK.md).

## Repository layout

```text
backend/    FastAPI app (package agroblackbox), science services, migrations, tests
frontend/   React app, design system, EN/ES messages
deploy/     Production Compose stack and operations scripts
docs/       Product, architecture, science methods and operations
scripts/    Context check, OpenAPI export, demo seeding
```

The method behind each feature is documented in [`docs/science/`](docs/science/), for example [climate anomalies](docs/science/CLIMATE_ANOMALIES.md), [GPM rainfall](docs/science/GPM_PRECIPITATION.md), [HLS vegetation](docs/science/HLS_VEGETATION.md) and [rotations](docs/science/ROTATIONS.md).

## Contributing

Read [`AGENTS.md`](AGENTS.md) first. It holds the rules for people and AI coding agents (Claude Code, Codex): uv only for Python, provenance on every scientific value, and the design system for any UI change.

*CropStory was formerly called AGRO BLACK BOX. The Python package `agroblackbox` and some internal identifiers keep that name.*
