import { useRef, useState } from 'react';
import type { HlsObservation, VegetationResponse } from '../../api/types';
import { useI18n } from '../../i18n/I18n';
import type { MessageKey } from '../../i18n/messages';

const DAY = 86_400_000;
const W = 720, H = 268, X0 = 52, X1 = 708, Y_TOP = 16, Y_BOT = 186, ROW_OBSCURED = 212, ROW_GAP = 238;

/**
 * NDVI per satellite overpass on one honest scale (0–1, or lower when the data go below 0).
 * Clear observations are filled squares with their min–max window range; overpasses without a
 * clear view sit on their own row, and days without any valid observation are drawn as dotted
 * gap bars. Points are not joined: nothing between two overpasses is known.
 */
export function NdviChart({ data }: { data: VegetationResponse }) {
  const { t, num, lang } = useI18n();
  const wrap = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);
  const t0 = Date.parse(`${data.start}T00:00:00Z`);
  const t1 = Date.parse(`${data.end}T00:00:00Z`) + DAY;
  const x = (iso: string) => X0 + ((Date.parse(iso) - t0) / (t1 - t0)) * (X1 - X0);
  const xDay = (d: string) => x(`${d}T00:00:00Z`);
  const lows = data.observations.flatMap((o) => (o.ndvi_min === null ? [] : [o.ndvi_min]));
  const lo = Math.min(0, Math.floor(Math.min(...lows, 0) * 10) / 10);
  const y = (v: number) => Y_BOT - ((v - lo) / (1 - lo)) * (Y_BOT - Y_TOP);
  const ticks = [lo, ...[0, 0.2, 0.4, 0.6, 0.8, 1].filter((v) => v > lo)];
  const monthFmt = new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { month: 'short', timeZone: 'UTC' });
  const dayFmt = new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });
  const months: Date[] = [];
  for (let d = new Date(t0); d.getTime() < t1; d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))) {
    months.push(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)));
  }

  const say = (o: HlsObservation) => {
    const when = `${dayFmt.format(new Date(o.acquired_at))}, ${o.sensor}`;
    return o.status === 'VALID' && o.ndvi !== null
      ? t('veg.pointValid', { when, ndvi: num(o.ndvi, { digits: 2 }), clear: o.pixels.clear, total: o.window_pixels })
      : `${when}: ${t(`veg.status.${o.status}` as MessageKey)}`;
  };
  const show = (o: HlsObservation, el: SVGGElement) => {
    const r = el.getBoundingClientRect();
    const w = wrap.current!.getBoundingClientRect();
    setTip({ text: say(o), x: Math.min(Math.max(r.left - w.left + r.width / 2, 120), w.width - 120), y: r.top - w.top });
  };
  const valid = data.observations.filter((o) => o.status === 'VALID' && o.ndvi !== null);
  const other = data.observations.filter((o) => !(o.status === 'VALID' && o.ndvi !== null));

  return (
    <div className="chart-wrap" ref={wrap}>
      <svg className="chart ndvi" viewBox={`0 0 ${W} ${H}`} role="group" aria-labelledby="ndvi-t ndvi-d">
        <title id="ndvi-t">{t('veg.chartTitle')}</title>
        <desc id="ndvi-d">{t('veg.summaryShort', { valid: valid.length, total: data.observations.length, gaps: data.gaps.length })}</desc>
        {ticks.map((v) => (
          <g key={v}>
            <line className={v === 0 ? 'zero' : 'grid'} x1={X0} x2={X1} y1={y(v)} y2={y(v)} />
            <text x={X0 - 8} y={y(v) + 4} textAnchor="end">{num(v, { digits: 1 })}</text>
          </g>
        ))}
        <text x={X0 - 8} y={ROW_OBSCURED + 4} textAnchor="end">{t('veg.rowObscured')}</text>
        <text x={X0 - 8} y={ROW_GAP + 4} textAnchor="end">{t('veg.rowGap')}</text>
        {data.gaps.map((g) => (
          <rect key={g.start} className="gap" x={xDay(g.start)} y={ROW_GAP - 6} width={Math.max(2, xDay(g.end) + (X1 - X0) * DAY / (t1 - t0) - xDay(g.start))} height={12} />
        ))}
        {months.map((m) => (
          <text key={m.getTime()} x={Math.max(X0, X0 + ((m.getTime() - t0) / (t1 - t0)) * (X1 - X0))} y={H - 4}>{monthFmt.format(m)}</text>
        ))}
        {other.map((o) => (
          <g key={`${o.product}-${o.acquired_at}`} className="bar-g" tabIndex={0} role="img" aria-label={say(o)}
             onMouseEnter={(e) => show(o, e.currentTarget)} onFocus={(e) => show(o, e.currentTarget)} onMouseLeave={() => setTip(null)} onBlur={() => setTip(null)}>
            <rect className="hit" x={x(o.acquired_at) - 7} y={ROW_OBSCURED - 9} width={14} height={18} rx={3} />
            <rect className="obscured" x={x(o.acquired_at) - 3.5} y={ROW_OBSCURED - 3.5} width={7} height={7} />
          </g>
        ))}
        {valid.map((o) => (
          <g key={`${o.product}-${o.acquired_at}`} className="bar-g" tabIndex={0} role="img" aria-label={say(o)}
             onMouseEnter={(e) => show(o, e.currentTarget)} onFocus={(e) => show(o, e.currentTarget)} onMouseLeave={() => setTip(null)} onBlur={() => setTip(null)}>
            <rect className="hit" x={x(o.acquired_at) - 7} y={Y_TOP - 4} width={14} height={Y_BOT - Y_TOP + 8} rx={3} />
            <line className="range" x1={x(o.acquired_at)} x2={x(o.acquired_at)} y1={y(o.ndvi_min ?? o.ndvi!)} y2={y(o.ndvi_max ?? o.ndvi!)} />
            <rect className={`obs ${o.product === 'HLSL30' ? 'l30' : 's30'}`} x={x(o.acquired_at) - 4} y={y(o.ndvi!) - 4} width={8} height={8} />
          </g>
        ))}
      </svg>
      <div className={`tip${tip ? ' on' : ''}`} style={tip ? { left: tip.x, top: tip.y } : undefined} aria-hidden="true">{tip?.text}</div>
      <p className="muted veg-key">
        <span className="key-obs" aria-hidden="true" /> {t('veg.keyL30')} <span className="key-obs s30" aria-hidden="true" /> {t('veg.keyS30')}{' '}
        <span className="key-obscured" aria-hidden="true" /> {t('veg.keyObscured')} <span className="key-gap" aria-hidden="true" /> {t('veg.keyGap')}
      </p>
    </div>
  );
}
