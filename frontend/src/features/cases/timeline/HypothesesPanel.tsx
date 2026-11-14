import { useEffect, useState, type FormEvent } from 'react';
import { useI18n } from '../../../i18n/I18n';
import type { MessageKey } from '../../../i18n/messages';
import { Button, EvidenceLabel, StatusMessage, TextArea, type EvidenceKind } from '../../../design/components';
import { api } from '../../../api/client';
import type { EvaluationStatus, EvidenceRef, HypothesisTemplateView, HypothesisView } from '../../../api/types';
import { caseRepository } from '../../../cases/repository';
import { caseErrorText } from '../caseErrors';

const STATUS_LABEL: Record<string, MessageKey> = {
  OPEN: 'tl.hypStatus.OPEN', COMPATIBLE: 'tl.hypStatus.COMPATIBLE',
  CONTRADICTED: 'tl.hypStatus.CONTRADICTED', NOT_EVALUABLE: 'tl.hypStatus.NOT_EVALUABLE',
};
const EVALUABLE: EvaluationStatus[] = ['OPEN', 'COMPATIBLE', 'CONTRADICTED', 'NOT_EVALUABLE'];
/** Evidence kinds the ABB-10 timeline actually places as an event (resolve_evidence in
 * hypotheses.py): only observations/anomalies. Literature claims and local answers have no
 * timeline event to jump to, so their items stay plain text here. */
const INSPECTABLE: EvidenceRef['evidence_type'][] = ['ANOMALY', 'OBSERVATION'];

