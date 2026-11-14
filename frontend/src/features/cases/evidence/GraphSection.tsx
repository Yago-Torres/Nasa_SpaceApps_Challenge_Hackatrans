import { useEffect, useMemo, useRef, useState } from 'react';
import { evidenceApi } from '../../../api/client';
import type { EvidenceGraph, EvidenceTrace, GraphEdge, GraphNode, GraphNodeType } from '../../../api/types';
import { Button, StatusMessage } from '../../../design/components';
import { useI18n } from '../../../i18n/I18n';
import { caseErrorText } from '../caseErrors';
import { useDates } from '../collaboration/format';
import { DoiLink, NodeKindLabel, useEnum } from './labels';

/** Left to right: what a trace ends at, what is derived from it, then hypotheses and conclusions. */
const COLUMNS: { key: string; types: GraphNodeType[] }[] = [
  { key: 'original', types: ['SOURCE_MANIFEST', 'FARMER_REPORT', 'FIELD', 'PAPER'] },
  { key: 'derived', types: ['OBSERVATION', 'EVIDENCE_CLAIM', 'MISSING_DATA'] },
  { key: 'anomalies', types: ['ANOMALY'] },
  { key: 'hypotheses', types: ['HYPOTHESIS'] },
  { key: 'conclusions', types: ['CONCLUSION'] },
];
const SYMBOL: Record<string, string | null> = {
  OBSERVED: 'observed', FARMER_REPORTED: 'farmer', LITERATURE_REVIEWED: 'literature', HYPOTHESIS: 'hypothesis',
  MISSING_DATA: 'missing', LITERATURE_METADATA: null, CONCLUSION: null,
};
const NODE_W = 176;
const NODE_H = 48;
const COL_W = 224;
const ROW_H = 62;
const TOP = 46;

function layout(nodes: GraphNode[]) {
  const positions = new Map<string, { x: number; y: number }>();
  let rows = 1;
  COLUMNS.forEach((col, i) => {
    const inCol = nodes.filter((n) => col.types.includes(n.node_type));
    rows = Math.max(rows, inCol.length);
    inCol.forEach((n, r) => positions.set(n.id, { x: 16 + i * COL_W, y: TOP + r * ROW_H }));
  });
  return { positions, width: 16 + COLUMNS.length * COL_W, height: TOP + rows * ROW_H + 8 };
}

function shorten(s: string, n = 26) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

/**
 * Case evidence graph (ABB-16): observation → hypothesis → conclusion and DOI, with a full
 * text alternative. Selecting any node opens its provenance and its trace to original evidence;
 * a conclusion's trace is the set of evidence it rests on, including unreviewed literature and
 * reviewer-confirmed contradictions. Nothing is computed here: the backend builds graph and trace.
 */
