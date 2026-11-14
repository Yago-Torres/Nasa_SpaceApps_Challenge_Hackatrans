import { useEffect, useMemo, useState } from 'react';
import { casesApi } from '../../../api/client';
import type { EvidenceGraph, EvidenceTrace, GraphNode, GraphNodeKind } from '../../../api/types';
import { useI18n } from '../../../i18n/I18n';
import { Button, EvidenceLabel, PageHeader, StatusMessage, type EvidenceKind } from '../../../design/components';
import { caseRepository } from '../../../cases/repository';
import type { IncidentCase } from '../../../cases/model';
import { CaseTitleBlock } from '../CaseTitleBlock';
import { caseErrorText } from '../caseErrors';
import './evidenceGraph.css';

const KINDS: GraphNodeKind[] = ['OBSERVED', 'FARMER_REPORTED', 'LITERATURE_METADATA', 'LITERATURE_REVIEWED', 'HYPOTHESIS', 'CONCLUSION', 'MISSING_DATA'];
const EVIDENCE_KINDS = new Set<EvidenceKind>(['OBSERVED', 'FARMER_REPORTED', 'LITERATURE_REVIEWED', 'HYPOTHESIS', 'MISSING_DATA']);

function Kind({ kind }: { kind: GraphNodeKind }) {
  const { t } = useI18n();
  if (EVIDENCE_KINDS.has(kind as EvidenceKind)) return <EvidenceLabel kind={kind as EvidenceKind} />;
  if (kind === 'LITERATURE_METADATA') return <span className="chip-meta">{t('evidence.metadataOnly')}</span>;
  return <span className="eg-conclusion">{t('eg.conclusion')}</span>;
}

function layout(nodes: GraphNode[]) {
  const byKind = new Map(KINDS.map((kind) => [kind, nodes.filter((n) => n.kind === kind)]));
  const positions = new Map<string, { x: number; y: number }>();
  let maxRows = 1;
  KINDS.forEach((kind, col) => {
    const items = byKind.get(kind) ?? [];
    maxRows = Math.max(maxRows, items.length);
    items.forEach((node, row) => positions.set(node.id, { x: 80 + col * 125, y: 55 + row * 64 }));
  });
  return { positions, height: Math.max(180, 100 + maxRows * 64) };
}

