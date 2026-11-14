import { useEffect, useRef, useState } from 'react';
import { rotationsApi } from '../api/client';
import { useI18n } from '../i18n/I18n';
import { Button, Field, PageHeader, StatusMessage } from '../design/components';
import { errorText } from './errors';
import { CropHistoryEditor } from './rotations/CropHistoryEditor';
import { CalendarEditor } from './rotations/CalendarEditor';
import { ConstraintsForm } from './rotations/ConstraintsForm';
import { PrioritiesEditor } from './rotations/PrioritiesEditor';
import { ClimateScenarioEditor } from './rotations/ClimateScenarioEditor';
import { StrategyCard } from './rotations/StrategyCard';
import { SensitivityPanel } from './rotations/SensitivityPanel';
import { buildHorizonYears, buildProfile, validateProfileForm } from './rotations/model';
import { rotEnum } from './rotations/labels';
import { useRotationsState, setRotationsState } from './rotations/store';
import type { CropCatalogEntry, PriorityCriterion, ScenarioAnalysisRequest } from '../api/types';

const RECOMPUTE_DEBOUNCE_MS = 600;

/**
 * Interactive rotation builder/comparator (ABB-24, request B4). Replaces the illustrative
 * `GET /api/rotations/demo` screen: every strategy, calendar, risk and explanation shown here
 * comes from a real `POST /api/v1/rotations/scenarios` call over the farmer's own declared
 * crop history, calendar, constraints and priorities (ABB-17/ABB-18). The backend — not this
 * component — decides which strategies exist and why; see the design note in the PR for the
 * one deliberate scope decision (alternatives are backend-generated, not hand-authored).
 */
