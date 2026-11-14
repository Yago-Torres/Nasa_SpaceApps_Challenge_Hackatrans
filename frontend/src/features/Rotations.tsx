import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { useI18n } from '../i18n/I18n';
import { Button, EvidenceLabel, EvidenceSymbol, PageHeader, StatusMessage } from '../design/components';
import { useInvestigation } from '../app/investigation';
import { errorText } from './errors';

/**
 * Shows /api/rotations/demo. CURRENT_STATE lists it as ILLUSTRATIVE ONLY, so it is labelled
 * Illustrative even though the payload says kind "modelled_scenario".
 */
export function Rotations() {
  const { t } = useI18n();
  const { rotations, setRotations } = useInvestigation();
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const [failure, setFailure] = useState('');
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  async function load() {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setStatus('loading');
    try {
      setRotations(await api.rotationsDemo(controller.signal));
      setStatus('idle');
    } catch (err) {
      if (controller.signal.aborted) return;
      setFailure(errorText(err, t));
      setStatus('error');
    }
  }

  return (
    <>
      <PageHeader title={t('rot.title')} lead={t('rot.lead')} />
      <div className="msg msg--illustrative" role="note">
        <EvidenceSymbol kind="ILLUSTRATIVE" />
        <b>{t('rot.illustrativeTitle')}</b>
        <div className="msg-body">{t('rot.illustrativeBody')}</div>
      </div>

      {rotations.length === 0 && status !== 'loading' && status !== 'error' && (
        <StatusMessage tone="empty" title={t('rot.emptyBody')} action={<Button variant="primary" onClick={load}>{t('rot.load')}</Button>} />
      )}
      {status === 'loading' && <StatusMessage tone="loading" title={t('rot.loading')} />}
      {status === 'error' && <StatusMessage tone="error" title={t('rot.errorTitle')} action={<Button onClick={load}>{t('state.retry')}</Button>}>{failure}</StatusMessage>}

      {rotations.length > 0 && (
        <div className="rotations">
          {rotations.map((r, i) => (
            <article key={r.id} className="rotation" aria-labelledby={`rot-${r.id}`}>
              <span className="tag-current">{i === 0 ? t('rot.current') : t('rot.alternative')}</span>
              <h3 id={`rot-${r.id}`}>{r.name}</h3>
              <EvidenceLabel kind="ILLUSTRATIVE" />
              <ol>
                {r.years.map((crops, y) => (
                  <li key={y}><span>{t('rot.year', { n: y + 1 })}</span><span>{crops.join(' + ')}</span></li>
                ))}
              </ol>
              <ul>
                <li>{t('rot.diversity', { n: r.crop_diversity_count })}</li>
                {r.includes_legume && <li>{t('rot.legume')}</li>}
                {r.includes_cover_crop && <li>{t('rot.cover')}</li>}
              </ul>
              <p className="muted">{r.interpretation}</p>
              <p className="muted"><b>{r.warning}</b></p>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
