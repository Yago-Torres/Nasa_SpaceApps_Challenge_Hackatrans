import { useEffect, useMemo, useState } from 'react';
import { uncertaintyApi } from '../../../api/client';
import type { AnswerOrigin, UncertaintyAnswer, UncertaintyQuestion, UncertaintyReport } from '../../../api/types';
import { canEdit } from '../../../cases/model';
import { Button, EvidenceLabel, Field, StatusMessage, TextArea } from '../../../design/components';
import { useI18n } from '../../../i18n/I18n';
import { CaseGate } from '../CaseGate';
import { CaseTitleBlock } from '../CaseTitleBlock';
import { caseErrorText } from '../caseErrors';
import { useDates } from '../collaboration/format';

export function CaseUncertainty({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  return <CaseGate caseId={caseId} title={t('unc.title')}>{(c) => <>
    <CaseTitleBlock c={c} lead={t('unc.lead')} />
    <UncertaintyWorkspace caseId={caseId} canWrite={canEdit(c)} />
  </>}</CaseGate>;
}

function UncertaintyWorkspace({ caseId, canWrite }: { caseId: string; canWrite: boolean }) {
  const { t } = useI18n();
  const [report, setReport] = useState<UncertaintyReport | null>(null);
  const [answers, setAnswers] = useState<UncertaintyAnswer[]>([]);
  const [error, setError] = useState(''); const [reload, setReload] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    Promise.all([uncertaintyApi.report(caseId, c.signal), uncertaintyApi.answers(caseId, c.signal)]).then(([r, a]) => {
      setReport(r); setAnswers(a.items); setError('');
    }, (err) => { if (err?.name !== 'AbortError') setError(caseErrorText(err, t)); });
    return () => c.abort();
  }, [caseId, reload]); // eslint-disable-line react-hooks/exhaustive-deps
  const current = useMemo(() => new Map(answers.filter((a) => a.status === 'ANSWERED' || a.status === 'REVIEWED').map((a) => [a.question_id, a])), [answers]);
  return <section className="panel" aria-labelledby="unc-h">
    <div className="section-head"><h2 id="unc-h">{t('unc.questions')}</h2><p>{t('unc.questionsLead')}</p></div>
    {error && <StatusMessage tone="error" title={t('unc.error')} action={<Button onClick={() => setReload((n) => n + 1)}>{t('state.retry')}</Button>}>{error}</StatusMessage>}
    {!report && !error && <StatusMessage tone="loading" title={t('state.loading')} />}
    {report && <>
      <StatusMessage tone={report.prioritisation.status === 'NO_BASIS_TO_PRIORITISE' ? 'partial' : 'empty'} title={t(`unc.priority.${report.prioritisation.status}` as 'unc.priority.NO_OPEN_QUESTIONS')}>{report.prioritisation.statement}</StatusMessage>
      <dl className="review-list unc-summary"><div><dt>{t('unc.gaps')}</dt><dd>{report.summary.gaps}</dd></div><div><dt>{t('unc.open')}</dt><dd>{report.summary.open_questions}</dd></div><div><dt>{t('unc.notLocal')}</dt><dd>{report.summary.gaps_not_answerable_locally}</dd></div></dl>
      {report.questions.length === 0 ? <StatusMessage tone="empty" title={t('unc.none')} /> : <ol className="unc-questions">
        {report.questions.map((q) => <QuestionCard key={q.id} caseId={caseId} q={q} answer={current.get(q.id)} canWrite={canWrite} onChanged={() => setReload((n) => n + 1)} />)}
      </ol>}
      <details><summary>{t('unc.gapDetails', { n: report.gaps.length })}</summary><ul className="list-plain">{report.gaps.map((g) => <li key={g.id}><EvidenceLabel kind="MISSING_DATA" /> <b>{g.title}</b><p>{g.description}</p><p className="muted">{g.limitations.join(' ')}</p></li>)}</ul></details>
      <ul className="list-plain">{report.limitations.map((l, i) => <li key={i} className="muted">{l}</li>)}</ul>
    </>}
  </section>;
}

