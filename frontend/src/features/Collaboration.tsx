import { useEffect, useRef, useState } from 'react';
import { collabApi } from '../api/client';
import { useSession } from '../api/session';
import type { ReceivedInvitationView } from '../api/types';
import { hrefForCaseTab } from '../app/routes';
import { Button, ButtonLink, PageHeader, StatusMessage } from '../design/components';
import { useI18n } from '../i18n/I18n';
import type { MessageKey } from '../i18n/messages';
import { AuthPanel } from './account/AuthPanel';
import { caseErrorText, isUnauthorized } from './cases/caseErrors';
import { useDates } from './cases/collaboration/format';

type Answered = { id: string; caseId: string; title: string; accepted: boolean };

/**
 * Invitations addressed to the signed-in account (ABB-25 `GET /api/v1/invitations`). No e-mail is
 * sent: people come here after signing in with the invited address. Accepting gives access at
 * once; case discussion and sharing live in each case's tabs.
 */
export function Collaboration() {
  const { t } = useI18n();
  const dates = useDates();
  const session = useSession();
  const [items, setItems] = useState<ReceivedInvitationView[] | null>(null);
  const [failure, setFailure] = useState('');
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [answered, setAnswered] = useState<Answered[]>([]);
  const everSignedIn = useRef(!!session);
  if (session) everSignedIn.current = true;

  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    setFailure('');
    collabApi.received(controller.signal).then(
      (list) => setItems(list.items),
      (e) => { if (e?.name !== 'AbortError' && !isUnauthorized(e)) setFailure(caseErrorText(e, t)); },
    );
    return () => controller.abort();
  }, [session, reload]); // eslint-disable-line react-hooks/exhaustive-deps

  async function answer(inv: ReceivedInvitationView, accept: boolean) {
    setBusy(inv.id); setFailure('');
    try {
      const decision = accept ? await collabApi.accept(inv.id) : await collabApi.decline(inv.id);
      setAnswered((a) => [{ id: inv.id, caseId: decision.case_id, title: inv.case.title, accepted: decision.status === 'ACCEPTED' }, ...a]);
      setItems((list) => (list ?? []).filter((x) => x.id !== inv.id));
    } catch (e) {
      setFailure(caseErrorText(e, t));
      setReload((n) => n + 1); // revoked or expired meanwhile: show the current list
    } finally { setBusy(null); }
  }

  if (!session) {
    return (
      <>
        <PageHeader title={t('col.title')} lead={t('col.lead')} />
        <AuthPanel primary notice={everSignedIn.current ? t('auth.sessionEnded') : t('col.signInHint')} />
      </>
    );
  }

  return (
    <>
      <PageHeader title={t('col.title')} lead={t('col.lead')} />
      {answered.map((a) => (
        <StatusMessage key={a.id} tone="ok" title={a.accepted ? t('col.accepted', { title: a.title }) : t('col.declined', { title: a.title })}
          action={a.accepted ? <ButtonLink href={hrefForCaseTab(a.caseId, 'details')}>{t('col.openCase')}</ButtonLink> : undefined} />
      ))}
      <section className="panel" aria-labelledby="col-inbox-h">
        <div className="section-head">
          <h2 id="col-inbox-h">{t('col.inboxTitle')}</h2>
          <p>{t('col.inboxLead', { email: session.user.email })}</p>
        </div>
        {failure && <StatusMessage tone="error" title={t('col.error')} action={<Button onClick={() => setReload((n) => n + 1)}>{t('state.retry')}</Button>}>{failure}</StatusMessage>}
        {items === null && !failure && <StatusMessage tone="loading" title={t('state.loading')} />}
        {items && items.length === 0 && <StatusMessage tone="empty" title={t('col.noneTitle')}>{t('col.noneBody')}</StatusMessage>}
        {items && items.length > 0 && (
          <ul className="invites">
            {items.map((inv) => (
              <li key={inv.id} className="slip">
                <h3>{inv.case.title}</h3>
                <p className="who">
                  {t('col.invitedBy', { name: inv.invited_by?.display_name ?? t('collab.deletedAccount'), role: t(`case.role.${inv.role}` as MessageKey) })}
                  {' · '}{t('col.expires', { date: dates.dateTime(inv.expires_at) })}
                </p>
                <p className="muted">{t(`collab.roleHint.${inv.role}` as MessageKey)}</p>
                {inv.note && <blockquote>{inv.note}</blockquote>}
                <div className="actions">
                  <Button busy={busy === inv.id} disabled={busy !== null} onClick={() => answer(inv, true)}>{t('col.accept')}</Button>
                  <Button variant="text" disabled={busy !== null} onClick={() => answer(inv, false)}>{t('col.decline')}</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="panel" aria-labelledby="col-how-h">
        <div className="section-head"><h2 id="col-how-h">{t('col.howTitle')}</h2></div>
        <ul className="list-plain">
          <li>{t('col.how1')}</li>
          <li>{t('col.how2')}</li>
          <li>{t('col.how3')}</li>
        </ul>
      </section>
    </>
  );
}
