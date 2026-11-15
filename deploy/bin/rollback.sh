#!/usr/bin/env bash
# Usage: deploy/bin/rollback.sh [--to <version>]
# Returns to an earlier release (default: the previous one). If that release has an older migration
# head, the schema is first downgraded with the *current* image (which contains the newer migrations
# and their downgrade steps). A backup is taken before any downgrade: downgrades can drop columns.
. "$(dirname "$0")/lib.sh"

target="$(previous_version)"
if [ "${1:-}" = "--to" ]; then target="${2:-}"; fi
current="$(current_version)"
[ -n "$target" ] || die "no previous release recorded; use --to <version>"
[ -n "$current" ] || die "no current release recorded"
[ "$target" != "$current" ] || die "$target is already the current release"

target_head="$(release_head "$target")"
[ -n "$target_head" ] || target_head="$(image_head "$target")"
[ -n "$target_head" ] || die "unknown migration head for $target (image missing? pull or build it first)"
db_rev="$(db_revision)"
log "rollback $current -> $target (schema ${db_rev:-?} -> $target_head)"

if [ -n "$db_rev" ] && [ "$db_rev" != "$target_head" ]; then
  "$DEPLOY_DIR/bin/backup.sh" "pre-rollback-$current" >/dev/null
  CROPSTORY_VERSION="$current" compose stop web api || true
  CROPSTORY_VERSION="$current" compose run --rm migrate alembic downgrade "$target_head"
fi

CROPSTORY_VERSION="$target" compose up -d --wait --wait-timeout 180 api web
wait_ready 40 || die "$target did not become ready; restore the pre-rollback backup with restore.sh --replace"

echo "$current" > "$STATE_DIR/previous_version"
echo "$target" > "$STATE_DIR/current_version"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) rollback $current -> $target head=$target_head" >> "$STATE_DIR/history.log"
log "rolled back to $target"
