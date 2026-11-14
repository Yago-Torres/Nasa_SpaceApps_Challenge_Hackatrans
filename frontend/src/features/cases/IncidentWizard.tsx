import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, LocateFixed, Plus, Trash2 } from 'lucide-react';
import { useI18n } from '../../i18n/I18n';
import type { MessageKey } from '../../i18n/messages';
import { Button, ButtonLink, Checkbox, EvidenceLabel, Field, PageHeader, RadioGroup, StatusMessage, TextArea } from '../../design/components';
import {
  STEPS, emptyCase, missingItems, newId, parseNumber, validateStep,
  type FieldError, type IncidentCase, type Rounding, type Step,
} from '../../cases/model';
import { caseRepository, StorageUnavailableError } from '../../cases/repository';
import { hrefFor, navigate } from '../../app/routes';
import { useInvestigation } from '../../app/investigation';
import { PrivacyPreview } from './PrivacyPreview';

type SaveState = { status: 'idle' | 'saving' | 'saved' | 'error'; at?: string; error?: string };

const ERROR_TEXT: Partial<Record<string, MessageKey>> = {
  title: 'f.titleError', latitude: 'f.latError', longitude: 'f.lonError', regionLabel: 'f.regionError',
  incidentYear: 'f.incidentYearError', symptomsStart: 'f.monthError', symptomsEnd: 'f.monthError', symptomsOrder: 'f.orderError',
  symptoms: 'f.symptomsError', affectedShare: 'f.shareError',
};

