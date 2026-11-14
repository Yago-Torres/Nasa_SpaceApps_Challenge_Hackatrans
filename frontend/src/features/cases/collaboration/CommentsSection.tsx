import { useEffect, useMemo, useState } from 'react';
import { collabApi, ApiError } from '../../../api/client';
import type { CommentRevisionView, CommentView } from '../../../api/types';
import { Button, StatusMessage, TextArea } from '../../../design/components';
import { useI18n } from '../../../i18n/I18n';
import type { MessageKey } from '../../../i18n/messages';
import { caseErrorText } from '../caseErrors';
import { useDates } from './format';

export const COMMENT_MAX = 4000;

/**
 * Case discussion (ABB-25). Comments are plain text written by people: they are rendered as React
 * text nodes inside a ReviewSlip (never innerHTML or Markdown), which is the XSS boundary documented
 * in docs/architecture/COLLABORATION.md. Comments never change a review status; reviews keep their
 * own screens and roles.
 */
export function CommentsSection({ caseId, canPost, onPosted }: { caseId: string; canPost: boolean; onPosted?: () => void }) {
  const { t } = useI18n();
  const [items, setItems] = useState<CommentView[] | null>(null);
  const [total, setTotal] = useState(0);
  const [failure, setFailure] = useState('');
  const [reload, setReload] = useState(0);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [postError, setPostError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    collabApi.comments(caseId, controller.signal).then(
      (list) => { setItems(list.items); setTotal(list.total); setFailure(''); },
      (e) => { if (e?.name !== 'AbortError') setFailure(caseErrorText(e, t)); },
    );
    return () => controller.abort();
  }, [caseId, reload]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () => { setReload((n) => n + 1); onPosted?.(); };
  const threads = useMemo(() => {
    const top = (items ?? []).filter((c) => c.parent_id === null);
    const replies = new Map<string, CommentView[]>();
    for (const c of items ?? []) if (c.parent_id) replies.set(c.parent_id, [...(replies.get(c.parent_id) ?? []), c]);
    return top.map((c) => ({ comment: c, replies: replies.get(c.id) ?? [] }));
  }, [items]);

  const length = draft.trim().length;
  async function post(event: React.FormEvent) {
    event.preventDefault();
    if (!length || length > COMMENT_MAX) { setPostError(length ? t('collab.c.tooLong', { n: COMMENT_MAX }) : t('collab.c.empty')); return; }
    setBusy(true); setPostError('');
    try { await collabApi.comment(caseId, { body: draft }); setDraft(''); refresh(); }
    catch (e) { setPostError(caseErrorText(e, t)); } finally { setBusy(false); }
  }

  return (
    <section className="panel" aria-labelledby="collab-comments-h">
      <div className="section-head">
        <h2 id="collab-comments-h">{t('collab.c.title')}</h2>
        <p>{t('collab.c.lead')}</p>
      </div>
      {canPost ? (
        <form className="stack" onSubmit={post}>
          <TextArea label={t('collab.c.new')} hint={t('collab.c.hint', { n: COMMENT_MAX - length })} rows={3} value={draft}
            maxLength={COMMENT_MAX * 2} error={postError || undefined} onChange={(e) => { setDraft(e.target.value); setPostError(''); }} />
          <div className="actions"><Button type="submit" variant="primary" busy={busy}>{t('collab.c.post')}</Button></div>
        </form>
      ) : (
        <StatusMessage tone="empty" title={t('collab.c.closedTitle')}>{t('collab.c.closedBody')}</StatusMessage>
      )}

      {failure && <StatusMessage tone="error" title={t('collab.c.loadError')} action={<Button onClick={() => setReload((n) => n + 1)}>{t('state.retry')}</Button>}>{failure}</StatusMessage>}
      {items === null && !failure && <StatusMessage tone="loading" title={t('state.loading')} />}
      {items && items.length === 0 && <p className="muted">{t('collab.c.none')}</p>}
      {threads.length > 0 && (
        <ol className="thread" aria-label={t('collab.c.listLabel', { n: total })}>
          {threads.map(({ comment, replies }) => (
            <li key={comment.id}>
              <CommentSlip caseId={caseId} comment={comment} canReply={canPost && !comment.deleted} onChanged={refresh} />
              {replies.length > 0 && (
                <ol className="thread" aria-label={t('collab.c.repliesLabel', { n: replies.length })}>
                  {replies.map((r) => <li key={r.id}><CommentSlip caseId={caseId} comment={r} canReply={false} onChanged={refresh} /></li>)}
                </ol>
              )}
            </li>
          ))}
        </ol>
      )}
      {items && total > items.length && <p className="muted">{t('collab.c.truncated', { shown: items.length, total })}</p>}
    </section>
  );
}

type Mode = 'view' | 'edit' | 'reply' | 'confirm-delete';

