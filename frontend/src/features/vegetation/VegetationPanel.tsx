import { useEffect, useRef, useState, type FormEvent } from 'react';
import { api, ApiError } from '../../api/client';
import type { VegetationResponse } from '../../api/types';
import { useI18n } from '../../i18n/I18n';
import type { MessageKey } from '../../i18n/messages';
import { Button, EvidenceLabel, Field, SourceLabel, StatusMessage } from '../../design/components';
import { errorText } from '../errors';
import { NdviChart } from './NdviChart';

export const MAX_DAYS = 92;
const HLS_START = '2013-04-11';

type Range = { start: string; end: string };
type RangeErrors = Partial<Record<keyof Range | 'span', true>>;

const DAY = 86_400_000;
const parseDay = (s: string) => (/^\d{4}-\d{2}-\d{2}$/.test(s) ? Date.parse(`${s}T00:00:00Z`) : NaN);

/** Mirrors hls.validate_range so people see the problem before a request. */
export function validateRange(range: Range, today: string): RangeErrors {
  const start = parseDay(range.start);
  const end = parseDay(range.end);
  const errors: RangeErrors = {};
  if (!(start >= parseDay(HLS_START))) errors.start = true;
  if (!(end <= parseDay(today))) errors.end = true;
  if (!errors.start && !errors.end && !(end >= start && (end - start) / DAY + 1 <= MAX_DAYS)) errors.span = true;
  return errors;
}

/**
 * NASA HLS vegetation observations (ABB-12) for the investigation point: every satellite
 * overpass, the ones hidden by clouds and the days with no clear view. Values come only from
 * /api/vegetation/hls; without them nothing is drawn.
 */
