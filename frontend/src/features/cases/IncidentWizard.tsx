import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, LocateFixed, Plus, Trash2 } from 'lucide-react';
import { useI18n } from '../../i18n/I18n';
import type { MessageKey } from '../../i18n/messages';
import { Button, ButtonLink, Checkbox, EvidenceLabel, Field, PageHeader, RadioGroup, StatusMessage, TextArea } from '../../design/components';
import {
  MAX_CROP_ROWS, STEPS, canEdit, displayedLocation, emptyCase, missingItems, monthOutOfRange, newId, parseNumber, validateStep,
  type FieldError, type IncidentCase, type Rounding, type Step,
} from '../../cases/model';
import { readyForServer } from '../../cases/mapping';
import { CaseConflictError, caseRepository } from '../../cases/repository';
import { getSession, useSession } from '../../api/session';
import { hrefFor, navigate } from '../../app/routes';
import { useInvestigation } from '../../app/investigation';
import { AuthPanel } from '../account/AuthPanel';
import { CaseTitleBlock } from './CaseTitleBlock';
import { LocationMap, viewerLocationForReadOnlyCase } from './LocationMap';
import { PrivacyPreview } from './PrivacyPreview';
import { caseErrorText, isStorageUnavailable, isUnauthorized } from './caseErrors';

type SaveState = { status: 'idle' | 'saving' | 'saved' | 'error'; at?: string; error?: string };
type LoadState = { status: 'loading' | 'missing' | 'unavailable' | 'error'; error?: string };
type Meta = Pick<IncidentCase, 'id' | 'version' | 'updatedAt' | 'server'>;

const metaOf = ({ id, version, updatedAt, server }: IncidentCase): Meta => ({ id, version, updatedAt, server });

const ERROR_TEXT: Partial<Record<string, MessageKey>> = {
  title: 'f.titleError', latitude: 'f.latError', longitude: 'f.lonError', regionLabel: 'f.regionError',
  incidentYear: 'f.incidentYearError', symptomsStart: 'f.monthError', symptomsEnd: 'f.monthError', symptomsOrder: 'f.orderError',
  symptomsRange: 'f.rangeError', symptoms: 'f.symptomsError', affectedShare: 'f.shareError',
};

/**
 * Five-step incident wizard (ABB-21) saving to /api/v1/cases (ABB-06). Nothing typed is lost:
 * drafts the API cannot accept yet, a signed-out user or a failed save keep the answers on
 * the page; a version conflict asks the user which version to keep.
 */
