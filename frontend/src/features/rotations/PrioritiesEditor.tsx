import { ChevronDown, ChevronUp, Plus, X } from 'lucide-react';
import { useI18n } from '../../i18n/I18n';
import { Button } from '../../design/components';
import type { FarmerPriority, PriorityCriterion } from '../../api/types';
import { ALL_PRIORITY_CRITERIA, addPriority, movePriority, removePriority } from './model';
import { rotEnum } from './labels';

/**
 * Ordinal priority ranking (ABB-11 `FarmerPriority`: rank 1 = most important, never a numeric
 * weight). Changing this list is the input the comparator is built to react to: every change
 * here should trigger a real backend recompute through `POST /rotations/scenarios`
 * (docs/architecture/FRONTEND_INTEGRATION.md B4), which orders strategies lexicographically by
 * rank and explains every step — never a client-side score.
 */
export function PrioritiesEditor({ priorities, onChange }: { priorities: FarmerPriority[]; onChange: (p: FarmerPriority[]) => void }) {
  const { t } = useI18n();
  const ranked = [...priorities].sort((a, b) => a.rank - b.rank);
  const unranked = ALL_PRIORITY_CRITERIA.filter((c) => c === 'OTHER' || !priorities.some((p) => p.criterion === c));

  return (
    <div>
      <p className="muted">{t('rot.pri.hint')}</p>
      {ranked.length === 0 && <p className="muted">{t('rot.pri.empty')}</p>}
      {ranked.length > 0 && (
        <ol className="crop-rows">
          {ranked.map((p, i) => (
            <li key={p.criterion}>
              <div className="rot-priority">
                <b className="num">{t('rot.pri.rank', { n: p.rank })}</b>
                <span>{t(rotEnum(p.criterion))}</span>
                <Button variant="text" icon={<ChevronUp aria-hidden="true" />} disabled={i === 0}
                  aria-label={t('rot.pri.up', { name: t(rotEnum(p.criterion)) })}
                  onClick={() => onChange(movePriority(priorities, p.criterion, -1))} />
                <Button variant="text" icon={<ChevronDown aria-hidden="true" />} disabled={i === ranked.length - 1}
                  aria-label={t('rot.pri.down', { name: t(rotEnum(p.criterion)) })}
                  onClick={() => onChange(movePriority(priorities, p.criterion, 1))} />
                <Button variant="text" icon={<X aria-hidden="true" />}
                  aria-label={t('rot.pri.remove', { name: t(rotEnum(p.criterion)) })}
                  onClick={() => onChange(removePriority(priorities, p.criterion))} />
              </div>
            </li>
          ))}
        </ol>
      )}
      {unranked.length > 0 && (
        <div className="actions">
          {unranked.map((c) => (
            <Button key={c} variant="secondary" icon={<Plus aria-hidden="true" />} onClick={() => onChange(addPriority(priorities, c as PriorityCriterion))}>
              {t(rotEnum(c))}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
