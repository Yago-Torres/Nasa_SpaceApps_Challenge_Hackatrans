import { useState } from 'react';
import { useI18n } from '../../i18n/I18n';
import { Button, StatusMessage } from '../../design/components';
import type { FarmerPriority, PriorityCriterion, SensitivityAnalysis } from '../../api/types';
import type { AsyncStatus } from './store';
import { rotEnum } from './labels';

/**
 * "What changes if I swap these two priorities?" (ABB-18 `POST /rotations/sensitivity`,
 * `PRIORITY_SWAP`). A direct, real backend recompute — never a client-side guess — that
 * reports which strategy pair's order changed and the exact criterion that decided it
 * (docs/science/SCENARIOS_SENSITIVITY.md). Requires at least two ranked priorities.
 */
export function SensitivityPanel({ rankedPriorities, status, failure, result, onRun }: {
  rankedPriorities: FarmerPriority[];
  status: AsyncStatus;
  failure: string;
  result: SensitivityAnalysis | null;
  onRun: (a: PriorityCriterion, b: PriorityCriterion) => void;
}) {
  const { t } = useI18n();
  const ranked = [...rankedPriorities].filter((p) => p.criterion !== 'OTHER').sort((x, y) => x.rank - y.rank);
  const [a, setA] = useState<PriorityCriterion | ''>('');
  const [b, setB] = useState<PriorityCriterion | ''>('');

  if (ranked.length < 2) return <p className="muted">{t('rot.sens.needTwoRanked')}</p>;

  return (
    <div>
      <p className="muted">{t('rot.sens.hint')}</p>
      <div className="form-row">
        <div className="field">
          <label htmlFor="sens-a">{t('rot.sens.criterionA')}</label>
          <div className="ctl">
            <select id="sens-a" value={a} onChange={(e) => setA(e.target.value as PriorityCriterion)}>
              <option value="">{t('rot.sens.choose')}</option>
              {ranked.map((p) => <option key={p.criterion} value={p.criterion}>{t(rotEnum(p.criterion))}</option>)}
            </select>
          </div>
        </div>
        <div className="field">
          <label htmlFor="sens-b">{t('rot.sens.criterionB')}</label>
          <div className="ctl">
            <select id="sens-b" value={b} onChange={(e) => setB(e.target.value as PriorityCriterion)}>
              <option value="">{t('rot.sens.choose')}</option>
              {ranked.filter((p) => p.criterion !== a).map((p) => <option key={p.criterion} value={p.criterion}>{t(rotEnum(p.criterion))}</option>)}
            </select>
          </div>
        </div>
        <div className="actions">
          <Button variant="secondary" busy={status === 'loading'} disabled={!a || !b || a === b}
            onClick={() => a && b && onRun(a, b)}>
            {status === 'loading' ? t('rot.sens.running') : t('rot.sens.run')}
          </Button>
        </div>
      </div>

      {status === 'error' && <StatusMessage tone="error" title={t('rot.sens.errorTitle')}>{failure}</StatusMessage>}

      {status === 'done' && result && (
        result.status === 'NOT_COMPARABLE' ? (
          <StatusMessage tone="partial" title={t('rot.sens.notComparable')} />
        ) : (
          <div>
            <ul className="list-plain">
              {result.explanation.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
            {result.pair_changes.filter((p) => p.order_changed).length > 0 && (
              <div>
                <h4>{t('rot.sens.pairChangesTitle')}</h4>
                <ul className="list-plain">
                  {result.pair_changes.filter((p) => p.order_changed).map((p, i) => <li key={i}>{p.explanation}</li>)}
                </ul>
              </div>
            )}
          </div>
        )
      )}
    </div>
  );
}
