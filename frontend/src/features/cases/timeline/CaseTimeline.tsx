import { useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from '../../../i18n/I18n';
import type { MessageKey } from '../../../i18n/messages';
import { Button, ButtonLink, EvidenceLabel, PageHeader, SourceLabel, StatusMessage, type SourceRow } from '../../../design/components';
import { hrefFor } from '../../../app/routes';
import { useSession } from '../../../api/session';
import type { HypothesisList, Timeline, TimelineEvent, TimelineKind } from '../../../api/types';
import { canEdit, type IncidentCase } from '../../../cases/model';
import { caseRepository } from '../../../cases/repository';
import { AuthPanel } from '../../account/AuthPanel';
import { CaseTitleBlock } from '../CaseTitleBlock';
import { caseErrorText, isStorageUnavailable, isUnauthorized } from '../caseErrors';
import { TimelineChart } from './TimelineChart';
import { HypothesesPanel } from './HypothesesPanel';

const LAYER_ORDER: TimelineKind[] = ['OBSERVED', 'FARMER_REPORTED', 'HYPOTHESIS', 'MISSING_DATA'];
const LAYER_LABEL: Record<TimelineKind, MessageKey> = {
  OBSERVED: 'evidence.OBSERVED', FARMER_REPORTED: 'evidence.FARMER_REPORTED',
  HYPOTHESIS: 'evidence.HYPOTHESIS', MISSING_DATA: 'evidence.MISSING_DATA',
};
const SEVERITY_LABEL: Record<string, MessageKey> = {
  WITHIN_REFERENCE_SPREAD: 'tl.severity.WITHIN_REFERENCE_SPREAD', MODERATE_DEPARTURE: 'tl.severity.MODERATE_DEPARTURE',
  LARGE_DEPARTURE: 'tl.severity.LARGE_DEPARTURE', NOT_CLASSIFIED: 'tl.severity.NOT_CLASSIFIED',
};
const EVALUATOR_ROLES = new Set(['OWNER', 'EDITOR', 'REVIEWER']);
const OPEN_STATUSES = new Set(['DRAFT', 'INVESTIGATING']);

type LoadState =
  | { status: 'loading' }
  | { status: 'missing' }
  | { status: 'unavailable' }
  | { status: 'error'; message: string }
  | { status: 'ready'; case: IncidentCase; timeline: Timeline; hypotheses: HypothesisList };

/**
 * ABB-22 forensic timeline + hypotheses for one case (the "Timeline" tab opened from
 * `features/Cases.tsx`). Loads its own data independently of the "Details" tab
 * (IncidentWizard): same case-access rules, but this is read-mostly forensic evidence, not
 * the wizard's editable form state. Only renders for a case the signed-in viewer can access
 * (ADR-0004): the case API returns 404 for both "doesn't exist" and "no access", exactly as
 * `cases/repository.ts` already treats it elsewhere.
 */
export function CaseTimeline({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  const session = useSession();
  const repo = caseRepository();
  const [load, setLoad] = useState<LoadState>({ status: 'loading' });
  const [reloadToken, setReloadToken] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const everSignedIn = useRef(!!session);
  if (session) everSignedIn.current = true;

  const reload = useCallback(() => setReloadToken((n) => n + 1), []);

  useEffect(() => {
    if (!session) return;
    let live = true;
    setLoad({ status: 'loading' });
    Promise.all([repo.get(caseId), repo.getTimeline(caseId), repo.getHypotheses(caseId)]).then(
      ([c, timeline, hypotheses]) => {
        if (!live) return;
        if (!c) {
          setLoad({ status: 'missing' });
          return;
        }
        setLoad({ status: 'ready', case: c, timeline, hypotheses });
      },
      (err) => {
        if (!live || isUnauthorized(err)) return; // signed out: the sign-in panel shows
        setLoad(isStorageUnavailable(err) ? { status: 'unavailable' } : { status: 'error', message: caseErrorText(err, t) });
      },
    );
    return () => {
      live = false;
    };
  }, [caseId, session, reloadToken]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!session) {
    return (
      <>
        <PageHeader title={t('tl.title')} />
        <AuthPanel primary notice={everSignedIn.current ? t('auth.sessionEnded') : undefined} />
      </>
    );
  }

  if (load.status === 'missing') {
    return (
      <>
        <PageHeader title={t('tl.title')} />
        <StatusMessage tone="error" title={t('cases.notFound')} action={<ButtonLink href={hrefFor('cases')}>{t('nav.cases')}</ButtonLink>} />
      </>
    );
  }
  if (load.status === 'unavailable') {
    return (
      <>
        <PageHeader title={t('tl.title')} />
        <StatusMessage tone="error" title={t('cases.storageUnavailable')}>{t('cases.storageUnavailableBody')}</StatusMessage>
      </>
    );
  }
  if (load.status === 'error') {
    return (
      <>
        <PageHeader title={t('tl.title')} />
        <StatusMessage tone="error" title={t('tl.errorTitle')} action={<Button onClick={reload}>{t('state.retry')}</Button>}>
          {load.message}
        </StatusMessage>
      </>
    );
  }
  if (load.status === 'loading') {
    return (
      <>
        <PageHeader title={t('tl.title')} />
        <StatusMessage tone="loading" title={t('state.loading')} />
      </>
    );
  }

  const { timeline, hypotheses, case: c } = load;
  const events = timeline.events;
  const selectedEvent = events.find((e) => e.id === selected) ?? null;
  const inspectEvidence = (evidenceId: string) => {
    // An anomaly is itself a timeline event, while an observation is represented by its
    // associated anomaly event (backend/api/timeline.py::to_event_ids). Resolve both wire IDs
    // here so clicking either kind of linked evidence opens the provenance panel.
    const event = events.find((e) => e.id === evidenceId
      || e.provenance.anomaly_id === evidenceId
      || e.provenance.observation_id === evidenceId);
    setSelected(event?.id ?? null);
  };
  const server = c.server;
  const canCreateHypotheses = canEdit(c); // OWNER/EDITOR, DRAFT/INVESTIGATING, not archived (cases/model.ts)
  const canEvaluate = !!server && EVALUATOR_ROLES.has(server.myRole) && OPEN_STATUSES.has(server.status) && !server.archived;

  return (
    <>
      {/* Signature title block (components.md §5), reused read-only from the Details tab's
          component so every case screen opens the same way (design-system rule D5). */}
      <CaseTitleBlock c={c} lead={t('tl.lead')} />

      <section className="panel" aria-labelledby="tl-legend-h">
        <div className="section-head">
          <h2 id="tl-legend-h">{t('tl.legendTitle')}</h2>
          <p>{t('tl.legendLead')}</p>
        </div>
        <ul className="legend">
          {LAYER_ORDER.map((kind) => {
            const layer = timeline.layers.find((l) => l.kind === kind);
            return (
              <li key={kind}>
                <EvidenceLabel kind={kind} detail={String(layer?.event_count ?? 0)} />
                <p>{layer?.description}</p>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="panel" aria-labelledby="tl-chart-h">
        <div className="section-head">
          <h2 id="tl-chart-h">{t('tl.chartSectionTitle')}</h2>
          <p>{t('tl.chartLead')}</p>
        </div>
        <TimelineChart events={events} incidentStart={timeline.incident_start} incidentEnd={timeline.incident_end}
          selectedId={selected} onSelect={setSelected} />
      </section>

      {selectedEvent && <EventDetail event={selectedEvent} onClose={() => setSelected(null)} />}

      <section className="panel" aria-labelledby="tl-limits-h">
        <h2 id="tl-limits-h" className="sr-only">{t('tl.limitationsTitle')}</h2>
        <ul className="list-plain">
          {timeline.limitations.map((l) => <li key={l}>{l}</li>)}
        </ul>
      </section>

      <HypothesesPanel caseId={caseId} hypotheses={hypotheses.items} listLimitations={hypotheses.limitations}
        canCreate={canCreateHypotheses} canEvaluate={canEvaluate} onInspectEvidence={inspectEvidence} onChange={reload} />
    </>
  );
}

/** Click-through provenance for one timeline event: raw value, reference window, QA and the
 * full source manifest, in the same herbarium-label shape as Investigation's SourceLabel. */
function EventDetail({ event, onClose }: { event: TimelineEvent; onClose: () => void }) {
  const { t, num } = useI18n();
  const p = event.provenance;
  const missing = <EvidenceLabel kind="MISSING_DATA" detail={t('src.notReturned')} />;
  const rows: SourceRow[] = [
    { label: t('tl.detail.period'), value: `${event.start ?? t('tl.undated')} – ${event.end ?? t('tl.undated')}` },
    { label: t('tl.detail.description'), value: event.description },
    { label: t('tl.detail.sourceDescription'), value: p.description },
  ];
  if (event.observed) {
    const o = event.observed;
    rows.push(
      { label: t('src.parameters'), value: o.source_parameter, mono: true },
      { label: t('tl.detail.value'), value: o.value === null ? t('inv.noData') : `${num(o.value, { digits: 2 })} ${o.units}`, mono: true },
      {
        label: t('tl.detail.reference'),
        value: o.reference_value === null ? t('inv.noData')
          : `${num(o.reference_value, { digits: 2 })} ${o.units} (${o.reference_start}–${o.reference_end}, n=${o.reference_sample_count})`,
      },
      { label: t('tl.detail.anomaly'), value: o.anomaly === null ? t('inv.noData') : `${num(o.anomaly, { digits: 2, signed: true })} ${o.units}`, mono: true },
    );
  }
  if (event.departure) {
    const d = event.departure;
    rows.push({
      label: t('tl.detail.severity'),
      value: `${t(SEVERITY_LABEL[d.severity] ?? 'tl.severity.NOT_CLASSIFIED')}` +
        (d.departure_in_reference_sd !== null ? ` (${num(d.departure_in_reference_sd, { digits: 2, signed: true })} SD)` : ''),
    });
  }
  if (event.data_quality) {
    const q = event.data_quality;
    rows.push(
      { label: t('tl.detail.quality'), value: t(`tl.quality.${q.status}` as MessageKey) },
      { label: t('tl.detail.referenceQuality'), value: t(`tl.referenceQuality.${q.reference_status}` as MessageKey) },
      { label: t('tl.detail.qualityFlags'), value: q.flags.length ? q.flags.join(', ') : t('tl.detail.none') },
    );
    if (q.reason) rows.push({ label: t('tl.detail.qualityReason'), value: q.reason });
  }
  if (event.crops && event.crops.length) {
    rows.push({ label: t('tl.detail.crops'), value: event.crops.join(', ') });
  }
  if (event.hypothesis) {
    rows.push({ label: t('tl.hyp.colStatus'), value: event.hypothesis.status });
  }
  rows.push(
    { label: t('tl.detail.provider'), value: p.provider ?? missing },
    { label: t('src.dataset'), value: p.dataset ?? missing },
    { label: t('tl.detail.datasetVersion'), value: p.dataset_version ?? missing },
    { label: t('tl.detail.sourceUri'), value: p.source_uri
      ? <a href={p.source_uri} target="_blank" rel="noreferrer">{p.source_uri}</a>
      : missing },
    { label: t('src.resolution'), value: p.spatial_resolution ? p.spatial_resolution.description : missing },
    { label: t('tl.detail.temporalResolution'), value: p.temporal_resolution ? p.temporal_resolution.description : missing },
    { label: t('src.retrieved'), value: p.retrieved_at ?? missing },
    { label: t('src.checksum'), value: p.checksum_sha256 ? <span className="mono">{p.checksum_sha256.slice(0, 16)}…</span> : missing },
    { label: t('tl.detail.processingVersion'), value: p.processing_version ?? missing, mono: true },
  );
  return (
    <section className="panel" aria-labelledby="tl-detail-h">
      <div className="panel-head">
        <h2 id="tl-detail-h">{t('tl.detailTitle')}</h2>
        <Button variant="text" onClick={onClose}>{t('tl.detailClose')}</Button>
      </div>
      <SourceLabel name={event.title} kind={event.kind} rows={rows} limitations={event.limitations.join(' ')} />
    </section>
  );
}