function QuestionCard({ caseId, q, answer, canWrite, onChanged }: { caseId: string; q: UncertaintyQuestion; answer?: UncertaintyAnswer; canWrite: boolean; onChanged: () => void }) {
  const { t } = useI18n(); const dates = useDates();
  const [value, setValue] = useState(''); const [unit, setUnit] = useState(''); const [method, setMethod] = useState(''); const [source, setSource] = useState('');
  const [origin, setOrigin] = useState<AnswerOrigin>('FARMER_REPORTED'); const [note, setNote] = useState(''); const [actionNote, setActionNote] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function run(action: () => Promise<unknown>) { setBusy(true); setError(''); try { await action(); onChanged(); } catch (err) { setError(caseErrorText(err, t)); } finally { setBusy(false); } }
  async function submit(e: React.FormEvent) { e.preventDefault(); if (!value.trim() || (origin === 'LOCAL_MEASUREMENT' && !method.trim())) return setError(t('review.required')); await run(() => uncertaintyApi.answer(caseId, q.id, { value_text: value.trim(), unit: unit.trim() || null, origin, method: method.trim() || null, source_reference: source.trim() || null, note: note.trim() || null, replaces_answer_id: answer?.id ?? null })); }
  const dismissed = q.resolution.status === 'DISMISSED';
  return <li className="unc-question">
    <article className="stack-tight">
      <header><span className="unc-position">{q.position ?? '—'}</span><div><h3>{q.question}</h3><p className="muted">{q.category} · {t(`unc.status.${q.resolution.status}` as 'unc.status.OPEN')}</p></div></header>
      <p>{q.why_it_matters}</p><p><b>{t('unc.measure')}</b> {q.measurement}</p>
      {q.would_change.length > 0 && <details><summary>{t('unc.couldChange', { n: q.would_change.length })}</summary><ul className="list-plain">{q.would_change.map((x) => <li key={`${x.target_type}-${x.target_id}`}><b>{x.label}</b>: {x.how}</li>)}</ul></details>}
      {answer && <div className="slip"><EvidenceLabel kind="FARMER_REPORTED" /><blockquote>{answer.value_text ?? `${answer.value_number} ${answer.unit ?? ''}`}</blockquote><p className="who">{answer.answered_by?.display_name ?? t('collab.deletedAccount')} · {dates.dateTime(answer.answered_at)} · {t(`unc.answer.${answer.status}` as 'unc.answer.ANSWERED')}</p>{answer.method && <p>{answer.method}</p>}{answer.review_note && <p className="muted">{answer.review_note}</p>}</div>}
      {answer?.can_review && <ReviewAnswer caseId={caseId} answer={answer} busy={busy} run={run} />}
      {canWrite && q.answerable_here && !dismissed && <form className="stack review-box" onSubmit={submit}>
        <TextArea label={answer ? t('unc.correctAnswer') : t('unc.answerLabel')} value={value} maxLength={5000} onChange={(e) => setValue(e.target.value)} />
        <div className="form-row form-row--2"><label className="field"><span>{t('unc.origin')}</span><span className="ctl"><select value={origin} onChange={(e) => setOrigin(e.target.value as AnswerOrigin)}>{(['FARMER_REPORTED', 'LOCAL_MEASUREMENT', 'FIELD_RECORD', 'ADVISOR_REPORT'] as AnswerOrigin[]).map((x) => <option key={x} value={x}>{t(`unc.origin.${x}` as 'unc.origin.FARMER_REPORTED')}</option>)}</select></span></label><Field label={t('unc.unit')} value={unit} maxLength={40} onChange={(e) => setUnit(e.target.value)} /></div>
        <Field label={t('unc.method')} hint={origin === 'LOCAL_MEASUREMENT' ? t('unc.methodRequired') : undefined} value={method} maxLength={2000} onChange={(e) => setMethod(e.target.value)} /><Field label={t('unc.source')} value={source} maxLength={1000} onChange={(e) => setSource(e.target.value)} /><TextArea label={t('review.note')} value={note} onChange={(e) => setNote(e.target.value)} />
        <Button type="submit" busy={busy}>{answer ? t('unc.saveCorrection') : t('unc.saveAnswer')}</Button>
      </form>}
      {canWrite && <div className="review-box stack"><Field label={t('unc.actionNote')} value={actionNote} maxLength={5000} onChange={(e) => setActionNote(e.target.value)} /><Button variant="text" disabled={!actionNote.trim() || busy} onClick={() => run(() => dismissed ? uncertaintyApi.reopen(caseId, q.id, actionNote.trim()) : uncertaintyApi.dismiss(caseId, q.id, actionNote.trim()))}>{dismissed ? t('unc.reopen') : t('unc.dismiss')}</Button></div>}
      {q.answer_route && <StatusMessage tone="pending" title={t('unc.analysisTask')}>{q.answer_route}</StatusMessage>}
      {error && <StatusMessage tone="error" title={t('unc.actionError')}>{error}</StatusMessage>}
    </article>
  </li>;
}

function ReviewAnswer({ caseId, answer, busy, run }: { caseId: string; answer: UncertaintyAnswer; busy: boolean; run: (a: () => Promise<unknown>) => Promise<void> }) {
  const { t } = useI18n(); const [note, setNote] = useState(''); const [decision, setDecision] = useState<'REVIEWED' | 'REJECTED'>('REVIEWED');
  return <div className="review-box stack"><h4>{t('unc.reviewAnswer')}</h4><label className="field"><span>{t('review.decision')}</span><span className="ctl"><select value={decision} onChange={(e) => setDecision(e.target.value as typeof decision)}><option value="REVIEWED">{t('unc.answer.REVIEWED')}</option><option value="REJECTED">{t('unc.answer.REJECTED')}</option></select></span></label><TextArea label={t('review.note')} value={note} onChange={(e) => setNote(e.target.value)} /><Button disabled={!note.trim()} busy={busy} onClick={() => run(() => uncertaintyApi.reviewAnswer(caseId, answer.id, { version: answer.version, decision, note: note.trim() }))}>{t('review.submit')}</Button></div>;
}