function CommentSlip({ caseId, comment, canReply, onChanged }: { caseId: string; comment: CommentView; canReply: boolean; onChanged: () => void }) {
  const { t } = useI18n();
  const dates = useDates();
  const [mode, setMode] = useState<Mode>('view');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState<CommentRevisionView[] | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const c = comment;
  const author = c.author?.display_name ?? t('collab.deletedAccount');

  function start(next: Mode) {
    setMode(next); setError('');
    setText(next === 'edit' ? c.body ?? '' : '');
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const length = text.trim().length;
    if (!length || length > COMMENT_MAX) { setError(length ? t('collab.c.tooLong', { n: COMMENT_MAX }) : t('collab.c.empty')); return; }
    setBusy(true); setError('');
    try {
      if (mode === 'edit') await collabApi.editComment(caseId, c.id, { version: c.version, body: text });
      else await collabApi.comment(caseId, { body: text, parent_id: c.id });
      setMode('view'); setHistory(null); onChanged();
    } catch (e) {
      setError(e instanceof ApiError && e.status === 409 ? t('collab.c.conflict') : caseErrorText(e, t));
    } finally { setBusy(false); }
  }

  async function remove() {
    setBusy(true); setError('');
    try { await collabApi.deleteComment(caseId, c.id); setMode('view'); onChanged(); }
    catch (e) { setError(caseErrorText(e, t)); } finally { setBusy(false); }
  }

  async function toggleHistory() {
    if (historyOpen) { setHistoryOpen(false); return; }
    setHistoryOpen(true);
    if (history) return;
    try { setHistory(await collabApi.revisions(caseId, c.id)); }
    catch (e) { setError(caseErrorText(e, t)); setHistoryOpen(false); }
  }

  return (
    <article className={c.deleted ? 'slip slip--deleted' : 'slip'} aria-label={t('collab.c.by', { name: author })}>
      <p className="who">
        <b>{author}</b> · <time dateTime={c.created_at}>{dates.dateTime(c.created_at)}</time>
        {c.edited_at && !c.deleted && <> · {t('collab.c.edited', { date: dates.dateTime(c.edited_at) })}</>}
        {c.target.kind !== 'CASE' && <> · <span className="chip-meta">{t(`collab.target.${c.target.kind}` as MessageKey)}</span></>}
      </p>
      {c.deleted ? (
        <p className="muted">{t('collab.c.deleted', { name: c.deleted_by?.display_name ?? t('collab.deletedAccount'), date: c.deleted_at ? dates.dateTime(c.deleted_at) : '' })}</p>
      ) : mode === 'edit' ? null : (
        <blockquote>{c.body}</blockquote>
      )}

      {(mode === 'edit' || mode === 'reply') && (
        <form className="stack" onSubmit={submit}>
          <TextArea label={mode === 'edit' ? t('collab.c.editLabel') : t('collab.c.replyLabel', { name: author })} rows={3} value={text}
            maxLength={COMMENT_MAX * 2} hint={t('collab.c.hint', { n: COMMENT_MAX - text.trim().length })} error={error || undefined}
            onChange={(e) => { setText(e.target.value); setError(''); }} />
          <div className="actions">
            <Button type="submit" busy={busy}>{mode === 'edit' ? t('collab.c.save') : t('collab.c.sendReply')}</Button>
            <Button variant="text" onClick={() => start('view')}>{t('collab.cancel')}</Button>
          </div>
        </form>
      )}

      {mode === 'confirm-delete' && (
        <div className="inline-confirm" role="group" aria-label={t('collab.c.confirmDelete')}>
          <span>{t('collab.c.confirmDelete')}</span>
          <Button busy={busy} onClick={remove}>{t('collab.c.delete')}</Button>
          <Button variant="text" onClick={() => start('view')}>{t('collab.cancel')}</Button>
        </div>
      )}
      {error && mode !== 'edit' && mode !== 'reply' && <p className="err" role="alert">{error}</p>}

      {mode === 'view' && !c.deleted && (canReply || c.can_edit || c.can_delete || c.revision_count > 0) && (
        <div className="slip-actions">
          {canReply && <Button variant="text" onClick={() => start('reply')}>{t('collab.c.reply')}</Button>}
          {c.can_edit && <Button variant="text" onClick={() => start('edit')}>{t('collab.c.edit')}</Button>}
          {c.can_delete && <Button variant="text" onClick={() => start('confirm-delete')}>{t('collab.c.delete')}</Button>}
          {c.revision_count > 0 && (
            <Button variant="text" aria-expanded={historyOpen} onClick={toggleHistory}>
              {historyOpen ? t('collab.c.hideHistory') : t('collab.c.history', { n: c.revision_count })}
            </Button>
          )}
        </div>
      )}
      {historyOpen && history && (
        <ol className="revisions" aria-label={t('collab.c.historyLabel')}>
          {history.map((r) => (
            <li key={r.revision}>
              <p className="who">{t('collab.c.revision', { n: r.revision, date: dates.dateTime(r.replaced_at), name: r.edited_by?.display_name ?? t('collab.deletedAccount') })}</p>
              <blockquote>{r.body}</blockquote>
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}
