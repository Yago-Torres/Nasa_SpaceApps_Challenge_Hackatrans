# Operations runbook (ABB-30)

Run every command from the repository checkout on the host. The scripts read `deploy/.env` and record release state in `deploy/state/`. Setup and release flow: `DEPLOYMENT.md`.

## Is it up?

```bash
deploy/bin/status.sh                         # releases, containers, /api/ready, source errors, recent errors
curl -s http://127.0.0.1:8080/api/ready      # {"status":"ready",...} or 503 with the failing check
docker compose -p cropstory logs --since 1h api | grep -E '"event": "(upstream_error|unhandled_error)"'
```

| Symptom | Meaning | Action |
|---|---|---|
| `checks.database = unreachable_or_not_migrated` | PostgreSQL down or schema missing | `docker compose -p cropstory ps db`; restart the stack. If the volume was lost, restore (below). |
| `checks.migrations = not_at_head` | The schema does not match the running image | Finish or undo a deploy: `deploy.sh <current tag>` or `rollback.sh` |
| `upstream_error source=nasa_power outcome=error:timeout` (or `rate_limited`, `upstream_error`) | NASA POWER is slow or failing | Nothing to fix locally. Users see an honest 502 and no substitute data. Retry later. |
| `upstream_error source=openalex_search` | OpenAlex is unavailable or rate limited | Set `OPENALEX_API_KEY` in `deploy/.env` if it keeps happening, then redeploy the same tag. |
| `unhandled_error` | A bug | Use the `request_id` from the user's response header to find the log line, then open an issue with the type and location. |

## Back up

```bash
deploy/bin/backup.sh [label]     # $BACKUP_DIR/cropstory-<UTC>-<release>-<label>.dump (+ .sha256, .meta)
```

- **Format:** `pg_dump` custom format, consistent while the app runs.
- **Retention:** the newest `BACKUP_KEEP` dumps are kept.
- **Automatic backups:** `deploy.sh`, `rollback.sh` and `restore.sh --replace` back up the database before they change anything.
- **Off-site copies:** copy the dumps elsewhere (external disk or another machine). A backup on the same SD card does not survive losing that card.

## Restore

```bash
deploy/bin/restore.sh <file.dump>             # drill: restores into a scratch DB, prints revision/users/cases, drops it
deploy/bin/restore.sh <file.dump> --replace   # real restore of the live database
```

`--replace` runs these steps:
1. Checks the SHA-256.
2. Takes a `pre-restore` backup.
3. Stops `api` and `web`.
4. Recreates the database from the dump.
5. Migrates it forward if the dump is older than the running release.
6. Starts the app and waits for `/api/ready`.

A dump from a *newer* release than the one running needs that release first: `deploy.sh <newer tag>`, then restore.

Run the drill after changing anything about backups, and at least once per release.

## Roll back a release

```bash
deploy/bin/rollback.sh                 # to the previous release
deploy/bin/rollback.sh --to v1.0.0     # to a specific earlier release (its image must be pullable or built)
```

If the target release has an older migration head, the current image downgrades the schema first, after a `pre-rollback` backup. Downgrades can drop columns or tables added since. If data written after the deploy matters, restore the `pre-rollback` dump onto the newer release instead.

## A migration failed during deploy

`deploy.sh` stops and prints `MIGRATION FAILED`. PostgreSQL DDL is transactional, so:
- the schema, `alembic_version` and data are as they were;
- the previous release keeps serving.

This is rehearsed in CI (`test_a_failed_migration_rolls_back_completely_and_the_previous_head_stays_usable`) and in the ABB-30 host rehearsal (CURRENT_STATE).

What to do:
1. Read the error: `docker compose -p cropstory logs migrate`.
2. Fix the migration in a new tag and deploy that tag.

Never edit `alembic_version` by hand.

## The new release does not start

`deploy.sh` waits for `/api/ready`. If the new release doesn't get there, it calls `rollback.sh` to the previous release on its own. Afterwards, check:
- `deploy/bin/status.sh`;
- `docker compose -p cropstory logs api`.

## Host lost or SD card failed

1. Prepare a new host as in `DEPLOYMENT.md`.
2. Deploy the same tag.
3. Run `restore.sh <latest off-site dump> --replace`.
4. Repoint the tunnel.

## Rotating secrets

- **`METRICS_TOKEN` and API keys:** edit `deploy/.env`, then `deploy.sh <current tag>`.
- **`POSTGRES_PASSWORD`:**
  1. Change it in PostgreSQL:
     ```bash
     docker compose -p cropstory exec db psql -U cropstory -c "ALTER USER cropstory PASSWORD '...'"
     ```
  2. Update `deploy/.env`.
  3. `deploy.sh <current tag>`.
