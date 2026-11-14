import { useEffect, useState } from 'react';
import { casesApi } from '../../../api/client';
import type { GrantableRole, PermissionView } from '../../../api/types';
import { Button, Field, StatusMessage } from '../../../design/components';
import { useI18n } from '../../../i18n/I18n';
import type { MessageKey } from '../../../i18n/messages';
import { caseErrorText } from '../caseErrors';

export const GRANTABLE: GrantableRole[] = ['EDITOR', 'REVIEWER', 'VIEWER'];

/** People with access (ABB-06 permissions). Owners revoke access or grant it at once to an existing account. */
export function MembersSection({ caseId, owner, onChanged }: { caseId: string; owner: boolean; onChanged?: () => void }) {
  const { t } = useI18n();
  const [members, setMembers] = useState<PermissionView[] | null>(null);
  const [failure, setFailure] = useState('');
  const [reload, setReload] = useState(0);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<GrantableRole>('REVIEWER');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    casesApi.permissions(caseId, controller.signal).then(
      (p) => { setMembers(p); setFailure(''); },
      (e) => { if (e?.name !== 'AbortError') setFailure(caseErrorText(e, t)); },
    );
    return () => controller.abort();
  }, [caseId, reload]); // eslint-disable-line react-hooks/exhaustive-deps

  async function revoke(userId: string) {
    setBusy(true); setFailure(''); setNotice('');
    try {
      await casesApi.revokePermission(caseId, userId);
      setConfirming(null);
      setNotice(t('collab.members.revoked'));
      setReload((n) => n + 1);
      onChanged?.();
    } catch (e) { setFailure(caseErrorText(e, t)); } finally { setBusy(false); }
  }

  async function grant(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); setFailure(''); setNotice('');
    try {
      await casesApi.grantPermission(caseId, { email: email.trim(), role });
      setEmail('');
      setNotice(t('collab.members.granted'));
      setReload((n) => n + 1);
      onChanged?.();
    } catch (e) { setFailure(caseErrorText(e, t)); } finally { setBusy(false); }
  }

  return (
    <section className="panel" aria-labelledby="collab-members-h">
      <div className="section-head">
        <h2 id="collab-members-h">{t('collab.members.title')}</h2>
        <p>{t('collab.members.lead')}</p>
      </div>
      {failure && <StatusMessage tone="error" title={t('collab.error')}>{failure}</StatusMessage>}
      {notice && <StatusMessage tone="ok" title={notice} />}
      {members === null && !failure && <StatusMessage tone="loading" title={t('state.loading')} />}
      {members && (
        <div className="table-wrap">
          <table className="data collab-table">
            <thead>
              <tr>
                <th scope="col">{t('collab.person')}</th>
                <th scope="col">{t('collab.role')}</th>
                {owner && <th scope="col"><span className="sr-only">{t('collab.actions')}</span></th>}
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.user_id}>
                  <th scope="row">{m.display_name}{m.email && <span className="muted"> · {m.email}</span>}</th>
                  <td data-label={t('collab.role')}>{t(`case.role.${m.role}` as MessageKey)}</td>
                  {owner && (
                    <td>
                      {m.role !== 'OWNER' && (confirming === m.user_id ? (
                        <span className="inline-confirm">
                          <Button variant="secondary" busy={busy} onClick={() => revoke(m.user_id)}>{t('collab.members.confirmRevoke', { name: m.display_name })}</Button>
                          <Button variant="text" onClick={() => setConfirming(null)}>{t('collab.cancel')}</Button>
                        </span>
                      ) : (
                        <Button variant="text" onClick={() => setConfirming(m.user_id)}>{t('collab.revoke')}</Button>
                      ))}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {owner && (
        <details>
          <summary>{t('collab.members.grantTitle')}</summary>
          <form className="stack" onSubmit={grant}>
            <p className="muted">{t('collab.members.grantLead')}</p>
            <div className="form-row form-row--2">
              <Field label={t('auth.email')} type="email" autoComplete="off" required value={email} onChange={(e) => setEmail(e.target.value)} />
              <RoleSelect id="grant-role" value={role} onChange={setRole} />
            </div>
            <div className="actions"><Button type="submit" busy={busy}>{t('collab.grant')}</Button></div>
          </form>
        </details>
      )}
    </section>
  );
}

export function RoleSelect({ id, value, onChange }: { id: string; value: GrantableRole; onChange: (r: GrantableRole) => void }) {
  const { t } = useI18n();
  return (
    <div className="field">
      <label htmlFor={id}>{t('collab.role')}</label>
      <div className="ctl">
        <select id={id} value={value} onChange={(e) => onChange(e.target.value as GrantableRole)}>
          {GRANTABLE.map((r) => <option key={r} value={r}>{t(`case.role.${r}` as MessageKey)}</option>)}
        </select>
      </div>
      <span className="hint">{t(`collab.roleHint.${value}` as MessageKey)}</span>
    </div>
  );
}
