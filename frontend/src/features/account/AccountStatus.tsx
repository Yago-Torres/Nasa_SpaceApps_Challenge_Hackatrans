import { useState } from 'react';
import { LogIn, LogOut } from 'lucide-react';
import { authApi } from '../../api/client';
import { clearSession, useSession } from '../../api/session';
import { hrefFor } from '../../app/routes';
import { useI18n } from '../../i18n/I18n';

/** Who is signed in, in the rail. Sign out revokes the token on the server, then forgets it locally either way. */
export function AccountStatus() {
  const { t } = useI18n();
  const session = useSession();
  const [busy, setBusy] = useState(false);

  if (!session) {
    return (
      <a className="account-link" href={hrefFor('cases')}>
        <LogIn aria-hidden="true" />
        <span>{t('auth.signInLink')}</span>
      </a>
    );
  }

  async function signOut() {
    setBusy(true);
    try {
      await authApi.logout();
    } catch {
      /* server unreachable or token already invalid: still sign out here */
    } finally {
      clearSession();
      setBusy(false);
    }
  }

  return (
    <div className="account">
      <p>{t('auth.signedInAs', { name: session.user.display_name })}</p>
      <button type="button" className="account-link" onClick={signOut} disabled={busy} aria-busy={busy || undefined}>
        <LogOut aria-hidden="true" />
        <span>{t('auth.signOut')}</span>
      </button>
    </div>
  );
}
