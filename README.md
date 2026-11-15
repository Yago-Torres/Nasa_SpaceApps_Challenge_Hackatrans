<p align="center">
  <img src="docs/images/cropstory-banner.jpg" alt="CropStory, the agricultural black box" width="760">
</p>

<p align="center">
  <b>Find out what happened to a crop, with satellite data and real science.</b>
</p>

<h2 align="center">
  🌱 <a href="https://cropstory.yagotg.dev">Try the live demo → cropstory.yagotg.dev</a>
</h2>

<p align="center">
  <a href="https://cropstory.yagotg.dev">
    <img src="https://img.shields.io/badge/%E2%96%B6%20Live%20demo-cropstory.yagotg.dev-2f6f29?style=for-the-badge" alt="Open the live demo at cropstory.yagotg.dev" width="460">
  </a>
</p>

<p align="center">
  NASA Space Apps Challenge 2026 &nbsp;·&nbsp; No account needed to explore
</p>

<p align="center">
  <img src="docs/images/screenshot-home.jpg" alt="CropStory home page: investigate a failed harvest with NASA Earth data" width="900">
</p>

CropStory helps farmers and agronomists investigate a crop incident, such as a failed harvest, yellowing or a dry spell, as a case. It puts NASA Earth observation data for the field next to verifiable scientific literature, keeps rival explanations open, and compares crop rotation strategies for what comes next.

## ✨ What it does

| Feature | What you get |
|---|---|
| 🛰️ **Investigate a place and a year** | Monthly rain and temperature anomalies from NASA POWER against the 10 years before, monthly satellite rainfall from GPM IMERG, and vegetation (NDVI) from Landsat and Sentinel-2 (HLS) with cloud-screened overpasses. |
| 📋 **Build a case** | A guided wizard records the fields, crop history, symptoms and constraints. Each field has its own location privacy: exact, rounded, region only or hidden. |
| 📚 **Weigh the evidence** | Search scientific papers (OpenAlex, DOI-checked with Crossref), turn them into reviewed claims, flag contradictions and check whether a study applies to your conditions. A timeline, rival hypotheses, an evidence graph and an "uncertainty hunter" show what is known and what is not. |
| 🌾 **Compare rotations** | At least three strategies, including the current one, checked against your water, market and equipment constraints and your priorities, with what-if climate scenarios. |
| 🤝 **Work together** | Invite editors and reviewers, comment, and share a consented read-only link. |
| 📄 **Report** | Export a versioned case report (Markdown, HTML, JSON or PDF, in English or Spanish) with sources and checksums. |

## 🔭 See it with real NASA data

The same place and year, read from two NASA products (a public grid point in the Ebro valley, Spain, 2022).

<p align="center">
  <img src="docs/images/screenshot-climate.png" alt="Monthly rain difference in 2022 against 2012–2021 from NASA POWER, with maximum-temperature differences per month" width="680">
  <br>
  <sub><b>NASA POWER.</b> Each month of 2022 against the 10 years before: brown is drier, teal wetter; the row shows how much hotter or colder the days were.</sub>
</p>

<p align="center">
  <img src="docs/images/screenshot-satellite-rain.png" alt="Monthly 2022 rainfall from NASA GPM IMERG with its error estimate, next to NASA POWER totals" width="820">
  <br>
  <sub><b>NASA GPM IMERG.</b> Satellite and rain-gauge rainfall for the 11 km cell, with its own error estimate, next to the NASA POWER total for the same months.</sub>
</p>

## 🌍 Data sources

| Source | Used for | Access |
|---|---|---|
| [NASA POWER](https://power.larc.nasa.gov/) | Daily rain and maximum temperature, monthly anomalies | Open, no key |
| [NASA GPM IMERG](https://gpm.nasa.gov/data/imerg) (GES DISC) | Monthly satellite and gauge rainfall, 0.1° | NASA Earthdata token |
| [NASA HLS](https://www.earthdata.nasa.gov/data/projects/hls) (LP DAAC) | NDVI from Landsat 8/9 and Sentinel-2, 30 m | NASA Earthdata token |
| [OpenAlex](https://openalex.org/) and [Crossref](https://www.crossref.org/) | Scientific papers and DOI verification | Open |

## 🛠️ Tech stack

Python 3.12 · FastAPI · PostgreSQL 17 · SQLAlchemy/Alembic · React · TypeScript · Vite · Docker Compose · Caddy · GitHub Actions. Python dependencies are managed with [uv](https://docs.astral.sh/uv/) and frontend dependencies with npm (Node.js 24).

## 🚀 Run it locally

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

## ✅ Tests

```bash
make check    # context check, lock check, backend tests, frontend build
cd frontend && npm test
```

Backend tests run offline against recorded NASA response shapes. `make smoke-real` checks the live sources and needs `EARTHDATA_TOKEN`.

## 📦 Deploy

Tagged releases publish Docker images, and `deploy/bin/deploy.sh <tag>` runs the stack with backups, migrations, a readiness check and automatic rollback. See [`docs/operations/DEPLOYMENT.md`](docs/operations/DEPLOYMENT.md) and [`RUNBOOK.md`](docs/operations/RUNBOOK.md).

## 🗂️ Repository layout

```text
backend/    FastAPI app (package agroblackbox), science services, migrations, tests
frontend/   React app, design system, EN/ES messages
deploy/     Production Compose stack and operations scripts
docs/       Product, architecture, science methods and operations
scripts/    Context check, OpenAPI export, demo seeding
```

The method behind each feature is documented in [`docs/science/`](docs/science/), for example [climate anomalies](docs/science/CLIMATE_ANOMALIES.md), [GPM rainfall](docs/science/GPM_PRECIPITATION.md), [HLS vegetation](docs/science/HLS_VEGETATION.md) and [rotations](docs/science/ROTATIONS.md).

