import { useEffect, useState } from 'react';
import { evidenceApi } from '../../../api/client';
import type {
  AccessBasis, ClaimReviewStatus, ClaimView, ConclusionList, DisagreementStatus, DisagreementView,
  EdgeList, EvidenceBasis, EvidenceGraph, GraphEdge, GraphNode,
} from '../../../api/types';
import { Button, Field, StatusMessage, TextArea } from '../../../design/components';
import { useI18n } from '../../../i18n/I18n';
import { caseErrorText } from '../caseErrors';
import { useEnum } from './labels';

const decisions: Exclude<ClaimReviewStatus, 'PENDING'>[] = ['ACCEPTED', 'CHANGES_REQUESTED', 'REJECTED'];
const access: AccessBasis[] = ['OPEN_ACCESS_LICENSE', 'PUBLISHER_FREE_TO_READ', 'INSTITUTIONAL_SUBSCRIPTION', 'AUTHOR_PROVIDED_COPY'];

export function ClaimReviewForm({ caseId, claim, onDone }: { caseId: string; claim: ClaimView; onDone: () => void }) {
  const { t } = useI18n();
  const toEnum = useEnum();
  const [open, setOpen] = useState(false);
  const [decision, setDecision] = useState<Exclude<ClaimReviewStatus, 'PENDING'>>('CHANGES_REQUESTED');
  const [note, setNote] = useState('');
  const [basis, setBasis] = useState<EvidenceBasis>('FULL_TEXT');
  const [accessBasis, setAccessBasis] = useState<AccessBasis>('OPEN_ACCESS_LICENSE');
  const [license, setLicense] = useState('');
  const [locator, setLocator] = useState('');
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!claim.can_review) return null;
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!note.trim() || !locator.trim() || (basis === 'FULL_TEXT' && !license.trim()) || (decision === 'ACCEPTED' && basis !== 'FULL_TEXT')) return setError(t('review.required'));
    setBusy(true); setError('');
    try {
      await evidenceApi.reviewClaim(caseId, claim.id, {
        version: claim.version, decision, note: note.trim(),
        source_consulted: { basis, access_basis: accessBasis, license: license.trim() || null, locator: locator.trim(), consulted_url: url.trim() || null },
      });
      setOpen(false); onDone();
    } catch (err) { setError(caseErrorText(err, t)); } finally { setBusy(false); }
  }
  return (
    <div className="review-box">
      <Button variant="text" aria-expanded={open} onClick={() => setOpen((v) => !v)}>{t('review.claim.open')}</Button>
      {open && <form className="stack" onSubmit={submit}>
        <div className="form-row form-row--2">
          <Select label={t('review.decision')} value={decision} onChange={(v) => setDecision(v as typeof decision)} options={decisions.map((v) => [v, toEnum('review', v)])} />
          <Select label={t('review.basis')} value={basis} onChange={(v) => setBasis(v as EvidenceBasis)} options={(['ABSTRACT', 'FULL_TEXT'] as EvidenceBasis[]).map((v) => [v, toEnum('basis', v)])} />
          <Select label={t('review.access')} value={accessBasis} onChange={(v) => setAccessBasis(v as AccessBasis)} options={access.map((v) => [v, toEnum('access', v)])} />
          <Field label={t('review.locator')} value={locator} maxLength={300} onChange={(e) => setLocator(e.target.value)} />
          <Field label={t('review.license')} value={license} maxLength={500} onChange={(e) => setLicense(e.target.value)} />
          <Field label={t('review.url')} type="url" value={url} maxLength={2000} onChange={(e) => setUrl(e.target.value)} />
        </div>
        <TextArea label={t('review.note')} value={note} maxLength={5000} onChange={(e) => setNote(e.target.value)} />
        {decision === 'ACCEPTED' && basis !== 'FULL_TEXT' && <StatusMessage tone="partial" title={t('review.fullTextRequired')} />}
        {error && <StatusMessage tone="error" title={t('review.error')}>{error}</StatusMessage>}
        <div className="actions"><Button type="submit" busy={busy}>{t('review.submit')}</Button><Button variant="text" onClick={() => setOpen(false)}>{t('cases.cancel')}</Button></div>
      </form>}
    </div>
  );
}

