import { useEffect, useState } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useI18n } from '../i18n/I18n';
import { Button, ButtonLink, PageHeader, StatusMessage } from '../design/components';
import { hrefFor, useRouteParam } from '../app/routes';
import { displayedLocation, type IncidentCase } from '../cases/model';
import { caseRepository, StorageUnavailableError } from '../cases/repository';
import { IncidentWizard } from './cases/IncidentWizard';

/** Cases list + wizard routes (#/cases, #/cases/new, #/cases/<id>). Storage is the dev adapter for now. */
export function Cases() {
  const param = useRouteParam();
  return param ? <IncidentWizard key={param} caseId={param} /> : <CaseList />;
}

function CaseList() {
  const { t, lang, num } = useI18n();
  const repo = caseRepository();
  const [cases, setCases] = useState<IncidentCase[] | null>(null);
  const [failure, setFailure] = useState('');
  const [confirm, setConfirm] = useState<string | 'all' | null>(null);

  const load = () =>
    repo.list().then(setCases, (err) => {
      setFailure(err instanceof StorageUnavailableError ? t('cases.storageError') : t('state.unknownError'));
      setCases([]);
    });
  useEffect(() => { void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const dateFmt = new Intl.DateTimeFormat(lang === 'es' ? 'es-ES' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' });
  const sharedAs = (c: IncidentCase) => {
    const d = displayedLocation(c.location, 'guest');
    if (d.kind === 'hidden') return t('f.tier.private');
    if (d.kind === 'region') return d.label;
    return `${num(d.latitude, { digits: 2 })}, ${num(d.longitude, { digits: 2 })}${d.kind === 'rounded' ? ` (±${num(d.rounding / 2, { digits: 2 })}°)` : ''}`;
  };

  async function remove(target: string | 'all') {
    try {
      if (target === 'all') await repo.clear();
      else await repo.remove(target);
      setConfirm(null);
      await load();
    } catch {
      setFailure(t('cases.storageError'));
    }
  }

  return (
    <>
      <PageHeader title={t('cases.title')} lead={t('cases.lead')}
        aside={<ButtonLink variant="primary" href={hrefFor('cases', 'new')} icon={<Plus aria-hidden="true" />}>{t('cases.new')}</ButtonLink>} />
      <StatusMessage tone="pending" title={t('cases.devTitle')}>{t('cases.devBody')}</StatusMessage>
      {failure && <StatusMessage tone="error" title={failure} />}
      {cases === null && <StatusMessage tone="loading" title={t('state.loading')} />}
      {cases?.length === 0 && !failure && <StatusMessage tone="empty" title={t('cases.empty')} />}

      {cases && cases.length > 0 && (
        <section className="panel">
          <div className="table-wrap">
            <table className="data cases-table">
              <thead>
                <tr>
                  <th scope="col">{t('cases.colTitle')}</th>
                  <th scope="col">{t('cases.colLocation')}</th>
                  <th scope="col">{t('cases.colYear')}</th>
                  <th scope="col">{t('cases.colUpdated')}</th>
                  <th scope="col"><span className="sr-only">{t('cases.colActions')}</span></th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => (
                  <tr key={c.id}>
                    <th scope="row"><a href={hrefFor('cases', c.id)}>{c.title.trim() || t('cases.untitled')}</a></th>
                    <td data-label={t('cases.colLocation')}>{sharedAs(c)}</td>
                    <td data-label={t('cases.colYear')}>{c.incidentYear || '—'}</td>
                    <td data-label={t('cases.colUpdated')}>{dateFmt.format(new Date(c.updatedAt))}</td>
                    <td className="row-actions">
                      {confirm === c.id ? (
                        <span className="confirm" role="group" aria-label={t('cases.confirmDelete', { title: c.title || t('cases.untitled') })}>
                          <span>{t('cases.confirmDelete', { title: c.title || t('cases.untitled') })}</span>
                          <Button variant="secondary" onClick={() => remove(c.id)}>{t('cases.confirm')}</Button>
                          <Button variant="text" onClick={() => setConfirm(null)}>{t('cases.cancel')}</Button>
                        </span>
                      ) : (
                        <>
                          <ButtonLink href={hrefFor('cases', c.id)} icon={<Pencil aria-hidden="true" />}>{t('cases.edit')}</ButtonLink>
                          <Button variant="text" icon={<Trash2 aria-hidden="true" />} onClick={() => setConfirm(c.id)}>{t('cases.delete')}</Button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="actions">
            {confirm === 'all' ? (
              <span className="confirm" role="group" aria-label={t('cases.confirmClear')}>
                <span>{t('cases.confirmClear')}</span>
                <Button variant="secondary" onClick={() => remove('all')}>{t('cases.clear')}</Button>
                <Button variant="text" onClick={() => setConfirm(null)}>{t('cases.cancel')}</Button>
              </span>
            ) : (
              <Button variant="text" icon={<Trash2 aria-hidden="true" />} onClick={() => setConfirm('all')}>{t('cases.clear')}</Button>
            )}
          </div>
        </section>
      )}
    </>
  );
}
