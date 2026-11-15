#!/usr/bin/env bash
# Usage: deploy/bin/status.sh
# Releases, containers, readiness and external-source health (from /api/metrics when METRICS_TOKEN is set).
. "$(dirname "$0")/lib.sh"

version="$(current_version)"
echo "current release : ${version:-none}"
echo "previous release: $(previous_version)"
echo "database schema : $(db_revision)"
CROPSTORY_VERSION="${version:-unset}" compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Image}}'
echo "ready           : $(curl -fsS "http://127.0.0.1:${WEB_PORT}/api/ready" 2>/dev/null || echo 'no answer')"
if [ -n "${METRICS_TOKEN:-}" ]; then
  echo "external sources and errors since the API started:"
  curl -fsS -H "Authorization: Bearer ${METRICS_TOKEN}" "http://127.0.0.1:${WEB_PORT}/api/metrics" \
    | grep -E '^cropstory_(upstream_calls_total|upstream_last_error_timestamp_seconds|unhandled_errors_total)' || echo "  (none recorded)"
fi
echo "recent upstream/unhandled errors in the API log:"
CROPSTORY_VERSION="${version:-unset}" compose logs --since 24h api 2>/dev/null \
  | grep -E '"event": "(upstream_error|unhandled_error)"' | tail -10 || echo "  (none in the last 24 h)"
