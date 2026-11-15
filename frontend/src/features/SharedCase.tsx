import { useEffect, useState } from 'react';
import { ApiError, collabApi } from '../api/client';
import type { SharedCaseView } from '../api/types';
import { EvidenceLabel, PageHeader, StatusMessage, type EvidenceKind } from '../design/components';
import { useI18n } from '../i18n/I18n';
import type { MessageKey } from '../i18n/messages';
import { useDates } from './cases/collaboration/format';
import { useEnum } from './cases/evidence/labels';

type Load = { status: 'loading' } | { status: 'gone' } | { status: 'error'; message: string } | { status: 'ready'; view: SharedCaseView };

const EVIDENCE_KINDS = new Set<string>(['OBSERVED', 'FARMER_REPORTED', 'LITERATURE_REVIEWED', 'HYPOTHESIS', 'MODEL_SCENARIO', 'ILLUSTRATIVE', 'MISSING_DATA']);

/**
 * Public, read-only view of a case shared by its owner with explicit consent (ABB-25
 * `GET /api/v1/shared/{token}`). No account. The server already removed exact coordinates,
 * e-mails, member lists, observations and history; this screen renders only what it returned
 * and says which sections the owner chose not to share. Free text is rendered as text.
 */
export function SharedCase({ token }: { token: string }) {
  const { t, num } = useI18n();
  const dates = useDates();
  const toEnum = useEnum();
  const [load, setLoad] = useState<Load>({ status: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    setLoad({ status: 'loading' });
    collabApi.shared(token, controller.signal).then(
      (view) => setLoad({ status: 'ready', view }),
      (e) => {
        if (e?.name === 'AbortError') return;
        if (e instanceof ApiError && e.status === 404) setLoad({ status: 'gone' });
        else setLoad({ status: 'error', message: e instanceof ApiError && e.isNetwork ? t('state.networkError') : String(e?.message ?? '') });
      },
    );
    return () => controller.abort();
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  if (load.status === 'loading') return <><PageHeader title={t('shared.title')} /><StatusMessage tone="loading" title={t('state.loading')} /></>;
  if (load.status === 'gone') return <><PageHeader title={t('shared.title')} /><StatusMessage tone="error" title={t('shared.goneTitle')}>{t('shared.goneBody')}</StatusMessage></>;
  if (load.status === 'error') return <><PageHeader title={t('shared.title')} /><StatusMessage tone="error" title={t('shared.errorTitle')}>{load.message}</StatusMessage></>;

  const { view } = load;
  const c = view.case;
  const s = view.sections;
  const notShared = <p className="muted">{t('shared.notShared')}</p>;
  // When the owner withheld names, the server sends English pseudonyms ("Field 2", "Member 1"); show them in the UI language.
  const fieldLabel = (label: string) => {
    const m = !s.field_labels && /^Field (\d+)$/.exec(label);
    return m ? t('shared.fieldN', { n: m[1] }) : label;
  };
  const authorLabel = (author: string) => {
    const m = !s.member_names && /^Member (\d+)$/.exec(author);
    return m ? t('shared.memberN', { n: m[1] }) : author;
  };

  return (
    <>
      <PageHeader title={c.title} lead={t('shared.lead')} />
      <StatusMessage tone="partial" title={t('shared.bannerTitle')}>
        {t('shared.bannerBody', { expires: dates.dateTime(view.link_expires_at), generated: dates.dateTime(view.generated_at) })}
      </StatusMessage>

      <section className="panel" aria-labelledby="shared-case-h">
        <div className="section-head"><h2 id="shared-case-h">{t('shared.caseTitle')}</h2></div>
        <dl className="review-list">
          <div><dt>{t('shared.status')}</dt><dd>{t(`case.status.${c.status}` as MessageKey)}</dd></div>
          <div><dt>{t('shared.period')}</dt><dd>{dates.date(c.incident_start)}{c.incident_end ? ` – ${dates.date(c.incident_end)}` : ''}</dd></div>
          <div><dt>{t('shared.crops')}</dt><dd>{c.crop_history.length ? c.crop_history.join(' · ') : '—'}</dd></div>
          <div><dt>{t('shared.notes')}</dt><dd>{s.incident_notes ? (c.incident_notes ? <span className="voice">{c.incident_notes}</span> : '—') : t('shared.notSharedShort')}</dd></div>
          <div><dt>{t('shared.version')}</dt><dd>{t('shared.versionValue', { n: c.case_version, date: dates.dateTime(c.updated_at) })}</dd></div>
        </dl>
      </section>

      <section className="panel" aria-labelledby="shared-fields-h">
        <div className="section-head"><h2 id="shared-fields-h">{t('shared.fieldsTitle')}</h2><p>{t('shared.fieldsLead')}</p></div>
        {view.fields.length === 0 ? <p className="muted">—</p> : (
          <ul className="list-plain">
            {view.fields.map((f, i) => (
              <li key={i}>
                <b>{fieldLabel(f.label)}</b>{': '}
                {f.location_precision === 'APPROXIMATE' && f.latitude !== null && f.longitude !== null
                  ? t('shared.approx', { lat: num(f.latitude, { digits: 2 }), lon: num(f.longitude, { digits: 2 }), half: num((f.rounding_deg ?? 0) / 2, { digits: 2 }) })
                  : f.location_precision === 'REGION_ONLY' ? (f.region_label ?? t('shared.noLocation')) : t('shared.noLocation')}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-labelledby="shared-hyp-h">
        <div className="section-head"><h2 id="shared-hyp-h">{t('shared.hypothesesTitle')}</h2></div>
        {view.hypotheses === null ? notShared : view.hypotheses.length === 0 ? <p className="muted">—</p> : (
          <ul className="list-plain">
            {view.hypotheses.map((h, i) => (
              <li key={i} className="stack-tight">
                <p><EvidenceLabel kind="HYPOTHESIS" /> <b>{h.title ?? h.statement}</b> <span className="chip-meta">{toEnum('review', h.status)}</span></p>
                {h.title && <p>{h.statement}</p>}
                <p className="muted">{t('shared.hypCounts', { s: h.supporting_evidence_count, c: h.contradicting_evidence_count })}</p>
                {h.evaluation_note && <p className="voice">{h.evaluation_note}</p>}
                {h.missing_evidence.length > 0 && <p className="muted">{t('shared.missing', { list: h.missing_evidence.join('; ') })}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-labelledby="shared-claims-h">
        <div className="section-head"><h2 id="shared-claims-h">{t('shared.claimsTitle')}</h2></div>
        {view.evidence_claims === null ? notShared : view.evidence_claims.length === 0 ? <p className="muted">—</p> : (
          <ul className="list-plain">
            {view.evidence_claims.map((cl, i) => (
              <li key={i} className="stack-tight">
                <p>{EVIDENCE_KINDS.has(cl.source_kind) ? <EvidenceLabel kind={cl.source_kind as EvidenceKind} /> : <span className="chip-meta">{cl.source_kind === 'LITERATURE_METADATA' ? t('evidence.metadataOnly') : cl.source_kind}</span>} {cl.claim_text}</p>
                <p className="muted">
                  {cl.paper.title}{cl.paper.year ? ` (${cl.paper.year})` : ''}
                  {cl.paper.doi && <> · <a href={`https://doi.org/${cl.paper.doi}`} target="_blank" rel="noreferrer noopener">{cl.paper.doi}</a></>}
                  {' · '}{toEnum('review', cl.review_status)}
                </p>
                {cl.limitations.length > 0 && <p className="muted">{cl.limitations.join(' ')}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-labelledby="shared-concl-h">
        <div className="section-head"><h2 id="shared-concl-h">{t('shared.conclusionsTitle')}</h2></div>
        {view.conclusions === null ? notShared : view.conclusions.length === 0 ? <p className="muted">—</p> : (
          <ul className="list-plain">
            {view.conclusions.map((co, i) => (
              <li key={i} className="stack-tight">
                <p><b>{co.title ?? co.statement}</b> <span className="chip-meta">{toEnum('review', co.review_status)}</span></p>
                {co.title && <p>{co.statement}</p>}
                {co.limitations.length > 0 && <p className="muted">{co.limitations.join(' ')}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel" aria-labelledby="shared-comments-h">
        <div className="section-head"><h2 id="shared-comments-h">{t('shared.commentsTitle')}</h2></div>
        {view.comments === null ? notShared : view.comments.length === 0 ? <p className="muted">—</p> : (
          <ol className="thread">
            {view.comments.map((cm) => (
              <li key={cm.ref} className={cm.reply_to ? 'slip reply' : 'slip'}>
                <p className="who">
                  <b>{authorLabel(cm.author)}</b> · {dates.dateTime(cm.created_at)} · {cm.ref}
                  {cm.reply_to && <> · {t('shared.replyTo', { ref: cm.reply_to })}</>}
                  {cm.edited && <> · {t('shared.edited')}</>}
                </p>
                <blockquote>{cm.body}</blockquote>
              </li>
            ))}
          </ol>
        )}
      </section>

      {view.limitations.length > 0 && (
        <section className="panel" aria-labelledby="shared-lim-h">
          <div className="section-head"><h2 id="shared-lim-h">{t('shared.limitationsTitle')}</h2></div>
          <ul className="list-plain">{view.limitations.map((l, i) => <li key={i} className="muted">{l}</li>)}</ul>
        </section>
      )}
    </>
  );
}
