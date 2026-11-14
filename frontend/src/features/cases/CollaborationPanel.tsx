import { useI18n } from '../../i18n/I18n';
import { StatusMessage } from '../../design/components';
import { CaseGate } from './CaseGate';
import { CaseTitleBlock } from './CaseTitleBlock';
import { MembersSection } from './collaboration/MembersSection';
import { InvitationsSection } from './collaboration/InvitationsSection';
import { ShareLinksSection } from './collaboration/ShareLinksSection';

/**
 * Case "Collaborators" tab (ABB-25): who has access, invitations and consented share links.
 * The server enforces every rule (ADR-0004, docs/architecture/COLLABORATION.md); this screen only
 * hides controls a role cannot use. Discussion and the audit trail live in the "Discussion" tab.
 */
export function CollaborationPanel({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  return (
    <CaseGate caseId={caseId} title={t('collab.caseTitle')}>
      {(c) => {
        const owner = c.server?.myRole === 'OWNER';
        return (
          <>
            <CaseTitleBlock c={c} lead={t('collab.caseLead')} />
            <MembersSection caseId={caseId} owner={owner} />
            {owner ? (
              <>
                <InvitationsSection caseId={caseId} />
                <ShareLinksSection caseId={caseId} />
              </>
            ) : (
              <StatusMessage tone="empty" title={t('collab.ownerOnlyTitle')}>{t('collab.ownerOnlyBody')}</StatusMessage>
            )}
          </>
        );
      }}
    </CaseGate>
  );
}
