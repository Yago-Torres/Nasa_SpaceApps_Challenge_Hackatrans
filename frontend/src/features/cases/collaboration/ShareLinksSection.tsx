import { useEffect, useRef, useState } from 'react';
import { Copy } from 'lucide-react';
import { collabApi } from '../../../api/client';
import type { ShareLinkCreated, ShareLinkView, ShareLocationDetail, ShareSections } from '../../../api/types';
import { Button, Checkbox, Field, RadioGroup, StatusMessage } from '../../../design/components';
import { useI18n } from '../../../i18n/I18n';
import type { MessageKey } from '../../../i18n/messages';
import { caseErrorText } from '../caseErrors';
import { useDates } from './format';

const BOOLEAN_SECTIONS = ['incident_notes', 'field_labels', 'hypotheses', 'evidence_claims', 'conclusions', 'comments', 'member_names'] as const;
type BooleanSection = (typeof BOOLEAN_SECTIONS)[number];

/** Nothing is pre-selected: every section is an explicit choice by the owner (consent covers exactly what is listed). */
const NOTHING: ShareSections = {
  incident_notes: false, field_labels: false, location_detail: 'NONE', hypotheses: false,
  evidence_claims: false, conclusions: false, member_names: false, comments: false,
};

/** Public read link for the shared view, served by this app at #/shared/<token>. The token never goes to the server in a URL path we log. */
export function sharedViewUrl(token: string) {
  const { origin, pathname } = window.location;
  return `${origin}${pathname}#/shared/${encodeURIComponent(token)}`;
}

/**
 * Owner-only consented share links (ABB-25). The owner chooses every section, confirms consent
 * and sees the link once (only its digest is stored). Exact coordinates, e-mails, member lists,
 * observations and history are never part of a shared view, whatever is selected here.
 */
