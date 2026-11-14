import { useEffect, useId, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useI18n } from '../../i18n/I18n';
import { displayedLocation, parseNumber, type DisplayedLocation, type IncidentCase } from '../../cases/model';
import { Button, StatusMessage } from '../../design/components';
import './LocationMap.css';

/**
 * Real basemap for a case location (ABB-21, ADR-0006). A visual COMPLEMENT to
 * `PrivacyPreview`'s to-scale diagram, not a replacement: that diagram explains the privacy
 * mechanics (grid cell, NASA POWER cell); this draws the same point/area on real geography.
 *
 * Tile provider: OpenStreetMap raster tiles (ADR-0006). Tiles are opt-in because requesting
 * them discloses the viewer's IP/referrer and a coarse map area to that third party.
 *
 * PRIVACY CONTRACT (hard requirement, see ADR-0006 and LocationMap.test.tsx): this component
 * never decides what a viewer may see. The caller must pass `viewer`, already the result of
 * `cases/model.ts` `displayedLocation()` for an owner/editor, or `viewerLocationForReadOnlyCase`
 * below for a reviewer/viewer reading the server-redacted field. A `viewer.kind === 'precise'`
 * marker is drawn only when the caller asserts the current viewer is authorized for it; this
 * component performs no rounding, consent or role check of its own.
 */

const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const OSM_COPYRIGHT_URL = 'https://www.openstreetmap.org/copyright';
const MAX_ZOOM = 18;

function zoomFor(viewer: DisplayedLocation): number {
  // Precise points use a 1°-rounded tile centre, so zoom 8 keeps the local point visible.
  if (viewer.kind === 'precise') return 8;
  if (viewer.kind === 'rounded') {
    if (viewer.rounding <= 0.1) return 11;
    if (viewer.rounding <= 0.5) return 9;
    return 8;
  }
  return 10;
}

type TileState = 'idle' | 'loading' | 'ok' | 'partial' | 'error';

/** Centre sent to the tile provider. Exact coordinates never determine a tile request. */
export function tileRequestCenter(viewer: Extract<DisplayedLocation, { kind: 'precise' | 'rounded' }>) {
  if (viewer.kind === 'rounded') return { lat: viewer.latitude, lon: viewer.longitude };
  return { lat: Math.round(viewer.latitude), lon: Math.round(viewer.longitude) };
}

export function LocationMap({ viewer, title }: { viewer: DisplayedLocation; title?: string }) {
  const { t, num, lang } = useI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const [tiles, setTiles] = useState<TileState>('idle');
  const [tilesRequested, setTilesRequested] = useState(false);
  const [retryTick, setRetryTick] = useState(0);
  const headingId = useId();

  const point = viewer.kind === 'precise' || viewer.kind === 'rounded' ? { lat: viewer.latitude, lon: viewer.longitude } : null;

  useEffect(() => {
    if (!point || !containerRef.current) return undefined;
    const remoteCenter = tileRequestCenter(viewer as Extract<DisplayedLocation, { kind: 'precise' | 'rounded' }>);
    setTiles(tilesRequested ? 'loading' : 'idle');
    const map = L.map(containerRef.current, {
      center: [remoteCenter.lat, remoteCenter.lon],
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

    if (tilesRequested) {
      const layer = L.tileLayer(TILE_URL, { maxZoom: MAX_ZOOM });
      let loaded = 0;
      let failed = 0;
      layer.on('tileload', () => { loaded += 1; });
      layer.on('tileerror', () => { failed += 1; });
      layer.on('load', () => setTiles(failed ? (loaded ? 'partial' : 'error') : 'ok'));
      layer.addTo(map);
    }

    if (viewer.kind === 'rounded') {
      const half = viewer.rounding / 2;
      L.rectangle([[point.lat - half, point.lon - half], [point.lat + half, point.lon + half]],
        { fillOpacity: 0.35, className: 'lm-pin lm-pin--area', interactive: false }).addTo(map);
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
  }, [point?.lat, point?.lon, viewer.kind, viewer.kind === 'rounded' ? viewer.rounding : null, lang, retryTick, tilesRequested]);

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
        {tiles === 'idle' && (
          <div className="locmap-overlay">
            <StatusMessage tone="pending" title={t('map2.tilesConsentTitle')}
              action={<Button onClick={() => setTilesRequested(true)}>{t('map2.loadTiles')}</Button>}>
              {t('map2.tilesConsentBody')}
            </StatusMessage>
          </div>
        )}
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
        {tiles === 'partial' && (
          <div className="locmap-overlay locmap-overlay--partial">
            <StatusMessage tone="partial" title={t('map2.tilePartial')}
              action={<Button variant="secondary" onClick={() => setRetryTick((n) => n + 1)}>{t('state.retry')}</Button>} />
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