export function GraphSection({ caseId, refreshKey, onOpenClaim }: { caseId: string; refreshKey: number; onOpenClaim: (claimId: string) => void }) {
  const { t } = useI18n();
  const toEnum = useEnum();
  const [graph, setGraph] = useState<EvidenceGraph | null>(null);
  const [failure, setFailure] = useState('');
  const [reload, setReload] = useState(0);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [trace, setTrace] = useState<EvidenceTrace | null>(null);
  const [traceError, setTraceError] = useState('');
  const traceAbort = useRef<AbortController | null>(null);
  const detail = useRef<HTMLElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    evidenceApi.graph(caseId, controller.signal).then(
      (g) => { setGraph(g); setFailure(''); },
      (e) => { if (e?.name !== 'AbortError') setFailure(caseErrorText(e, t)); },
    );
    return () => { controller.abort(); traceAbort.current?.abort(); };
  }, [caseId, refreshKey, reload]); // eslint-disable-line react-hooks/exhaustive-deps

  const [showAll, setShowAll] = useState(false);
  const byId = useMemo(() => new Map((graph?.nodes ?? []).map((n) => [n.id, n])), [graph]);
  const conclusions = (graph?.nodes ?? []).filter((n) => n.node_type === 'CONCLUSION');
  const inTrace = useMemo(() => new Set(trace?.nodes.map((n) => n.id) ?? []), [trace]);
  // A NASA POWER retrieval yields dozens of monthly values. Values that no hypothesis, study or
  // conclusion uses are folded away from the drawing (never from the text list below) so the
  // links that matter stay readable; the open trace always shows everything it reaches.
  const background = useMemo(() => {
    const observedChain = new Set(['SOURCE_MANIFEST', 'OBSERVATION', 'ANOMALY']);
    const linked = new Set<string>();
    for (const e of graph?.edges ?? []) {
      const a = byId.get(e.from);
      const b = byId.get(e.to);
      if (a && b && !(observedChain.has(a.node_type) && observedChain.has(b.node_type))) { linked.add(a.id); linked.add(b.id); }
    }
    return new Set((graph?.nodes ?? []).filter((n) => (n.node_type === 'OBSERVATION' || n.node_type === 'ANOMALY') && !linked.has(n.id)).map((n) => n.id));
  }, [graph, byId]);
  const visible = useMemo(() => (graph?.nodes ?? []).filter((n) => showAll || !background.has(n.id) || inTrace.has(n.id)), [graph, showAll, background, inTrace]);
  const hiddenCount = (graph?.nodes.length ?? 0) - visible.length;
  const drawing = useMemo(() => layout(visible), [visible]);
  /** Backend messages name records by node id; show the record's label instead. */
  const humanize = (text: string) => text.replace(/\b[a-z_]+:[0-9a-f-]{36}\b|\bfarmer:[a-z_]+\b/g, (id) => (byId.has(id) ? `“${byId.get(id)!.label}”` : id));
  const traceEdges = useMemo(() => new Set([...(trace?.edges ?? []), ...(trace?.contradiction_edges ?? []), ...(trace?.limiting_edges ?? [])].map((e) => e.id)), [trace]);

  async function inspect(node: GraphNode) {
    setSelected(node); setTrace(null); setTraceError('');
    traceAbort.current?.abort();
    const controller = new AbortController();
    traceAbort.current = controller;
    requestAnimationFrame(() => detail.current?.focus());
    try { setTrace(await evidenceApi.trace(caseId, node.id, controller.signal)); }
    catch (e) { if (!controller.signal.aborted) setTraceError(caseErrorText(e, t)); }
  }

  const label = (id: string) => byId.get(id)?.label ?? id;

  return (
    <>
      <section className="panel" aria-labelledby="evx-graph-h">
        <div className="section-head">
          <h2 id="evx-graph-h">{t('evx.graph.title')}</h2>
          <p>{t('evx.graph.lead')}</p>
        </div>
        {failure && <StatusMessage tone="error" title={t('evx.graph.error')} action={<Button onClick={() => setReload((n) => n + 1)}>{t('state.retry')}</Button>}>{failure}</StatusMessage>}
        {!graph && !failure && <StatusMessage tone="loading" title={t('state.loading')} />}
        {graph && graph.nodes.length === 0 && <StatusMessage tone="empty" title={t('evx.graph.emptyTitle')}>{t('evx.graph.emptyBody')}</StatusMessage>}
        {graph && graph.nodes.length > 0 && (
          <>
            <div className="stack-tight">
              <h3>{t('evx.graph.conclusions')}</h3>
              {conclusions.length === 0 ? <p className="muted">{t('evx.graph.noConclusions')}</p> : (
                <ul className="list-plain conclusions">
                  {conclusions.map((n) => (
                    <li key={n.id}>
                      <b>{n.label}</b> <span className="chip-meta">{toEnum('review', n.status)}</span>{' '}
                      <Button variant="text" onClick={() => inspect(n)}>{t('evx.graph.openEvidence')}</Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="graph-scroll" tabIndex={0} aria-label={t('evx.graph.scrollLabel')}>
              <svg className={`eg${trace ? ' eg--traced' : ''}`} width={drawing.width} height={drawing.height} viewBox={`0 0 ${drawing.width} ${drawing.height}`}
                role="group" aria-labelledby="evx-svg-title">
                <title id="evx-svg-title">{t('evx.graph.svgTitle', { nodes: graph.counts.total_nodes, edges: graph.counts.total_edges })}</title>
                <defs>
                  <marker id="eg-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 8 4 0 8z" fill="currentColor" /></marker>
                </defs>
                {COLUMNS.map((c, i) => <text key={c.key} className="eg-col" x={16 + i * COL_W} y={22}>{t(`evx.col.${c.key}` as 'evx.col.original')}</text>)}
                {graph.edges.map((e) => <EdgePath key={e.id} edge={e} from={drawing.positions.get(e.from)} to={drawing.positions.get(e.to)} traced={traceEdges.has(e.id)} title={`${label(e.from)} — ${toEnum('rel', e.relation)} → ${label(e.to)}`} />)}
                {visible.map((n) => {
                  const p = drawing.positions.get(n.id);
                  if (!p) return null;
                  const symbol = SYMBOL[n.kind];
                  const unreviewed = n.kind === 'LITERATURE_METADATA';
                  const cls = ['eg-node', `eg-node--${n.kind.toLowerCase()}`, unreviewed ? 'is-unreviewed' : '', !n.active ? 'is-superseded' : '',
                    selected?.id === n.id ? 'is-selected' : '', trace && !inTrace.has(n.id) ? 'is-dim' : ''].filter(Boolean).join(' ');
                  const kindText = unreviewed ? t('evx.graph.notReviewedShort') : n.kind === 'CONCLUSION' ? t('evx.conclusion') : t(`evidence.${n.kind}` as 'evidence.OBSERVED');
                  return (
                    <g key={n.id} className={cls} transform={`translate(${p.x} ${p.y})`} role="button" tabIndex={0}
                      aria-label={`${n.label}. ${kindText}${n.status ? `. ${toEnum('review', n.status)}` : ''}`} aria-pressed={selected?.id === n.id}
                      onClick={() => inspect(n)} onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); void inspect(n); } }}>
                      <rect width={NODE_W} height={NODE_H} rx={n.kind === 'CONCLUSION' ? 8 : 3} />
                      {symbol && <use href={`#s-${symbol}`} className={`ev--${symbol}`} x={8} y={9} width={12} height={12} />}
                      <text x={symbol ? 26 : 10} y={19}>{shorten(n.label)}</text>
                      <text className="eg-kind" x={10} y={37}>{kindText}{n.status && n.kind !== 'OBSERVED' ? ` · ${toEnum('review', n.status)}` : ''}</text>
                      <title>{n.label}</title>
                    </g>
                  );
                })}
              </svg>
            </div>
            {(hiddenCount > 0 || showAll) && background.size > 0 && (
              <p className="muted">
                {showAll ? t('evx.graph.allShown', { n: background.size }) : t('evx.graph.folded', { n: hiddenCount })}{' '}
                <Button variant="text" aria-pressed={showAll} onClick={() => setShowAll((v) => !v)}>{showAll ? t('evx.graph.foldAgain') : t('evx.graph.showAll')}</Button>
              </p>
            )}
            <ul className="eg-legend" aria-label={t('evx.graph.relLegend')}>
              {(['SUPPORTS', 'CONTRADICTS', 'LIMITS', 'OTHER'] as const).map((r) => (
                <li key={r}><svg width="34" height="10" aria-hidden="true"><line className={`eg-edge eg-edge--${r.toLowerCase()}`} x1="1" y1="5" x2="33" y2="5" /></svg>{t(`evx.graph.line.${r}` as 'evx.graph.line.OTHER')}</li>
              ))}
              <li><span className="eg-swatch is-unreviewed" aria-hidden="true" />{t('evx.graph.dashedBox')}</li>
            </ul>

            <details>
              <summary>{t('evx.graph.textAlt', { nodes: graph.nodes.length, edges: graph.edges.length })}</summary>
              <div className="table-wrap">
                <table className="data collab-table">
                  <caption className="sr-only">{t('evx.graph.nodesCaption')}</caption>
                  <thead><tr><th scope="col">{t('evx.graph.item')}</th><th scope="col">{t('evx.graph.kind')}</th><th scope="col">{t('evx.graph.status')}</th></tr></thead>
                  <tbody>
                    {graph.nodes.map((n) => (
                      <tr key={n.id}>
                        <th scope="row"><button type="button" className="tl-table-select" onClick={() => inspect(n)}>{n.label}</button></th>
                        <td data-label={t('evx.graph.kind')}><NodeKindLabel kind={n.kind} /></td>
                        <td data-label={t('evx.graph.status')}>{n.status ? toEnum('review', n.status) : '—'}{!n.active ? ` · ${t('evx.graph.superseded')}` : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h4>{t('evx.graph.relations')}</h4>
              <ul className="list-plain">
                {graph.edges.map((e) => (
                  <li key={e.id}>{label(e.from)} — <b>{toEnum('rel', e.relation)}</b> → {label(e.to)} <span className="muted">({toEnum('origin', e.origin)}{e.review_status !== 'NOT_APPLICABLE' ? ` · ${toEnum('review', e.review_status)}` : ''})</span>{e.note ? ` — ${e.note}` : ''}</li>
                ))}
              </ul>
            </details>
            <ul className="list-plain">{graph.limitations.map((l, i) => <li key={i} className="muted">{l}</li>)}</ul>
          </>
        )}
      </section>

      {selected && (
        <section className="panel" aria-labelledby="evx-detail-h" ref={detail} tabIndex={-1}>
          <div className="panel-head">
            <h2 id="evx-detail-h">{selected.label}</h2>
            <Button variant="text" onClick={() => { setSelected(null); setTrace(null); }}>{t('tl.detailClose')}</Button>
          </div>
          <NodeDetail node={selected} onOpenClaim={onOpenClaim} />
          {traceError && <StatusMessage tone="error" title={t('evx.trace.error')}>{traceError}</StatusMessage>}
          {!trace && !traceError && <StatusMessage tone="loading" title={t('evx.trace.loading')} />}
          {trace && <TraceView trace={trace} label={label} byId={byId} humanize={humanize} onOpenClaim={onOpenClaim} />}
        </section>
      )}
    </>
  );
}

function EdgePath({ edge, from, to, traced, title }: { edge: GraphEdge; from?: { x: number; y: number }; to?: { x: number; y: number }; traced: boolean; title: string }) {
  if (!from || !to) return null;
  const leftToRight = from.x <= to.x;
  const x1 = leftToRight ? from.x + NODE_W : from.x;
  const x2 = leftToRight ? to.x : to.x + NODE_W;
  const y1 = from.y + NODE_H / 2;
  const y2 = to.y + NODE_H / 2;
  const sameCol = from.x === to.x;
  const bend = sameCol ? 40 : Math.max(30, Math.abs(x2 - x1) / 2);
  const d = sameCol
    ? `M${from.x + NODE_W} ${y1} C${from.x + NODE_W + bend} ${y1} ${to.x + NODE_W + bend} ${y2} ${to.x + NODE_W} ${y2}`
    : `M${x1} ${y1} C${x1 + (leftToRight ? bend : -bend)} ${y1} ${x2 - (leftToRight ? bend : -bend)} ${y2} ${x2} ${y2}`;
  const rel = ['SUPPORTS', 'CONTRADICTS', 'LIMITS'].includes(edge.relation) ? edge.relation.toLowerCase() : 'other';
  return (
    <path d={d} className={`eg-edge eg-edge--${rel}${traced ? ' is-traced' : ''}`} markerEnd="url(#eg-arrow)">
      <title>{title}</title>
    </path>
  );
}

function NodeDetail({ node, onOpenClaim }: { node: GraphNode; onOpenClaim: (id: string) => void }) {
  const { t } = useI18n();
  const toEnum = useEnum();
  const dates = useDates();
  const p = node.provenance;
  const rows: [string, React.ReactNode][] = [
    [t('evx.graph.kind'), <NodeKindLabel key="k" kind={node.kind} />],
    [t('evx.graph.status'), node.status ? toEnum('review', node.status) : null],
    [t('evx.prov.source'), p.description],
    [t('evx.prov.dataset'), [p.provider, p.dataset, p.dataset_version].filter(Boolean).join(' · ') || null],
    [t('evx.prov.uri'), p.source_uri ? <a href={p.source_uri} target="_blank" rel="noreferrer noopener">{p.source_uri}<span className="sr-only"> {t('ev.newTab')}</span></a> : null],
    [t('evx.prov.retrieved'), p.retrieved_at ? dates.dateTime(p.retrieved_at) : null],
    [t('evx.prov.resolution'), [p.spatial_resolution?.description, p.temporal_resolution?.description].filter(Boolean).join(' · ') || null],
    [t('evx.prov.period'), node.start ? `${dates.date(node.start)}${node.end ? ` – ${dates.date(node.end)}` : ''}` : null],
    [t('evx.prov.field'), [p.field_label, p.region_label].filter(Boolean).join(' · ') || null],
    ['DOI', node.node_type === 'PAPER' || node.node_type === 'EVIDENCE_CLAIM' || p.doi ? <DoiLink key="d" doi={p.doi} status={p.doi_status} /> : null],
    ['OpenAlex', p.openalex_id ? <a href={p.openalex_id} target="_blank" rel="noreferrer noopener">{p.openalex_id.replace('https://openalex.org/', '')}</a> : null],
    [t('evx.prov.checksum'), p.checksum_sha256 ? <span className="mono">{p.checksum_sha256.slice(0, 16)}…</span> : null],
    [t('evx.prov.created'), p.created_by ? `${p.created_by.display_name}${p.created_at ? ` · ${dates.dateTime(p.created_at)}` : ''}` : null],
    [t('evx.prov.reviewed'), p.reviewed_by ? `${p.reviewed_by.display_name}${p.reviewed_at ? ` · ${dates.dateTime(p.reviewed_at)}` : ''}` : null],
    [t('evx.prov.evaluated'), p.evaluated_by ? `${p.evaluated_by.display_name}${p.evaluated_at ? ` · ${dates.dateTime(p.evaluated_at)}` : ''}` : null],
  ];
  return (
    <div className="label">
      <dl>
        {rows.filter(([, v]) => v !== null && v !== '').map(([k, v]) => <div key={k} className="label-row"><dt>{k}</dt><dd>{v}</dd></div>)}
        {!node.active && <div className="label-row"><dt>{t('evx.graph.status')}</dt><dd>{t('evx.graph.superseded')}</dd></div>}
        <dd className="lim"><ul className="list-plain">{node.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></dd>
      </dl>
      {p.claim_id && <div className="slip-actions"><Button variant="text" onClick={() => onOpenClaim(p.claim_id!)}>{t('evx.dis.openClaim')}</Button></div>}
    </div>
  );
}

function TraceView({ trace, label, byId, humanize, onOpenClaim }: { trace: EvidenceTrace; label: (id: string) => string; byId: Map<string, GraphNode>; humanize: (s: string) => string; onOpenClaim: (id: string) => void }) {
  const { t } = useI18n();
  const toEnum = useEnum();
  const s = trace.summary;
  const yes = (v: boolean) => (v ? t('evx.trace.yes') : t('evx.trace.no'));
  const original = trace.original_evidence.map((id) => byId.get(id) ?? trace.nodes.find((n) => n.id === id)).filter(Boolean) as GraphNode[];
  return (
    <div className="stack" aria-live="polite">
      <h3>{t('evx.trace.title')}</h3>
      <StatusMessage tone={trace.complete ? 'ok' : 'partial'} title={trace.complete ? t('evx.trace.complete') : t('evx.trace.incomplete')}>
        {trace.complete ? t('evx.trace.completeBody') : t('evx.trace.incompleteBody', { n: trace.dead_ends.length })}
      </StatusMessage>
      <dl className="review-list">
        <div><dt>{t('evx.trace.observed')}</dt><dd>{yes(s.reaches_observed_data)}</dd></div>
        <div><dt>{t('evx.trace.farmer')}</dt><dd>{yes(s.reaches_farmer_report)}</dd></div>
        <div><dt>{t('evx.trace.literature')}</dt><dd>{yes(s.reaches_literature)}</dd></div>
        <div><dt>{t('evx.trace.reviewedClaims')}</dt><dd>{s.reviewed_claim_ids.length}</dd></div>
        <div><dt>{t('evx.trace.unreviewedClaims')}</dt><dd>{s.unreviewed_claim_ids.length > 0 ? <b>{t('evx.trace.unreviewedValue', { n: s.unreviewed_claim_ids.length })}</b> : 0}</dd></div>
        <div><dt>{t('evx.trace.unevaluated')}</dt><dd>{s.unevaluated_hypothesis_ids.length}</dd></div>
      </dl>
      {trace.review_blockers.length > 0 && (
        <div className="stack-tight">
          <h4>{t('evx.trace.blockers')}</h4>
          <ul className="list-plain">{trace.review_blockers.map((b, i) => <li key={i}>{humanize(b)}</li>)}</ul>
        </div>
      )}
      <div className="stack-tight">
        <h4>{t('evx.trace.original', { n: original.length })}</h4>
        <ul className="list-plain">
          {original.map((n) => (
            <li key={n.id}>
              <NodeKindLabel kind={n.kind} /> {n.label}
              {n.node_type === 'PAPER' && <> · <DoiLink doi={n.provenance.doi} status={n.provenance.doi_status} /></>}
            </li>
          ))}
        </ul>
      </div>
      {s.unreviewed_claim_ids.length > 0 && (
        <div className="stack-tight">
          <h4>{t('evx.trace.unreviewedList')}</h4>
          <ul className="list-plain">
            {s.unreviewed_claim_ids.map((id) => {
              const n = byId.get(id);
              return <li key={id}>{n ? n.label : id} {n?.provenance.claim_id && <Button variant="text" onClick={() => onOpenClaim(n.provenance.claim_id!)}>{t('evx.dis.openClaim')}</Button>}</li>;
            })}
          </ul>
        </div>
      )}
      {(trace.contradiction_edges.length > 0 || trace.limiting_edges.length > 0) && (
        <div className="stack-tight">
          <h4>{t('evx.trace.qualifiers')}</h4>
          <ul className="list-plain">
            {[...trace.contradiction_edges, ...trace.limiting_edges].map((e) => <li key={e.id}>{label(e.from)} — <b>{toEnum('rel', e.relation)}</b> → {label(e.to)}{e.note ? ` — ${e.note}` : ''}</li>)}
          </ul>
        </div>
      )}
      <details>
        <summary>{t('evx.trace.paths', { n: trace.paths.length })}</summary>
        <ol className="paths">
          {trace.paths.map((path, i) => (
            <li key={i}>
              {path.steps.map((st, j) => (
                <span key={j}>{j > 0 && <> <span className="muted">— {toEnum('rel', st.relation)} →</span> </>}{label(st.node_id)}</span>
              ))}
              {!path.ends_at_original_evidence && <span className="muted"> · {t('evx.trace.deadEnd')}</span>}
            </li>
          ))}
        </ol>
        {trace.truncated && <p className="muted">{t('evx.trace.truncated')}</p>}
      </details>
      <ul className="list-plain">{trace.limitations.map((l, i) => <li key={i} className="muted">{l}</li>)}</ul>
    </div>
  );
}
