import { useEffect, useId, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useI18n } from '../../i18n/I18n';
import { displayedLocation, parseNumber, type DisplayedLocation, type IncidentCase } from '../../cases/model';
import { Button, StatusMessage } from '../../design/components';
import './LocationMap.css';

/**
 * Real basemap for a case location (ABB-21, ADR-0005). A visual COMPLEMENT to
 * `PrivacyPreview`'s to-scale diagram, not a replacement: that diagram explains the privacy
 * mechanics (grid cell, NASA POWER cell); this draws the same point/area on real geography.
 *
 * Tile provider: OpenStreetMap raster tiles, free and keyless (ADR-0005). No autoplay/polling:
 * tiles load once per pan/zoom, driven by the user.
 *
 * PRIVACY CONTRACT (hard requirement, see ADR-0005 and LocationMap.test.tsx): this component
 * never decides what a viewer may see. The caller must pass `viewer`, already the result of
 * `cases/model.ts` `displayedLocation()` for an owner/editor, or `viewerLocationForReadOnlyCase`
 * below for a reviewer/viewer reading the server-redacted field. A `viewer.kind === 'precise'`
 * marker is drawn only when the caller asserts the current viewer is authorized for it; this
 * component performs no rounding, consent or role check of its own.
 */

const TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_SUBDOMAINS = ['a', 'b', 'c'];
const OSM_COPYRIGHT_URL = 'https://www.openstreetmap.org/copyright';
const MAX_ZOOM = 18;

/** Degrees of latitude to metres, used only to size the approximate-area circle (same linear approximation PrivacyPreview's SVG diagram already uses for its square; not a geodesic calculation). */
const METERS_PER_DEGREE = 111_320;

function zoomFor(viewer: DisplayedLocation): number {
  if (viewer.kind === 'precise') return 14;
  if (viewer.kind === 'rounded') {
    if (viewer.rounding <= 0.1) return 11;
    if (viewer.rounding <= 0.5) return 9;
    return 8;
  }
  return 10;
}

type TileState = 'loading' | 'ok' | 'error';

