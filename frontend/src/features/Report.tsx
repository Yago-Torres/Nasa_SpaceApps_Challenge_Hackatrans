import { useState } from 'react';
import { Download } from 'lucide-react';
import { api } from '../api/client';
import { useI18n } from '../i18n/I18n';
import { Button, Field, PageHeader, StatusMessage } from '../design/components';
import { useInvestigation } from '../app/investigation';
import { errorText } from './errors';

/** POST /api/report with exactly what this tab holds. Disabled until a real NASA record exists. */
export function Report() {
  const { t } = useI18n();
  const { climate, papers, rotations } = useInvestigation();
  const [label, setLabel] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'error' | 'done'>('idle');
  const [message, setMessage] = useState('');

  async function download() {
    if (!climate) return;
    setStatus('loading');
    try {
      const out = await api.report({ location_label: label.trim() || climate.dataset, climate, literature: papers, rotations });
      const url = URL.createObjectURL(new Blob([out.markdown], { type: 'text/markdown' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = out.filename;
      a.click();
      URL.revokeObjectURL(url);
      setMessage(t('rep.done', { file: out.filename }));
      setStatus('done');
    } catch (err) {
      setMessage(errorText(err, t));
      setStatus('error');
    }
  }

  return (
    <>
      <PageHeader title={t('rep.title')} lead={t('rep.lead')} />
      <section className="panel" aria-labelledby="rep-contents">
        <h2 id="rep-contents">{t('rep.contents')}</h2>
        <ul className="list-plain">
          <li>{t('rep.climate')}: {climate ? `${climate.event_year} · ${climate.data_sha256.slice(0, 12)}…` : '—'}</li>
          <li>{t('rep.papers', { n: papers.length })}</li>
          <li>{t('rep.rotations', { n: rotations.length })}</li>
        </ul>
        {!climate ? (
          <StatusMessage tone="empty" title={t('rep.missingClimate')} />
        ) : (
          <>
            <Field label={t('rep.location')} name="location" value={label} maxLength={160} onChange={(e) => setLabel(e.target.value)} hint={t('rep.locationHint')} />
            <div className="actions">
              <Button variant="primary" busy={status === 'loading'} icon={<Download aria-hidden="true" />} onClick={download}>
                {status === 'loading' ? t('rep.downloading') : t('rep.download')}
              </Button>
            </div>
          </>
        )}
        {status === 'done' && <StatusMessage tone="ok" title={message} />}
        {status === 'error' && <StatusMessage tone="error" title={t('rep.errorTitle')}>{message}</StatusMessage>}
        <p className="muted">{t('rep.preliminary')}</p>
      </section>
    </>
  );
}
