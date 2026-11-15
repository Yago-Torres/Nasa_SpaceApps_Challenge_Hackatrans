import { useEffect, useState } from 'react';
import { evidenceApi } from '../../../api/client';
import type { DisagreementClaimRef, DisagreementList } from '../../../api/types';
import { Button, EvidenceLabel, StatusMessage } from '../../../design/components';
import { useI18n } from '../../../i18n/I18n';
import { caseErrorText } from '../caseErrors';
import { useDates } from '../collaboration/format';
import { DoiLink, NotReviewed, useEnum } from './labels';
import { DisagreementReviewForm } from './ReviewForms';

/**
 * Candidate and reviewed disagreements between studies (ABB-15), with the recorded differences
 * that may explain them and every reviewer's annotation. A candidate is not a contradiction until
 * a reviewer confirms it, and a confirmed contradiction does not say which study is right.
 */
export function DisagreementsSection({ caseId, refreshKey, onOpenClaim }: { caseId: string; refreshKey: number; onOpenClaim: (claimId: string) => void }) {
  const { t } = useI18n();
  const toEnum = useEnum();
  const dates = useDates();
  const [list, setList] = useState<DisagreementList | null>(null);
  const [failure, setFailure] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    evidenceApi.disagreements(caseId, controller.signal).then(
      (l) => { setList(l); setFailure(''); },
      (e) => { if (e?.name !== 'AbortError') setFailure(caseErrorText(e, t)); },
    );
    return () => controller.abort();
  }, [caseId, refreshKey, reload]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section className="panel" aria-labelledby="evx-dis-h">
      <div className="section-head">
        <h2 id="evx-dis-h">{t('evx.dis.title')}</h2>
        <p>{t('evx.dis.lead')}</p>
      </div>
      {failure && <StatusMessage tone="error" title={t('evx.dis.error')} action={<Button onClick={() => setReload((n) => n + 1)}>{t('state.retry')}</Button>}>{failure}</StatusMessage>}
      {!list && !failure && <StatusMessage tone="loading" title={t('state.loading')} />}
      {list && list.items.length === 0 && <StatusMessage tone="empty" title={t('evx.dis.noneTitle')}>{t('evx.dis.noneBody')}</StatusMessage>}
      {list && list.items.map((d) => (
        <article key={d.id} className="disagreement" aria-labelledby={`dis-${d.id}-h`}>
          <header className="stack-tight">
            <h3 id={`dis-${d.id}-h`}>
              {t('evx.dis.heading', { intervention: d.matched_on.intervention ?? '—', outcome: d.matched_on.outcome_variable ?? '—' })}
            </h3>
            <p>
              <span className={`chip-meta dis-status dis-status--${d.status.toLowerCase()}`}>{toEnum('dis', d.status)}</span>
              {' '}<span className="muted">{toEnum('disKind', d.kind)}</span>
            </p>
          </header>
          <div className="dis-sides">
            <Side side={d.claim_a} label={t('evx.dis.studyA')} onOpenClaim={onOpenClaim} />
            <Side side={d.claim_b} label={t('evx.dis.studyB')} onOpenClaim={onOpenClaim} />
          </div>
          {d.comparability_notes.length > 0 && (
            <div className="table-wrap">
              <table className="data collab-table">
                <caption>{t('evx.dis.notesCaption')}</caption>
                <thead><tr><th scope="col">{t('evx.fit.dimension')}</th><th scope="col">{t('evx.fit.result')}</th><th scope="col">{t('evx.dis.studyA')}</th><th scope="col">{t('evx.dis.studyB')}</th><th scope="col">{t('evx.fit.why')}</th></tr></thead>
                <tbody>
                  {d.comparability_notes.map((n) => (
                    <tr key={n.dimension}>
                      <th scope="row">{toEnum('dim', n.dimension)}</th>
                      <td data-label={t('evx.fit.result')}><span className={`chip-meta match match--${n.status.toLowerCase()}`}>{toEnum('match', n.status)}</span></td>
                      <td data-label={t('evx.dis.studyA')}>{n.claim_a_value ?? '—'}</td>
                      <td data-label={t('evx.dis.studyB')}>{n.claim_b_value ?? '—'}</td>
                      <td data-label={t('evx.fit.why')}>{n.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <ul className="list-plain">{d.warnings.map((w, i) => <li key={i} className="muted">{w}</li>)}</ul>
          <DisagreementReviewForm caseId={caseId} item={d} onDone={() => setReload((n) => n + 1)} />
          <div className="stack-tight">
            <h4>{t('evx.dis.reviews')}</h4>
            {d.reviews.length === 0 ? <p className="muted">{t('evx.dis.noReviews')}</p> : (
              <ol className="thread">
                {d.reviews.map((r) => (
                  <li key={r.id} className={r.applies_to_current_versions ? 'slip' : 'slip slip--deleted'}>
                    <p className="who">
                      <b>{r.reviewer?.display_name ?? t('collab.deletedAccount')}</b> · {dates.dateTime(r.reviewed_at)} · {toEnum('dis', r.decision)}
                      {!r.applies_to_current_versions && <> · {t('evx.dis.stale')}</>}
                    </p>
                    <blockquote>{r.note}</blockquote>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </article>
      ))}
      {list && list.claims_not_compared.length > 0 && (
        <details>
          <summary>{t('evx.dis.notCompared', { n: list.claims_not_compared.length })}</summary>
          <ul className="list-plain">{list.claims_not_compared.map((c) => <li key={c.claim_id}>{c.reasons.join(' ')}</li>)}</ul>
        </details>
      )}
      {list && <ul className="list-plain">{list.limitations.map((l, i) => <li key={i} className="muted">{l}</li>)}</ul>}
    </section>
  );
}

function Side({ side, label, onOpenClaim }: { side: DisagreementClaimRef; label: string; onOpenClaim: (id: string) => void }) {
  const { t } = useI18n();
  const toEnum = useEnum();
  return (
    <div className="label dis-side">
      <header>
        <b>{label}</b>
        {side.is_reviewed ? <EvidenceLabel kind="LITERATURE_REVIEWED" /> : <NotReviewed status={side.review_status} />}
      </header>
      <dl>
        <div className="label-row"><dt>{t('evx.dis.claim')}</dt><dd>{side.claim_text}</dd></div>
        <div className="label-row"><dt>{t('evx.dis.direction')}</dt><dd>{toEnum('direction', side.effect_direction)}{side.comparator ? ` · ${t('evx.comparator', { value: side.comparator })}` : ''}</dd></div>
        <div className="label-row"><dt>{t('evx.design')}</dt><dd>{toEnum('design', side.study_design)}</dd></div>
        <div className="label-row"><dt>{t('evx.study')}</dt><dd>{side.paper.title}{side.paper.year ? ` (${side.paper.year})` : ''}</dd></div>
        <div className="label-row"><dt>DOI</dt><dd><DoiLink doi={side.paper.doi} status={side.paper.doi_status} /></dd></div>
      </dl>
      <div className="slip-actions"><Button variant="text" onClick={() => onOpenClaim(side.claim_id)}>{t('evx.dis.openClaim')}</Button></div>
    </div>
  );
}
