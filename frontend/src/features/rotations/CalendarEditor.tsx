import { Plus, Trash2 } from 'lucide-react';
import { useI18n } from '../../i18n/I18n';
import { Button, Field } from '../../design/components';
import { emptyCalendarRow, type CalendarRow, type FieldErrors } from './model';
import type { CropCatalogEntry } from '../../api/types';

const MAX_ROWS = 40;

/**
 * Editor for the farmer's declared sowing/harvest month windows (`local_calendar`). The
 * backend never invents a calendar: a crop with no window here cannot be used in a
 * rule-generated alternative (docs/science/ROTATIONS.md, "candidate screening"). This is
 * therefore the editor that actually widens or narrows which alternative strategies the
 * backend is able to generate.
 */
export function CalendarEditor({ rows, onChange, errors, catalog }: {
  rows: CalendarRow[];
  onChange: (rows: CalendarRow[]) => void;
  errors: FieldErrors;
  catalog: CropCatalogEntry[];
}) {
  const { t, lang } = useI18n();
  const set = (id: string, patch: Partial<CalendarRow>) => onChange(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const names = catalog.map((c) => (lang === 'es' ? c.common_name_es : c.common_name_en));

  return (
    <div>
      <p className="muted">{t('rot.cal.hint')}</p>
      <datalist id="rot-cal-crop-names">
        {names.map((n) => <option key={n} value={n} />)}
      </datalist>
      <ol className="crop-rows">
        {rows.map((row, i) => (
          <li key={row.id}>
            <div className="form-row">
              <Field label={t('rot.cal.label')} list="rot-cal-crop-names" value={row.cropLabel} maxLength={120}
                error={errors[`cal.${row.id}.cropLabel`] ? t('rot.cal.labelError') : undefined}
                onChange={(e) => set(row.id, { cropLabel: e.target.value, cropCode: catalog.find((c) => c.common_name_en === e.target.value || c.common_name_es === e.target.value)?.code ?? null })} />
              <Field label={t('rot.cal.sowingStart')} inputMode="numeric" unit={t('rot.cal.monthUnit')} value={row.sowingStartMonth}
                error={errors[`cal.${row.id}.sowingStartMonth`] ? t('rot.cal.monthError') : undefined}
                onChange={(e) => set(row.id, { sowingStartMonth: e.target.value })} />
              <Field label={t('rot.cal.sowingEnd')} inputMode="numeric" unit={t('rot.cal.monthUnit')} value={row.sowingEndMonth}
                error={errors[`cal.${row.id}.sowingEndMonth`] ? t('rot.cal.monthError') : undefined}
                onChange={(e) => set(row.id, { sowingEndMonth: e.target.value })} />
            </div>
            <div className="form-row">
              <Field label={t('rot.cal.harvestStart')} inputMode="numeric" unit={t('rot.cal.monthUnit')} value={row.harvestStartMonth} hint={t('rot.cal.harvestHint')}
                error={errors[`cal.${row.id}.harvestStartMonth`] ? t(errors[`cal.${row.id}.harvestStartMonth`] === 'pair' ? 'rot.cal.pairError' : 'rot.cal.monthError') : undefined}
                onChange={(e) => set(row.id, { harvestStartMonth: e.target.value })} />
              <Field label={t('rot.cal.harvestEnd')} inputMode="numeric" unit={t('rot.cal.monthUnit')} value={row.harvestEndMonth}
                error={errors[`cal.${row.id}.harvestEndMonth`] ? t(errors[`cal.${row.id}.harvestEndMonth`] === 'pair' ? 'rot.cal.pairError' : 'rot.cal.monthError') : undefined}
                onChange={(e) => set(row.id, { harvestEndMonth: e.target.value })} />
            </div>
            {rows.length > 1 && (
              <div className="actions">
                <Button variant="text" icon={<Trash2 aria-hidden="true" />} onClick={() => onChange(rows.filter((r) => r.id !== row.id))}>
                  {t('rot.cal.remove', { n: i + 1 })}
                </Button>
              </div>
            )}
          </li>
        ))}
      </ol>
      {rows.length < MAX_ROWS && (
        <div className="actions">
          <Button variant="secondary" icon={<Plus aria-hidden="true" />} onClick={() => onChange([...rows, emptyCalendarRow()])}>{t('rot.cal.add')}</Button>
        </div>
      )}
    </div>
  );
}
