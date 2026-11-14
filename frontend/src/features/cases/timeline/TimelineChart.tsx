import { useMemo, useState } from 'react';
import { useI18n } from '../../../i18n/I18n';
import type { MessageKey } from '../../../i18n/messages';
import { Button } from '../../../design/components';
import type { TimelineEvent, TimelineKind } from '../../../api/types';
import { dayScale, monthTicks, packRows, severitySize, timelineSpan } from './timelineLayout';

const LAYER_ORDER: TimelineKind[] = ['OBSERVED', 'FARMER_REPORTED', 'HYPOTHESIS', 'MISSING_DATA'];
const LAYER_LABEL: Record<TimelineKind, MessageKey> = {
  OBSERVED: 'evidence.OBSERVED', FARMER_REPORTED: 'evidence.FARMER_REPORTED',
  HYPOTHESIS: 'evidence.HYPOTHESIS', MISSING_DATA: 'evidence.MISSING_DATA',
};

const W = 880;
const MARGIN_LEFT = 164;
const MARGIN_RIGHT = 16;
const ROW_H = 26;
const ROW_GAP = 4;
const LANE_GAP = 10;
const AXIS_H = 34;
const TOP_PAD = 10;

/**
 * Marks drawn here are the same shapes/colours as the shared legend sprite
 * (`design/components.tsx` LegendSprite: filled square = OBSERVED, filled circle =
 * FARMER_REPORTED, dashed ring = HYPOTHESIS, dotted square = MISSING_DATA) and the same
 * `--ev-*` tokens, kept inline because this chart's viewBox is scaled independently of the
 * sprite's own 12x12 box — this is the one legend, drawn twice at two scales, not a second
 * legend system. The permanent legend above the chart (`EvidenceLabel`) is the sprite itself.
 */
function Mark({ kind, x, x2, y, h, opacity, selected }: {
  kind: TimelineKind; x: number; x2: number; y: number; h: number; opacity: number; selected: boolean;
}) {
  const w = Math.max(x2 - x, 6);
  const ring = selected ? { stroke: 'var(--focus)', strokeWidth: 2.5 } : {};
  if (kind === 'OBSERVED') {
    return <rect x={x} y={y} width={w} height={h} rx={2} fill="var(--ev-observed)" fillOpacity={opacity} {...ring} />;
  }
  if (kind === 'FARMER_REPORTED') {
    return <rect x={x} y={y} width={w} height={h} rx={h / 2} fill="var(--ev-farmer)" fillOpacity={0.85} {...ring} />;
  }
  if (kind === 'HYPOTHESIS') {
    return <rect x={x} y={y} width={w} height={h} rx={3} fill="none" stroke="var(--ev-hypothesis)" strokeWidth={2} strokeDasharray="5 3" {...ring} />;
  }
  return <rect x={x} y={y} width={w} height={h} rx={2} fill="var(--surface-sunken)" stroke="var(--ev-missing)" strokeWidth={1.5} strokeDasharray="2 2" {...ring} />;
}

/**
 * Horizontal time axis, one lane per evidence kind (dataviz.md "Timeline (F-04)"). Events
 * without a start date (e.g. undated crop history) are never placed here; the caller lists
 * them separately. Clicking or focusing + Enter/Space on a mark selects it for inspection
 * ("temporal selection"): the caller renders that event's full provenance below the chart.
 */
