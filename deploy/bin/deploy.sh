#!/usr/bin/env bash
# Usage: deploy/bin/deploy.sh <version> [--build]
# Deploys a tagged release: pulls (or builds) its images, backs up the database, migrates, starts the
# app and waits for /api/ready. If the new release does not become ready, it rolls back automatically
# to the previous release (schema included). A failed migration changes nothing (transactional DDL),
# and the previous release keeps serving.
. "$(dirname "$0")/lib.sh"

version="${1:-}"; build="${2:-}"
[[ "$version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.-]+)?$ ]] || die "usage: deploy.sh vX.Y.Z [--build]"
prev="$(current_version)"
log "deploying $version (current: ${prev:-none})"

if [ "$build" = "--build" ]; then
  tag_commit="$(git -C "$DEPLOY_DIR/.." rev-parse -q --verify "refs/tags/$version^{commit}" || true)"
  [ -n "$tag_commit" ] || die "tag $version does not exist in this checkout (git fetch --tags)"
  [ "$tag_commit" = "$(git -C "$DEPLOY_DIR/.." rev-parse HEAD)" ] || die "check out $version first (git checkout $version)"
  [ -z "$(git -C "$DEPLOY_DIR/.." status --porcelain -- backend frontend deploy)" ] || die "uncommitted changes in the checkout"
  CROPSTORY_VERSION="$version" compose build migrate web
else
  CROPSTORY_VERSION="$version" compose pull migrate api web
fi

new_head="$(image_head "$version")"
[ -n "$new_head" ] || die "could not read the migration head of $version"

CROPSTORY_VERSION="$version" compose up -d --wait db
prev_rev="$(db_revision)"
if [ -n "$prev_rev" ]; then
  "$DEPLOY_DIR/bin/backup.sh" "pre-deploy-$version" >/dev/null
fi

log "migrating ${prev_rev:-empty database} -> $new_head"
if ! CROPSTORY_VERSION="$version" compose run --rm migrate; then
  log "MIGRATION FAILED: the schema is unchanged (revision $(db_revision)); ${prev:-no release} keeps serving"
  exit 1
fi

CROPSTORY_VERSION="$version" compose up -d --wait --wait-timeout 180 api web || true
if ! wait_ready 40; then
  log "$version is not ready"
  if [ -n "$prev" ]; then
    log "rolling back to $prev"
    echo "$version" > "$STATE_DIR/current_version"
    echo "$version $new_head" >> "$STATE_DIR/releases"
    exec "$DEPLOY_DIR/bin/rollback.sh" --to "$prev"
  fi
  exit 1
fi

[ -n "$prev" ] && [ "$prev" != "$version" ] && echo "$prev" > "$STATE_DIR/previous_version"
echo "$version" > "$STATE_DIR/current_version"
echo "$version $new_head" >> "$STATE_DIR/releases"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) deploy $version head=$new_head from=${prev:-none}" >> "$STATE_DIR/history.log"
log "deployed $version"
