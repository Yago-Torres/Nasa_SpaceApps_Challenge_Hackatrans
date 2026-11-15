#!/usr/bin/env bash
# Usage: deploy/bin/backup.sh [label]
# Consistent logical backup of the CropStory database (pg_dump custom format) with a SHA-256 sidecar
# and metadata (release, migration revision). Keeps the newest $BACKUP_KEEP dumps.
. "$(dirname "$0")/lib.sh"

label="${1:-manual}"
[[ "$label" =~ ^[A-Za-z0-9._-]{1,40}$ ]] || die "label must be 1-40 characters of [A-Za-z0-9._-]"
db_running || die "the db service is not running"
dir="${BACKUP_DIR:-$DEPLOY_DIR/backups}"
keep="${BACKUP_KEEP:-14}"
umask 077
mkdir -p "$dir"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
version="$(current_version)"; version="${version:-unknown}"
file="$dir/cropstory-${stamp}-${version}-${label}.dump"
revision="$(db_revision)"

compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges > "$file.partial"
[ -s "$file.partial" ] || { rm -f "$file.partial"; die "pg_dump produced no output"; }
mv "$file.partial" "$file"
(cd "$dir" && sha256sum "$(basename "$file")" > "$(basename "$file").sha256")
printf 'created=%s\nrelease=%s\nrevision=%s\nlabel=%s\n' "$stamp" "$version" "${revision:-none}" "$label" > "$file.meta"

ls -1t "$dir"/cropstory-*.dump 2>/dev/null | tail -n +"$((keep + 1))" | while read -r old; do
  rm -f "$old" "$old.sha256" "$old.meta"
done

log "backup written: $file ($(du -h "$file" | cut -f1), revision ${revision:-none})"
echo "$file"
