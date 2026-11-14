import { useCallback, useEffect, useState, type ReactElement } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useI18n } from '../i18n/I18n';
import type { MessageKey } from '../i18n/messages';
import { Button, ButtonLink, PageHeader, StatusMessage } from '../design/components';
import { hrefFor, hrefForCaseTab, useCaseTab, useRouteParam } from '../app/routes';
import { useSession } from '../api/session';
import { ApiError } from '../api/client';
import { canEdit, type IncidentCase } from '../cases/model';
import { caseRepository, legacyBrowserCases } from '../cases/repository';
import { AuthPanel } from './account/AuthPanel';
import { IncidentWizard } from './cases/IncidentWizard';
import { CaseTimeline } from './cases/timeline/CaseTimeline';
import { CaseReport } from './cases/report/CaseReport';
import { CollaborationPanel } from './cases/CollaborationPanel';
import { DiscussionPanel } from './cases/DiscussionPanel';
import { CaseEvidence } from './cases/evidence/CaseEvidence';
import { sharedAsText } from './cases/CaseTitleBlock';
import { caseErrorText, isStorageUnavailable } from './cases/caseErrors';

/**
 * Case sub-screens, reached as "#/cases/<id>/<tab>" (`parseCaseTab` in app/routes.ts; "details"
 * is the default and keeps the plain "#/cases/<id>" URL). This is the shared extension point
 * for case-bound screens: the fixed 7-screen top nav (App.test.tsx) cannot grow, so ABB-23
 * (Evidence), ABB-25 (Collaboration) and ABB-26 (Report) each add one entry here plus a
 * `render` function, instead of inventing their own routing or a new top-level nav item.
 */
const CASE_TABS = [
  { id: 'details', label: 'cases.tab.details' as MessageKey, render: (caseId: string) => <IncidentWizard key={caseId} caseId={caseId} /> },
  { id: 'timeline', label: 'cases.tab.timeline' as MessageKey, render: (caseId: string) => <CaseTimeline key={caseId} caseId={caseId} /> },
  { id: 'evidence', label: 'cases.tab.evidence' as MessageKey, render: (caseId: string) => <CaseEvidence key={caseId} caseId={caseId} /> },
  { id: 'collaboration', label: 'cases.tab.collaboration' as MessageKey, render: (caseId: string) => <CollaborationPanel key={caseId} caseId={caseId} /> },
  { id: 'discussion', label: 'cases.tab.discussion' as MessageKey, render: (caseId: string) => <DiscussionPanel key={caseId} caseId={caseId} /> },
  { id: 'report', label: 'cases.tab.report' as MessageKey, render: (caseId: string) => <CaseReport key={caseId} caseId={caseId} /> },
  // New case sub-screens: add { id, label, render } here.
] as const satisfies readonly { id: string; label: MessageKey; render: (caseId: string) => ReactElement }[];

/** Cases list + wizard routes (#/cases, #/cases/new, #/cases/<id>[/<tab>]), backed by /api/v1/cases. */
export function Cases() {
  const param = useRouteParam();
  return param ? <CaseWorkspace caseId={param} /> : <CaseList />;
}

