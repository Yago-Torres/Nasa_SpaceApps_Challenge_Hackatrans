import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ExternalLink } from 'lucide-react';
import { api } from '../api/client';
import { useI18n } from '../i18n/I18n';
import { Button, Field, PageHeader, StatusMessage } from '../design/components';
import { useInvestigation } from '../app/investigation';
import { errorText } from './errors';

/** OpenAlex search. Results are bibliographic metadata, never reviewed evidence (SCIENTIFIC_POLICY). */
export function Evidence() {
  const { t, num } = useI18n();
  const { papers, setPapers, query, setQuery } = useInvestigation();
  const [status, setStatus] = useState<'idle' | 'loading' | 'error' | 'done'>(papers.length ? 'done' : 'idle');
  const [failure, setFailure] = useState('');
  const [invalid, setInvalid] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  async function search(e?: FormEvent) {
    e?.preventDefault();
    const q = query.trim();
    if (q.length < 3 || q.length > 180) {
      setInvalid(true);
      input.current?.focus();
      return;
    }
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setStatus('loading');
    try {
      setPapers(await api.literature(q, controller.signal));
      setStatus('done');
    } catch (err) {
      if (controller.signal.aborted) return;
      setFailure(errorText(err, t));
      setStatus('error');
    }
  }

  return (
    <>
      <PageHeader title={t('ev.title')} lead={t('ev.lead')} />
      <form className="panel" onSubmit={search} noValidate role="search">
        <div className="form-row" style={{ gridTemplateColumns: 'minmax(0, 1fr)' }}>
          <Field ref={input} label={t('ev.query')} name="query" type="search" value={query} maxLength={180}
            onChange={(e) => { setQuery(e.target.value); setInvalid(false); }}
            hint={t('ev.queryHint')} error={invalid ? t('ev.queryError') : undefined} />
        </div>
        <div className="actions">
          <Button type="submit" variant="primary" busy={status === 'loading'}>{status === 'loading' ? t('ev.searching') : t('ev.search')}</Button>
        </div>
      </form>

      {status === 'loading' && <StatusMessage tone="loading" title={t('ev.searching')} />}
      {status === 'error' && (
        <StatusMessage tone="error" title={t('ev.errorTitle')} action={<Button onClick={() => search()}>{t('state.retry')}</Button>}>{failure}</StatusMessage>
      )}
      {status === 'idle' && <StatusMessage tone="empty" title={t('ev.emptyTitle')}>{t('ev.emptyBody')}</StatusMessage>}
      {status === 'done' && papers.length === 0 && <StatusMessage tone="empty" title={t('ev.noResults')} />}

      {status === 'done' && papers.length > 0 && (
        <section className="panel" aria-label={t('ev.title')}>
          <ul className="papers">
            {papers.map((p) => (
              <li key={p.openalex_id ?? p.title}>
                <b>{p.title}</b>
                <span className="meta">
                  <span className="chip-meta">{t('evidence.metadataOnly')}</span>
                  <span>{p.year === null ? t('ev.yearUnknown') : `${t('ev.year')} ${num(p.year).replace(/\D/g, '')}`}</span>
                  {p.doi ? (
                    <a href={p.doi} target="_blank" rel="noreferrer">
                      {t('ev.openDoi')} <ExternalLink aria-hidden="true" width={14} height={14} /><span className="sr-only">{t('ev.newTab')}</span>
                    </a>
                  ) : (
                    <span>{t('ev.noDoi')}</span>
                  )}
                </span>
                <span className="muted">{p.caveat}</span>
              </li>
            ))}
          </ul>
          <StatusMessage tone="empty" title={t('ev.keepTitle')}>{t('ev.keepBody')}</StatusMessage>
        </section>
      )}
    </>
  );
}
