import { useEffect, useState } from 'react';
import { collabApi } from '../../../api/client';
import type { GrantableRole, InvitationView } from '../../../api/types';
import { Button, Field, StatusMessage, TextArea } from '../../../design/components';
import { useI18n } from '../../../i18n/I18n';
import type { MessageKey } from '../../../i18n/messages';
import { caseErrorText } from '../caseErrors';
import { RoleSelect } from './MembersSection';
import { useDates } from './format';

const NOTE_MAX = 500;

/**
 * Owner-only invitations (ABB-25). No e-mail is sent: the invitee signs in with the invited
 * address and answers from the Collaboration page. Because accounts have no e-mail verification
 * yet, the form tells the owner to invite only addresses they have confirmed with the person.
 */
export function InvitationsSection({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  const dates = useDates();
  const [items, setItems] = useState<InvitationView[] | null>(null);
  const [failure, setFailure] = useState('');
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<GrantableRole>('REVIEWER');
  const [note, setNote] = useState('');
  const [days, setDays] = useState('14');
  const [sent, setSent] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    collabApi.invitations(caseId, controller.signal).then(
      (list) => { setItems(list.items); setFailure(''); },
      (e) => { if (e?.name !== 'AbortError') setFailure(caseErrorText(e, t)); },
    );
    return () => controller.abort();
  }, [caseId, reload]); // eslint-disable-line react-hooks/exhaustive-deps

  const daysNumber = Number(days);
  const daysInvalid = !Number.isInteger(daysNumber) || daysNumber < 1 || daysNumber > 30;
  const noteTooLong = note.trim().length > NOTE_MAX;

  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (daysInvalid || noteTooLong) return;
    setBusy(true); setFailure(''); setSent('');
    try {
      const created = await collabApi.invite(caseId, { email: email.trim(), role, note: note.trim() || null, expires_in_days: daysNumber });
      setSent(t('collab.inv.sent', { email: created.email }));
      setEmail(''); setNote('');
      setReload((n) => n + 1);
    } catch (e) { setFailure(caseErrorText(e, t)); } finally { setBusy(false); }
  }

  async function revoke(id: string) {
    setBusy(true); setFailure(''); setSent('');
    try { await collabApi.revokeInvitation(caseId, id); setReload((n) => n + 1); }
    catch (e) { setFailure(caseErrorText(e, t)); } finally { setBusy(false); }
  }

  return (
    <section className="panel" aria-labelledby="collab-inv-h">
      <div className="section-head">
        <h2 id="collab-inv-h">{t('collab.inv.title')}</h2>
        <p>{t('collab.inv.lead')}</p>
      </div>
      <form className="stack" onSubmit={send}>
        <StatusMessage tone="partial" title={t('collab.inv.verifyTitle')}>{t('collab.inv.verifyBody')}</StatusMessage>
        <div className="form-row">
          <Field label={t('auth.email')} type="email" autoComplete="off" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <RoleSelect id="invite-role" value={role} onChange={setRole} />
          <Field label={t('collab.inv.days')} inputMode="numeric" unit={t('collab.inv.daysUnit')} value={days}
            error={daysInvalid ? t('collab.inv.daysError') : undefined} onChange={(e) => setDays(e.target.value)} />
        </div>
        <TextArea label={t('collab.inv.note')} hint={t('collab.inv.noteHint', { n: NOTE_MAX - note.trim().length })} rows={2}
          maxLength={NOTE_MAX * 2} value={note} error={noteTooLong ? t('collab.inv.noteError', { n: NOTE_MAX }) : undefined}
          onChange={(e) => setNote(e.target.value)} />
        <div className="actions">
          <Button type="submit" variant="primary" busy={busy}>{t('collab.inv.send')}</Button>
        </div>
        {sent && <StatusMessage tone="ok" title={sent}>{t('collab.inv.sentBody')}</StatusMessage>}
      </form>

      {failure && <StatusMessage tone="error" title={t('collab.error')}>{failure}</StatusMessage>}
      {items === null && !failure && <StatusMessage tone="loading" title={t('state.loading')} />}
      {items && items.length === 0 && <p className="muted">{t('collab.inv.none')}</p>}
      {items && items.length > 0 && (
        <div className="table-wrap">
          <table className="data collab-table">
            <caption className="sr-only">{t('collab.inv.listCaption')}</caption>
            <thead>
              <tr>
                <th scope="col">{t('auth.email')}</th>
                <th scope="col">{t('collab.role')}</th>
                <th scope="col">{t('collab.status')}</th>
                <th scope="col">{t('collab.inv.expires')}</th>
                <th scope="col"><span className="sr-only">{t('collab.actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {items.map((inv) => (
                <tr key={inv.id}>
                  <th scope="row">{inv.email}{inv.note && <span className="muted block">{inv.note}</span>}</th>
                  <td data-label={t('collab.role')}>{t(`case.role.${inv.role}` as MessageKey)}</td>
                  <td data-label={t('collab.status')}><span className="chip-meta">{t(`collab.inv.status.${inv.status}` as MessageKey)}</span></td>
                  <td data-label={t('collab.inv.expires')}>{dates.dateTime(inv.expires_at)}</td>
                  <td>{inv.status === 'PENDING' && <Button variant="text" disabled={busy} onClick={() => revoke(inv.id)}>{t('collab.inv.revoke')}</Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