export function DisagreementReviewForm({ caseId, item, onDone }: { caseId: string; item: DisagreementView; onDone: () => void }) {
  const { t } = useI18n(); const toEnum = useEnum();
  const [decision, setDecision] = useState<Exclude<DisagreementStatus, 'CANDIDATE'>>('INCONCLUSIVE');
  const [note, setNote] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  if (!item.can_review) return null;
  async function submit(e: React.FormEvent) {
    e.preventDefault(); if (!note.trim()) return setError(t('review.required'));
    setBusy(true); setError('');
    try { await evidenceApi.reviewDisagreement(caseId, item.id, { decision, note: note.trim(), claim_a_version: item.claim_a.claim_version, claim_b_version: item.claim_b.claim_version }); onDone(); }
    catch (err) { setError(caseErrorText(err, t)); } finally { setBusy(false); }
  }
  return <form className="review-box stack" onSubmit={submit}>
    <h4>{t('review.disagreement.title')}</h4>
    <Select label={t('review.decision')} value={decision} onChange={(v) => setDecision(v as typeof decision)} options={(['CONFIRMED_CONTRADICTION', 'NOT_COMPARABLE', 'INCONCLUSIVE'] as const).map((v) => [v, toEnum('dis', v)])} />
    <TextArea label={t('review.note')} value={note} maxLength={5000} onChange={(e) => setNote(e.target.value)} />
    {!item.both_claims_reviewed && decision === 'CONFIRMED_CONTRADICTION' && <StatusMessage tone="partial" title={t('review.bothClaimsRequired')} />}
    {error && <StatusMessage tone="error" title={t('review.error')}>{error}</StatusMessage>}
    <div className="actions"><Button type="submit" busy={busy}>{t('review.submit')}</Button></div>
  </form>;
}

