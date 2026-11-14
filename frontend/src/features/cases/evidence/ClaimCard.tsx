import { useState } from 'react';
import { evidenceApi } from '../../../api/client';
import type { ApplicabilityReport, ClaimEventView, ClaimView, KoppenClass } from '../../../api/types';
import { Button, EvidenceLabel, Field, StatusMessage } from '../../../design/components';
import { useI18n } from '../../../i18n/I18n';
import { caseErrorText } from '../caseErrors';
import { useDates } from '../collaboration/format';
import { DoiLink, NotReviewed, useEnum } from './labels';

export const KOPPEN: KoppenClass[] = ['Af', 'Am', 'Aw', 'As', 'BWh', 'BWk', 'BSh', 'BSk', 'Csa', 'Csb', 'Csc', 'Cwa', 'Cwb', 'Cwc',
  'Cfa', 'Cfb', 'Cfc', 'Dsa', 'Dsb', 'Dsc', 'Dsd', 'Dwa', 'Dwb', 'Dwc', 'Dwd', 'Dfa', 'Dfb', 'Dfc', 'Dfd', 'ET', 'EF'];

/**
 * One study claim as a herbarium label (design system: provenance labels). Shows exactly what the
 * backend returned: the claim, its paper and registered DOI, what was read, the study conditions,
 * the outcome as stated, limitations and warnings. Only ACCEPTED claims carry the reviewed-literature
 * symbol; every other status is marked "Not reviewed" with an icon and text.
 */
export function ClaimCard({ caseId, claim, focused }: { caseId: string; claim: ClaimView; focused?: boolean }) {
  const { t } = useI18n();
  const toEnum = useEnum();
  const dates = useDates();
  const c = claim;
  const ctx = c.context;
  const rows: [string, string][] = [
    [t('evx.ctx.population'), ctx.population ?? ''],
    [t('evx.ctx.crops'), ctx.crops.join(', ')],
    [t('evx.ctx.soils'), [...ctx.soils, ...ctx.soil_texture_classes.map((x) => toEnum('texture', x))].join(', ')],
    [t('evx.ctx.ph'), ctx.soil_ph_min !== null && ctx.soil_ph_max !== null ? `${ctx.soil_ph_min}–${ctx.soil_ph_max}` : ''],
    [t('evx.ctx.region'), [ctx.region, ctx.geographic_scope !== 'NOT_REPORTED' ? toEnum('scope', ctx.geographic_scope) : null, ctx.countries.join(', ')].filter(Boolean).join(' · ')],
    [t('evx.ctx.climate'), [ctx.climate, ctx.climate_classes.join(', ')].filter(Boolean).join(' · ')],
    [t('evx.ctx.water'), ctx.water_regime !== 'NOT_REPORTED' ? toEnum('water', ctx.water_regime) : ''],
    [t('evx.ctx.management'), ctx.management ?? ''],
  ].filter(([, v]) => v) as [string, string][];
  const outcome = c.reported_outcome;
  const outcomeRows: [string, string | null][] = [
    [t('evx.out.outcome'), outcome.outcome], [t('evx.out.comparison'), outcome.comparison],
    [t('evx.out.effect'), outcome.effect_as_stated], [t('evx.out.units'), outcome.units_as_stated],
    [t('evx.out.uncertainty'), outcome.uncertainty_as_stated], [t('evx.out.sample'), outcome.sample_as_stated],
  ];
  const locator = [c.source_locator.page, c.source_locator.section, c.source_locator.figure_or_table].filter(Boolean).join(', ');

  return (
    <article className={`label claim${focused ? ' is-focused' : ''}`} id={`claim-${c.id}`} aria-labelledby={`claim-${c.id}-h`} tabIndex={-1}>
      <header>
        <b id={`claim-${c.id}-h`}>{c.claim_text}</b>
        {c.is_reviewed
          ? <EvidenceLabel kind="LITERATURE_REVIEWED" detail={c.reviewer ? t('evx.reviewedBy', { name: c.reviewer.display_name, date: c.reviewed_at ? dates.date(c.reviewed_at) : '' }) : undefined} />
          : <NotReviewed status={c.review_status} />}
      </header>
      <dl>
        <div className="label-row"><dt>{t('evx.study')}</dt><dd>{c.paper.title}{c.paper.year ? ` (${c.paper.year})` : ''}</dd></div>
        <div className="label-row"><dt>DOI</dt><dd><DoiLink doi={c.paper.doi} status={c.paper.doi_status} /></dd></div>
        {c.paper.openalex_id && <div className="label-row"><dt>OpenAlex</dt><dd><a href={c.paper.openalex_id} target="_blank" rel="noreferrer noopener">{c.paper.openalex_id.replace('https://openalex.org/', '')}<span className="sr-only"> {t('ev.newTab')}</span></a></dd></div>}
        <div className="label-row"><dt>{t('evx.read')}</dt><dd>{toEnum('basis', c.evidence_basis)}{c.access_basis !== 'NONE' ? ` · ${toEnum('access', c.access_basis)}` : ''}</dd></div>
        <div className="label-row"><dt>{t('evx.design')}</dt><dd>{toEnum('design', c.study_design)}</dd></div>
        <div className="label-row"><dt>{t('evx.studyContext')}</dt><dd>{c.study_context}</dd></div>
        {rows.map(([k, v]) => <div key={k} className="label-row"><dt>{k}</dt><dd>{v}</dd></div>)}
        {(c.intervention || c.outcome_variable) && (
          <div className="label-row"><dt>{t('evx.effect')}</dt><dd>{t('evx.effectValue', { intervention: c.intervention ?? '—', outcome: c.outcome_variable ?? '—', direction: toEnum('direction', c.effect_direction) })}{c.comparator ? ` · ${t('evx.comparator', { value: c.comparator })}` : ''}</dd></div>
        )}
        {outcomeRows.filter(([, v]) => v).map(([k, v]) => <div key={k} className="label-row"><dt>{k}</dt><dd>{v}</dd></div>)}
        {c.quoted_fragment && <div className="label-row"><dt>{t('evx.quote')}</dt><dd><q className="voice">{c.quoted_fragment}</q>{locator ? ` (${locator})` : ''}</dd></div>}
        <div className="label-row"><dt>{t('evx.addedBy')}</dt><dd>{c.created_by?.display_name ?? t('collab.deletedAccount')} · {dates.date(c.created_at)}{c.origin === 'PILOT_SEED_UNVERIFIED' ? ` · ${t('evx.pilot')}` : ''}</dd></div>
        <dd className="lim">
          <b>{t('evx.limitations')}</b>
          <ul className="list-plain">{[...c.limitations, ...c.warnings].map((l, i) => <li key={i}>{l}</li>)}</ul>
        </dd>
      </dl>
      <ClaimTools caseId={caseId} claim={c} />
    </article>
  );
}

