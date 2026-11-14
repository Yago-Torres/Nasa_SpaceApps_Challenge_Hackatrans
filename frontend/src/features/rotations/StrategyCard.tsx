import { AlertTriangle, Check } from 'lucide-react';
import { useI18n } from '../../i18n/I18n';
import { EvidenceLabel } from '../../design/components';
import { rotEnum } from './labels';
import type { OrderedPosition, RotationStrategy, StrategyExposure, StrategyTradeOff } from '../../api/types';

function Badge({ children }: { children: string }) {
  return <span className="chip-meta">{children}</span>;
}

/**
 * One strategy (current rotation or a rule-generated alternative) exactly as the backend
 * described it: calendar, constraint checks, descriptive comparison, benefits/risks framed as
 * unquantified and needing review, assumptions, and what still needs review before field use.
 * Nothing here is computed in the browser (docs/science/ROTATIONS.md, SCIENTIFIC_POLICY).
 */
export function StrategyCard({ strategy, position, exposure, tradeOff }: {
  strategy: RotationStrategy;
  position: OrderedPosition | null;
  exposure: StrategyExposure[];
  tradeOff: StrategyTradeOff | null;
}) {
  const { t } = useI18n();
  const s = strategy;

  return (
    <article className="rotation" aria-labelledby={`strategy-${s.id}`}>
      <div className="panel-head">
        <h3 id={`strategy-${s.id}`}>{t(rotEnum(s.strategy_kind))}</h3>
        <EvidenceLabel kind="MODEL_SCENARIO" />
      </div>

      {position && (
        <p className="muted">
          {position.tied_with.length > 0
            ? t('rot.card.positionTied', { n: position.position })
            : t('rot.card.position', { n: position.position })}
        </p>
      )}
      <p className="muted">
        {s.sequence_origin === 'FARMER_REPORTED' ? t('rot.card.sequenceOrigin.FARMER_REPORTED') : t('rot.card.sequenceOrigin.RULE_GENERATED')}
        {' — '}{s.selection_rule}
      </p>

      <div>
        <h4>{t('rot.card.calendarTitle')}</h4>
        <ol>
          {s.years.map((crops, y) => (
            <li key={y}><span>{t('rot.year', { n: y + 1 })}</span><span>{crops.length ? crops.join(' + ') : t('rot.card.fallowSlot')}</span></li>
          ))}
        </ol>
      </div>

      {s.transitions.length > 0 && (
        <div>
          <h4>{t('rot.card.transitionsTitle')}</h4>
          <ul className="list-plain">
            {s.transitions.map((tr, i) => (
              <li key={i}>
                <Badge>{t(rotEnum(tr.status))}</Badge> {tr.from_crop} → {tr.to_crop}: {tr.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* A list, not a table: a three-column table cannot fit the narrow strategy column without
          horizontal scrolling, and each detail is a sentence rather than a comparable value. */}
      <div>
        <h4>{t('rot.card.constraintsTitle')}</h4>
        <ul className="list-plain">
          {s.constraint_checks.map((c, i) => (
            <li key={i}>
              <b>{t(rotEnum(c.constraint))}</b> <Badge>{t(rotEnum(c.status))}</Badge> {c.detail}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h4>{t('rot.card.comparisonTitle')}</h4>
        <ul className="list-plain">
          <li>{t('rot.card.distinctCrops', { n: s.comparison.distinct_crops })}</li>
          <li>{t('rot.card.families', { n: s.comparison.distinct_families, list: s.comparison.families.join(', ') })}</li>
          {s.comparison.includes_legume && <li>{t('rot.card.legumeYears', { n: s.comparison.legume_years_per_cycle })}</li>}
          {s.comparison.months_with_crop && (
            <li>{t('rot.card.monthsWithCrop', { min: s.comparison.months_with_crop.min, max: s.comparison.months_with_crop.max })}</li>
          )}
          {s.comparison.longest_fallow_gap && (
            <li>{t('rot.card.fallowGap', { min: s.comparison.longest_fallow_gap.min, max: s.comparison.longest_fallow_gap.max })}</li>
          )}
          {s.comparison.crops_new_to_farm.length > 0 && <li>{t('rot.card.newToFarm', { list: s.comparison.crops_new_to_farm.join(', ') })}</li>}
          {s.comparison.market_status.map((m, i) => <li key={i}>{m.crop_label}: {t(rotEnum(m.status))}</li>)}
          {s.comparison.not_evaluable.map((n, i) => <li key={`ne-${i}`} className="muted">{n}</li>)}
        </ul>
      </div>

      {s.priorities_addressed.length > 0 && !s.is_current && (
        <div>
          <h4>{t('rot.card.prioritiesTitle')}</h4>
          <ul className="list-plain">
            {s.priorities_addressed.map((p, i) => (
              <li key={i}>{t('rot.pri.rank', { n: p.rank })} {t(rotEnum(p.criterion))}: <Badge>{t(rotEnum(p.relation_to_current))}</Badge> — {p.basis}</li>
            ))}
          </ul>
        </div>
      )}

      {(s.possible_benefits.length > 0 || s.risks.length > 0) && (
        <div className="gap-list">
          {s.possible_benefits.map((b, i) => <p key={`b-${i}`}><Check aria-hidden="true" width={16} height={16} /> {b}</p>)}
          {s.risks.map((r, i) => <p key={`r-${i}`}><AlertTriangle aria-hidden="true" width={16} height={16} /> {r}</p>)}
        </div>
      )}

      {exposure.map((ex) => (
        <p key={ex.scenario_id} className="muted">
          {ex.status === 'NOT_EVALUABLE' ? t('rot.card.exposureNotEvaluable', { scenario: ex.scenario_id })
            : ex.flagged_months_in_field_per_year
              ? t('rot.card.exposure', { min: ex.flagged_months_in_field_per_year.min, max: ex.flagged_months_in_field_per_year.max, scenario: ex.scenario_id })
              : t('rot.card.exposurePartial', { scenario: ex.scenario_id })}
        </p>
      ))}

      {/* Two different comparisons from the backend, kept apart so a gain is never read as a loss:
          gains_vs_current = more favourable than the current rotation; gives_up = another strategy
          is more favourable on that criterion (applies to the current rotation too). */}
      {tradeOff && !s.is_current && tradeOff.gains_vs_current.length > 0 && (
        <div>
          <h4>{t('rot.card.gainsTitle')}</h4>
          <ul className="list-plain">
            {tradeOff.gains_vs_current.map((g, i) => <li key={`g-${i}`}>{g}</li>)}
          </ul>
        </div>
      )}
      {tradeOff && tradeOff.gives_up.length > 0 && (
        <div>
          <h4>{t('rot.card.givesUpTitle')}</h4>
          <ul className="list-plain">
            {tradeOff.gives_up.map((g, i) => <li key={`u-${i}`}>{g}</li>)}
          </ul>
        </div>
      )}

      <details>
        <summary>{t('rot.card.detailsTitle')}</summary>
        <ul className="list-plain">
          {s.assumptions.map((a, i) => <li key={`a-${i}`}>{a}</li>)}
          {s.conditions_requiring_review.map((c, i) => <li key={`c-${i}`}>{c}</li>)}
          {s.limitations.map((l, i) => <li key={`l-${i}`} className="muted">{l}</li>)}
        </ul>
        {s.evidence_refs.length > 0 && (
          <ul className="papers">
            {s.evidence_refs.map((e) => (
              <li key={e.id}>
                <b>{e.title}</b>
                <span className="meta">
                  <span className="chip-meta">{t('evidence.metadataOnly')}</span>
                  <a href={`https://doi.org/${e.doi}`} target="_blank" rel="noreferrer">{e.doi}</a>
                </span>
                <span className="muted">{e.topic} {e.limitation}</span>
              </li>
            ))}
          </ul>
        )}
      </details>
    </article>
  );
}
