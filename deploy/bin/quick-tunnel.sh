#!/usr/bin/env bash
# Usage: deploy/bin/quick-tunnel.sh [--stop]
# Temporary public HTTPS URL (https://<random>.trycloudflare.com) for the running stack, without a
# Cloudflare account. The URL changes every time the tunnel starts. For a fixed hostname use a named
# tunnel (docs/operations/DEPLOYMENT.md).
. "$(dirname "$0")/lib.sh"

version="$(current_version)"; [ -n "$version" ] || die "deploy a release first"
if [ "${1:-}" = "--stop" ]; then
  CROPSTORY_VERSION="$version" compose --profile quicktunnel stop quicktunnel
  CROPSTORY_VERSION="$version" compose --profile quicktunnel rm -f quicktunnel
  exit 0
fi
CROPSTORY_VERSION="$version" compose --profile quicktunnel up -d quicktunnel
for _ in $(seq 1 30); do
  url="$(CROPSTORY_VERSION="$version" compose --profile quicktunnel logs quicktunnel 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true)"
  [ -n "$url" ] && { echo "$url"; exit 0; }
  sleep 2
done
die "no tunnel URL yet; check: docker compose --profile quicktunnel logs quicktunnel"