export function VegetationPanel({ point, year }: { point: { latitude: number; longitude: number } | null; year: string }) {
  const { t, num, lang } = useI18n();
  const [range, setRange] = useState<Range>({ start: '', end: '' });
  const [errors, setErrors] = useState<RangeErrors>({});
  const [status, setStatus] = useState<'idle' | 'loading' | 'error' | 'unavailable'>('idle');
  const [failure, setFailure] = useState('');
  const [data, setData] = useState<VegetationResponse | null>(null);
  const [showTable, setShowTable] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const startRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    // Suggest the spring of the incident year once; never overwrite what the person typed.
    if (/^\d{4}$/.test(year) && Number(year) >= 2014 && !range.start && !range.end) setRange({ start: `${year}-04-01`, end: `${year}-06-30` });
  }, [year]); // eslint-disable-line react-hooks/exhaustive-deps

  const dateFmt = new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
  const day = (s: string) => dateFmt.format(new Date(`${s}T00:00:00Z`));

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!point) return;
    const found = validateRange(range, new Date().toISOString().slice(0, 10));
    setErrors(found);
    if (Object.keys(found).length) {
      startRef.current?.focus();
      return;
    }
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setStatus('loading');
    try {
      setData(await api.vegetation({ ...point, ...range }, controller.signal));
      setStatus('idle');
    } catch (err) {
      if (controller.signal.aborted) return;
      setData(null);
      setFailure(errorText(err, t));
      setStatus(err instanceof ApiError && err.status === 503 ? 'unavailable' : 'error');
    }
  }

  const statusLabel = (s: string) => t(`veg.status.${s}` as MessageKey);
  const s = data?.summary;

  return (
    <section className="panel" aria-labelledby="veg-title">
      <div className="panel-head">
        <h2 id="veg-title">{t('veg.title')}</h2>
        <EvidenceLabel kind="OBSERVED" detail="NASA HLS" />
      </div>
      <p className="muted">{t('veg.lead')}</p>
      {!point ? (
        <StatusMessage tone="empty" title={t('veg.needPoint')} />
      ) : (
        <form onSubmit={submit} noValidate aria-label={t('veg.formLabel')}>
          <div className="form-row">
            <Field ref={startRef} type="date" label={t('veg.start')} name="veg-start" value={range.start} min={HLS_START}
                   onChange={(e) => setRange({ ...range, start: e.target.value })} error={errors.start ? t('veg.startError') : undefined} />
            <Field type="date" label={t('veg.end')} name="veg-end" value={range.end}
                   onChange={(e) => setRange({ ...range, end: e.target.value })}
                   error={errors.end ? t('veg.endError') : errors.span ? t('veg.spanError', { n: MAX_DAYS }) : undefined}
                   hint={t('veg.rangeHint', { n: MAX_DAYS })} />
          </div>
          <div className="actions">
            <Button type="submit" variant="secondary" busy={status === 'loading'}>{status === 'loading' ? t('veg.submitting') : t('veg.submit')}</Button>
          </div>
        </form>
      )}

      {status === 'loading' && <StatusMessage tone="loading" title={t('veg.submitting')}>{t('veg.slow')}</StatusMessage>}
      {status === 'unavailable' && <StatusMessage tone="pending" title={t('veg.unavailableTitle')}>{failure}</StatusMessage>}
      {status === 'error' && (
        <StatusMessage tone="error" title={t('veg.errorTitle')} action={<Button variant="secondary" onClick={() => submit()}>{t('state.retry')}</Button>}>
          {failure}
        </StatusMessage>
      )}

      {data && s && status !== 'loading' && (
        <>
          <p>{t('veg.summary', { total: s.acquisitions, valid: s.valid, obscured: s.obscured + s.no_data + s.not_read, start: day(data.start), end: day(data.end) })}</p>
          {s.acquisitions === 0 ? (
            <StatusMessage tone="empty" title={t('veg.noneTitle')}>{t('veg.noneBody')}</StatusMessage>
          ) : (
            <>
              {s.valid === 0 && <StatusMessage tone="partial" title={t('veg.noValidTitle')}>{t('veg.noValidBody')}</StatusMessage>}
              {s.not_read > 0 && <StatusMessage tone="partial" title={t('veg.notReadTitle', { n: s.not_read })}>{t('veg.notReadBody')}</StatusMessage>}
              <NdviChart data={data} />
              <p className="muted">{t('veg.caption')}</p>
            </>
          )}
          {data.gaps.length > 0 && (
            <div>
              <h3>{t('veg.gapsTitle', { days: s.gap_days, longest: s.longest_gap_days })}</h3>
              <ul className="veg-gaps">
                {data.gaps.map((g) => (
                  <li key={g.start}>
                    <EvidenceLabel kind="MISSING_DATA" symbolOnly />
                    {g.start === g.end ? day(g.start) : `${day(g.start)} – ${day(g.end)}`} · {t('veg.days', { n: g.days })}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {s.acquisitions > 0 && (
            <div className="actions">
              <Button variant="text" aria-expanded={showTable} aria-controls="veg-table" onClick={() => setShowTable((v) => !v)}>
                {showTable ? t('inv.hideTable') : t('inv.showTable')}
              </Button>
            </div>
          )}
          {showTable && (
            <div className="table-wrap" id="veg-table">
              <table className="data">
                <caption className="sr-only">{t('veg.tableCaption')}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t('veg.colDate')}</th>
                    <th scope="col">{t('veg.colSensor')}</th>
                    <th scope="col">{t('veg.colStatus')}</th>
                    <th scope="col">{t('veg.colNdvi')}</th>
                    <th scope="col">{t('veg.colClear')}</th>
                    <th scope="col">{t('veg.colReason')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.observations.map((o) => (
                    <tr key={`${o.product}-${o.acquired_at}`}>
                      <th scope="row">{day(o.date)}</th>
                      <td>{o.sensor}</td>
                      <td>{statusLabel(o.status)}</td>
                      <td>{o.ndvi === null ? t('inv.noData') : `${num(o.ndvi, { digits: 2 })} (${num(o.ndvi_min ?? o.ndvi, { digits: 2 })}–${num(o.ndvi_max ?? o.ndvi, { digits: 2 })})`}</td>
                      <td>{o.window_pixels ? `${o.pixels.clear}/${o.window_pixels}` : '–'}</td>
                      <td>{o.reason ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <SourceLabel
            name={t('veg.srcTitle')}
            kind="OBSERVED"
            rows={[
              { label: t('src.dataset'), value: data.dataset },
              { label: t('veg.srcProducts'), value: String(data.request_params.products ?? ''), mono: true },
              { label: t('src.point'), value: `${data.request_params.latitude}, ${data.request_params.longitude}`, mono: true },
              { label: t('src.period'), value: `${day(data.start)} – ${day(data.end)}` },
              { label: t('src.resolution'), value: data.spatial_resolution.description },
              { label: t('src.retrieved'), value: new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(data.retrieved_at)) },
              { label: t('src.checksum'), value: `${data.provenance.checksum_sha256.slice(0, 16)}…`, mono: true },
              { label: t('src.docs'), value: <a href={data.source_url} target="_blank" rel="noreferrer">lpdaac.usgs.gov <span className="sr-only">{t('ev.newTab')}</span></a> },
            ]}
            limitations={data.limitations.join(' ')}
          />
        </>
      )}
    </section>
  );
}
