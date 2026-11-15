#!/usr/bin/env bash
# Usage: deploy/bin/restore.sh <file.dump> [--check | --replace]
#   --check   (default) restore into a scratch database, report revision and row counts, drop it.
#             Production data is not touched: this is the restore drill.
#   --replace stop the app, take a safety backup, replace the database with the dump, migrate it to
#             this release's head if it is older, start the app and wait until it is ready.
. "$(dirname "$0")/lib.sh"

dump="${1:-}"; mode="${2:---check}"
[ -n "$dump" ] && [ -f "$dump" ] || die "usage: restore.sh <file.dump> [--check|--replace]"
[ -f "$dump.sha256" ] || die "missing $dump.sha256"
(cd "$(dirname "$dump")" && sha256sum --check --quiet "$(basename "$dump").sha256") || die "checksum mismatch: $dump"
db_running || die "the db service is not running"

psql_admin() { compose exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres "$@"; }
counts_sql="SELECT (SELECT version_num FROM alembic_version) AS revision,
  (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM cases) AS cases"

case "$mode" in
  --check)
    scratch="cropstory_restore_check"
    psql_admin -qc "DROP DATABASE IF EXISTS $scratch WITH (FORCE)" -c "CREATE DATABASE $scratch"
    compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$scratch" --no-owner --no-privileges --exit-on-error < "$dump"
    log "restore drill OK: $(compose exec -T db psql -U "$POSTGRES_USER" -d "$scratch" -tAF ' ' -c "$counts_sql" | tr -s ' ' | sed 's/^/revision users cases = /')"
    psql_admin -qc "DROP DATABASE $scratch WITH (FORCE)"
    ;;
  --replace)
    "$DEPLOY_DIR/bin/backup.sh" pre-restore >/dev/null
    version="$(current_version)"; [ -n "$version" ] || die "no current release recorded; deploy first"
    log "stopping api and web"
    CROPSTORY_VERSION="$version" compose stop web api
    psql_admin -qc "DROP DATABASE IF EXISTS $POSTGRES_DB WITH (FORCE)" -c "CREATE DATABASE $POSTGRES_DB"
    compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --exit-on-error < "$dump"
    log "restored: $(compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAF ' ' -c "$counts_sql" | tr -s ' ' | sed 's/^/revision users cases = /')"
    CROPSTORY_VERSION="$version" compose run --rm migrate   # no-op when the dump is at this head
    CROPSTORY_VERSION="$version" compose up -d --wait --wait-timeout 180 api web
    wait_ready || die "the app is not ready after the restore; see deploy/bin/status.sh"
    ;;
  *) die "unknown mode $mode" ;;
esac