export function LocationMap({ viewer, title }: { viewer: DisplayedLocation; title?: string }) {
  const { t, num, lang } = useI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const [tiles, setTiles] = useState<TileState>('loading');
  const [retryTick, setRetryTick] = useState(0);
  const headingId = useId();

  const point = viewer.kind === 'precise' || viewer.kind === 'rounded' ? { lat: viewer.latitude, lon: viewer.longitude } : null;

  useEffect(() => {
    if (!point || !containerRef.current) return undefined;
    setTiles('loading');
    const map = L.map(containerRef.current, {
      center: [point.lat, point.lon],
      zoom: zoomFor(viewer),
      scrollWheelZoom: false, // never trap page scroll inside the form
      attributionControl: false, // added manually below, without Leaflet's own unlocalised self-credit
      zoomControl: false, // added manually below, with EN/ES titles instead of Leaflet's hardcoded English
    });
    mapRef.current = map;

    L.control
      .attribution({
        prefix: false,
        position: 'bottomright',
      })
      .addAttribution(`&copy; <a href="${OSM_COPYRIGHT_URL}" target="_blank" rel="noopener noreferrer">${t('map2.osmCredit')}</a>`)
      .addTo(map);
    L.control.zoom({ position: 'topright', zoomInTitle: t('map2.zoomIn'), zoomOutTitle: t('map2.zoomOut') }).addTo(map);

    const layer = L.tileLayer(TILE_URL, { subdomains: TILE_SUBDOMAINS, maxZoom: MAX_ZOOM });
    let loaded = false;
    layer.on('tileload', () => {
      loaded = true;
      setTiles('ok');
    });
    layer.on('tileerror', () => {
      if (!loaded) setTiles('error');
    });
    layer.addTo(map);

    if (viewer.kind === 'rounded') {
      // Leaflet's default fillOpacity (0.2) is deliberately kept here: a translucent area, not a pin.
      const radiusMeters = (viewer.rounding / 2) * METERS_PER_DEGREE;
      L.circle([point.lat, point.lon], { radius: radiusMeters, fillOpacity: 0.35, className: 'lm-pin lm-pin--area', interactive: false }).addTo(map);
    } else {
      // Leaflet's default fillOpacity (0.2) would make a solid point marker nearly invisible against busy tiles.
      L.circleMarker([point.lat, point.lon], { radius: 9, fillOpacity: 1, className: 'lm-pin lm-pin--precise', interactive: false }).addTo(map);
    }

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // Re-create the map only when the point, its kind, the UI language (control titles/credit
    // text) or an explicit retry changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [point?.lat, point?.lon, viewer.kind, lang, retryTick]);

  const caption =
    viewer.kind === 'precise' ? t('map2.capPrecise')
    : viewer.kind === 'rounded' ? t('map2.capRounded', { half: num(viewer.rounding / 2, { digits: 2 }) })
    : viewer.kind === 'region' ? t('map2.capRegion', { label: viewer.label })
    : t('map2.capHidden');

  if (viewer.kind === 'region') {
    return (
      <figure className="locmap" aria-labelledby={headingId}>
        <figcaption id={headingId}>{title ?? t('map2.title')}</figcaption>
        <StatusMessage tone="empty" title={caption} />
      </figure>
    );
  }
  if (viewer.kind === 'hidden' || !point) {
    return (
      <figure className="locmap" aria-labelledby={headingId}>
        <figcaption id={headingId}>{title ?? t('map2.title')}</figcaption>
        <StatusMessage tone="empty" title={caption} />
      </figure>
    );
  }

  return (
    <figure className="locmap" aria-labelledby={headingId}>
      <figcaption id={headingId}>{title ?? t('map2.title')}</figcaption>
      <div className="locmap-frame">
        <div ref={containerRef} className="locmap-canvas" role="group" aria-label={caption} />
        {tiles === 'loading' && (
          <div className="locmap-overlay">
            <StatusMessage tone="loading" title={t('map2.loading')} />
          </div>
        )}
        {tiles === 'error' && (
          <div className="locmap-overlay">
            <StatusMessage
              tone="error"
              title={t('map2.tileError')}
              action={<Button onClick={() => setRetryTick((n) => n + 1)}>{t('state.retry')}</Button>}
            />
          </div>
        )}
      </div>
      <p className="muted locmap-caption">{caption}</p>
    </figure>
  );
}

/**
 * What a REVIEWER or VIEWER (or anyone reading a non-editable case) is shown, for the map.
 * Mirrors `CaseTitleBlock.tsx` `sharedAsText`: owners/editors always see the stored point
 * (`displayedLocation(..., 'owner')`, ADR-0004); reviewers/viewers see exactly what the
 * server already redacted into `field.latitude/longitude` + `location_precision` — this
 * function never re-derives privacy from raw coordinates for them, only reads what the
 * API already decided to send. Keep in sync with `CaseTitleBlock.sharedAsText` if that
 * reviewer/viewer branch changes.
 */
export function viewerLocationForReadOnlyCase(c: IncidentCase): DisplayedLocation {
  if (!c.server || c.server.myRole === 'OWNER' || c.server.myRole === 'EDITOR') {
    return displayedLocation(c.location, 'owner');
  }
  const lat = parseNumber(c.location.latitude);
  const lon = parseNumber(c.location.longitude);
  const valid = Number.isFinite(lat) && Number.isFinite(lon);
  switch (c.server.locationPrecision) {
    case 'EXACT':
      return valid ? { kind: 'precise', latitude: lat, longitude: lon } : { kind: 'hidden' };
    case 'APPROXIMATE':
      return valid ? { kind: 'rounded', latitude: lat, longitude: lon, rounding: c.location.rounding } : { kind: 'hidden' };
    case 'REGION_ONLY':
      return c.location.regionLabel.trim() ? { kind: 'region', label: c.location.regionLabel.trim() } : { kind: 'hidden' };
    default:
      return { kind: 'hidden' };
  }
}
