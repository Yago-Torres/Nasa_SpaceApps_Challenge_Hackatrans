# ADR-0009 — NASA Earthdata access for HLS, read with a standard-library COG reader

- Status: accepted
- Date: 2026-11-15
- Related GitHub Issue: ABB-12 (#12); ABB-09 (#9) uses the same token
- Reviewers / coordination notes: backend (A) and science (B) reviewers; the token is owned by the team's Earthdata account holder.

## Context

RELEASE_1_0 F-03 requires a NASA source besides POWER. HLS (LP DAAC) and GPM IMERG (GES DISC) both need an Earthdata Login token. The team stored one as the repository secret `EARTHDATA_TOKEN` (valid until 2027-01-13). A probe on 2026-11-15 showed LP DAAC accepts it, while GES DISC answers `403 EULA Acceptance Failure` until the account approves the "NASA GESDISC DATA ARCHIVE" application, so HLS goes first.

HLS files are Cloud-Optimized GeoTIFFs. CropStory only needs a 3 × 3 pixel window from three bands per scene.

## Options considered

1. **rasterio/GDAL** (`/vsicurl/`). Mature, but a large native wheel in the API image (also arm64 for the Raspberry Pi), and more surface than a point read needs.
2. **Download whole files** (~28 MB per band). Rejected: hundreds of MB per request.
3. **Harmony / AppEEARS subsetting services.** Asynchronous jobs that take minutes; poor fit for an interactive request.
4. **Standard-library reader** for the exact COG layout HLS uses (classic TIFF, tiled, Deflate, predictor 2, UTM GeoKeys), reading only the header and the tiles needed with HTTP range requests. Chosen.

## Decision

- `services/geotiff.py` (no new dependency) parses the first IFD and decodes tiles; everything outside the supported layout is rejected, not guessed. Its output was cross-checked against rasterio/GDAL on real HLS scenes (exact match, see `docs/science/HLS_VEGETATION.md`).
- New external services: NASA CMR (public search) and LP DAAC data (`data.lpdaac.earthdatacloud.nasa.gov`). The bearer token is attached only to that host over HTTPS; httpx drops it on the cross-origin redirect to signed storage. Upstream errors never echo URLs, coordinates or bodies.
- New endpoint `GET /api/vegetation/hls`. Without the token the server answers 503 (not configured); a rejected token is 502 and stops the whole request.
- Configuration: `EARTHDATA_TOKEN` environment variable (`deploy/.env`, compose passes it to `api`), and the `EARTHDATA_TOKEN` Actions secret for the manual `earthdata-smoke` workflow. Never in Git.
- Local disk cache under `backend/.cache/hls` (search 1 day, per-scene results 30 days), like the POWER cache.

## Tradeoffs and consequences

- The reader must be maintained if LP DAAC changes the file layout (BigTIFF, another compression); the smoke workflow would fail loudly with "unexpected structure" rather than return wrong values.
- A 92-day request makes about 200–250 small requests (about 30 s live); results are cached per scene. Requests are capped at 92 days and 400 granules.
- Earthdata tokens expire after 60 days: rotate the secret and `deploy/.env` before 2027-01-13 (RUNBOOK).
- The cache stores derived values keyed by a hash of the coordinates, like the POWER cache (privacy note in ABB-28).

## Rollout / rollback

Additive: a new router and service. Without `EARTHDATA_TOKEN` the rest of the app is unchanged and the panel says HLS is not available. Rollback removes the router include in `app.py`.