function EvidenceList({ ids, refs, onInspect }: { ids: string[]; refs: Map<string, EvidenceRef>; onInspect?: (id: string) => void }) {
  const { t } = useI18n();
  if (!ids.length) return <span className="muted">{t('tl.hyp.none')}</span>;
  return (
    <ul className="list-plain">
      {ids.map((id) => {
        const ref = refs.get(id);
        if (!ref) return <li key={id} className="muted">{t('evidence.MISSING_DATA')}</li>;
        // Unreviewed literature is never shown as the reviewed LITERATURE_REVIEWED kind (same
        // rule as the Evidence screen's "Metadata only" chip): ref.kind is a backend string,
        // only its known EvidenceKind values go through the shared symbol+label component.
        const symbol = ref.kind === 'LITERATURE_METADATA'
          ? <span className="chip-meta">{t('evidence.metadataOnly')}</span>
          : <EvidenceLabel kind={ref.kind as EvidenceKind} />;
        const body = <>{symbol} {ref.label}{!ref.active && ` (${t('tl.hyp.superseded')})`}</>;
        return (
          <li key={id}>
            {onInspect && INSPECTABLE.includes(ref.evidence_type) ? (
              <button type="button" className="tl-table-select" onClick={() => onInspect(id)}>{body}</button>
            ) : body}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Rival hypotheses (components.md §10): Explanation · Supports it · Argues against · Would
 * settle it, plus the human-set Status (never a confidence score). OWNER/EDITOR create;
 * OWNER/EDITOR/REVIEWER evaluate — gated by `canCreate`/`canEvaluate`, computed by the caller
 * from the case's role, status and archived flag (same rule as the rest of the case API).
 */
export function HypothesesPanel({
  caseId, hypotheses, listLimitations, canCreate, canEvaluate, onInspectEvidence, onChange,
}: {
  caseId: string;
  hypotheses: HypothesisView[];
  /** The list envelope's own limitations (e.g. "a hypothesis is not a demonstrated cause"),
   * never dropped (frontend/AGENTS.md: every limitation the API sends is rendered). */
  listLimitations: string[];
  canCreate: boolean;
  canEvaluate: boolean;
  onInspectEvidence?: (id: string) => void;
  onChange: () => void;
}) {
  const { t } = useI18n();
  const repo = caseRepository();
  const [templates, setTemplates] = useState<HypothesisTemplateView[] | null>(null);
  const [templateError, setTemplateError] = useState('');
  const [templateReload, setTemplateReload] = useState(0);
  const [showAdd, setShowAdd] = useState(false);
  const [statement, setStatement] = useState('');
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const [evaluating, setEvaluating] = useState<{ id: string; status: EvaluationStatus; note: string } | null>(null);
  const [evalError, setEvalError] = useState('');

  useEffect(() => {
    if (!showAdd || templates) return;
    let live = true;
    setTemplateError('');
    api.hypothesisTemplates().then(
      (cat) => { if (live) setTemplates(cat.items); },
      (err) => {
        if (!live) return;
        setTemplates([]);
        setTemplateError(caseErrorText(err, t));
      },
    );
    return () => { live = false; };
  }, [showAdd, templateReload]); // eslint-disable-line react-hooks/exhaustive-deps

  const addedCodes = new Set(hypotheses.map((h) => h.template_code).filter((c): c is string => c !== null));
  const refs = new Map(hypotheses.flatMap((h) => h.evidence.map((e) => [e.id, e] as const)));

  async function addTemplate(code: string) {
    setBusy(true);
    setFormError('');
    try {
      await repo.addHypothesisTemplates(caseId, [code]);
      onChange();
    } catch (err) {
      setFormError(caseErrorText(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function submitCustom(e: FormEvent) {
    e.preventDefault();
    if (!statement.trim()) return;
    setBusy(true);
    setFormError('');
    try {
      await repo.createHypothesis(caseId, { statement: statement.trim() });
      setStatement('');
      onChange();
    } catch (err) {
      setFormError(caseErrorText(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function submitEvaluation(h: HypothesisView) {
    if (!evaluating || evaluating.id !== h.id) return;
    setEvalError('');
    try {
      await repo.evaluateHypothesis(caseId, h.id, {
        version: h.version, status: evaluating.status,
        note: evaluating.status === 'OPEN' ? null : evaluating.note.trim() || null,
      });
      setEvaluating(null);
      onChange();
    } catch (err) {
      setEvalError(caseErrorText(err, t));
    }
  }

  return (
    <section className="panel" aria-labelledby="tl-hyp-h">
      <div className="section-head">
        <h2 id="tl-hyp-h">{t('tl.hyp.title')}</h2>
        <p>{t('tl.hyp.lead')}</p>
      </div>

      {listLimitations.length > 0 && (
        <ul className="list-plain muted">{listLimitations.map((l) => <li key={l}>{l}</li>)}</ul>
      )}

      {hypotheses.length === 0 && <StatusMessage tone="empty" title={t('tl.hyp.emptyTitle')}>{t('tl.hyp.emptyBody')}</StatusMessage>}

      {hypotheses.length > 0 && (
        <div className="table-wrap">
          <table className="data hyp-table">
            <caption className="sr-only">{t('tl.hyp.title')}</caption>
            <thead>
              <tr>
                <th scope="col">{t('tl.hyp.colExplanation')}</th>
                <th scope="col">{t('tl.hyp.colStatus')}</th>
                <th scope="col">{t('tl.hyp.colSupports')}</th>
                <th scope="col">{t('tl.hyp.colAgainst')}</th>
                <th scope="col">{t('tl.hyp.colSettle')}</th>
              </tr>
            </thead>
            <tbody>
              {hypotheses.map((h) => {
                // Each hypothesis's own limitations beyond the list-level ones shown above
                // (e.g. TEMPLATE_LIMITATION, or a user's own caveat) — never dropped.
                const ownLimitations = h.limitations.filter((l) => !listLimitations.includes(l));
                return (
                <tr key={h.id}>
                  <th scope="row">
                    <EvidenceLabel kind="HYPOTHESIS" />
                    <p>{h.title ?? h.statement}</p>
                    {h.title && <p className="muted">{h.statement}</p>}
                    {ownLimitations.map((l) => <p key={l} className="muted">{l}</p>)}
                  </th>
                  <td data-label={t('tl.hyp.colStatus')}>
                    <p>{t(STATUS_LABEL[h.status] ?? 'tl.hypStatus.OPEN')}</p>
                    {h.evaluation_note && <p className="muted">{h.evaluation_note}</p>}
                    {canEvaluate && (
                      evaluating?.id === h.id ? (
                        <div className="tl-eval-form">
                          <label className="sr-only" htmlFor={`eval-status-${h.id}`}>{t('tl.hyp.colStatus')}</label>
                          <select id={`eval-status-${h.id}`} value={evaluating.status}
                            onChange={(e) => setEvaluating({ ...evaluating, status: e.target.value as EvaluationStatus })}>
                            {EVALUABLE.map((s) => <option key={s} value={s}>{t(STATUS_LABEL[s])}</option>)}
                          </select>
                          {evaluating.status !== 'OPEN' && (
                            <TextArea label={t('tl.hyp.noteLabel')} value={evaluating.note}
                              onChange={(e) => setEvaluating({ ...evaluating, note: e.target.value })} />
                          )}
                          {evalError && <p className="err">{evalError}</p>}
                          <div className="actions">
                            <Button variant="primary" onClick={() => submitEvaluation(h)}>{t('tl.hyp.saveStatus')}</Button>
                            <Button variant="text" onClick={() => setEvaluating(null)}>{t('cases.cancel')}</Button>
                          </div>
                        </div>
                      ) : (
                        <Button variant="text" onClick={() => { setEvaluating({ id: h.id, status: h.status as EvaluationStatus, note: h.evaluation_note ?? '' }); setEvalError(''); }}>
                          {t('tl.hyp.changeStatus')}
                        </Button>
                      )
                    )}
                  </td>
                  <td data-label={t('tl.hyp.colSupports')}><EvidenceList ids={h.supporting_evidence_ids} refs={refs} onInspect={onInspectEvidence} /></td>
                  <td data-label={t('tl.hyp.colAgainst')}><EvidenceList ids={h.contradicting_evidence_ids} refs={refs} onInspect={onInspectEvidence} /></td>
                  <td data-label={t('tl.hyp.colSettle')}>
                    {h.missing_evidence.length === 0 && h.verification_questions.length === 0 ? (
                      <span className="muted">{t('tl.hyp.none')}</span>
                    ) : (
                      <ul className="list-plain">
                        {h.missing_evidence.map((m) => <li key={m}>{m}</li>)}
                        {h.verification_questions.map((q) => <li key={q.question}><b>{q.question}</b> — {q.why_it_matters}</li>)}
                      </ul>
                    )}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {canCreate && (
        <div className="actions">
          {/* Primary only in the empty, collapsed state: once the disclosure is open, the
              custom-hypothesis submit below is the view's one primary action (design system
              D3: one yellow-green action per view). */}
          <Button variant={hypotheses.length || showAdd ? 'secondary' : 'primary'} aria-expanded={showAdd} aria-controls="tl-hyp-add" onClick={() => setShowAdd((s) => !s)}>
            {showAdd ? t('tl.hyp.hideAdd') : t('tl.hyp.showAdd')}
          </Button>
        </div>
      )}

      {canCreate && showAdd && (
        <div id="tl-hyp-add" className="review-block">
          {formError && <StatusMessage tone="error" title={formError} />}
          <div>
            <p className="muted">{t('tl.hyp.templatesLead')}</p>
            {templateError ? (
              <StatusMessage tone="error" title={t('tl.hyp.templatesError')}
                action={<Button variant="secondary" onClick={() => { setTemplates(null); setTemplateReload((n) => n + 1); }}>{t('state.retry')}</Button>}>
                {templateError}
              </StatusMessage>
            ) : templates === null ? (
              <StatusMessage tone="loading" title={t('state.loading')} />
            ) : (
              <ul className="list-plain">
                {templates.filter((tpl) => !addedCodes.has(tpl.code)).map((tpl) => (
                  <li key={tpl.code}>
                    <Button variant="secondary" busy={busy} onClick={() => addTemplate(tpl.code)}>{t('tl.hyp.addTemplate', { title: tpl.title })}</Button>
                  </li>
                ))}
                {templates.every((tpl) => addedCodes.has(tpl.code)) && <li className="muted">{t('tl.hyp.allTemplatesAdded')}</li>}
              </ul>
            )}
          </div>
          <form onSubmit={submitCustom}>
            <TextArea label={t('tl.hyp.customLabel')} hint={t('tl.hyp.customHint')} value={statement} onChange={(e) => setStatement(e.target.value)} />
            <div className="actions">
              <Button type="submit" variant="primary" busy={busy} disabled={!statement.trim()}>{t('tl.hyp.addCustom')}</Button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}
