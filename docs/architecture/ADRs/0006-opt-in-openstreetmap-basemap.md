# ADR-0006 — Opt-in OpenStreetMap basemap with coarse request centre

- Status: accepted
- Date: 2026-11-14
- Related GitHub Issue: ABB-21 (#21), PR #55
- Reviewers / coordination notes: privacy/security review required before changing provider or request precision

## Context

The incident wizard needs geographic context, but public raster-tile requests disclose the
viewer's IP address, referrer and requested tile area to the provider. Centering a zoomed map on
the stored point would reveal a private farm area even when case sharing is disabled.

## Options considered

1. Load standard OpenStreetMap tiles automatically at the exact point. Rejected: unannounced third-party disclosure.
2. Operate a tile proxy or self-host tiles. Preferred later, but no reviewed infrastructure or operational owner exists in ABB-21.
3. Keep the local privacy diagram only. Safest, but does not meet the approved basemap scope.
4. Require an explicit per-view load action and request tiles around a coarse centre. Chosen.

## Decision

The app draws the point/privacy cell locally before any network request. OpenStreetMap raster
tiles load only after the user activates “Load map background” beside a disclosure. For an exact
point, the tile centre is rounded to 1° and zoom is limited to 8; the exact point is used only
for the local Leaflet overlay. For an already rounded case, the server-authorized shared centre
and matching coarse zoom are used. The shared area is a latitude/longitude rectangle. OSM
attribution remains visible.

## Tradeoffs and consequences

- OSM still receives an IP address, referrer and coarse area after opt-in; the policy and UI disclose this.
- Rounding reduces but does not anonymise a sparsely populated location.
- Standard OSM tiles are suitable for this low-volume prototype, not an unrestricted production SLA.
- Partial tile failure is visible and retryable; the local overlay remains usable.

## Rollout / rollback

Leaflet and its CSS are isolated to `LocationMap`. Rollback removes the component and dependency,
leaving `PrivacyPreview`. Provider, automatic-loading, precision or proxy changes require an ADR/policy update.
