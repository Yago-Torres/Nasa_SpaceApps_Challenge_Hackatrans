import { useI18n } from '../i18n/I18n';
import { PageHeader, StatusMessage } from '../design/components';

/** Placeholder until invitations and reviews exist (ABB-25, needs ABB-05). */
export function Collaboration() {
  const { t } = useI18n();
  return (
    <>
      <PageHeader title={t('col.title')} lead={t('col.lead')} />
      <StatusMessage tone="pending" title={t('state.notBuiltTitle')}>{t('col.pending')}</StatusMessage>
    </>
  );
}