export function TimelineChart({
  events, incidentStart, incidentEnd, selectedId, onSelect,
}: {
  events: TimelineEvent[];
  incidentStart: string;
  incidentEnd: string | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { t, lang } = useI18n();
  const dateFmt = new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { month: 'short', year: '2-digit' });
  const [showTable, setShowTable] = useState(false);
  const dated = useMemo(() => events.filter((e) => e.start !== null), [events]);
  const undated = useMemo(() => events.filter((e) => e.start === null), [events]);

  const layout = useMemo(() => {
    if (!dated.length) return null;
    const [min, max] = timelineSpan(dated, incidentStart, incidentEnd);
    const scale = dayScale(min, max, MARGIN_LEFT, W - MARGIN_RIGHT);
    const ticks = monthTicks(min, max);
    let y = TOP_PAD;
    const lanes = LAYER_ORDER.map((kind) => {
      const inLane = dated.filter((e) => e.kind === kind).sort((a, b) => (a.start! < b.start! ? -1 : 1));
      const rows = packRows(inLane.map((e) => ({ start: e.start!, end: e.end ?? e.start! })));
      const rowCount = Math.max(1, rows.length ? Math.max(...rows) + 1 : 1);
      const laneTop = y;
      const laneH = rowCount * ROW_H + (rowCount - 1) * ROW_GAP;
      y += laneH + LANE_GAP;
      return { kind, top: laneTop, height: laneH, items: inLane.map((e, i) => ({ event: e, row: rows[i] })) };
    });
    return { scale, ticks, lanes, min, max, height: y - LANE_GAP + AXIS_H };
  }, [dated, incidentStart, incidentEnd]);

  const summary = t('tl.chartSummary', { n: dated.length, total: events.length });

  return (
    <figure className="tl-chart-figure">
      <figcaption className="sr-only" id="tl-chart-d">{summary}</figcaption>
      {layout ? (
        <div className="chart-wrap">
          <svg className="chart tl-chart" viewBox={`0 0 ${W} ${layout.height}`} role="img" aria-labelledby="tl-chart-t" aria-describedby="tl-chart-d">
            <title id="tl-chart-t">{t('tl.chartTitle')}</title>
            {(() => {
              const bandX1 = layout.scale(incidentStart);
              const bandX2 = layout.scale(incidentEnd ?? incidentStart);
              return (
                <rect x={Math.min(bandX1, bandX2)} y={0} width={Math.max(bandX2 - bandX1, 2)} height={layout.height - AXIS_H}
                  fill="var(--viz-event)" opacity={0.35} />
              );
            })()}
            {layout.ticks.map(({ iso, date }) => (
              <g key={iso}>
                <line className="tl-grid" x1={layout.scale(iso)} x2={layout.scale(iso)} y1={0} y2={layout.height - AXIS_H} />
                <text className="tl-axis" x={layout.scale(iso)} y={layout.height - AXIS_H + 16} textAnchor="middle">
                  {dateFmt.format(date)}
                </text>
              </g>
            ))}
            {layout.lanes.map((lane) => (
              <g key={lane.kind}>
                <text className="tl-lane-label" x={MARGIN_LEFT - 12} y={lane.top + lane.height / 2 + 4} textAnchor="end">
                  {t(LAYER_LABEL[lane.kind])}
                </text>
                {lane.items.map(({ event, row }) => {
                  const x = layout.scale(event.start!);
                  const x2 = layout.scale(event.end ?? event.start!);
                  const y = lane.top + row * (ROW_H + ROW_GAP);
                  const size = event.kind === 'OBSERVED' ? severitySize(event.departure?.severity) : 1;
                  const sel = selectedId === event.id;
                  return (
                    <g key={String(event.id)} tabIndex={0} role="button" aria-pressed={sel} aria-label={event.title}
                       className="tl-mark" onClick={() => onSelect(event.id)}
                       onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onSelect(event.id); } }}>
                      <rect className="tl-hit" x={Math.min(x, x2) - 3} y={y - 3} width={Math.max(Math.abs(x2 - x), 6) + 6} height={ROW_H + 6} rx={4} />
                      <Mark kind={event.kind} x={Math.min(x, x2)} x2={Math.max(x, x2)} y={y} h={ROW_H} opacity={size} selected={sel} />
                    </g>
                  );
                })}
              </g>
            ))}
          </svg>
        </div>
      ) : (
        <p className="muted">{t('tl.noDatedEvents')}</p>
      )}
      <p className="muted">{summary}</p>
      {undated.length > 0 && (
        <div className="tl-undated">
          <p className="muted">{t('tl.undatedTitle')}</p>
          <ul className="list-plain">
            {undated.map((e) => (
              <li key={String(e.id)}>
                <button type="button" className="tl-undated-item" aria-pressed={selectedId === e.id} onClick={() => onSelect(e.id)}>
                  {e.title}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="actions">
        <Button variant="text" aria-expanded={showTable} aria-controls="tl-table" onClick={() => setShowTable((s) => !s)}>
          {showTable ? t('tl.hideTable') : t('tl.showTable')}
        </Button>
      </div>
      {showTable && (
        <div className="table-wrap" id="tl-table">
          <table className="data">
            <caption className="sr-only">{t('tl.chartTitle')}</caption>
            <thead>
              <tr>
                <th scope="col">{t('tl.colKind')}</th>
                <th scope="col">{t('tl.colStart')}</th>
                <th scope="col">{t('tl.colEnd')}</th>
                <th scope="col">{t('tl.colTitle')}</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={String(e.id)} aria-current={selectedId === e.id ? 'true' : undefined}>
                  <th scope="row">{t(LAYER_LABEL[e.kind])}</th>
                  <td>{e.start ?? t('tl.undated')}</td>
                  <td>{e.end ?? t('tl.undated')}</td>
                  <td>
                    <button type="button" className="tl-table-select" onClick={() => onSelect(e.id)}>{e.title}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </figure>
  );
}
