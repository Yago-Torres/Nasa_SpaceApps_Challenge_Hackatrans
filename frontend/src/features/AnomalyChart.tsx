import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ClimateMonth } from '../api/types';
import { useI18n } from '../i18n/I18n';
import type { MessageKey } from '../i18n/messages';
import { rainStep, symmetricScale, tempClass } from './chartScale';

const FILL = { 'dry-3': 'var(--viz-dry-3)', 'dry-2': 'var(--viz-dry-2)', 'dry-1': 'var(--viz-dry-1)', 'wet-1': 'var(--viz-wet-1)', 'wet-2': 'var(--viz-wet-2)', 'wet-3': 'var(--viz-wet-3)' };

/**
 * Monthly rain anomaly bars (BrBG) plus a max-temperature difference row (RdBu), drawn
 * from the API values only. Vertical bars on wide screens, horizontal rows when narrow.
 * Each month is focusable and announces its value; a data table is offered separately.
 */
export function AnomalyChart({ monthly, eventYear }: { monthly: ClimateMonth[]; eventYear: number }) {
  const { t, num } = useI18n();
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);
  const [grow, setGrow] = useState(false);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    setWidth(el.clientWidth || 800);
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width || 800));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Bars grow once when new data arrives (a user action), unless reduced motion is on.
  useEffect(() => {
    const reduce = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) return;
    setGrow(false);
    const id = requestAnimationFrame(() => setGrow(true));
    return () => cancelAnimationFrame(id);
  }, [monthly]);

  const rain = monthly.map((m) => m.precipitation_anomaly_mm);
  const { max, ticks } = symmetricScale(rain);
  const horiz = width < 560;
  const monthName = (m: number) => t(`month.${m}` as MessageKey);
  const say = (m: ClimateMonth) =>
    m.precipitation_anomaly_mm === null
      ? `${monthName(m.month)}: ${t('inv.noData')}`
      : `${monthName(m.month)}: ${t(m.precipitation_anomaly_mm < 0 ? 'inv.below' : 'inv.above', { value: num(Math.abs(m.precipitation_anomaly_mm)) })}`;
  const withData = rain.filter((v): v is number => v !== null);
  const summary = t('inv.chartSummary', { dry: withData.filter((v) => v < 0).length, total: withData.length });

  const show = (m: ClimateMonth, el: SVGGElement) => {
    const r = el.getBoundingClientRect();
    const w = wrap.current!.getBoundingClientRect();
    setTip({ text: say(m), x: Math.min(Math.max(r.left - w.left + r.width / 2, 90), w.width - 90), y: r.top - w.top + (horiz ? 0 : 24) });
  };

  const bars = horiz ? horizontal() : vertical();

  function vertical() {
    const W = 720, H = 262, x0 = 60, x1 = 712, y0 = 130, k = 100 / max, slot = (x1 - x0) / 12, bw = Math.min(36, slot - 12);
    return (
      <svg className={`chart${grow ? ' grow' : ''}`} viewBox={`0 0 ${W} ${H}`} role="group" aria-labelledby="chart-t chart-d">
        <title id="chart-t">{t('inv.chartTitle', { year: eventYear })}</title>
        <desc id="chart-d">{summary}</desc>
        {ticks.filter((v) => v !== 0).map((v) => <line key={v} className="grid" x1={x0} x2={x1} y1={y0 - v * k} y2={y0 - v * k} />)}
        {ticks.map((v) => <text key={v} x={x0 - 8} y={y0 - v * k + 4} textAnchor="end">{v === 0 ? '0 mm' : num(v, { signed: true })}</text>)}
        {monthly.map((m, i) => {
          const v = m.precipitation_anomaly_mm;
          const bx = x0 + slot * i + (slot - bw) / 2;
          return (
            <g key={m.month} className="bar-g" tabIndex={0} role="img" aria-label={say(m)}
               onMouseEnter={(e) => show(m, e.currentTarget)} onFocus={(e) => show(m, e.currentTarget)} onMouseLeave={() => setTip(null)} onBlur={() => setTip(null)}>
              <rect className="hit" x={x0 + slot * i + 2} y={24} width={slot - 4} height={212} rx={3} />
              {v === null ? (
                <>
                  <rect className="gap" x={bx} y={y0 - 20} width={bw} height={40} />
                  <text className="na" x={bx + bw / 2} y={y0 + 4} textAnchor="middle">n/a</text>
                </>
              ) : (
                <rect className={`b ${v < 0 ? 'neg' : 'pos'}`} style={{ ['--i' as string]: i }} x={bx} y={v < 0 ? y0 : y0 - v * k} width={bw} height={Math.abs(v) * k} fill={FILL[rainStep(v, max)]} />
              )}
              <text x={x0 + slot * i + slot / 2} y={256} textAnchor="middle">{t(`mon.${m.month}` as MessageKey)}</text>
            </g>
          );
        })}
        <line className="zero" x1={x0} x2={x1} y1={y0} y2={y0} />
      </svg>
    );
  }

  function horizontal() {
    const W = 360, slot = 32, y0 = 8, xz = 200, k = 130 / max, H = y0 + slot * 12 + 28;
    return (
      <svg className={`chart horiz${grow ? ' grow' : ''}`} viewBox={`0 0 ${W} ${H}`} role="group" aria-labelledby="chart-t chart-d">
        <title id="chart-t">{t('inv.chartTitle', { year: eventYear })}</title>
        <desc id="chart-d">{summary}</desc>
        {ticks.filter((v) => v !== 0).map((v) => <line key={v} className="grid" x1={xz + v * k} x2={xz + v * k} y1={y0} y2={y0 + slot * 12} />)}
        {[-max, 0, max].map((v) => <text key={v} x={xz + v * k} y={y0 + slot * 12 + 18} textAnchor="middle">{v === 0 ? '0 mm' : num(v, { signed: true })}</text>)}
        {monthly.map((m, i) => {
          const v = m.precipitation_anomaly_mm;
          const y = y0 + slot * i;
          return (
            <g key={m.month} className="bar-g" tabIndex={0} role="img" aria-label={say(m)}
               onMouseEnter={(e) => show(m, e.currentTarget)} onFocus={(e) => show(m, e.currentTarget)} onMouseLeave={() => setTip(null)} onBlur={() => setTip(null)}>
              <rect className="hit" x={0} y={y + 2} width={W} height={slot - 4} rx={3} />
              <text x={0} y={y + slot / 2 + 4}>{t(`mon.${m.month}` as MessageKey)}</text>
              {v === null ? (
                <>
                  <rect className="gap" x={xz - 20} y={y + 7} width={40} height={slot - 14} />
                  <text className="na" x={xz + 28} y={y + slot / 2 + 4}>n/a</text>
                </>
              ) : (
                <>
                  <rect className={`b ${v < 0 ? 'neg' : 'pos'}`} style={{ ['--i' as string]: i }} x={v < 0 ? xz + v * k : xz} y={y + 7} width={Math.abs(v) * k} height={slot - 14} fill={FILL[rainStep(v, max)]} />
                  <text x={v < 0 ? xz + v * k - 6 : xz + v * k + 6} y={y + slot / 2 + 4} textAnchor={v < 0 ? 'end' : 'start'}>{num(v, { signed: true })}</text>
                </>
              )}
            </g>
          );
        })}
        <line className="zero" x1={xz} x2={xz} y1={y0} y2={y0 + slot * 12} />
      </svg>
    );
  }

  return (
    <div>
      <div className="chart-wrap" ref={wrap}>
        {bars}
        <div className={`tip${tip ? ' on' : ''}`} style={tip ? { left: tip.x, top: tip.y } : undefined} aria-hidden="true">{tip?.text}</div>
      </div>
      <ul className="heat" aria-label={t('inv.colTmaxDiff')}>
        <li className="lbl" aria-hidden="true">{t('inv.tmaxRow')}</li>
        {monthly.map((m) => {
          const v = m.max_temperature_anomaly_c;
          const text = v === null ? 'n/a' : num(v, { digits: 1, signed: true });
          return (
            <li key={m.month} className={tempClass(v)} aria-label={`${monthName(m.month)}: ${v === null ? t('inv.noData') : `${text} °C`}`}>{text}</li>
          );
        })}
      </ul>
    </div>
  );
}
