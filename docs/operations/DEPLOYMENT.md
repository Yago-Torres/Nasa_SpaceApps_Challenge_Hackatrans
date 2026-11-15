# Deployment (ABB-30)

How CropStory is released and run on the demo host. Decision record: `docs/architecture/ADRs/0008-demo-hosting-raspberry-pi-cloudflare-tunnel.md`. Recovery procedures: `RUNBOOK.md`.

## Pieces

| Piece | Where | What it does |
|---|---|---|
| API image | `backend/Dockerfile` | uv-locked Python 3.12, non-root user. Its uvicorn has no access log because the app logs route templates with request ids. |
| Web image | `frontend/Dockerfile`, `frontend/Caddyfile` | Node 24 build served by Caddy. Caddy proxies `/api`, sets CSP and security headers, and has no access log (query strings carry coordinates). |
| Stack | `deploy/compose.yaml` | `db` (PostgreSQL 17, no published port), `migrate` (one-shot `alembic upgrade head`), `api`, `web` (`127.0.0.1:${WEB_PORT}`). Optional `quicktunnel` profile. |
| Scripts | `deploy/bin/` | `deploy.sh`, `rollback.sh`, `backup.sh`, `restore.sh`, `status.sh`, `quick-tunnel.sh` |
| Release CI | `.github/workflows/release.yml` | Multi-arch images to GHCR for every `v*` tag; optional SSH deploy |
| PR CI | `deploy-smoke` job in `.github/workflows/ci.yml` | Builds both images, deploys with the scripts, checks readiness, then backs up and runs the restore drill |

## Health and monitoring

- `GET /api/health`: liveness only (process up, version).
- `GET /api/ready`: 200 when PostgreSQL answers and its schema is at this build's migration head; otherwise 503 with `checks` (`not_configured`, `unreachable_or_not_migrated`, `not_at_head`). It never returns connection details.
- `GET /api/metrics` is in Prometheus text format and only exists when `METRICS_TOKEN` (16+ characters) is set; it needs `Authorization: Bearer <token>`. It reports:
  - requests by method, **route template** and status class;
  - time per route;
  - unhandled errors by type;
  - calls to external sources by outcome: `nasa_power` (`ok`, `cache`, `error:<reason>`), `openalex_search`, `openalex_lookup`, `crossref`;
  - the time of the last failure per source.
- Logs are one JSON object per line on stdout (`docker compose logs api`), and every response carries `X-Request-ID`. Each event type records the following:
  - `request`: method, route template, status, duration.
  - `upstream_error`: source and outcome code.
  - `unhandled_error`: exception type and code location, never the message.
- What never reaches logs or metrics: raw URLs or query strings, coordinates, e-mails, tokens, response bodies. The `httpx` logger is kept at WARNING because at INFO it prints outbound URLs, including NASA POWER queries with coordinates. Tested in `backend/tests/test_operations.py`.
- `deploy/bin/status.sh` shows releases, containers, readiness, external-source counters and the latest upstream or unhandled errors in the last 24 h.

## First-time host setup (Raspberry Pi OS 64-bit or any Linux with Docker)

1. **Docker.** Install Docker Engine with the Compose plugin (v2.20+), and add the deploy user to the `docker` group. Both need the host owner's privileges.
2. **Code and configuration.**
   ```bash
   git clone https://github.com/Yago-Torres/Nasa_SpaceApps_Challenge_Hackatrans.git cropstory
   cd cropstory && cp deploy/env.example deploy/.env && chmod 600 deploy/.env
   # set POSTGRES_PASSWORD (openssl rand -base64 32), METRICS_TOKEN (openssl rand -hex 24), BACKUP_DIR, WEB_PORT
   ```
3. **Images.**
   - If the GHCR packages are private, sign in once with a token that has only `read:packages`:
     ```bash
     docker login ghcr.io -u <user>
     ```
   - Otherwise use `--build` (see Deploy).
4. **Public hostname.** Point the Cloudflare tunnel to `http://127.0.0.1:${WEB_PORT}`. This needs the tunnel owner.
   - Named tunnel: add an ingress rule, either in the Zero Trust dashboard or in `config.yml`:
     ```yaml
     - hostname: cropstory.example.dev
       service: http://127.0.0.1:8080
     ```
   - Temporary alternative: `deploy/bin/quick-tunnel.sh` prints a `https://<random>.trycloudflare.com` URL.
5. **Daily backup.** Add a cron entry for the deploy user:
   ```
   15 3 * * * cd ~/cropstory && deploy/bin/backup.sh nightly >> deploy/state/backup.log 2>&1
   ```

## Deploy a release

```bash
git fetch --tags && git checkout v1.0.0
deploy/bin/deploy.sh v1.0.0            # pull ghcr.io/<owner>/cropstory-{api,web}:v1.0.0
deploy/bin/deploy.sh v1.0.0 --build    # or build them on the host from the checked-out tag
deploy/bin/status.sh
```

`deploy.sh` runs these steps:
1. Checks that the tag exists and is checked out cleanly (only with `--build`).
2. Pulls or builds the images and reads their migration head.
3. Backs up the database (`pre-deploy-<tag>`).
4. Runs the `migrate` job.
5. Starts `api` and `web`, then waits for `/api/ready`.
6. Records the release in `deploy/state/` (`current_version`, `previous_version`, `releases`, `history.log`).

When something fails:
- **Failed migration:** nothing changes (transactional DDL) and the old release keeps serving.
- **New release never becomes ready:** `deploy.sh` rolls back automatically to the previous release, including the schema.

**Automatic deploys from CI** (optional). The tunnel owner sets up the following, and pushing a tag then deploys it:
- Repository variables: `DEPLOY_ENABLED=true`, `DEPLOY_SSH_HOST`, `DEPLOY_PATH`, and optionally `DEPLOY_MODE=--build`.
- Secrets: `DEPLOY_SSH_KEY` (a dedicated key), `DEPLOY_SSH_USER`, `DEPLOY_SSH_KNOWN_HOSTS`.
- A `demo` environment with required reviewers.

## Cutting a release

1. CI is green on `main`.
2. `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`.
3. The `release` workflow publishes the images.
4. Deploy as above.
5. Record the deploy in `CURRENT_STATE.md` only after `/api/ready` and a manual check of the demo URL.

## Demo data

Synthetic cases only. Do not enter real farm locations, real people or real e-mail addresses on the demo host (`LEGAL_AND_DATA_POLICY.md`). Accounts created on the demo can be removed with `POST /api/v1/account/delete`.
