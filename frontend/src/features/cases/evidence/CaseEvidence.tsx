import { useState } from 'react';
import { useI18n } from '../../../i18n/I18n';
import { canEdit } from '../../../cases/model';
import { CaseGate } from '../CaseGate';
import { CaseTitleBlock } from '../CaseTitleBlock';
import { ClaimsSection } from './ClaimsSection';
import { DisagreementsSection } from './DisagreementsSection';
import { GraphSection } from './GraphSection';
import { GraphWorkflowSection } from './ReviewForms';

/**
 * Case "Evidence" tab (ABB-23): the studies kept for this case with their review status, context
 * and limitations (ABB-14), disagreements and transferability (ABB-15), and the evidence graph with
 * the trace from any conclusion back to observations, farmer reports and DOIs (ABB-16). Every member
 * can read; adding a study needs OWNER/EDITOR on an editable case, and the server enforces it.
 */
export function CaseEvidence({ caseId }: { caseId: string }) {
  const { t } = useI18n();
  const [version, setVersion] = useState(0);
  const [focusClaim, setFocusClaim] = useState<{ id: string; seq: number } | null>(null);
  const openClaim = (id: string) => setFocusClaim((f) => ({ id, seq: (f?.seq ?? 0) + 1 }));
  return (
    <CaseGate caseId={caseId} title={t('evx.title')}>
      {(c) => (
        <>
          <CaseTitleBlock c={c} lead={t('evx.lead')} />
          <GraphSection caseId={caseId} refreshKey={version} onOpenClaim={openClaim} />
          <GraphWorkflowSection caseId={caseId} canWrite={canEdit(c)} refreshKey={version} onChanged={() => setVersion((n) => n + 1)} />
          <ClaimsSection caseId={caseId} canAdd={canEdit(c)} focusClaim={focusClaim} onChanged={() => setVersion((n) => n + 1)} />
          <DisagreementsSection caseId={caseId} refreshKey={version} onOpenClaim={openClaim} />
        </>
      )}
    </CaseGate>
  );
}
