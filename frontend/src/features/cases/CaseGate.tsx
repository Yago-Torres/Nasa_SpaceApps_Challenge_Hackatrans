import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useI18n } from '../../i18n/I18n';
import { Button, ButtonLink, PageHeader, StatusMessage } from '../../design/components';
import { hrefFor } from '../../app/routes';
import { useSession } from '../../api/session';
import type { IncidentCase } from '../../cases/model';
import { caseRepository } from '../../cases/repository';
import { AuthPanel } from '../account/AuthPanel';
import { caseErrorText, isStorageUnavailable, isUnauthorized } from './caseErrors';

type LoadState =
  | { status: 'loading' }
  | { status: 'missing' }
  | { status: 'unavailable' }
  | { status: 'error'; message: string }
  | { status: 'ready'; case: IncidentCase };

/**
 * Sign-in, loading, not-found (404 = missing or no access, ADR-0004), storage-unavailable and
 * error states for a case sub-tab, so each tab only renders once the case is readable. Same
 * behaviour as the ABB-22 timeline tab, shared by the ABB-25 collaboration and discussion tabs.
 */
export function CaseGate({ caseId, title, children }: {
  caseId: string;
  title: string;
  children: (c: IncidentCase, reload: () => void) => ReactNode;
}) {
  const { t } = useI18n();
  const session = useSession();
  const [load, setLoad] = useState<LoadState>({ status: 'loading' });
  const [token, setToken] = useState(0);
  const everSignedIn = useRef(!!session);
  if (session) everSignedIn.current = true;
  const reload = useCallback(() => setToken((n) => n + 1), []);

  useEffect(() => {
    if (!session) return;
    let live = true;
    setLoad((s) => (s.status === 'ready' ? s : { status: 'loading' }));
    caseRepository().get(caseId).then(
      (c) => { if (live) setLoad(c ? { status: 'ready', case: c } : { status: 'missing' }); },
      (err) => {
        if (!live || isUnauthorized(err)) return; // signed out: the sign-in panel shows
        setLoad(isStorageUnavailable(err) ? { status: 'unavailable' } : { status: 'error', message: caseErrorText(err, t) });
      },
    );
    return () => { live = false; };
  }, [caseId, session, token]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!session) {
    return (
      <>
        <PageHeader title={title} />
        <AuthPanel primary notice={everSignedIn.current ? t('auth.sessionEnded') : undefined} />
      </>
    );
  }
  switch (load.status) {
    case 'ready':
      return <>{children(load.case, reload)}</>;
    case 'missing':
      return (
        <>
          <PageHeader title={title} />
          <StatusMessage tone="error" title={t('cases.notFound')} action={<ButtonLink href={hrefFor('cases')}>{t('nav.cases')}</ButtonLink>} />
        </>
      );
    case 'unavailable':
      return (
        <>
          <PageHeader title={title} />
          <StatusMessage tone="error" title={t('cases.storageUnavailable')}>{t('cases.storageUnavailableBody')}</StatusMessage>
        </>
      );
    case 'error':
      return (
        <>
          <PageHeader title={title} />
          <StatusMessage tone="error" title={t('collab.loadError')} action={<Button onClick={reload}>{t('state.retry')}</Button>}>{load.message}</StatusMessage>
        </>
      );
    default:
      return (
        <>
          <PageHeader title={title} />
          <StatusMessage tone="loading" title={t('state.loading')} />
        </>
      );
  }
}
