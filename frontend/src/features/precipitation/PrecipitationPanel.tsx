import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { GpmMonth, PrecipitationResponse } from '../../api/types';
import { useI18n } from '../../i18n/I18n';
import type { MessageKey } from '../../i18n/messages';
import { Button, EvidenceLabel, SourceLabel, StatusMessage } from '../../design/components';
import { errorText } from '../errors';
import { RainCompareChart } from './RainCompareChart';

export const GPM_FIRST_YEAR = 1998;

/** Mirrors gpm.validate_year: whole year from 1998 to the current year. */
export function gpmYear(year: string, currentYear: number): number | null {
  const n = Number(year.trim());
  return Number.isInteger(n) && n >= GPM_FIRST_YEAR && n <= currentYear ? n : null;
}

/**
 * NASA GPM IMERG monthly rain (ABB-09) for the investigation point and year, next to the NASA
 * POWER totals. Every number comes from /api/precipitation/gpm; nothing is drawn without it.
 */
export function PrecipitationPanel({ point, year }: { point: { latitude: number; longitude: number } | null; year: string }) {
  const { t, num, lang } = useI18n();
  const [status, setStatus] = useState<'idle' | 'loading' | 'error' | 'unavailable'>('idle');
  const [failure, setFailure] = useState('');
  const [data, setData] = useState<PrecipitationResponse | null>(null);
  const [showTable, setShowTable] = useState(false);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  const validYear = gpmYear(year, new Date().getUTCFullYear());
  const stale = data !== null && (data.year !== validYear || data.request_params.latitude !== point?.latitude || data.request_params.longitude !== point?.longitude);

  async function load() {
    if (!point || validYear === null) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setStatus('loading');
    try {
      setData(await api.precipitation({ ...point, year: validYear }, controller.signal));
      setStatus('idle');
    } catch (err) {
      if (controller.signal.aborted) return;
      setData(null);
      setFailure(errorText(err, t));
      setStatus(err instanceof ApiError && err.status === 503 ? 'unavailable' : 'error');
    }
  }

  const mm = (v: number | null) => (v === null ? t('inv.noData') : num(v, { digits: 1 }));
  const reason = (m: GpmMonth) => (m.status === 'OBSERVED' ? '' : m.status === 'NOT_READ' ? m.reason ?? '' : t(`gpm.status.${m.status}` as MessageKey));
  const c = data?.comparison;

  return (
    <section className="panel" aria-labelledby="gpm-title">
      <div className="panel-head">
        <h2 id="gpm-title">{t('gpm.title')}</h2>
        <EvidenceLabel kind="OBSERVED" detail="NASA GPM IMERG" />
      </div>
      <p className="muted">{t('gpm.lead')}</p>
      {!point || validYear === null ? (
        <StatusMessage tone="empty" title={t('gpm.needInput', { first: GPM_FIRST_YEAR })} />
      ) : (
        <div className="actions">
          <Button variant="secondary" busy={status === 'loading'} onClick={load}>
            {status === 'loading' ? t('gpm.submitting') : t('gpm.submit', { year: validYear })}
          </Button>
        </div>
      )}

      {status === 'loading' && <StatusMessage tone="loading" title={t('gpm.submitting')} />}
      {status === 'unavailable' && <StatusMessage tone="pending" title={t('gpm.unavailableTitle')}>{failure}</StatusMessage>}
      {status === 'error' && (
        <StatusMessage tone="error" title={t('gpm.errorTitle')} action={<Button variant="secondary" onClick={load}>{t('state.retry')}</Button>}>
          {failure}
        </StatusMessage>
      )}

      {data && c && status !== 'loading' && (
        <>
          {stale && <StatusMessage tone="stale" title={t('gpm.staleTitle')}>{t('gpm.staleBody', { year: data.year })}</StatusMessage>}
          <p>
            {t('gpm.cell', { lat: num(data.cell.latitude, { digits: 2 }), lon: num(data.cell.longitude, { digits: 2 }) })}{' '}
            {c.status === 'COMPARED' && c.months_compared > 0
              ? t('gpm.totals', { n: c.months_compared, gpm: mm(c.gpm_total_mm), power: mm(c.power_total_mm) })
              : t('gpm.noComparison', { reason: c.reason ?? '' })}
          </p>
          {(data.summary.not_available ?? 0) + (data.summary.missing ?? 0) + (data.summary.not_read ?? 0) > 0 && (
            <StatusMessage tone="partial" title={t('gpm.partialTitle')}>
              {t('gpm.partialBody', { months: data.monthly.filter((m) => m.precipitation_mm === null).map((m) => t(`month.${m.month}` as MessageKey)).join(', ') })}
            </StatusMessage>
          )}
          <RainCompareChart monthly={data.monthly} year={data.year} />
          <p className="muted">{t('gpm.caption')}</p>
          <div className="actions">
            <Button variant="text" aria-expanded={showTable} aria-controls="gpm-table" onClick={() => setShowTable((s) => !s)}>
              {showTable ? t('inv.hideTable') : t('inv.showTable')}
            </Button>
          </div>
          {showTable && (
            <div className="table-wrap" id="gpm-table">
              <table className="data">
                <caption className="sr-only">{t('gpm.chartTitle', { year: data.year })}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t('inv.colMonth')}</th>
                    <th scope="col">{t('gpm.colGpm')}</th>
                    <th scope="col">{t('gpm.colError')}</th>
                    <th scope="col">{t('gpm.colPower')}</th>
                    <th scope="col">{t('gpm.colDiff')}</th>
                    <th scope="col">{t('gpm.colGauge')}</th>
                    <th scope="col">{t('gpm.colNote')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.monthly.map((m) => (
                    <tr key={m.month}>
                      <th scope="row">{t(`month.${m.month}` as MessageKey)}</th>
                      <td>{mm(m.precipitation_mm)}</td>
                      <td>{m.random_error_mm === null ? '–' : `± ${num(m.random_error_mm, { digits: 1 })}`}</td>
                      <td>{mm(m.power_precipitation_mm)}</td>
                      <td>{m.difference_mm === null ? '–' : num(m.difference_mm, { digits: 1, signed: true })}</td>
                      <td>{m.gauge_weight_percent === null ? '–' : `${num(m.gauge_weight_percent, { digits: 0 })} %`}</td>
                      <td>{reason(m)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <SourceLabel
            name={t('gpm.srcTitle')}
            kind="OBSERVED"
            rows={[
              { label: t('src.dataset'), value: data.dataset },
              { label: t('gpm.srcCell'), value: `${data.cell.latitude}, ${data.cell.longitude} (0.1°)`, mono: true },
              { label: t('src.period'), value: String(data.year) },
              { label: t('src.resolution'), value: data.spatial_resolution.description },
              { label: t('gpm.srcCompare'), value: `${c.dataset}, ${c.parameter}, ${c.spatial_resolution}` },
              { label: t('src.retrieved'), value: new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(data.retrieved_at)) },
              { label: t('src.checksum'), value: `${data.provenance.checksum_sha256.slice(0, 16)}…`, mono: true },
              { label: t('src.docs'), value: <a href={data.source_url} target="_blank" rel="noreferrer">doi.org · GPM_3IMERGM v07 <span className="sr-only">{t('ev.newTab')}</span></a> },
            ]}
            limitations={data.limitations.join(' ')}
          />
        </>
      )}
    </section>
  );
}
