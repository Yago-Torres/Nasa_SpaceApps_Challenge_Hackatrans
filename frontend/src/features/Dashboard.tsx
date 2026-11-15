import { ArrowRight } from 'lucide-react';
import { useI18n } from '../i18n/I18n';
import { ButtonLink, EvidenceLabel, StatusMessage, type EvidenceKind } from '../design/components';
import { ROUTES, hrefFor } from '../app/routes';

const KINDS: EvidenceKind[] = ['OBSERVED', 'FARMER_REPORTED', 'LITERATURE_REVIEWED', 'HYPOTHESIS', 'MODEL_SCENARIO', 'ILLUSTRATIVE', 'MISSING_DATA'];

export function Dashboard() {
  const { t } = useI18n();
  return (
    <>
      <section className="hero" aria-labelledby="dash-title">
        <h1 id="dash-title" tabIndex={-1} data-page-title>{t('dash.title')}</h1>
        <p>{t('dash.lead')}</p>
        <div className="actions">
          <ButtonLink variant="primary" href={hrefFor('cases')} icon={<ArrowRight className="go" aria-hidden="true" />}>{t('dash.start')}</ButtonLink>
          <ButtonLink href={hrefFor('investigation')}>{t('dash.oneOff')}</ButtonLink>
        </div>
      </section>

      <StatusMessage tone="partial" title={t('dash.unsavedTitle')}>{t('dash.unsavedBody')}</StatusMessage>

      <section className="panel" aria-labelledby="dash-steps">
        <h2 id="dash-steps">{t('dash.stepsTitle')}</h2>
        <ol className="steps">
          {ROUTES.slice(1).map((r, i) => (
            <li key={r.id} className={r.available ? undefined : 'pending'}>
              <a href={hrefFor(r.id)}>
                <span className="n" aria-hidden="true">{i + 1}</span>
                <b>{t(r.label)}</b>
                <small>{r.available ? t('dash.stepAvailable') : t('dash.stepPending')}</small>
              </a>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel" aria-labelledby="dash-legend">
        <h2 id="dash-legend">{t('dash.legendTitle')}</h2>
        <ul className="legend">
          {KINDS.map((k) => (
            <li key={k}>
              <EvidenceLabel kind={k} />
              <p>{t(`dash.legend.${k}`)}</p>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
