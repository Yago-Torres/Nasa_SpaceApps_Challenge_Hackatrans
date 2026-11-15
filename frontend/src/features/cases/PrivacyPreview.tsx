import { useI18n } from '../../i18n/I18n';
import { displayedLocation, parseNumber, roundToCell, type CaseLocation } from '../../cases/model';

/**
 * Local, to-scale geospatial map of what the owner and reviewers see. It deliberately
 * uses no third-party basemap: a tile request can disclose a field through its URL, IP
 * address and viewport. Nothing here contacts any server.
 */
export function PrivacyPreview({ location }: { location: CaseLocation }) {
  const { t, num } = useI18n();
  const lat = parseNumber(location.latitude);
  const lon = parseNumber(location.longitude);
  const valid = Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
  const guest = displayedLocation(location, 'guest');
  const fmt = (v: number) => num(v, { digits: 3 });

  // Scale so the larger of the shared square and the NASA POWER cell fills about 60% of the view.
  const span = Math.max(0.625, location.tier === 'rounded' ? location.rounding : 0);
  const PX = 170 / span;
  const W = 280, H = 220, cx = W / 2, cy = H / 2;
  const toX = (dLon: number) => cx + dLon * PX;
  const toY = (dLat: number) => cy - dLat * PX;

  let shared: { x: number; y: number; size: number } | null = null;
  if (valid && location.tier === 'rounded' && !location.consentPrecise) {
    const r = location.rounding;
    const sLat = roundToCell(lat, r), sLon = roundToCell(lon, r);
    shared = { x: toX(sLon - lon - r / 2), y: toY(sLat - lat + r / 2), size: r * PX };
  }
  // NASA POWER meteorology grid: 0.5° lat × 0.625° lon, aligned to -90/-180.
  const pLat0 = valid ? Math.floor((lat + 90) / 0.5) * 0.5 - 90 : 0;
  const pLon0 = valid ? Math.floor((lon + 180) / 0.625) * 0.625 - 180 : 0;

  return (
    <figure className="privacy">
      <figcaption><b>{t('map.title')}</b></figcaption>
      {valid ? (
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('map.title')} className="privacy-svg">
          <defs>
            <pattern id="pv-grid" width={PX * 0.1} height={PX * 0.1} patternUnits="userSpaceOnUse" x={toX(-(((lon % 0.1) + 0.1) % 0.1))} y={toY(((lat % 0.1) + 0.1) % 0.1)}>
              <path d={`M ${PX * 0.1} 0 L 0 0 0 ${PX * 0.1}`} fill="none" className="pv-gridline" />
            </pattern>
          </defs>
          <rect width={W} height={H} className="pv-ground" />
          <rect width={W} height={H} fill="url(#pv-grid)" />
          <rect x={toX(pLon0 - lon)} y={toY(pLat0 + 0.5 - lat)} width={0.625 * PX} height={0.5 * PX} className="pv-power" />
          {shared && <rect x={shared.x} y={shared.y} width={shared.size} height={shared.size} className="pv-shared" />}
          <circle cx={cx} cy={cy} r={6} className="pv-you" />
        </svg>
      ) : (
        <p className="muted">{t('map.invalid')}</p>
      )}
      <ul className="pv-legend">
        <li><span className="pv-key pv-key--you" aria-hidden="true" />{t('map.you')}</li>
        {shared && <li><span className="pv-key pv-key--shared" aria-hidden="true" />{t('map.shared')}</li>}
        <li><span className="pv-key pv-key--power" aria-hidden="true" />{t('map.power')}</li>
      </ul>
      <dl className="pv-says">
        {valid && <div><dd>{t('map.ownerSees', { lat: fmt(lat), lon: fmt(lon) })}</dd></div>}
        <div>
          <dd>
            <b>
              {guest.kind === 'hidden' && t('map.hidden')}
              {guest.kind === 'region' && t('map.regionOnly', { label: guest.label })}
              {guest.kind === 'rounded' && t('map.guestSees', { lat: fmt(guest.latitude), lon: fmt(guest.longitude), half: num(guest.rounding / 2, { digits: 2 }) })}
              {guest.kind === 'precise' && t('map.guestSees', { lat: fmt(guest.latitude), lon: fmt(guest.longitude), half: '0' })}
            </b>
          </dd>
        </div>
      </dl>
      <p className="muted">{t('map.localPrivacy')}</p>
    </figure>
  );
}