export function GraphWorkflowSection({ caseId, canWrite, refreshKey, onChanged }: { caseId: string; canWrite: boolean; refreshKey: number; onChanged: () => void }) {
  const { t } = useI18n(); const toEnum = useEnum();
  const [graph, setGraph] = useState<EvidenceGraph | null>(null); const [conclusions, setConclusions] = useState<ConclusionList | null>(null); const [edges, setEdges] = useState<EdgeList | null>(null);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const [statement, setStatement] = useState(''); const [limits, setLimits] = useState(''); const [support, setSupport] = useState(''); const [supportNote, setSupportNote] = useState('');
  const [from, setFrom] = useState(''); const [to, setTo] = useState(''); const [relation, setRelation] = useState<'SUPPORTS' | 'CONTRADICTS' | 'LIMITS' | 'ADDRESSES'>('SUPPORTS'); const [edgeNote, setEdgeNote] = useState('');
  useEffect(() => {
    const c = new AbortController();
    Promise.all([evidenceApi.graph(caseId, c.signal), evidenceApi.conclusions(caseId, c.signal), evidenceApi.edges(caseId, c.signal)]).then(([g, cs, es]) => {
      setGraph(g); setConclusions(cs); setEdges(es); setError('');
    }, (err) => { if (err?.name !== 'AbortError') setError(caseErrorText(err, t)); });
    return () => c.abort();
  }, [caseId, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const nodes = graph?.nodes.filter((n) => n.linkable) ?? [];
  async function createConclusion(e: React.FormEvent) {
    e.preventDefault(); const ls = lines(limits);
    if (!statement.trim() || !support || !supportNote.trim() || !ls.length) return setError(t('review.required'));
    setBusy(true); setError('');
    try { await evidenceApi.createConclusion(caseId, { statement: statement.trim(), limitations: ls, supporting: [{ node_id: support, note: supportNote.trim() }] }); setStatement(''); setLimits(''); setSupport(''); setSupportNote(''); onChanged(); }
    catch (err) { setError(caseErrorText(err, t)); } finally { setBusy(false); }
  }
  async function createEdge(e: React.FormEvent) {
    e.preventDefault(); if (!from || !to || !edgeNote.trim()) return setError(t('review.required'));
    setBusy(true); setError(''); try { await evidenceApi.createEdge(caseId, { from, to, relation, note: edgeNote.trim() }); setEdgeNote(''); onChanged(); }
    catch (err) { setError(caseErrorText(err, t)); } finally { setBusy(false); }
  }
  async function review(kind: 'conclusion' | 'edge', id: string, version: number, decision: 'ACCEPTED' | 'CHANGES_REQUESTED' | 'REJECTED', note: string) {
    setBusy(true); setError(''); try { kind === 'conclusion' ? await evidenceApi.reviewConclusion(caseId, id, { version, decision, note }) : await evidenceApi.reviewEdge(caseId, id, { version, decision, note }); onChanged(); }
    catch (err) { setError(caseErrorText(err, t)); } finally { setBusy(false); }
  }
  return <section className="panel" aria-labelledby="graph-work-h">
    <div className="section-head"><h2 id="graph-work-h">{t('graphWork.title')}</h2><p>{t('graphWork.lead')}</p></div>
    {error && <StatusMessage tone="error" title={t('review.error')}>{error}</StatusMessage>}
    {!graph && !error && <StatusMessage tone="loading" title={t('state.loading')} />}
    {canWrite && graph && <div className="workflow-grid">
      <form className="stack" onSubmit={createConclusion}><h3>{t('graphWork.newConclusion')}</h3>
        <TextArea label={t('graphWork.statement')} value={statement} maxLength={2000} onChange={(e) => setStatement(e.target.value)} />
        <TextArea label={t('graphWork.limitations')} hint={t('graphWork.onePerLine')} value={limits} onChange={(e) => setLimits(e.target.value)} />
        <NodeSelect label={t('graphWork.support')} value={support} nodes={nodes.filter((n) => n.node_type !== 'CONCLUSION')} onChange={setSupport} />
        <Field label={t('graphWork.why')} value={supportNote} maxLength={1000} onChange={(e) => setSupportNote(e.target.value)} />
        <Button type="submit" busy={busy}>{t('graphWork.createConclusion')}</Button>
      </form>
      <form className="stack" onSubmit={createEdge}><h3>{t('graphWork.newLink')}</h3>
        <NodeSelect label={t('graphWork.from')} value={from} nodes={nodes} onChange={setFrom} /><NodeSelect label={t('graphWork.to')} value={to} nodes={nodes} onChange={setTo} />
        <Select label={t('graphWork.relation')} value={relation} onChange={(v) => setRelation(v as typeof relation)} options={(['SUPPORTS', 'CONTRADICTS', 'LIMITS', 'ADDRESSES'] as const).map((v) => [v, toEnum('rel', v)])} />
        <Field label={t('graphWork.why')} value={edgeNote} maxLength={1000} onChange={(e) => setEdgeNote(e.target.value)} /><Button type="submit" busy={busy}>{t('graphWork.createLink')}</Button>
      </form>
    </div>}
    <div className="workflow-grid">
      <div className="stack"><h3>{t('graphWork.conclusions')}</h3>{conclusions?.items.map((c) => <ReviewRecord key={c.id} title={c.title ?? c.statement} status={c.review_status} blockers={c.review_blockers} canReview={c.can_review} busy={busy} onReview={(d, n) => review('conclusion', c.id, c.version, d, n)} />)}</div>
      <div className="stack"><h3>{t('graphWork.links')}</h3>{edges?.items.map((e) => <ReviewRecord key={e.id} title={`${label(graph, e.from)} · ${toEnum('rel', e.relation)} · ${label(graph, e.to)}`} status={e.review_status} canReview={e.can_review && !e.conclusion_id && !!e.record_id && e.version !== null} busy={busy} onReview={(d, n) => review('edge', e.record_id!, e.version!, d, n)} />)}</div>
    </div>
  </section>;
}

function ReviewRecord({ title, status, blockers = [], canReview, busy, onReview }: { title: string; status: string; blockers?: string[]; canReview: boolean; busy: boolean; onReview: (d: 'ACCEPTED' | 'CHANGES_REQUESTED' | 'REJECTED', note: string) => void }) {
  const { t } = useI18n(); const toEnum = useEnum(); const [note, setNote] = useState(''); const [decision, setDecision] = useState<'ACCEPTED' | 'CHANGES_REQUESTED' | 'REJECTED'>('CHANGES_REQUESTED');
  return <article className="slip"><b>{title}</b><span className="muted">{toEnum('review', status)}</span>{blockers.length > 0 && <ul className="list-plain">{blockers.map((b, i) => <li key={i}>{b}</li>)}</ul>}{canReview && <><Select label={t('review.decision')} value={decision} onChange={(v) => setDecision(v as typeof decision)} options={decisions.map((v) => [v, toEnum('review', v)])} /><TextArea label={t('review.note')} value={note} onChange={(e) => setNote(e.target.value)} /><Button onClick={() => note.trim() && onReview(decision, note.trim())} busy={busy}>{t('review.submit')}</Button></>}</article>;
}
function Select({ label: title, value, options, onChange }: { label: string; value: string; options: readonly (readonly [string, string])[]; onChange: (v: string) => void }) { return <label className="field"><span>{title}</span><span className="ctl"><select value={value} onChange={(e) => onChange(e.target.value)}>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></span></label>; }
function NodeSelect({ label: title, value, nodes, onChange }: { label: string; value: string; nodes: GraphNode[]; onChange: (v: string) => void }) { return <Select label={title} value={value} onChange={onChange} options={[['', '—'], ...nodes.map((n) => [n.id, n.label] as [string, string])]} />; }
function lines(value: string) { return value.split('\n').map((x) => x.trim()).filter(Boolean).slice(0, 20); }
function label(graph: EvidenceGraph | null, id: string) { return graph?.nodes.find((n) => n.id === id)?.label ?? id; }
