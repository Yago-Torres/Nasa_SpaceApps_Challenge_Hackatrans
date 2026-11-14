import { useState, type KeyboardEvent } from 'react';
import { Plus, Trash2, X } from 'lucide-react';
import { useI18n } from '../../i18n/I18n';
import { Button, Field, TextArea } from '../../design/components';
import { emptyConstraints, type ConstraintsState, type FieldErrors, type MarketRow, newRowId } from './model';
import { rotEnum } from './labels';

const WATER = ['UNKNOWN', 'RAINFED', 'IRRIGATED', 'SUPPLEMENTAL_IRRIGATION'] as const;
const IRRIGATION_UNITS = ['mm/season', 'mm/year', 'm3/ha/season', 'm3/ha/year'] as const;
const MARKET_STATUS = ['UNKNOWN', 'CONTRACTED', 'SELLABLE', 'NO_MARKET'] as const;
const MAX_MARKET_ROWS = 40;

function ChipList({ legend, hint, values, onChange, addLabel, removeLabel }: {
  legend: string; hint?: string; values: string[]; onChange: (values: string[]) => void; addLabel: string;
  removeLabel: (value: string) => string;
}) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const v = draft.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setDraft('');
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      add();
    }
  };
  return (
    <div className="field">
      <label htmlFor={`chip-${legend}`}>{legend}</label>
      {hint && <span className="hint">{hint}</span>}
      <div className="form-row form-row--2">
        <div className="ctl">
          <input id={`chip-${legend}`} value={draft} maxLength={80} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKeyDown} autoComplete="off" />
        </div>
        <Button variant="secondary" icon={<Plus aria-hidden="true" />} onClick={add}>{addLabel}</Button>
      </div>
      {values.length > 0 && (
        <div className="actions">
          {values.map((v) => (
            <Button key={v} variant="text" icon={<X aria-hidden="true" />} aria-label={removeLabel(v)} onClick={() => onChange(values.filter((x) => x !== v))}>{v}</Button>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Farmer constraints that the backend screens alternatives against (ABB-11 `FarmerConstraints`):
 * water regime, equipment and market access per crop. These map directly onto
 * `constraint_checks` in each returned strategy (EXCLUDED_CROPS, MARKET_ACCESS, WATER_REGIME,
 * EQUIPMENT in docs/science/ROTATIONS.md).
 */
export function ConstraintsForm({ value, onChange, errors }: { value: ConstraintsState; onChange: (v: ConstraintsState) => void; errors: FieldErrors }) {
  const { t } = useI18n();
  const update = (patch: Partial<ConstraintsState>) => onChange({ ...value, ...patch });
  const setMarket = (id: string, patch: Partial<MarketRow>) => update({ market: value.market.map((m) => (m.id === id ? { ...m, ...patch } : m)) });

  return (
    <div>
      <div className="form-row">
        <div className="field">
          <label htmlFor="rot-water-regime">{t('rot.con.water')}</label>
          <div className="ctl">
            <select id="rot-water-regime" value={value.waterRegime} onChange={(e) => update({ waterRegime: e.target.value as ConstraintsState['waterRegime'] })}>
              {WATER.map((w) => <option key={w} value={w}>{t(rotEnum(w))}</option>)}
            </select>
          </div>
        </div>
        <Field label={t('rot.con.irrigation')} inputMode="decimal" value={value.irrigationValue}
          error={errors['constraints.irrigationValue'] ? t('rot.con.irrigationError') : undefined}
          hint={t('rot.con.irrigationHint')} onChange={(e) => update({ irrigationValue: e.target.value })} />
        <div className="field">
          <label htmlFor="rot-irrigation-unit">{t('rot.con.irrigationUnit')}</label>
          <div className="ctl">
            <select id="rot-irrigation-unit" value={value.irrigationUnit} onChange={(e) => update({ irrigationUnit: e.target.value as ConstraintsState['irrigationUnit'] })}>
              {IRRIGATION_UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </div>
        </div>
      </div>

      <ChipList legend={t('rot.con.excluded')} hint={t('rot.con.excludedHint')} values={value.excludedCrops}
        onChange={(v) => update({ excludedCrops: v })} addLabel={t('rot.con.addChip')} removeLabel={(v) => t('rot.con.removeChip', { value: v })} />

      <ChipList legend={t('rot.con.equipment')} values={value.availableEquipment}
        onChange={(v) => update({ availableEquipment: v })} addLabel={t('rot.con.addChip')} removeLabel={(v) => t('rot.con.removeChip', { value: v })} />

      <TextArea label={t('rot.con.equipmentLimitations')} value={value.equipmentLimitations} maxLength={1000}
        onChange={(e) => update({ equipmentLimitations: e.target.value })} />

      <div>
        <h3>{t('rot.con.marketTitle')}</h3>
        <ol className="crop-rows">
          {value.market.map((row, i) => (
            <li key={row.id}>
              <div className="form-row">
                <Field label={t('rot.con.marketCrop')} value={row.cropLabel} maxLength={120} onChange={(e) => setMarket(row.id, { cropLabel: e.target.value })} />
                <div className="field">
                  <label htmlFor={`market-status-${row.id}`}>{t('rot.con.marketStatus')}</label>
                  <div className="ctl">
                    <select id={`market-status-${row.id}`} value={row.status} onChange={(e) => setMarket(row.id, { status: e.target.value as MarketRow['status'] })}>
                      {MARKET_STATUS.map((s) => <option key={s} value={s}>{t(rotEnum(s))}</option>)}
                    </select>
                  </div>
                </div>
                <div className="actions">
                  <Button variant="text" icon={<Trash2 aria-hidden="true" />} onClick={() => update({ market: value.market.filter((m) => m.id !== row.id) })}>
                    {t('rot.con.marketRemove', { n: i + 1 })}
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ol>
        {value.market.length < MAX_MARKET_ROWS && (
          <div className="actions">
            <Button variant="secondary" icon={<Plus aria-hidden="true" />}
              onClick={() => update({ market: [...value.market, { id: newRowId('mkt'), cropLabel: '', status: 'UNKNOWN' }] })}>
              {t('rot.con.marketAdd')}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

export { emptyConstraints };
