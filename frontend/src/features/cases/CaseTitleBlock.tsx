import type { ReactNode } from 'react';
import { useI18n } from '../../i18n/I18n';
import type { MessageKey } from '../../i18n/messages';
import { displayedLocation, parseNumber, type IncidentCase } from '../../cases/model';

type I18n = ReturnType<typeof useI18n>;

/** Owners and editors receive the stored point; reviewers and viewers only what the server allowed (ADR-0004). */
export function seesStoredLocation(c: IncidentCase) {
  return !c.server || c.server.myRole === 'OWNER' || c.server.myRole === 'EDITOR';
}

/**
 * "Shared as": what reviewers see. For owners/editors this mirrors the server rule from the
 * stored tier (cases/model displayedLocation); for reviewers/viewers it is the location the
 * server returned to them, already redacted.
 */
export function sharedAsText(c: IncidentCase, { t, num }: Pick<I18n, 't' | 'num'>): string {
  const fmt = (v: number, digits = 2) => num(v, { digits });
  if (seesStoredLocation(c)) {
    const d = displayedLocation(c.location, 'guest');
    if (d.kind === 'hidden') return t('f.tier.private');
    if (d.kind === 'region') return d.label;
    return `${fmt(d.latitude)}, ${fmt(d.longitude)}${d.kind === 'rounded' ? ` (±${fmt(d.rounding / 2)}°)` : ''}`;
  }
  const lat = parseNumber(c.location.latitude);
  const lon = parseNumber(c.location.longitude);
  switch (c.server?.locationPrecision) {
    case 'EXACT': return t('loc.seenExact', { lat: fmt(lat, 3), lon: fmt(lon, 3) });
    case 'APPROXIMATE': return t('loc.seenRounded', { lat: fmt(lat), lon: fmt(lon), half: fmt(c.location.rounding / 2) });
    case 'REGION_ONLY': return c.location.regionLabel || t('loc.seenHidden');
    default: return t('loc.seenHidden');
  }
}

/** The privacy setting in words, for the owner/editor. */
function tierText(c: IncidentCase, { t, num }: Pick<I18n, 't' | 'num'>): string {
  const l = c.location;
  const tier = l.tier === 'rounded' ? t('loc.rounded', { deg: num(l.rounding, { digits: l.rounding < 1 ? 1 : 0 }) }) : t(l.tier === 'region' ? 'f.tier.region' : 'f.tier.private');
  return l.consentPrecise ? `${tier} · ${t('loc.consent')}` : tier;
}

/**
 * Signature title block (design system components.md §5): what this case is, its ID,
 * location as this user may see it, workflow status, role, owner and last update.
 * Only values the API returned; a case not saved yet says so.
 */
export function CaseTitleBlock({ c, lead }: { c: IncidentCase; lead?: ReactNode }) {
  const i18n = useI18n();
  const { t, lang } = i18n;
  const dateFmt = new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' });
  const s = c.server;
  const location = seesStoredLocation(c) ? `${tierText(c, i18n)} · ${t('cases.colLocation')}: ${sharedAsText(c, i18n)}` : sharedAsText(c, i18n);
  return (
    <dl className="titleblock">
      <div className="name">
        <h1 tabIndex={-1} data-page-title>{c.title.trim() || t('cases.untitled')}</h1>
        {lead && <p>{lead}</p>}
      </div>
      <div><dt>{t('case.id')}</dt><dd className={s ? 'mono' : undefined}>{s ? c.id : t('case.notSaved')}</dd></div>
      <div><dt>{t('case.location')}</dt><dd>{location}</dd></div>
      <div><dt>{t('case.status')}</dt><dd>{s ? t(`case.status.${s.status}` as MessageKey) : '—'}</dd></div>
      <div><dt>{t('case.role')}</dt><dd>{s ? t(`case.role.${s.myRole}` as MessageKey) : '—'}</dd></div>
      <div><dt>{t('case.owner')}</dt><dd>{s ? s.ownerName : '—'}</dd></div>
      <div><dt>{t('case.updated')}</dt><dd className="num">{s ? <time dateTime={c.updatedAt}>{dateFmt.format(new Date(c.updatedAt))}</time> : '—'}</dd></div>
    </dl>
  );
}
