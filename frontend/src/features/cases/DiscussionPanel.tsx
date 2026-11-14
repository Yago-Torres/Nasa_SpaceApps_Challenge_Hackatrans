import { useState } from 'react';
import { useI18n } from '../../i18n/I18n';
import { CaseGate } from './CaseGate';
import { CaseTitleBlock } from './CaseTitleBlock';
import { CommentsSection } from './collaboration/CommentsSection';
import { ActivitySection } from './collaboration/ActivitySection';

/**
 * Case "Discussion" tab (ABB-25): plain-text comments from every member (viewers included, as the
 * Issue requires that a guest can comment) and the case's read-only audit trail. Archived cases
 * reject new comments (409), so the composer is replaced by an explanation there.
 */
export function DiscussionPanel({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  const [activityKey, setActivityKey] = useState(0);
  return (
    <CaseGate caseId={caseId} title={t('collab.discussionTitle')}>
      {(c) => (
        <>
          <CaseTitleBlock c={c} lead={t('collab.discussionLead')} />
          <CommentsSection caseId={caseId} canPost={!c.server?.archived} onPosted={() => setActivityKey((n) => n + 1)} />
          <ActivitySection caseId={caseId} refreshKey={activityKey} />
        </>
      )}
    </CaseGate>
  );
}