/** Review annotations (claim history) and the transferability check, loaded on demand. */
function ClaimTools({ caseId, claim }: { caseId: string; claim: ClaimView }) {
  const { t } = useI18n();
  const toEnum = useEnum();
  const dates = useDates();
  const [history, setHistory] = useState<ClaimEventView[] | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [fitOpen, setFitOpen] = useState(false);
  const [country, setCountry] = useState('');
  const [koppen, setKoppen] = useState<KoppenClass | ''>('');
  const [report, setReport] = useState<ApplicabilityReport | null>(null);
  const [fitBusy, setFitBusy] = useState(false);
  const [fitError, setFitError] = useState('');
  const countryInvalid = country.trim() !== '' && !/^[A-Za-z]{2}$/.test(country.trim());

  async function toggleHistory() {
    if (historyOpen) { setHistoryOpen(false); return; }
    setHistoryOpen(true);
    if (history) return;
    try { setHistory(await evidenceApi.claimHistory(caseId, claim.id)); setHistoryError(''); }
    catch (e) { setHistoryError(caseErrorText(e, t)); }
  }

  async function check(event: React.FormEvent) {
    event.preventDefault();
    if (countryInvalid) return;
    setFitBusy(true); setFitError('');
    try {
      setReport(await evidenceApi.applicability(caseId, claim.id, { country_code: country.trim() ? country.trim().toUpperCase() : null, koppen_climate: koppen || null }));
    } catch (e) { setFitError(caseErrorText(e, t)); } finally { setFitBusy(false); }
  }

  return (
    <div className="claim-tools">
      <div className="slip-actions">
        <Button variant="text" aria-expanded={historyOpen} onClick={toggleHistory}>{historyOpen ? t('evx.hideHistory') : t('evx.history')}</Button>
        <Button variant="text" aria-expanded={fitOpen} onClick={() => setFitOpen((o) => !o)}>{fitOpen ? t('evx.fit.hide') : t('evx.fit.open')}</Button>
      </div>
      {historyOpen && (
        <div className="stack-tight">
          {historyError && <p className="err" role="alert">{historyError}</p>}
          {!history && !historyError && <p className="muted">{t('state.loading')}</p>}
          {history && (
            <ol className="revisions" aria-label={t('evx.historyLabel')}>
              {history.map((ev) => (
                <li key={ev.id}>
                  <p className="who">
                    <b>{ev.actor?.display_name ?? t('collab.deletedAccount')}</b> · {dates.dateTime(ev.created_at)} · {toEnum('event', ev.action)}
                    {' · '}{ev.from_status ? `${toEnum('review', ev.from_status)} → ` : ''}{toEnum('review', ev.to_status)} · v{ev.claim_version}
                  </p>
                  {ev.note && <p className="voice">{ev.note}</p>}
                  {ev.source_consulted && (
                    <p className="muted">{t('evx.consulted', { basis: toEnum('basis', ev.source_consulted.basis), access: toEnum('access', ev.source_consulted.access_basis) })}
                      {ev.source_consulted.locator ? ` · ${ev.source_consulted.locator}` : ''}{ev.source_consulted.license ? ` · ${ev.source_consulted.license}` : ''}</p>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
      {fitOpen && (
        <div className="stack">
          <form className="stack" onSubmit={check}>
            <p className="muted">{t('evx.fit.lead')}</p>
            <div className="form-row form-row--2">
              <Field label={t('evx.fit.country')} hint={t('evx.fit.countryHint')} maxLength={2} value={country}
                error={countryInvalid ? t('evx.fit.countryError') : undefined} onChange={(e) => setCountry(e.target.value)} />
              <div className="field">
                <label htmlFor={`koppen-${claim.id}`}>{t('evx.fit.koppen')}</label>
                <div className="ctl">
                  <select id={`koppen-${claim.id}`} value={koppen} onChange={(e) => setKoppen(e.target.value as KoppenClass | '')}>
                    <option value="">{t('evx.fit.unknown')}</option>
                    {KOPPEN.map((k) => <option key={k} value={k}>{k}</option>)}
                  </select>
                </div>
              </div>
            </div>
            <div className="actions"><Button type="submit" busy={fitBusy}>{t('evx.fit.run')}</Button></div>
          </form>
          {fitError && <StatusMessage tone="error" title={t('evx.fit.error')}>{fitError}</StatusMessage>}
          {report && (
            <div className="stack" aria-live="polite">
              <StatusMessage tone={report.transfer_status === 'DIFFERENCES_FOUND' ? 'partial' : 'empty'} title={toEnum('transfer', report.transfer_status)}>
                {report.notes.map((n, i) => <p key={i}>{n}</p>)}
              </StatusMessage>
              <div className="table-wrap">
                <table className="data collab-table">
                  <caption className="sr-only">{t('evx.fit.caption')}</caption>
                  <thead><tr><th scope="col">{t('evx.fit.dimension')}</th><th scope="col">{t('evx.fit.result')}</th><th scope="col">{t('evx.fit.study')}</th><th scope="col">{t('evx.fit.case')}</th><th scope="col">{t('evx.fit.why')}</th></tr></thead>
                  <tbody>
                    {report.dimensions.map((d) => (
                      <tr key={d.dimension}>
                        <th scope="row">{toEnum('dim', d.dimension)}</th>
                        <td data-label={t('evx.fit.result')}><span className={`chip-meta match match--${d.status.toLowerCase()}`}>{toEnum('match', d.status)}</span></td>
                        <td data-label={t('evx.fit.study')}>{d.study_value ?? '—'}</td>
                        <td data-label={t('evx.fit.case')}>{d.case_value ?? '—'}{d.case_value_source ? <span className="muted block">{d.case_value_source}</span> : null}</td>
                        <td data-label={t('evx.fit.why')}>{d.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ul className="list-plain">{report.limitations.map((l, i) => <li key={i} className="muted">{l}</li>)}</ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