export function Rotations() {
  const { t } = useI18n();
  const state = useRotationsState();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [catalog, setCatalog] = useState<CropCatalogEntry[]>([]);
  const [catalogFailed, setCatalogFailed] = useState(false);
  const compareAbort = useRef<AbortController | null>(null);
  const sensitivityAbort = useRef<AbortController | null>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasResult = useRef(false);
  hasResult.current = state.result !== null;

  useEffect(() => {
    const controller = new AbortController();
    rotationsApi.cropCatalog(controller.signal)
      .then((c) => { setCatalog(c.entries); setCatalogFailed(false); })
      .catch(() => { if (!controller.signal.aborted) setCatalogFailed(true); });
    return () => {
      controller.abort();
      compareAbort.current?.abort();
      sensitivityAbort.current?.abort();
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  function buildRequest(): ScenarioAnalysisRequest {
    return {
      profile: buildProfile(state.form),
      horizon_years: buildHorizonYears(state.form),
      climate_scenarios: state.climateScenarios,
    };
  }

  async function runCompare(recompute: boolean) {
    const fieldErrors = validateProfileForm(state.form);
    setErrors(fieldErrors);
    if (Object.keys(fieldErrors).length > 0) return;

    compareAbort.current?.abort();
    const controller = new AbortController();
    compareAbort.current = controller;
    setRotationsState(recompute ? { recomputing: true, failure: '' } : { status: 'loading', failure: '' });
    try {
      const result = await rotationsApi.scenarios(buildRequest(), controller.signal);
      setRotationsState({ status: 'done', result, recomputing: false, failure: '' });
    } catch (err) {
      if (controller.signal.aborted) return;
      setRotationsState((s) => ({ status: recompute ? s.status : 'error', recomputing: false, failure: errorText(err, t) }));
    }
  }

  // Changing priorities or what-if climate flags must trigger a real backend recompute
  // (never a client-side re-score) once an initial comparison exists.
  useEffect(() => {
    if (!hasResult.current) return;
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => { void runCompare(true); }, RECOMPUTE_DEBOUNCE_MS);
    return () => { if (debounceTimer.current) clearTimeout(debounceTimer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.form.priorities, state.climateScenarios]);

  async function runSensitivity(criterionA: PriorityCriterion, criterionB: PriorityCriterion) {
    sensitivityAbort.current?.abort();
    const controller = new AbortController();
    sensitivityAbort.current = controller;
    setRotationsState({ sensitivityStatus: 'loading', sensitivityFailure: '' });
    try {
      const result = await rotationsApi.sensitivity(
        { base: buildRequest(), change: { change_type: 'PRIORITY_SWAP', criterion_a: criterionA, criterion_b: criterionB } },
        controller.signal,
      );
      setRotationsState({ sensitivityStatus: 'done', sensitivity: result });
    } catch (err) {
      if (controller.signal.aborted) return;
      setRotationsState({ sensitivityStatus: 'error', sensitivityFailure: errorText(err, t) });
    }
  }

  const result = state.result;
  const errorCount = Object.keys(errors).length;

  return (
    <>
      <PageHeader title={t('rot.title')} lead={t('rot.lead')} />

      {catalogFailed && <StatusMessage tone="partial" title={t('rot.catalog.unavailableTitle')}>{t('rot.catalog.unavailableBody')}</StatusMessage>}

      <section className="panel" aria-labelledby="rot-crop-heading">
        <div className="section-head">
          <h2 id="rot-crop-heading">{t('rot.crop.sectionTitle')}</h2>
          <p>{t('rot.crop.sectionHint')}</p>
        </div>
        <CropHistoryEditor rows={state.form.cropHistory} catalog={catalog} errors={errors}
          onChange={(rows) => setRotationsState((s) => ({ form: { ...s.form, cropHistory: rows } }))} />
      </section>

      <section className="panel" aria-labelledby="rot-cal-heading">
        <div className="section-head">
          <h2 id="rot-cal-heading">{t('rot.cal.sectionTitle')}</h2>
          <p>{t('rot.cal.sectionHint')}</p>
        </div>
        <CalendarEditor rows={state.form.calendar} catalog={catalog} errors={errors}
          onChange={(rows) => setRotationsState((s) => ({ form: { ...s.form, calendar: rows } }))} />
      </section>

      <section className="panel" aria-labelledby="rot-con-heading">
        <div className="section-head">
          <h2 id="rot-con-heading">{t('rot.con.sectionTitle')}</h2>
          <p>{t('rot.con.sectionHint')}</p>
        </div>
        <ConstraintsForm value={state.form.constraints} errors={errors}
          onChange={(c) => setRotationsState((s) => ({ form: { ...s.form, constraints: c } }))} />
      </section>

      <section className="panel" aria-labelledby="rot-pri-heading">
        <div className="section-head">
          <h2 id="rot-pri-heading">{t('rot.pri.sectionTitle')}</h2>
          <p>{t('rot.pri.sectionHint')}</p>
        </div>
        <PrioritiesEditor priorities={state.form.priorities} onChange={(p) => setRotationsState((s) => ({ form: { ...s.form, priorities: p } }))} />
        <Field label={t('rot.horizon')} inputMode="numeric" value={state.form.horizonYears} hint={t('rot.horizonHint')}
          error={errors.horizonYears ? t('rot.horizonError') : undefined}
          onChange={(e) => setRotationsState((s) => ({ form: { ...s.form, horizonYears: e.target.value } }))} />
      </section>

      <section className="panel" aria-labelledby="rot-clim-heading">
        <div className="section-head">
          <h2 id="rot-clim-heading">{t('rot.clim.sectionTitle')}</h2>
          <p>{t('rot.clim.sectionHint')}</p>
        </div>
        <ClimateScenarioEditor scenarios={state.climateScenarios} onChange={(s) => setRotationsState({ climateScenarios: s })} />
      </section>

      <div className="actions">
        <Button variant="primary" busy={state.status === 'loading'} onClick={() => runCompare(false)}>
          {state.status === 'loading' ? t('rot.action.comparing') : t('rot.action.compare')}
        </Button>
        {state.recomputing && <StatusMessage tone="loading" title={t('rot.action.recomputing')} />}
        {errorCount > 0 && <StatusMessage tone="error" title={t('rot.validation.title', { n: errorCount })} />}
      </div>

      {state.failure && (
        <StatusMessage tone={state.result ? 'partial' : 'error'} title={t('rot.status.errorTitle')} action={<Button onClick={() => runCompare(false)}>{t('state.retry')}</Button>}>
          <p>{state.failure}</p>
          {state.result && <p>{t('rot.status.staleBody')}</p>}
        </StatusMessage>
      )}
      {state.status === 'idle' && <StatusMessage tone="empty" title={t('rot.status.emptyTitle')}>{t('rot.status.emptyBody')}</StatusMessage>}

      {result && (
        <section className="panel" aria-labelledby="rot-results-heading">
          <div className="section-head">
            <h2 id="rot-results-heading">{t('rot.res.title')}</h2>
          </div>

          <StatusMessage
            tone={result.comparison.status === 'COMPARED' ? 'ok' : result.comparison.status === 'FEWER_ALTERNATIVES' ? 'partial' : 'error'}
            title={t(rotEnum(result.comparison.status))}
          >
            {result.comparison.explanation.map((e, i) => <p key={i}>{e}</p>)}
          </StatusMessage>

          {result.comparison.profile_issues.length > 0 && (
            <details>
              <summary>{t('rot.res.issuesTitle', { n: result.comparison.profile_issues.length })}</summary>
              <ul className="list-plain">
                {result.comparison.profile_issues.map((issue, i) => (
                  <li key={i}><span className="chip-meta">{t(rotEnum(issue.severity))}</span> {issue.message} {issue.consequence}</li>
                ))}
              </ul>
            </details>
          )}

          {result.comparison.strategies.length > 0 && (
            <div className="rotations">
              {result.comparison.strategies.map((s) => (
                <StrategyCard key={s.id} strategy={s}
                  position={result.ordering?.positions.find((p) => p.strategy_id === s.id) ?? null}
                  exposure={result.exposure.filter((e) => e.strategy_id === s.id)}
                  tradeOff={result.trade_offs.find((to) => to.strategy_id === s.id) ?? null} />
              ))}
            </div>
          )}

          {result.ordering && (
            <details>
              <summary>{t('rot.ord.title')}</summary>
              <p>{result.ordering.description}</p>
              <ul className="list-plain">
                {result.ordering.criteria_not_used.map((c, i) => <li key={i}>{t(rotEnum(c.criterion))}: {c.reason}</li>)}
                {result.ordering.steps.map((step, i) => <li key={`s-${i}`}>{step.explanation}</li>)}
                {result.ordering.adjacent_decisions.map((d, i) => <li key={`d-${i}`}>{d.explanation}</li>)}
                {result.ordering.notes.map((n, i) => <li key={`n-${i}`} className="muted">{n}</li>)}
              </ul>
            </details>
          )}

          {(result.comparison.candidate_screening.length > 0 || result.comparison.incompatible_transitions.length > 0) && (
            <details>
              <summary>{t('rot.res.screeningTitle')}</summary>
              <ul className="list-plain">
                {result.comparison.candidate_screening.map((c, i) => (
                  <li key={i}>{c.crop.crop_label}: <span className="chip-meta">{t(rotEnum(c.status))}</span> {c.reasons.map((r) => r.message).join(' ')}</li>
                ))}
                {result.comparison.incompatible_transitions.map((tr, i) => (
                  <li key={`i-${i}`}>{tr.from_crop} → {tr.to_crop}: {tr.message}</li>
                ))}
              </ul>
            </details>
          )}

          <details>
            <summary>{t('rot.sep.title')}</summary>
            <ul className="list-plain">
              {result.separation.map((sep, i) => <li key={i} className="muted">{sep.meaning}</li>)}
              {result.limitations.map((l, i) => <li key={`lim-${i}`} className="muted">{l}</li>)}
            </ul>
          </details>

          <section aria-labelledby="rot-sens-heading">
            <div className="section-head">
              <h3 id="rot-sens-heading">{t('rot.sens.title')}</h3>
            </div>
            <SensitivityPanel rankedPriorities={state.form.priorities} status={state.sensitivityStatus}
              failure={state.sensitivityFailure} result={state.sensitivity} onRun={runSensitivity} />
          </section>
        </section>
      )}
    </>
  );
}
