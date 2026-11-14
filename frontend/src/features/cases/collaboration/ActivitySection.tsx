import { useEffect, useState } from 'react';
import { collabApi } from '../../../api/client';
import type { ActivityEntry, JsonValue } from '../../../api/types';
import { Button, StatusMessage } from '../../../design/components';
import { useI18n } from '../../../i18n/I18n';
import { en, type MessageKey } from '../../../i18n/messages';
import { caseErrorText } from '../caseErrors';
import { useDates } from './format';

/**
 * Read-only audit trail (ABB-25 `GET /cases/{id}/activity`): who did what, when, on which record
 * and with which evidence. Nothing is computed here; the backend merges the audit sources and
 * already redacts coordinates for reviewers and viewers.
 */
export function ActivitySection({ caseId, refreshKey }: { caseId: string; refreshKey: number }) {
  const { t } = useI18n();
  const dates = useDates();
  const [items, setItems] = useState<ActivityEntry[] | null>(null);
  const [total, setTotal] = useState(0);
  const [failure, setFailure] = useState('');
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    collabApi.activity(caseId, 0, controller.signal).then(
      (page) => { setItems(page.items); setTotal(page.total); setFailure(''); },
      (e) => { if (e?.name !== 'AbortError') setFailure(caseErrorText(e, t)); },
    );
    return () => controller.abort();
  }, [caseId, refreshKey, reload]); // eslint-disable-line react-hooks/exhaustive-deps

  async function more() {
    if (!items) return;
    setBusy(true);
    try {
      const page = await collabApi.activity(caseId, items.length);
      setItems([...items, ...page.items.filter((e) => !items.some((x) => x.id === e.id))]);
      setTotal(page.total);
    } catch (e) { setFailure(caseErrorText(e, t)); } finally { setBusy(false); }
  }

  return (
    <section className="panel" aria-labelledby="collab-activity-h">
      <div className="section-head">
        <h2 id="collab-activity-h">{t('collab.act.title')}</h2>
        <p>{t('collab.act.lead')}</p>
      </div>
      {failure && <StatusMessage tone="error" title={t('collab.act.loadError')} action={<Button onClick={() => setReload((n) => n + 1)}>{t('state.retry')}</Button>}>{failure}</StatusMessage>}
      {items === null && !failure && <StatusMessage tone="loading" title={t('state.loading')} />}
      {items && items.length === 0 && <p className="muted">{t('collab.act.none')}</p>}
      {items && items.length > 0 && (
        <ol className="activity">
          {items.map((e) => (
            <li key={e.id}>
              <time dateTime={e.created_at} className="muted">{dates.dateTime(e.created_at)}</time>
              <div className="stack-tight">
                <p>
                  <span className="chip-meta">{t(`collab.act.cat.${e.category}` as MessageKey)}</span>{' '}
                  <b>{e.actor?.display_name ?? t('collab.act.noActor')}</b>{' '}
                  {kindLabel(e.kind, t)}
                </p>
                {e.note && <p className="voice">{e.note}</p>}
                {(e.evidence || e.changes) && (
                  <details>
                    <summary>{e.evidence ? t('collab.act.evidence') : t('collab.act.changes')}</summary>
                    {e.evidence && <JsonList value={e.evidence} />}
                    {e.evidence && e.changes && <p className="muted">{t('collab.act.changes')}</p>}
                    {e.changes && <JsonList value={e.changes} />}
                  </details>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
      {items && items.length < total && (
        <div className="actions"><Button busy={busy} onClick={more}>{t('collab.act.more', { n: total - items.length })}</Button></div>
      )}
    </section>
  );
}

/** Known actions get a translated sentence; anything new from the backend shows its code (never guessed). */
function kindLabel(kind: string, t: ReturnType<typeof useI18n>['t']) {
  const key = `collab.act.k.${kind}`;
  return key in en ? t(key as MessageKey) : <span className="mono">{kind}</span>;
}

/** Recorded evidence / before-after values, shown as text exactly as the backend returned them. */
function JsonList({ value }: { value: Record<string, JsonValue> }) {
  return (
    <dl className="json-list">
      {Object.entries(value).map(([k, v]) => (
        <div key={k}>
          <dt className="mono">{k}</dt>
          <dd>{v !== null && typeof v === 'object' && !Array.isArray(v) ? <JsonList value={v} /> : <span className="json-value">{format(v)}</span>}</dd>
        </div>
      ))}
    </dl>
  );
}

function format(v: JsonValue): string {
  if (v === null) return '—';
  if (typeof v === 'string') return v;
  return JSON.stringify(v);
}
