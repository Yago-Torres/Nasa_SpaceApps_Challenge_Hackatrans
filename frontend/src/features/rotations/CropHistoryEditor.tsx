import { Plus, Trash2 } from 'lucide-react';
import { useI18n } from '../../i18n/I18n';
import { Button, Field } from '../../design/components';
import { emptyCropRow, type CropRow, type FieldErrors } from './model';
import { rotEnum } from './labels';
import type { CropCatalogEntry } from '../../api/types';

const ROLES = ['MAIN_CROP', 'INTERCROP', 'COVER_CROP', 'FALLOW'] as const;
const WATER = ['UNKNOWN', 'RAINFED', 'IRRIGATED', 'SUPPLEMENTAL_IRRIGATION'] as const;
const MAX_ROWS = 60;

/**
 * Editor for the farmer's recorded crop history: the sequence the backend derives the
 * "current rotation" from (docs/science/ROTATIONS.md, rule 1). At least two seasons with a
 * main crop are needed before the backend can identify a cycle; the response explains this
 * with `profile_issues` / `status: INSUFFICIENT_INPUT` rather than the UI guessing it.
 */
export function CropHistoryEditor({ rows, onChange, errors, catalog }: {
  rows: CropRow[];
  onChange: (rows: CropRow[]) => void;
  errors: FieldErrors;
  catalog: CropCatalogEntry[];
}) {
  const { t, lang } = useI18n();
  const set = (id: string, patch: Partial<CropRow>) => onChange(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const names = catalog.map((c) => (lang === 'es' ? c.common_name_es : c.common_name_en));

  return (
    <div>
      <p className="muted">{t('rot.crop.hint')}</p>
      <datalist id="rot-crop-names">
        {names.map((n) => <option key={n} value={n} />)}
      </datalist>
      <ol className="crop-rows">
        {rows.map((row, i) => (
          <li key={row.id}>
            <div className="form-row">
              <div className="field">
                <label htmlFor={`crop-role-${row.id}`}>{t('rot.crop.role')}</label>
                <div className="ctl">
                  <select id={`crop-role-${row.id}`} value={row.role} onChange={(e) => set(row.id, { role: e.target.value as CropRow['role'] })}>
                    {ROLES.map((r) => <option key={r} value={r}>{t(rotEnum(r))}</option>)}
                  </select>
                </div>
              </div>
              <Field label={t('rot.crop.label')} list="rot-crop-names" value={row.cropLabel} maxLength={120}
                error={errors[`crop.${row.id}.cropLabel`] ? t('rot.crop.labelError') : undefined}
                onChange={(e) => set(row.id, { cropLabel: e.target.value, cropCode: catalog.find((c) => c.common_name_en === e.target.value || c.common_name_es === e.target.value)?.code ?? null })} />
              <Field label={t('rot.crop.year')} inputMode="numeric" value={row.seasonYear}
                error={errors[`crop.${row.id}.seasonYear`] ? t('rot.crop.yearError') : undefined}
                onChange={(e) => set(row.id, { seasonYear: e.target.value })} />
            </div>
            <div className="form-row">
              <Field label={t('rot.crop.sowing')} type="date" value={row.sowingDate}
                error={errors[`crop.${row.id}.sowingDate`] ? t('rot.crop.dateError') : undefined}
                onChange={(e) => set(row.id, { sowingDate: e.target.value })} />
              <Field label={t('rot.crop.harvest')} type="date" value={row.harvestDate}
                error={errors[`crop.${row.id}.harvestDate`] ? t(errors[`crop.${row.id}.harvestDate`] === 'order' ? 'rot.crop.orderError' : 'rot.crop.dateError') : undefined}
                onChange={(e) => set(row.id, { harvestDate: e.target.value })} />
              <div className="field">
                <label htmlFor={`crop-water-${row.id}`}>{t('rot.crop.water')}</label>
                <div className="ctl">
                  <select id={`crop-water-${row.id}`} value={row.waterRegime} onChange={(e) => set(row.id, { waterRegime: e.target.value as CropRow['waterRegime'] })}>
                    {WATER.map((w) => <option key={w} value={w}>{t(rotEnum(w))}</option>)}
                  </select>
                </div>
              </div>
            </div>
            {rows.length > 1 && (
              <div className="actions">
                <Button variant="text" icon={<Trash2 aria-hidden="true" />} onClick={() => onChange(rows.filter((r) => r.id !== row.id))}>
                  {t('rot.crop.remove', { n: i + 1 })}
                </Button>
              </div>
            )}
          </li>
        ))}
      </ol>
      {rows.length < MAX_ROWS && (
        <div className="actions">
          <Button variant="secondary" icon={<Plus aria-hidden="true" />} onClick={() => onChange([...rows, emptyCropRow()])}>{t('rot.crop.add')}</Button>
        </div>
      )}
    </div>
  );
}
