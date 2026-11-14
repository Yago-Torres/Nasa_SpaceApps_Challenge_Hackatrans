import { useEffect, useState } from 'react';
import { casesApi } from '../../api/client';
import type { GrantableRole, PermissionView, Role } from '../../api/types';
import { Button, PageHeader, StatusMessage } from '../../design/components';
import { useI18n } from '../../i18n/I18n';
import type { MessageKey } from '../../i18n/messages';
import { caseErrorText } from './caseErrors';

export function CollaborationPanel({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  const [members, setMembers] = useState<PermissionView[] | null>(null);
  const [role, setRole] = useState<GrantableRole>('VIEWER');
  const [myRole, setMyRole] = useState<Role>('VIEWER');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setMembers(null); setError('');
    Promise.all([casesApi.get(caseId, controller.signal), casesApi.permissions(caseId, controller.signal)])
      .then(([c, p]) => { setMembers(p); setMyRole(c.my_role); })
      .catch((e) => { if (e?.name !== 'AbortError') setError(caseErrorText(e, t)); });
    return () => controller.abort();
  }, [caseId, t, version]);
  const owner = myRole === 'OWNER';
  async function grant(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { await casesApi.grantPermission(caseId, { email, role }); setEmail(''); setVersion((n) => n + 1); }
    catch (e) { setError(caseErrorText(e, t)); } finally { setBusy(false); }
  }
  async function revoke(id: string) {
    setBusy(true); setError('');
    try { await casesApi.revokePermission(caseId, id); setVersion((n) => n + 1); }
    catch (e) { setError(caseErrorText(e, t)); } finally { setBusy(false); }
  }
  return <><PageHeader title={t('collab.caseTitle')} lead={t('collab.caseLead')} />
    {error && <StatusMessage tone="error" title={t('collab.error')}>{error}</StatusMessage>}
    {members === null ? <StatusMessage tone="loading" title={t('state.loading')} /> : <section className="panel">
      <h2>{t('collab.members')}</h2><div className="table-wrap"><table className="data"><thead><tr><th>{t('collab.person')}</th><th>{t('collab.role')}</th>{owner && <th>{t('collab.actions')}</th>}</tr></thead><tbody>
        {members.map((m) => <tr key={m.user_id}><th scope="row">{m.display_name}{m.email ? ` · ${m.email}` : ''}</th><td>{t(`case.role.${m.role}` as MessageKey)}</td>{owner && m.role !== 'OWNER' && <td><Button variant="text" disabled={busy} onClick={() => revoke(m.user_id)}>{t('collab.revoke')}</Button></td>}</tr>)}
      </tbody></table></div>
      {owner && <form className="panel" onSubmit={grant}><h3>{t('collab.invite')}</h3><p>{t('collab.registeredOnly')}</p>
        <div className="field"><label htmlFor="collab-email">{t('auth.email')}</label><input className="ctl" id="collab-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div className="field"><label htmlFor="collab-role">{t('collab.role')}</label><select className="ctl" id="collab-role" value={role} onChange={(e) => setRole(e.target.value as GrantableRole)}><option value="EDITOR">{t('case.role.EDITOR')}</option><option value="REVIEWER">{t('case.role.REVIEWER')}</option><option value="VIEWER">{t('case.role.VIEWER')}</option></select></div>
        <Button type="submit" variant="primary" busy={busy}>{t('collab.grant')}</Button></form>}
    </section>}</>;
}
