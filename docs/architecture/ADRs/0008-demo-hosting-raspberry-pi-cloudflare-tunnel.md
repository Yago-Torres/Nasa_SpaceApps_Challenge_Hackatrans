# ADR-0008: Demo hosting on a team Raspberry Pi behind a Cloudflare Tunnel, images from GHCR

- Status: accepted for the demo environment (ABB-30); revisit before a production launch with real farm data.
- Date: 2026-11-15
- Issue: ABB-30 (secure deployment, monitoring and recovery)

## Context

ABB-30 asks for a working demo URL with the minimum private data, a deployment the team can repeat from a tag, backup/restore of PostgreSQL, release rollback, and visible external-source errors without exposing sensitive data. The team has no paid cloud account. A team member offered a Raspberry Pi that is already reachable through a Cloudflare Tunnel (`connect.yagotg.dev`, SSH only through `cloudflared access ssh`).

## Decision

- **Runtime:** Docker Compose stack in `deploy/compose.yaml`: PostgreSQL 17, a one-shot `migrate` job (`alembic upgrade head`), the API (uvicorn, one worker) and the web server (Caddy, static build + `/api` proxy). Only Caddy publishes a port, and only on `127.0.0.1`.
- **Exposure:** Cloudflare Tunnel from the Pi to `127.0.0.1:${WEB_PORT}`. A named tunnel gives a fixed hostname (for example `cropstory.yagotg.dev`) and is configured by the tunnel owner. A Quick Tunnel (`deploy/bin/quick-tunnel.sh`, random `trycloudflare.com` URL, no account) works as a temporary fallback. No inbound port is opened on the network.
- **Images:** `.github/workflows/release.yml` builds `linux/amd64` and `linux/arm64` images on each `v*` tag and pushes them to `ghcr.io/<owner>/cropstory-{api,web}:<tag>`. The host pulls them. If the packages stay private, the host needs a read-only token. `deploy.sh <tag> --build` builds the images on the host from the checked-out tag instead (no registry needed).
- **Operations:** `deploy/bin/` scripts for deploy, rollback, backup, restore and status (`docs/operations/RUNBOOK.md`). Monitoring is application-level: JSON logs with request ids, `/api/ready`, and token-protected Prometheus metrics with external-source outcomes. No third-party error tracker.

## Costs

| Item | Cost |
|---|---|
| Raspberry Pi (already owned) | 0 € extra; about 5 W, roughly 45 kWh/year (≈ 7–12 €/year in electricity) |
| Cloudflare Tunnel / Access (free plan) | 0 € |
| Domain `yagotg.dev` (already owned) | existing renewal, about 12 €/year |
| GitHub Actions + GHCR | public repository: free. Private packages: free plan includes 500 MB storage and 1 GB/month transfer. |
| Alternatives considered | Small VPS (≈ 4–6 €/month), Render/Fly.io free tiers (sleep on idle, limited Postgres) |

## Access controls

- SSH only through the tunnel (`cloudflared access ssh`), key-based, as the host user that owns the deployment. No password logins should be used by automation.
- `deploy/.env` holds secrets (DB password, metrics token, optional API keys). It is mode 600 and never committed. The scripts refuse to run without it.
- PostgreSQL is not published on any port. The API container runs as a non-root user with a read-only filesystem, all capabilities dropped and `no-new-privileges`. The NASA POWER response cache (which holds queried coordinates) is a tmpfs in memory.
- `/api/metrics` is off unless `METRICS_TOKEN` is set, and it needs `Authorization: Bearer`. The optional CI deploy job needs the repository variable `DEPLOY_ENABLED=true` and the `DEPLOY_*` secrets. It runs in a GitHub environment (`demo`) that can require reviewers.
- Demo data policy: synthetic cases only. Real farm locations are not entered in the demo (LEGAL_AND_DATA_POLICY.md).

## Consequences

- A single small host: no high availability. Restarts are automatic (`restart: unless-stopped`); recovery is the runbook.
- In-process metrics reset on restart and are read with `curl` or `deploy/bin/status.sh`. A Prometheus/Grafana or Sentry integration is a later decision (it needs an account and a data-processing review).
- Backups are stored on the same host unless copied off (`BACKUP_DIR` can point to mounted external storage). Off-site copies are an open task.
- Running another workload on the shared Pi is possible, so memory limits are set (`API_MEM_LIMIT`, `WEB_MEM_LIMIT`).