/** A single case: the tab strip (only for an existing case, never "new") plus the active tab's screen. */
function CaseWorkspace({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  const tab = useCaseTab();
  const isNew = caseId === 'new';
  const active = CASE_TABS.find((x) => x.id === tab) ?? CASE_TABS[0];
  return (
    <>
      {!isNew && (
        <nav className="case-tabs" aria-label={t('cases.tabsLabel')}>
          <ol>
            {CASE_TABS.map((x) => (
              <li key={x.id}>
                <a href={hrefForCaseTab(caseId, x.id)} aria-current={active.id === x.id ? 'page' : undefined}>{t(x.label)}</a>
              </li>
            ))}
          </ol>
        </nav>
      )}
      {isNew ? CASE_TABS[0].render(caseId) : active.render(caseId)}
    </>
  );
}

function LegacyNotice() {
  const { t } = useI18n();
  const [count, setCount] = useState(() => legacyBrowserCases.count());
  if (!count) return null;
  return (
    <StatusMessage tone="pending" title={t('cases.legacyTitle')}
      action={<Button variant="secondary" icon={<Trash2 aria-hidden="true" />} onClick={() => { legacyBrowserCases.clear(); setCount(0); }}>{t('cases.legacyClear')}</Button>}>
      {t('cases.legacyBody', { n: count })}
    </StatusMessage>
  );
}

type Failure = { title: string; body?: string };

function CaseList() {
  const i18n = useI18n();
  const { t, lang } = i18n;
  const session = useSession();
  const repo = caseRepository();
  const [cases, setCases] = useState<IncidentCase[] | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [notice, setNotice] = useState('');
  const [confirm, setConfirm] = useState<string | null>(null);

  const load = useCallback(() => {
    setFailure(null);
    return repo.list().then(setCases, (err) => {
      setCases([]);
      setFailure(isStorageUnavailable(err)
        ? { title: t('cases.storageUnavailable'), body: t('cases.storageUnavailableBody') }
        : { title: t('cases.loadError'), body: caseErrorText(err, t) });
    });
  }, [repo, t]);

  useEffect(() => {
    if (!session) return;
    setCases(null);
    void load();
  }, [session, load]);

  const header = (
    <PageHeader title={t('cases.title')} lead={t('cases.lead')}
      aside={session ? <ButtonLink variant="primary" href={hrefFor('cases', 'new')} icon={<Plus aria-hidden="true" />}>{t('cases.new')}</ButtonLink> : undefined} />
  );

  if (!session) {
    return (
      <>
        {header}
        <AuthPanel />
        <LegacyNotice />
      </>
    );
  }

  const dateFmt = new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' });

  async function remove(c: IncidentCase) {
    setNotice('');
    try {
      await repo.remove(c.id, c.version);
      setConfirm(null);
      await load();
    } catch (err) {
      setConfirm(null);
      if (err instanceof ApiError && err.status === 409) {
        setNotice(t('cases.deleteConflict'));
        await load();
      } else {
        setNotice(caseErrorText(err, t));
      }
    }
  }

  return (
    <>
      {header}
      <LegacyNotice />
      {failure && (
        <StatusMessage tone="error" title={failure.title}
          action={<Button onClick={() => { setCases(null); void load(); }}>{t('state.retry')}</Button>}>
          {failure.body}
        </StatusMessage>
      )}
      {notice && <StatusMessage tone="error" title={notice} />}
      {cases === null && <StatusMessage tone="loading" title={t('state.loading')} />}
      {cases?.length === 0 && !failure && <StatusMessage tone="empty" title={t('cases.empty')} />}

      {cases && cases.length > 0 && (
        <section className="panel">
          <div className="table-wrap">
            <table className="data cases-table">
              <thead>
                <tr>
                  <th scope="col">{t('cases.colTitle')}</th>
                  <th scope="col">{t('cases.colStatus')}</th>
                  <th scope="col">{t('cases.colRole')}</th>
                  <th scope="col">{t('cases.colLocation')}</th>
                  <th scope="col">{t('cases.colYear')}</th>
                  <th scope="col">{t('cases.colUpdated')}</th>
                  <th scope="col"><span className="sr-only">{t('cases.colActions')}</span></th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => {
                  const title = c.title.trim() || t('cases.untitled');
                  const s = c.server!;
                  const editable = canEdit(c);
                  return (
                    <tr key={c.id}>
                      <th scope="row"><a href={hrefFor('cases', c.id)}>{title}</a></th>
                      <td data-label={t('cases.colStatus')}>{t(`case.status.${s.status}` as MessageKey)}</td>
                      <td data-label={t('cases.colRole')}>{t(`case.role.${s.myRole}` as MessageKey)}</td>
                      <td data-label={t('cases.colLocation')}>{sharedAsText(c, i18n)}</td>
                      <td data-label={t('cases.colYear')}>{c.incidentYear || '—'}</td>
                      <td data-label={t('cases.colUpdated')}><time dateTime={c.updatedAt}>{dateFmt.format(new Date(c.updatedAt))}</time></td>
                      <td className="row-actions">
                        {confirm === c.id ? (
                          <span className="confirm" role="group" aria-label={t('cases.confirmDelete', { title })}>
                            <span>{t('cases.confirmDelete', { title })}</span>
                            <Button variant="secondary" onClick={() => remove(c)}>{t('cases.confirm')}</Button>
                            <Button variant="text" onClick={() => setConfirm(null)}>{t('cases.cancel')}</Button>
                          </span>
                        ) : (
                          <>
                            <ButtonLink href={hrefFor('cases', c.id)} icon={editable ? <Pencil aria-hidden="true" /> : undefined}>
                              {editable ? t('cases.edit') : t('cases.open')}
                            </ButtonLink>
                            {s.myRole === 'OWNER' && (
                              <Button variant="text" icon={<Trash2 aria-hidden="true" />} onClick={() => setConfirm(c.id)}>{t('cases.delete')}</Button>
                            )}
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
