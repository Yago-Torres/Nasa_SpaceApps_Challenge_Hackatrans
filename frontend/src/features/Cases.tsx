import { ArrowRight } from 'lucide-react';
import { useI18n } from '../i18n/I18n';
import { ButtonLink, PageHeader, StatusMessage } from '../design/components';
import { hrefFor } from '../app/routes';

/** Placeholder until case storage and auth exist (ABB-05, ABB-06). No mock cases are shown. */
export function Cases() {
  const { t } = useI18n();
  return (
    <>
      <PageHeader title={t('cases.title')} lead={t('cases.lead')} />
      <StatusMessage
        tone="pending"
        title={t('state.notBuiltTitle')}
        action={<ButtonLink variant="primary" href={hrefFor('investigation')} icon={<ArrowRight className="go" aria-hidden="true" />}>{t('dash.start')}</ButtonLink>}
      >
        {t('cases.pending')}
      </StatusMessage>
    </>
  );
}