export function CaseEvidenceGraph({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  const [data, setData] = useState<{ c: IncidentCase; graph: EvidenceGraph } | null>(null);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [trace, setTrace] = useState<EvidenceTrace | null>(null);
  const [traceError, setTraceError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError('');
    Promise.all([caseRepository().get(caseId), casesApi.evidenceGraph(caseId, controller.signal)]).then(([c, graph]) => {
      if (!c) throw new Error(t('cases.notFound'));
      setData({ c, graph });
    }).catch((err) => { if (err?.name !== 'AbortError') setError(caseErrorText(err, t)); });
    return () => controller.abort();
  }, [caseId, reload, t]);

  const drawing = useMemo(() => layout(data?.graph.nodes ?? []), [data]);

  async function inspect(node: GraphNode) {
    setSelected(node); setTrace(null); setTraceError('');
    try { setTrace(await casesApi.evidenceTrace(caseId, node.id)); }
    catch (err) { setTraceError(caseErrorText(err, t)); }
  }

  if (error) return <><PageHeader title={t('eg.title')} /><StatusMessage tone="error" title={t('eg.error')} action={<Button onClick={() => setReload((n) => n + 1)}>{t('state.retry')}</Button>}>{error}</StatusMessage></>;
  if (!data) return <><PageHeader title={t('eg.title')} /><StatusMessage tone="loading" title={t('eg.loading')} /></>;
  const { graph, c } = data;

  return <>
    <CaseTitleBlock c={c} lead={t('eg.lead')} />
    {graph.nodes.length === 0 ? <StatusMessage tone="empty" title={t('eg.empty')} /> : <>
      <section className="panel" aria-labelledby="eg-visual-title">
        <div className="section-head"><h2 id="eg-visual-title">{t('eg.visual')}</h2><p>{t('eg.visualLead')}</p></div>
        <div className="chart-wrap">
          <svg className="eg-graph" viewBox={`0 0 910 ${drawing.height}`} role="img" aria-labelledby="eg-svg-title eg-svg-desc">
            <title id="eg-svg-title">{t('eg.visual')}</title><desc id="eg-svg-desc">{t('eg.summary', { nodes: graph.counts.total_nodes, edges: graph.counts.total_edges })}</desc>
            {graph.edges.map((edge) => { const a = drawing.positions.get(edge.from); const b = drawing.positions.get(edge.to); return a && b ? <line key={edge.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className={`eg-edge eg-edge--${edge.relation.toLowerCase()}`}><title>{edge.relation}: {edge.note ?? ''}</title></line> : null; })}
            {graph.nodes.map((node) => { const p = drawing.positions.get(node.id)!; return <g key={node.id} className={`eg-node eg-node--${node.kind.toLowerCase()}`} role="button" tabIndex={0} aria-label={node.label} onClick={() => inspect(node)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); void inspect(node); } }}>
              <rect x={p.x - 52} y={p.y - 20} width="104" height="40" rx="4" /><text x={p.x} y={p.y + 4} textAnchor="middle">{node.label.slice(0, 18)}</text>
            </g>; })}
          </svg>
        </div>
      </section>
      <section className="panel" aria-labelledby="eg-list-title"><h2 id="eg-list-title">{t('eg.list')}</h2>
        <div className="table-wrap"><table className="data"><thead><tr><th scope="col">{t('eg.kind')}</th><th scope="col">{t('eg.item')}</th><th scope="col">{t('eg.status')}</th></tr></thead><tbody>{graph.nodes.map((node) => <tr key={node.id}><td><Kind kind={node.kind} /></td><th scope="row"><button className="tl-table-select" onClick={() => inspect(node)}>{node.label}</button></th><td>{node.status ?? t('eg.notReviewed')}</td></tr>)}</tbody></table></div>
        <h3>{t('eg.relationships')}</h3>
        <ul>{graph.edges.map((edge) => <li key={edge.id}><b>{edge.relation}</b>: {graph.nodes.find((n) => n.id === edge.from)?.label ?? edge.from} → {graph.nodes.find((n) => n.id === edge.to)?.label ?? edge.to}{edge.note ? ` — ${edge.note}` : ''}</li>)}</ul>
      </section>
    </>}
    {selected && <section className="panel" aria-labelledby="eg-detail-title"><div className="panel-head"><h2 id="eg-detail-title">{selected.label}</h2><Button variant="text" onClick={() => { setSelected(null); setTrace(null); }}>{t('tl.detailClose')}</Button></div>
      <Kind kind={selected.kind} />
      <p>{t('eg.status')}: {selected.status ?? t('eg.notReviewed')}</p>
      {selected.provenance.doi ? <p><a href={selected.provenance.doi} target="_blank" rel="noreferrer">{selected.provenance.doi}</a></p> : null}
      <p>{selected.provenance.description}</p>
      {selected.limitations.length > 0 && <ul>{selected.limitations.map((x) => <li key={x}>{x}</li>)}</ul>}
      {traceError && <StatusMessage tone="error" title={t('eg.traceError')}>{traceError}</StatusMessage>}
      {!trace && !traceError && <StatusMessage tone="loading" title={t('eg.traceLoading')} />}
      {trace && <div><p><b>{trace.complete ? t('eg.traceComplete') : t('eg.traceIncomplete')}</b></p>{trace.review_blockers.length > 0 && <ul>{trace.review_blockers.map((x) => <li key={x}>{x}</li>)}</ul>}<p>{t('eg.traceCounts', { nodes: trace.nodes.length, edges: trace.edges.length })}</p><h3>{t('eg.traceEvidence')}</h3><ul>{trace.nodes.map((node) => <li key={node.id}><Kind kind={node.kind} /> {node.label}</li>)}</ul></div>}
    </section>}
    <section className="panel"><h2 className="sr-only">{t('src.limitations')}</h2><ul>{graph.limitations.map((x) => <li key={x}>{x}</li>)}</ul></section>
  </>;
}
