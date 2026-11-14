# Architecture — target 1.0 and reality

## Stack decision

- **Backend / science**: Python 3.12+, FastAPI, Pydantic, NumPy/pandas; use validated libraries only as required by approved feature.
- **Frontend**: React / TypeScript / Vite. MapLibre or Leaflet once mapping feature is approved; no scientific computations in TS.
- **Persistence**: PostgreSQL + migrations for accounts, cases, evidence, review and audit. Optional PostGIS after approval if geospatial queries justify it.
- **Jobs**: Redis-backed worker for slow/retriable ingestion or report processing; current baseline uses direct API requests and is **not** wired to Redis.
- **Source systems**: NASA POWER mandatory; GPM and HLS integrations for target 1.0 as available/appropriate, OpenAlex and Crossref for discovery. Raster products have different geospatial scales and must not be silently treated as parcel measurements.
- **External storage**: choose and document object storage when raw assets/reports need persistence; no speculative integration.

## Target logical modules

```text
React/TypeScript Web
     | HTTPS, versioned OpenAPI, typed client
     v
FastAPI (auth, cases, policies, validated DTOs)
   |-------- Cases & collaboration -> PostgreSQL
   |-------- NASA ingestion -> asynchronous job -> cache/raw provenance
   |-------- Metrics & hypothesis engine
   |-------- Literature registry & evidence graph
   |-------- Rotation scenario comparison
   |-------- Uncertainty / knowledge-gap analysis
   `-------- Case report generator -> signed export
```

## What exists at repository creation

`backend/agroblackbox/app.py` and `services/*.py` implement a small in-memory API for NASA POWER, OpenAlex metadata, illustrative rotations and a case note. `frontend/src/main.tsx` is a simple corresponding web UI. `backend/tests/` has climate metric tests. **No SQL persistence/auth/review/worker/GPM/HLS currently integrated.** The development baseline should evolve via approved Issues rather than an unreviewed rewrite.

## Data boundaries

1. Each scientific datum must be typed as source observation, local report, literature finding, hypothesis, or simulation; never silently transform categories.
2. Save original source URI, query params, fetch timestamp, units, geospatial/temporal resolution, processing version, dataset version and checksums when applicable.
3. Cases carry visibility and consent flags. Default is private/rounded location in shared context; secret, precise geometry is access-controlled.
4. Backend serves one authoritative data schema. Frontend types should be generated from OpenAPI once schemas stabilize; no duplicated computations.
5. Every change to external integrations, shared schema, storage architecture, or scientific algorithms requires an ADR and group sign-off.
6. Observations, scenarios and evidence findings require an explicit set of quality/uncertainty flags in the product API.

## Deployability strategy

Use GitHub Actions for testing, containerized backend/db and static built frontend. Configure secrets in GitHub/environment, never in code. Document infrastructure as implemented; do not claim running services without an integration test.