export function IncidentWizard({ caseId }: { caseId: string }) {
  const { t, lang } = useI18n();
  const session = useSession();
  const repo = caseRepository();
  const { setInput } = useInvestigation();
  const [c, setC] = useState<IncidentCase | null>(caseId === 'new' ? emptyCase() : null);
  const [load, setLoad] = useState<LoadState>({ status: 'loading' });
  const [reload, setReload] = useState(0);
  const [step, setStep] = useState(0);
  const [visited, setVisited] = useState(0);
  const [errors, setErrors] = useState<FieldError[]>([]);
  const [save, setSave] = useState<SaveState>({ status: 'idle' });
  const [conflict, setConflict] = useState<IncidentCase | null>(null);
  const [finished, setFinished] = useState(false);
  const [locating, setLocating] = useState<'idle' | 'busy' | 'denied' | 'unavailable'>('idle');
  const dirty = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);
  const cRef = useRef(c);
  cRef.current = c;
  // Authoritative server identity and version, updated synchronously after each save.
  const meta = useRef<Meta | null>(null);
  // Saves run one at a time, so a slow create can never be sent twice.
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const everSignedIn = useRef(!!session);
  if (session) everSignedIn.current = true;
  // Focus requested by a step change or a validation error. Applied right after the render
  // that shows the target (not in a later animation frame), so focus never jumps away while
  // the user has already started typing in the new step.
  const [focusRequest, setFocusRequest] = useState<{ selector: string } | null>(null);

  useEffect(() => {
    if (focusRequest) formRef.current?.querySelector<HTMLElement>(focusRequest.selector)?.focus();
  }, [focusRequest]);

  useEffect(() => {
    if (caseId === 'new' || cRef.current || !session) return;
    let live = true;
    setLoad({ status: 'loading' });
    repo.get(caseId).then(
      (found) => {
        if (!live) return;
        if (!found) return setLoad({ status: 'missing' });
        meta.current = metaOf(found);
        setC(found);
      },
      (err) => {
        if (!live || isUnauthorized(err)) return; // signed out: the sign-in panel shows
        setLoad(isStorageUnavailable(err) ? { status: 'unavailable' } : { status: 'error', error: caseErrorText(err, t) });
      },
    );
    return () => {
      live = false;
    };
  }, [caseId, session, reload]); // eslint-disable-line react-hooks/exhaustive-deps

  // Autosave 600 ms after the last change, once the API can accept the case.
  useEffect(() => {
    if (!c || !dirty.current || !session || conflict || !canEdit(c) || !readyForServer(c)) return;
    const id = window.setTimeout(() => void persist(), 600);
    return () => window.clearTimeout(id);
  }, [c, session, conflict]); // eslint-disable-line react-hooks/exhaustive-deps

  function persist(): Promise<IncidentCase | null> {
    const run = queue.current.then(saveNow);
    queue.current = run;
    return run;
  }

  async function saveNow(): Promise<IncidentCase | null> {
    const draft = cRef.current;
    if (!draft || !getSession()) return null;
    const current = meta.current ? { ...draft, ...meta.current } : draft;
    if (!readyForServer(current)) return null;
    dirty.current = false;
    setSave({ status: 'saving' });
    try {
      const saved = await repo.save(current);
      meta.current = metaOf(saved);
      setC((prev) => (prev ? { ...prev, ...meta.current } : prev));
      if (saved.id !== caseId) window.history.replaceState(null, '', hrefFor('cases', saved.id));
      setSave({ status: 'saved', at: new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { hour: '2-digit', minute: '2-digit' }).format(new Date()) });
      return saved;
    } catch (err) {
      dirty.current = true;
      if (err instanceof CaseConflictError) {
        setConflict(err.latest);
        setSave({ status: 'idle' });
      } else {
        setSave({ status: 'error', error: caseErrorText(err, t) });
      }
      return null;
    }
  }

  function loadSaved() {
    if (!conflict) return;
    repo.adopt(conflict);
    meta.current = metaOf(conflict);
    dirty.current = false;
    setC(conflict);
    setConflict(null);
    setSave({ status: 'idle' });
  }

  function keepMine() {
    if (!conflict) return;
    repo.adopt(conflict);
    meta.current = metaOf(conflict);
    setC((prev) => (prev ? { ...prev, ...meta.current } : prev));
    setConflict(null);
    void persist();
  }

  const authPanel = !session && (
    <AuthPanel primary={c === null} notice={everSignedIn.current ? t('auth.sessionEnded') : c ? t('auth.signInToSave') : undefined} />
  );

  if (!c) {
    const header = <PageHeader title={t('wiz.titleEdit')} />;
    if (!session) return <>{header}{authPanel}</>;
    if (load.status === 'missing') {
      return <>{header}<StatusMessage tone="error" title={t('cases.notFound')} action={<ButtonLink href={hrefFor('cases')}>{t('nav.cases')}</ButtonLink>} /></>;
    }
    if (load.status === 'unavailable' || load.status === 'error') {
      return (
        <>
          {header}
          <StatusMessage tone="error" title={load.status === 'unavailable' ? t('cases.storageUnavailable') : load.error ?? t('state.unknownError')}
            action={<Button onClick={() => setReload((n) => n + 1)}>{t('state.retry')}</Button>}>
            {load.status === 'unavailable' ? t('cases.storageUnavailableBody') : undefined}
          </StatusMessage>
        </>
      );
    }
    return <StatusMessage tone="loading" title={t('state.loading')} />;
  }

  if (!canEdit(c)) return <ReadOnlyCase c={c} />;

  const current: Step = STEPS[step];
  const update = (patch: Partial<IncidentCase>) => {
    dirty.current = true;
    setFinished(false);
    setC((prev) => (prev ? { ...prev, ...patch } : prev));
  };
  const updateLoc = (patch: Partial<IncidentCase['location']>) => update({ location: { ...c.location, ...patch } });
  const err = (key: FieldError) => (errors.includes(key) ? t(ERROR_TEXT[key] ?? (key.endsWith('.year') ? 'f.cropYearError' : 'f.cropError')) : undefined);
  const rangeErr = (month: string) => (errors.includes('symptomsRange') && monthOutOfRange(month) ? t('f.rangeError') : undefined);
  const clearErr = (...keys: FieldError[]) => keys.some((k) => errors.includes(k)) && setErrors(errors.filter((e) => !keys.includes(e)));

  function focusFirst(list: FieldError[]) {
    let key: string = list[0];
    if (key === 'symptomsOrder') key = 'symptomsEnd';
    if (key === 'symptomsRange') key = monthOutOfRange(c!.symptomsStart) ? 'symptomsStart' : 'symptomsEnd';
    setFocusRequest({ selector: `[data-field="${key}"]` }); // new object: always applied once, after the errors render
  }

  function goTo(i: number) {
    setErrors([]);
    setStep(i);
    setFocusRequest({ selector: 'h2' });
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
    if (!getSession()) return;
    const saved = await persist();
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

  const ready = readyForServer(c);
  const saveText =
    !session ? ''
    : save.status === 'saving' ? t('wiz.saving')
    : save.status === 'error' ? t('wiz.saveError', { error: save.error ?? '' })
    : !ready && (dirty.current || !c.server) ? t('wiz.notReady')
    : save.status === 'saved' ? t('wiz.saved', { time: save.at ?? '' }) : '';

  return (
    <>
      {c.server ? <CaseTitleBlock c={c} lead={t('wiz.lead')} /> : <PageHeader title={t('wiz.titleNew')} lead={t('wiz.lead')} />}
      {authPanel}
      {conflict && (
        <StatusMessage tone="error" title={t('wiz.conflictTitle')}
          action={
            <div className="actions">
              <Button variant="secondary" onClick={loadSaved}>{t('wiz.conflictLoad')}</Button>
              <Button variant="text" onClick={keepMine}>{t('wiz.conflictKeep')}</Button>
            </div>
          }>
          {t('wiz.conflictBody', { version: conflict.version })}
        </StatusMessage>
      )}
      {c.server && c.server.fieldCount > 1 && <StatusMessage tone="partial" title={t('cases.parcels', { n: c.server.fieldCount })} />}

      <div className="wizard">
        <nav aria-label={t('wiz.stepsLabel')}>
          <ol className="stepper">
            {STEPS.map((s, i) => (
              <li key={s} className={i < step ? 'done' : undefined}>
                <button type="button" onClick={() => goTo(i)} disabled={i > visited && !c.server} aria-current={i === step ? 'step' : undefined}>
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
              {/* Editing your own case: you are always authorized to see the exact point (ADR-0004). */}
              <LocationMap viewer={displayedLocation(c.location, 'owner')} />
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
              {c.crops.length < MAX_CROP_ROWS && (
                <div className="actions">
                  <Button variant="secondary" icon={<Plus aria-hidden="true" />} onClick={() => update({ crops: [...c.crops, { id: newId('y'), year: '', crop: '', notes: '' }] })}>{t('f.addYear')}</Button>
                </div>
              )}
            </>
          )}

          {current === 'incident' && (
            <>
              <Field label={t('f.incidentYear')} name="incidentYear" data-field="incidentYear" inputMode="numeric" value={c.incidentYear} hint={t('f.incidentYearHint')} error={err('incidentYear')}
                onChange={(e) => { update({ incidentYear: e.target.value }); clearErr('incidentYear'); }} />
              <div className="form-row form-row--2">
                <Field label={t('f.symptomsStart')} name="symptomsStart" data-field="symptomsStart" type="month" value={c.symptomsStart} hint={t('f.monthHint')}
                  error={err('symptomsStart') ?? rangeErr(c.symptomsStart)}
                  onChange={(e) => { update({ symptomsStart: e.target.value }); clearErr('symptomsStart', 'symptomsOrder', 'symptomsRange'); }} />
                <Field label={t('f.symptomsEnd')} name="symptomsEnd" data-field="symptomsEnd" type="month" value={c.symptomsEnd} hint={t('f.monthHint')}
                  error={err('symptomsEnd') ?? err('symptomsOrder') ?? rangeErr(c.symptomsEnd)}
                  onChange={(e) => { update({ symptomsEnd: e.target.value }); clearErr('symptomsEnd', 'symptomsOrder', 'symptomsRange'); }} />
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
              <Button type="submit" variant="primary" busy={current === 'review' && save.status === 'saving'}>
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

/** Reviewers, viewers, and cases that are reviewed, final or archived: read-only, location as the server returned it. */
function ReadOnlyCase({ c }: { c: IncidentCase }) {
  const { t } = useI18n();
  const s = c.server!;
  const reason = s.archived ? t('wiz.readOnlyArchived')
    : s.myRole === 'REVIEWER' || s.myRole === 'VIEWER' ? t('wiz.readOnlyRole', { role: t(`case.role.${s.myRole}` as MessageKey) })
    : t('wiz.readOnlyStatus', { status: t(`case.status.${s.status}` as MessageKey) });
  const notStated = t('rev.notStated');
  const months = [c.symptomsStart, c.symptomsEnd].filter(Boolean).join(' – ');
  const water = c.constraints.water ? t(`f.water.${c.constraints.water}` as MessageKey) : notStated;
  const crops = c.crops.filter((r) => r.crop.trim()).map((r) => `${r.year ? `${r.year}: ` : ''}${r.crop}${r.notes ? ` (${r.notes})` : ''}`).join('\n');
  return (
    <>
      <CaseTitleBlock c={c} />
      <StatusMessage tone="pending" title={reason} action={<ButtonLink href={hrefFor('cases')}>{t('nav.cases')}</ButtonLink>} />
      <section className="panel" aria-labelledby="ro-sum">
        <div className="panel-head">
          <h2 id="ro-sum">{t('rev.summary')}</h2>
          <EvidenceLabel kind="FARMER_REPORTED" />
        </div>
        <dl className="review-list">
          <div><dt>{t('f.incidentYear')}</dt><dd className="num">{c.incidentYear || notStated}</dd></div>
          <div><dt>{t('rev.missing.symptomDates')}</dt><dd className="num">{months || notStated}</dd></div>
          <div><dt>{t('f.symptoms')}</dt><dd className={c.symptoms.trim() ? 'voice' : undefined}>{c.symptoms.trim() || notStated}</dd></div>
          <div><dt>{t('f.share')}</dt><dd className="num">{c.affectedShare || notStated}</dd></div>
          <div><dt>{t('wiz.step.crops')}</dt><dd>{crops || notStated}</dd></div>
          <div><dt>{t('f.water')}</dt><dd>{water}</dd></div>
          <div><dt>{t('f.soilNotes')}</dt><dd>{c.constraints.soilKnown && c.constraints.soilNotes.trim() ? c.constraints.soilNotes : notStated}</dd></div>
          <div><dt>{t('f.priorities')}</dt><dd>{c.constraints.priorities.trim() || notStated}</dd></div>
        </dl>
      </section>
      {/* Server-redacted location only: never re-derived from raw coordinates for this viewer (ADR-0004/0005). */}
      <LocationMap viewer={viewerLocationForReadOnlyCase(c)} />
    </>
  );
}
