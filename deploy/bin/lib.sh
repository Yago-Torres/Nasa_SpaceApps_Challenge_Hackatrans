#!/usr/bin/env bash
# Shared helpers for the CropStory deployment scripts (ABB-30). Sourced, not executed.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${CROPSTORY_ENV_FILE:-$DEPLOY_DIR/.env}"
STATE_DIR="${CROPSTORY_STATE_DIR:-$DEPLOY_DIR/state}"

die() { echo "error: $*" >&2; exit 1; }
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

[ -f "$ENV_FILE" ] || die "missing $ENV_FILE (copy deploy/env.example and fill it in)"
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

POSTGRES_USER="${POSTGRES_USER:-cropstory}"
POSTGRES_DB="${POSTGRES_DB:-cropstory}"
WEB_PORT="${WEB_PORT:-8080}"

# CROPSTORY_VERSION from the caller's environment wins over deploy/.env (compose precedence too).
compose() {
  docker compose --project-directory "$DEPLOY_DIR" -f "$DEPLOY_DIR/compose.yaml" --env-file "$ENV_FILE" "$@"
}

current_version() { cat "$STATE_DIR/current_version" 2>/dev/null || true; }
previous_version() { cat "$STATE_DIR/previous_version" 2>/dev/null || true; }

# Head revision shipped with a release, recorded at deploy time ("<version> <revision>" lines).
release_head() { awk -v v="$1" '$1 == v { h = $2 } END { print h }' "$STATE_DIR/releases" 2>/dev/null || true; }

db_running() { [ -n "$(compose ps -q --status running db 2>/dev/null)" ]; }

db_revision() {
  compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT version_num FROM alembic_version" 2>/dev/null | tr -d '[:space:]' || true
}

# Head revision inside the image of a given version (alembic heads, no database needed).
image_head() {
  CROPSTORY_VERSION="$1" compose run --rm --no-deps -T migrate alembic heads 2>/dev/null \
    | awk '/\(head\)/ { print $1 }' | tail -1
}

wait_ready() {
  local tries="${1:-40}" body
  for _ in $(seq 1 "$tries"); do
    body="$(curl -fsS "http://127.0.0.1:${WEB_PORT}/api/ready" 2>/dev/null || true)"
    if printf '%s' "$body" | grep -q '"status":"ready"'; then
      log "ready: $body"
      return 0
    fi
    sleep 3
  done
  log "not ready: ${body:-no answer}"
  return 1
}
