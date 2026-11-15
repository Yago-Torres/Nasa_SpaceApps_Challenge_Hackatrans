import { useLayoutEffect, useRef, useState } from 'react';
import type { GpmMonth } from '../../api/types';
import { useI18n } from '../../i18n/I18n';
import type { MessageKey } from '../../i18n/messages';

const H = 260, X0 = 56, Y_TOP = 14, Y_BOT = 214;

/**
 * Monthly rain totals of two NASA products side by side on one scale from zero: GPM IMERG
 * (filled, with its own random-error whisker) and NASA POWER (outlined). Months without a value
 * are marked "n/a", never drawn as zero.
 */
export function RainCompareChart({ monthly, year }: { monthly: GpmMonth[]; year: number }) {
  const { t, num } = useI18n();
  const wrap = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(720);
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);
  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    setW(Math.max(280, el.clientWidth || 720));
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([entry]) => setW(Math.max(280, entry.contentRect.width || 720)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const values = monthly.flatMap((m) => [m.power_precipitation_mm ?? 0, (m.precipitation_mm ?? 0) + (m.random_error_mm ?? 0)]);
  const rawMax = Math.max(10, ...values);
  const step = rawMax > 200 ? 50 : rawMax > 80 ? 20 : 10;
  const max = Math.ceil(rawMax / step) * step;
  const ticks = Array.from({ length: max / step + 1 }, (_, i) => i * step);
  const y = (v: number) => Y_BOT - (v / max) * (Y_BOT - Y_TOP);
  const X1 = W - 8;
  const slot = (X1 - X0) / 12;
  const bw = Math.max(5, Math.min(16, slot / 2 - 4));
  const mon = (m: number) => t(`mon.${m}` as MessageKey);
  const v = (x: number | null) => (x === null ? t('inv.noData') : `${num(x, { digits: 1 })} mm`);
  const say = (m: GpmMonth) => t('gpm.pointLabel', { month: t(`month.${m.month}` as MessageKey), gpm: v(m.precipitation_mm), power: v(m.power_precipitation_mm) });
  const show = (m: GpmMonth, el: SVGGElement) => {
    const r = el.getBoundingClientRect();
    const w = wrap.current!.getBoundingClientRect();
    setTip({ text: say(m), x: Math.min(Math.max(r.left - w.left + r.width / 2, 130), w.width - 130), y: r.top - w.top + 12 });
  };

  return (
    <div className="chart-wrap" ref={wrap}>
      <svg className="chart rain2" viewBox={`0 0 ${W} ${H}`} role="group" aria-labelledby="rain2-t rain2-d">
        <title id="rain2-t">{t('gpm.chartTitle', { year })}</title>
        <desc id="rain2-d">{t('gpm.chartDesc')}</desc>
        {ticks.map((tk) => (
          <g key={tk}>
            <line className={tk === 0 ? 'zero' : 'grid'} x1={X0} x2={X1} y1={y(tk)} y2={y(tk)} />
            <text x={X0 - 8} y={y(tk) + 4} textAnchor="end">{tk === 0 ? '0 mm' : num(tk)}</text>
          </g>
        ))}
        {monthly.map((m, i) => {
          const cx = X0 + slot * i + slot / 2;
          const g = m.precipitation_mm;
          const p = m.power_precipitation_mm;
          return (
            <g key={m.month} className="bar-g" tabIndex={0} role="img" aria-label={say(m)}
               onMouseEnter={(e) => show(m, e.currentTarget)} onFocus={(e) => show(m, e.currentTarget)} onMouseLeave={() => setTip(null)} onBlur={() => setTip(null)}>
              <rect className="hit" x={X0 + slot * i + 1} y={Y_TOP - 4} width={slot - 2} height={Y_BOT - Y_TOP + 8} rx={3} />
              {g === null ? (
                <text className="na" x={cx - bw / 2 - 1} y={Y_BOT - 6} textAnchor="middle">n/a</text>
              ) : (
                <>
                  <rect className="gpm" x={cx - bw - 1} y={y(g)} width={bw} height={Y_BOT - y(g)} />
                  {m.random_error_mm !== null && (
                    <line className="err" x1={cx - bw / 2 - 1} x2={cx - bw / 2 - 1} y1={y(Math.max(0, g - m.random_error_mm))} y2={y(g + m.random_error_mm)} />
                  )}
                </>
              )}
              {p === null ? (
                <text className="na" x={cx + bw / 2 + 1} y={Y_BOT - 6} textAnchor="middle">n/a</text>
              ) : (
                <rect className="pwr" x={cx + 1} y={y(p)} width={bw} height={Y_BOT - y(p)} />
              )}
              <text x={cx} y={H - 22} textAnchor="middle">{mon(m.month)}</text>
            </g>
          );
        })}
      </svg>
      <div className={`tip${tip ? ' on' : ''}`} style={tip ? { left: tip.x, top: tip.y } : undefined} aria-hidden="true">{tip?.text}</div>
      <p className="muted rain2-key">
        <span className="key-gpm" aria-hidden="true" /> {t('gpm.keyGpm')} <span className="key-pwr" aria-hidden="true" /> {t('gpm.keyPower')}{' '}
        <span className="key-err" aria-hidden="true" /> {t('gpm.keyError')}
      </p>
    </div>
  );
}