export function ShareLinksSection({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  const dates = useDates();
  const [items, setItems] = useState<ShareLinkView[] | null>(null);
  const [failure, setFailure] = useState('');
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [sections, setSections] = useState<ShareSections>(NOTHING);
  const [label, setLabel] = useState('');
  const [days, setDays] = useState('14');
  const [consent, setConsent] = useState(false);
  const [consentError, setConsentError] = useState(false);
  const [created, setCreated] = useState<ShareLinkCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const linkInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    collabApi.shareLinks(caseId, controller.signal).then(
      (list) => { setItems(list.items); setFailure(''); },
      (e) => { if (e?.name !== 'AbortError') setFailure(caseErrorText(e, t)); },
    );
    return () => controller.abort();
  }, [caseId, reload]); // eslint-disable-line react-hooks/exhaustive-deps

  const daysNumber = Number(days);
  const daysInvalid = !Number.isInteger(daysNumber) || daysNumber < 1 || daysNumber > 30;

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (!consent) { setConsentError(true); return; }
    if (daysInvalid) return;
    setBusy(true); setFailure(''); setCopied(false);
    try {
      const link = await collabApi.createShareLink(caseId, { consent: true, sections, label: label.trim() || null, expires_in_days: daysNumber });
      setCreated(link);
      setOpen(false); setSections(NOTHING); setLabel(''); setConsent(false); setConsentError(false);
      setReload((n) => n + 1);
    } catch (e) { setFailure(caseErrorText(e, t)); } finally { setBusy(false); }
  }

  async function revoke(id: string) {
    setBusy(true); setFailure('');
    try {
      await collabApi.revokeShareLink(caseId, id);
      if (created?.id === id) setCreated(null);
      setReload((n) => n + 1);
    } catch (e) { setFailure(caseErrorText(e, t)); } finally { setBusy(false); }
  }

  async function copy() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(sharedViewUrl(created.token));
      setCopied(true);
    } catch {
      linkInput.current?.select(); // clipboard blocked: leave the link selected for manual copy
    }
  }

  const toggle = (key: BooleanSection) => (value: boolean) => setSections((s) => ({ ...s, [key]: value }));

  return (
    <section className="panel" aria-labelledby="collab-share-h">
      <div className="section-head">
        <h2 id="collab-share-h">{t('collab.share.title')}</h2>
        <p>{t('collab.share.lead')}</p>
      </div>

      {created && (
        <div className="share-once" role="status">
          <b>{t('collab.share.createdTitle')}</b>
          <p className="muted">{t('collab.share.createdBody')}</p>
          <div className="field">
            <label htmlFor="share-link-url">{t('collab.share.link')}</label>
            <div className="ctl">
              <input id="share-link-url" ref={linkInput} readOnly className="mono" value={sharedViewUrl(created.token)} onFocus={(e) => e.target.select()} />
            </div>
          </div>
          <div className="actions">
            <Button icon={<Copy aria-hidden="true" />} onClick={copy}>{copied ? t('collab.share.copied') : t('collab.share.copy')}</Button>
            <Button variant="text" onClick={() => setCreated(null)}>{t('collab.share.hideLink')}</Button>
          </div>
        </div>
      )}

      {!open && <div className="actions"><Button onClick={() => { setOpen(true); setCreated(null); }}>{t('collab.share.new')}</Button></div>}
      {open && (
        <form className="stack share-form" onSubmit={create} aria-labelledby="collab-share-form-h">
          <h3 id="collab-share-form-h">{t('collab.share.formTitle')}</h3>
          <StatusMessage tone="partial" title={t('collab.share.freeTextTitle')}>{t('collab.share.freeTextBody')}</StatusMessage>
          <fieldset className="choices">
            <legend>{t('collab.share.sectionsLegend')}</legend>
            <p className="hint">{t('collab.share.sectionsHint')}</p>
            <div className="check-list">
              {BOOLEAN_SECTIONS.map((key) => (
                <Checkbox key={key} name={`share-${key}`} label={t(`collab.share.s.${key}` as MessageKey)}
                  hint={t(`collab.share.h.${key}` as MessageKey)} checked={sections[key]} onChange={toggle(key)} />
              ))}
            </div>
          </fieldset>
          <RadioGroup<ShareLocationDetail> legend={t('collab.share.locationLegend')} name="share-location" value={sections.location_detail}
            hint={t('collab.share.locationHint')}
            options={(['NONE', 'REGION', 'APPROXIMATE'] as const).map((v) => ({ value: v, label: t(`collab.share.loc.${v}` as MessageKey), hint: t(`collab.share.locHint.${v}` as MessageKey) }))}
            onChange={(v) => setSections((s) => ({ ...s, location_detail: v }))} />
          <div className="form-row form-row--2">
            <Field label={t('collab.share.label')} hint={t('collab.share.labelHint')} maxLength={120} value={label} onChange={(e) => setLabel(e.target.value)} />
            <Field label={t('collab.inv.days')} inputMode="numeric" unit={t('collab.inv.daysUnit')} value={days}
              error={daysInvalid ? t('collab.inv.daysError') : undefined} onChange={(e) => setDays(e.target.value)} />
          </div>
          <div className={consentError ? 'consent bad' : 'consent'}>
            <Checkbox name="share-consent" label={t('collab.share.consent')} checked={consent}
              onChange={(v) => { setConsent(v); if (v) setConsentError(false); }} />
            {consentError && <p className="err" role="alert">{t('collab.share.consentError')}</p>}
          </div>
          <div className="actions">
            <Button type="submit" busy={busy}>{t('collab.share.create')}</Button>
            <Button variant="text" onClick={() => { setOpen(false); setConsentError(false); }}>{t('collab.cancel')}</Button>
          </div>
        </form>
      )}

      {failure && <StatusMessage tone="error" title={t('collab.error')}>{failure}</StatusMessage>}
      {items === null && !failure && <StatusMessage tone="loading" title={t('state.loading')} />}
      {items && items.length === 0 && <p className="muted">{t('collab.share.none')}</p>}
      {items && items.length > 0 && (
        <div className="table-wrap">
          <table className="data collab-table">
            <caption className="sr-only">{t('collab.share.listCaption')}</caption>
            <thead>
              <tr>
                <th scope="col">{t('collab.share.label')}</th>
                <th scope="col">{t('collab.share.includes')}</th>
                <th scope="col">{t('collab.status')}</th>
                <th scope="col">{t('collab.inv.expires')}</th>
                <th scope="col"><span className="sr-only">{t('collab.actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {items.map((link) => (
                <tr key={link.id}>
                  <th scope="row">{link.label ?? t('collab.share.unlabelled')}<span className="muted block">{t('collab.share.createdOn', { date: dates.dateTime(link.created_at) })}</span></th>
                  <td data-label={t('collab.share.includes')}>{sectionSummary(link.sections, t)}</td>
                  <td data-label={t('collab.status')}><span className="chip-meta">{t(`collab.share.status.${link.status}` as MessageKey)}</span></td>
                  <td data-label={t('collab.inv.expires')}>{dates.dateTime(link.expires_at)}</td>
                  <td>{link.status === 'ACTIVE' && <Button variant="text" disabled={busy} onClick={() => revoke(link.id)}>{t('collab.share.revoke')}</Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function sectionSummary(s: ShareSections, t: ReturnType<typeof useI18n>['t']) {
  const parts = BOOLEAN_SECTIONS.filter((k) => s[k]).map((k) => t(`collab.share.s.${k}` as MessageKey));
  parts.unshift(t(`collab.share.loc.${s.location_detail}` as MessageKey));
  return parts.join(' · ');
}
