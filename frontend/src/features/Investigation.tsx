import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowRight } from 'lucide-react';
import { api } from '../api/client';
import { useI18n } from '../i18n/I18n';
import type { MessageKey } from '../i18n/messages';
import { Button, ButtonLink, EvidenceLabel, Field, PageHeader, SourceLabel, StatusMessage } from '../design/components';
import { REFERENCE, useInvestigation, validateInput, type FieldErrors } from '../app/investigation';
import { hrefFor } from '../app/routes';
import { AnomalyChart } from './AnomalyChart';
import { errorText } from './errors';
import { VegetationPanel } from './vegetation/VegetationPanel';
import { PrecipitationPanel } from './precipitation/PrecipitationPanel';

export function Investigation() {
  const { t, num } = useI18n();
  const { input, setInput, climate, setClimate } = useInvestigation();
  const [errors, setErrors] = useState<FieldErrors>({});
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const [failure, setFailure] = useState('');
  const [showTable, setShowTable] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const refs = { latitude: useRef<HTMLInputElement>(null), longitude: useRef<HTMLInputElement>(null), year: useRef<HTMLInputElement>(null) };

  useEffect(() => () => abort.current?.abort(), []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const { errors: found, value } = validateInput(input);
    setErrors(found);
    if (!value) {
      const first = (['latitude', 'longitude', 'year'] as const).find((k) => found[k]);
      if (first) refs[first].current?.focus();
      return;
    }
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setStatus('loading');
    try {
      const data = await api.climate(
        { latitude: value.latitude, longitude: value.longitude, eventYear: value.year, referenceStart: REFERENCE.start, referenceEnd: REFERENCE.end },
        controller.signal,
      );
      setClimate(data);
      setStatus('idle');
    } catch (err) {
      if (controller.signal.aborted) return;
      setClimate(null); // never keep an older record that no longer matches the inputs
      setFailure(errorText(err, t));
      setStatus('error');
    }
  }

  const update = (key: keyof typeof input) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setInput({ ...input, [key]: e.target.value });
    if (errors[key]) setErrors({ ...errors, [key]: undefined });
  };

  const missing = climate?.monthly.filter((m) => m.precipitation_anomaly_mm === null || m.max_temperature_anomaly_c === null) ?? [];
  const monthName = (m: number) => t(`month.${m}` as MessageKey);
  const fmt = (v: number | null, digits = 1, signed = false) => (v === null ? t('inv.noData') : num(v, { digits, signed }));

  return (
    <>
      <PageHeader title={t('inv.title')} lead={t('inv.lead')} />

      <form className="panel" onSubmit={submit} noValidate aria-labelledby="inv-form">
        <h2 id="inv-form">{t('inv.formTitle')}</h2>
        <div className="form-row">
          <Field ref={refs.latitude} label={t('inv.lat')} name="latitude" inputMode="decimal" unit="°" value={input.latitude} onChange={update('latitude')} placeholder="41.6" error={errors.latitude ? t('inv.latError') : undefined} />
          <Field ref={refs.longitude} label={t('inv.lon')} name="longitude" inputMode="decimal" unit="°" value={input.longitude} onChange={update('longitude')} placeholder="-0.9" error={errors.longitude ? t('inv.lonError') : undefined} />
          <Field ref={refs.year} label={t('inv.year')} name="year" inputMode="numeric" value={input.year} onChange={update('year')} placeholder="2022" hint={t('inv.yearHint')} error={errors.year ? t('inv.yearError') : undefined} />
        </div>
        <p className="muted">{t('inv.reference')}</p>
        <p className="muted">{t('inv.privacy')}</p>
        <div className="actions">
          <Button type="submit" variant={climate ? 'secondary' : 'primary'} busy={status === 'loading'}>{status === 'loading' ? t('inv.submitting') : t('inv.submit')}</Button>
        </div>
        {Object.keys(errors).some((k) => errors[k as keyof FieldErrors]) && <p className="sr-only" role="alert">{t('inv.fixFields')}</p>}
      </form>

      {status === 'loading' && <StatusMessage tone="loading" title={t('inv.submitting')} />}
      {status === 'error' && (
        <StatusMessage tone="error" title={t('inv.errorTitle')} action={<Button variant="secondary" onClick={(e) => submit(e as unknown as FormEvent)}>{t('state.retry')}</Button>}>
          {failure}
        </StatusMessage>
      )}
      {status === 'idle' && !climate && <StatusMessage tone="empty" title={t('inv.emptyTitle')}>{t('inv.emptyBody')}</StatusMessage>}

      {climate && status !== 'loading' && (
        <div className="grid-2">
          <section className="panel" aria-labelledby="inv-result">
            <div className="panel-head">
              <h2 id="inv-result">{t('inv.resultTitle', { year: climate.event_year, start: climate.reference_start, end: climate.reference_end })}</h2>
              <EvidenceLabel kind="OBSERVED" detail="NASA POWER" />
            </div>
            <p className="muted">{t('inv.scope')}</p>
            {missing.length > 0 && (
              <StatusMessage tone="partial" title={t('inv.partialTitle')}>
                {t('inv.partialBody', { months: missing.map((m) => monthName(m.month)).join(', ') })}
              </StatusMessage>
            )}
            <AnomalyChart monthly={climate.monthly} eventYear={climate.event_year} />
            <p className="muted">{t('inv.chartCaption', { start: climate.reference_start, end: climate.reference_end })}</p>
            <div className="actions">
              <Button variant="text" aria-expanded={showTable} aria-controls="inv-table" onClick={() => setShowTable((s) => !s)}>
                {showTable ? t('inv.hideTable') : t('inv.showTable')}
              </Button>
            </div>
            {showTable && (
              <div className="table-wrap" id="inv-table">
                <table className="data">
                  <caption className="sr-only">{t('inv.chartTitle', { year: climate.event_year })}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t('inv.colMonth')}</th>
                      <th scope="col">{t('inv.colRain')}</th>
                      <th scope="col">{t('inv.colRainRef')}</th>
                      <th scope="col">{t('inv.colRainDiff')}</th>
                      <th scope="col">{t('inv.colTmaxDiff')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {climate.monthly.map((m) => (
                      <tr key={m.month}>
                        <th scope="row">{monthName(m.month)}</th>
                        <td>{fmt(m.precipitation_mm)}</td>
                        <td>{fmt(m.reference_precipitation_mm)}</td>
                        <td>{fmt(m.precipitation_anomaly_mm, 1, true)}</td>
                        <td>{fmt(m.max_temperature_anomaly_c, 1, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="actions">
              <ButtonLink variant="primary" href={hrefFor('evidence')} icon={<ArrowRight className="go" aria-hidden="true" />}>{t('inv.next')}</ButtonLink>
            </div>
          </section>

          <SourceLabel
            name={t('src.title')}
            kind="OBSERVED"
            rows={[
              { label: t('src.dataset'), value: climate.dataset },
              { label: t('src.parameters'), value: String(climate.request_params.parameters ?? ''), mono: true },
              { label: t('src.point'), value: `${climate.request_params.latitude}, ${climate.request_params.longitude}`, mono: true },
              { label: t('src.period'), value: `${climate.event_year} · ${climate.reference_start}–${climate.reference_end}` },
              { label: t('src.resolution'), value: <EvidenceLabel kind="MISSING_DATA" detail={t('src.notReturned')} /> },
              { label: t('src.retrieved'), value: <EvidenceLabel kind="MISSING_DATA" detail={t('src.notReturned')} /> },
              { label: t('src.checksum'), value: `${climate.data_sha256.slice(0, 16)}…`, mono: true },
              { label: t('src.docs'), value: <a href={climate.source_url} target="_blank" rel="noreferrer">power.larc.nasa.gov <span className="sr-only">{t('ev.newTab')}</span></a> },
            ]}
            limitations={climate.disclaimer}
          />
        </div>
      )}

      <PrecipitationPanel point={validateInput(input).value ?? null} year={input.year} />

      <VegetationPanel point={validateInput(input).value ?? null} year={input.year} />
    </>
  );
}