export function IncidentWizard({ caseId }: { caseId: string }) {
  const { t, lang } = useI18n();
  const repo = caseRepository();
  const { setInput } = useInvestigation();
  const [c, setC] = useState<IncidentCase | null>(caseId === 'new' ? emptyCase() : null);
  const [missing, setMissing] = useState(false);
  const [step, setStep] = useState(0);
  const [visited, setVisited] = useState(0);
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [save, setSave] = useState<SaveState>({ status: 'idle' });
  const [finished, setFinished] = useState(false);
  const [locating, setLocating] = useState<'idle' | 'busy' | 'denied' | 'unavailable'>('idle');
  const dirty = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (caseId === 'new') return;
    repo.get(caseId).then((found) => (found ? setC(found) : setMissing(true)), () => setMissing(true));
  }, [caseId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Autosave 600 ms after the last change. Draft data is saved even when a step has errors,
  // so nothing the farmer typed is ever lost.
  useEffect(() => {
    if (!c || !dirty.current) return;
    const id = window.setTimeout(() => persist(c), 600);
    return () => window.clearTimeout(id);
  }, [c]); // eslint-disable-line react-hooks/exhaustive-deps

  async function persist(current: IncidentCase): Promise<IncidentCase | null> {
    setSave({ status: 'saving' });
    try {
      const saved = await repo.save(current);
      dirty.current = false;
      setC((prev) => (prev && prev.id === saved.id ? { ...prev, version: saved.version, updatedAt: saved.updatedAt } : prev));
      if (caseId === 'new') window.history.replaceState(null, '', hrefFor('cases', saved.id));
      setSave({ status: 'saved', at: new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { hour: '2-digit', minute: '2-digit' }).format(new Date()) });
      return saved;
    } catch (err) {
      setSave({ status: 'error', error: err instanceof StorageUnavailableError ? t('cases.storageError') : String(err) });
      return null;
    }
  }

  if (missing) {
    return (
      <>
        <PageHeader title={t('wiz.titleEdit')} />
        <StatusMessage tone="error" title={t('cases.notFound')} action={<ButtonLink href={hrefFor('cases')}>{t('nav.cases')}</ButtonLink>} />
      </>
    );
  }
  if (!c) return <StatusMessage tone="loading" title={t('state.loading')} />;

  const current: Step = STEPS[step];
  const update = (patch: Partial<IncidentCase>) => {
    dirty.current = true;
    setC((prev) => (prev ? { ...prev, ...patch } : prev));
  };
  const updateLoc = (patch: Partial<IncidentCase['location']>) => update({ location: { ...c.location, ...patch } });
  const err = (key: FieldError) => (errors.includes(key) ? t(ERROR_TEXT[key] ?? (key.endsWith('.year') ? 'f.cropYearError' : 'f.cropError')) : undefined);
  const clearErr = (key: FieldError) => errors.includes(key) && setErrors(errors.filter((e) => e !== key));

  function focusFirst(list: FieldError[]) {
    const key = list[0] === 'symptomsOrder' ? 'symptomsEnd' : list[0];
    requestAnimationFrame(() => formRef.current?.querySelector<HTMLElement>(`[data-field="${key}"]`)?.focus());
  }

  function goTo(i: number) {
    setErrors([]);
    setStep(i);
    requestAnimationFrame(() => formRef.current?.querySelector<HTMLElement>('h2')?.focus());
  }

  function next() {
    const found = validateStep(c!, current);
    setErrors(found);
    if (found.length) return focusFirst(found);
    const n = Math.min(step + 1, STEPS.length - 1);
    setVisited((v) => Math.max(v, n));
    goTo(n);
  }

  async function finish() {
    for (let i = 0; i < STEPS.length; i++) {
      const found = validateStep(c!, STEPS[i]);
      if (found.length) {
        setStep(i);
        setErrors(found);
        return focusFirst(found);
      }
    }
    const saved = await persist(c!);
    if (saved) setFinished(true);
  }

  function useMyLocation() {
    if (!('geolocation' in navigator)) return setLocating('unavailable');
    setLocating('busy');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        updateLoc({ latitude: pos.coords.latitude.toFixed(4), longitude: pos.coords.longitude.toFixed(4) });
        setErrors(errors.filter((e) => e !== 'latitude' && e !== 'longitude'));
        setLocating('idle');
      },
      (e) => setLocating(e.code === e.PERMISSION_DENIED ? 'denied' : 'unavailable'),
      { enableHighAccuracy: false, timeout: 15000 },
    );
  }

  function investigate() {
    setInput({ latitude: c!.location.latitude, longitude: c!.location.longitude, year: c!.incidentYear });
    navigate('investigation');
  }

  const saveText =
    save.status === 'saving' ? t('wiz.saving')
    : save.status === 'saved' ? t('wiz.saved', { time: save.at ?? '' })
    : save.status === 'error' ? t('wiz.saveError', { error: save.error ?? '' }) : '';

  return (
    <>
      <PageHeader title={caseId === 'new' ? t('wiz.titleNew') : t('wiz.titleEdit')} lead={t('wiz.lead')} />
      <StatusMessage tone="pending" title={t('cases.devTitle')}>{t('cases.devBody')}</StatusMessage>

      <div className="wizard">
        <nav aria-label={t('wiz.stepsLabel')}>
          <ol className="stepper">
            {STEPS.map((s, i) => (
              <li key={s} className={i < step ? 'done' : undefined}>
                <button type="button" onClick={() => goTo(i)} disabled={i > visited} aria-current={i === step ? 'step' : undefined}>
                  <span className="n" aria-hidden="true">{i < step ? <Check /> : i + 1}</span>
                  <span>{t(`wiz.step.${s}` as MessageKey)}</span>
                </button>
              </li>
            ))}
          </ol>
        </nav>

        <form ref={formRef} className="panel wizard-form" noValidate onSubmit={(e) => { e.preventDefault(); if (current === 'review') void finish(); else next(); }}>
          <div className="panel-head">
            <h2 tabIndex={-1}>{t(`wiz.step.${current}` as MessageKey)}</h2>
            {current !== 'review' && current !== 'location' && <EvidenceLabel kind="FARMER_REPORTED" />}
          </div>
          {current !== 'review' && <p className="muted">{t('wiz.farmerNote')}</p>}
          {errors.length > 0 && <p className="sr-only" role="alert">{t('wiz.fixErrors', { n: errors.length })}</p>}

          {current === 'location' && (
            <>
              <Field label={t('f.title')} name="title" data-field="title" value={c.title} maxLength={120} hint={t('f.titleHint')} error={err('title')}
                onChange={(e) => { update({ title: e.target.value }); clearErr('title'); }} />
              <RadioGroup legend={t('f.tier')} name="tier" value={c.location.tier} onChange={(tier) => updateLoc({ tier })}
                options={[
                  { value: 'private', label: t('f.tier.private'), hint: t('f.tier.privateHint') },
                  { value: 'rounded', label: t('f.tier.rounded'), hint: t('f.tier.roundedHint') },
                  { value: 'region', label: t('f.tier.region'), hint: t('f.tier.regionHint') },
                ]} />
              {c.location.tier === 'rounded' && (
                <RadioGroup legend={t('f.rounding')} name="rounding" value={String(c.location.rounding) as `${Rounding}`} onChange={(v) => updateLoc({ rounding: Number(v) as Rounding })}
                  options={(['0.1', '0.5', '1'] as const).map((v) => ({ value: v, label: t(`f.round.${v}` as MessageKey) }))} />
              )}
              {c.location.tier === 'region' && (
                <Field label={t('f.region')} name="regionLabel" data-field="regionLabel" value={c.location.regionLabel} maxLength={120} hint={t('f.regionHint')} error={err('regionLabel')}
                  onChange={(e) => { updateLoc({ regionLabel: e.target.value }); clearErr('regionLabel'); }} />
              )}
              <div className="form-row form-row--2">
                <Field label={t('f.lat')} name="latitude" data-field="latitude" inputMode="decimal" unit="°" value={c.location.latitude} hint={t('f.coordsHint')} error={err('latitude')}
                  onChange={(e) => { updateLoc({ latitude: e.target.value }); clearErr('latitude'); }} />
                <Field label={t('f.lon')} name="longitude" data-field="longitude" inputMode="decimal" unit="°" value={c.location.longitude} error={err('longitude')}
                  onChange={(e) => { updateLoc({ longitude: e.target.value }); clearErr('longitude'); }} />
              </div>
              <div className="actions">
                <Button variant="text" onClick={useMyLocation} busy={locating === 'busy'} icon={<LocateFixed aria-hidden="true" />}>
                  {locating === 'busy' ? t('f.locating') : t('f.useLocation')}
                </Button>
              </div>
              {locating === 'denied' && <StatusMessage tone="partial" title={t('f.locationDenied')} />}
              {locating === 'unavailable' && <StatusMessage tone="partial" title={t('f.locationUnavailable')} />}
              <Checkbox name="consentPrecise" label={t('f.consent')} hint={t('f.consentHint')} checked={c.location.consentPrecise} onChange={(v) => updateLoc({ consentPrecise: v })} />
              <PrivacyPreview location={c.location} />
            </>
          )}

          {current === 'crops' && (
            <>
              <p className="muted">{t('f.cropsHint')}</p>
              <ol className="crop-rows">
                {c.crops.map((row, i) => {
                  const set = (patch: Partial<typeof row>) => update({ crops: c.crops.map((r) => (r.id === row.id ? { ...r, ...patch } : r)) });
                  return (
                    <li key={row.id} className="crop-row">
                      <Field label={t('f.cropYear')} name={`crop-year-${i}`} data-field={`crop.${i}.year`} inputMode="numeric" value={row.year} error={err(`crop.${i}.year`)}
                        onChange={(e) => { set({ year: e.target.value }); clearErr(`crop.${i}.year`); }} />
                      <Field label={t('f.crop')} name={`crop-${i}`} data-field={`crop.${i}.crop`} value={row.crop} maxLength={80} error={err(`crop.${i}.crop`)}
                        onChange={(e) => { set({ crop: e.target.value }); clearErr(`crop.${i}.crop`); }} />
                      <Field label={t('f.cropNotes')} name={`crop-notes-${i}`} value={row.notes} maxLength={200} onChange={(e) => set({ notes: e.target.value })} />
                      {c.crops.length > 1 && (
                        <Button variant="text" className="crop-remove" aria-label={t('f.removeYear', { n: i + 1 })} icon={<Trash2 aria-hidden="true" />}
                          onClick={() => { update({ crops: c.crops.filter((r) => r.id !== row.id) }); setErrors([]); }}>
                          <span className="sr-only">{t('f.removeYear', { n: i + 1 })}</span>
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ol>
              <div className="actions">
                <Button variant="secondary" icon={<Plus aria-hidden="true" />} onClick={() => update({ crops: [...c.crops, { id: newId('y'), year: '', crop: '', notes: '' }] })}>{t('f.addYear')}</Button>
              </div>
            </>
          )}

          {current === 'incident' && (
            <>
              <Field label={t('f.incidentYear')} name="incidentYear" data-field="incidentYear" inputMode="numeric" value={c.incidentYear} hint={t('f.incidentYearHint')} error={err('incidentYear')}
                onChange={(e) => { update({ incidentYear: e.target.value }); clearErr('incidentYear'); }} />
              <div className="form-row form-row--2">
                <Field label={t('f.symptomsStart')} name="symptomsStart" data-field="symptomsStart" type="month" value={c.symptomsStart} hint={t('f.monthHint')} error={err('symptomsStart')}
                  onChange={(e) => { update({ symptomsStart: e.target.value }); clearErr('symptomsStart'); clearErr('symptomsOrder'); }} />
                <Field label={t('f.symptomsEnd')} name="symptomsEnd" data-field="symptomsEnd" type="month" value={c.symptomsEnd} hint={t('f.monthHint')} error={err('symptomsEnd') ?? err('symptomsOrder')}
                  onChange={(e) => { update({ symptomsEnd: e.target.value }); clearErr('symptomsEnd'); clearErr('symptomsOrder'); }} />
              </div>
              <TextArea label={t('f.symptoms')} name="symptoms" data-field="symptoms" value={c.symptoms} maxLength={2000} hint={t('f.symptomsHint')} error={err('symptoms')} className="voice-input"
                onChange={(e) => { update({ symptoms: e.target.value }); clearErr('symptoms'); }} />
              <Field label={t('f.share')} name="affectedShare" data-field="affectedShare" inputMode="decimal" unit="%" value={c.affectedShare} error={err('affectedShare')}
                onChange={(e) => { update({ affectedShare: e.target.value }); clearErr('affectedShare'); }} />
            </>
          )}

          {current === 'constraints' && (
            <>
              <RadioGroup legend={t('f.water')} name="water" value={c.constraints.water || 'none'}
                onChange={(v) => update({ constraints: { ...c.constraints, water: v === 'none' ? '' : v } })}
                options={[
                  { value: 'none', label: t('f.water.none') }, { value: 'irrigated', label: t('f.water.irrigated') },
                  { value: 'rainfed', label: t('f.water.rainfed') }, { value: 'mixed', label: t('f.water.mixed') },
                ]} />
              <Checkbox name="soilKnown" label={t('f.soilKnown')} checked={c.constraints.soilKnown} onChange={(v) => update({ constraints: { ...c.constraints, soilKnown: v } })} />
              {c.constraints.soilKnown && (
                <TextArea label={t('f.soilNotes')} name="soilNotes" rows={2} value={c.constraints.soilNotes} maxLength={500} onChange={(e) => update({ constraints: { ...c.constraints, soilNotes: e.target.value } })} />
              )}
              <TextArea label={t('f.priorities')} name="priorities" rows={2} value={c.constraints.priorities} maxLength={500} hint={t('f.prioritiesHint')}
                onChange={(e) => update({ constraints: { ...c.constraints, priorities: e.target.value } })} />
            </>
          )}

          {current === 'review' && <Review c={c} />}

          {finished && (
            <StatusMessage tone="ok" title={t('wiz.saved', { time: save.at ?? '' })}
              action={
                <div className="actions">
                  {Number.isFinite(parseNumber(c.incidentYear)) && <Button variant="primary" icon={<ArrowRight className="go" aria-hidden="true" />} onClick={investigate}>{t('wiz.toInvestigation')}</Button>}
                  <ButtonLink href={hrefFor('cases')}>{t('nav.cases')}</ButtonLink>
                </div>
              } />
          )}

          <div className="wizard-bar">
            {step > 0 && <Button variant="secondary" icon={<ArrowLeft aria-hidden="true" />} onClick={() => goTo(step - 1)}>{t('wiz.back')}</Button>}
            {!finished && (
              <Button type="submit" variant="primary">
                {current === 'review' ? t('wiz.finish') : t('wiz.next')}
              </Button>
            )}
            <span className={`save-state save-state--${save.status}`} role="status" aria-live="polite">{saveText}</span>
          </div>
        </form>
      </div>
    </>
  );
}

function Review({ c }: { c: IncidentCase }) {
  const { t } = useI18n();
  const gaps = missingItems(c);
  const rows: [string, string][] = [
    [t('f.title'), c.title],
    [t('f.incidentYear'), c.incidentYear],
    [t('wiz.step.crops'), t('rev.years', { n: c.crops.filter((r) => r.crop.trim()).length })],
    [t('f.symptoms'), c.symptoms],
  ];
  return (
    <>
      <section aria-labelledby="rev-sum" className="review-block">
        <h3 id="rev-sum">{t('rev.summary')}</h3>
        <dl className="review-list">
          {rows.map(([k, v]) => (
            <div key={k}><dt>{k}</dt><dd>{v.trim() ? v : t('rev.notStated')}</dd></div>
          ))}
        </dl>
      </section>
      <section aria-labelledby="rev-missing" className="review-block">
        <h3 id="rev-missing">{t('rev.missingTitle')}</h3>
        {gaps.length === 0 ? (
          <StatusMessage tone="ok" title={t('rev.complete')} />
        ) : (
          <>
            <ul className="gap-list">
              {gaps.map((g) => (
                <li key={g}><EvidenceLabel kind="MISSING_DATA" symbolOnly /> {t(`rev.missing.${g}` as MessageKey)}</li>
              ))}
            </ul>
            <p className="muted">{t('rev.missingHint')}</p>
          </>
        )}
      </section>
      <PrivacyPreview location={c.location} />
    </>
  );
}
