import { Plus, X } from 'lucide-react';
import { useI18n } from '../../i18n/I18n';
import type { MessageKey } from '../../i18n/messages';
import { Button } from '../../design/components';
import type { Condition, HypotheticalScenario } from '../../api/types';

const PRESETS: { id: string; labelKey: MessageKey; condition: Condition; months: number[] }[] = [
  { id: 'dry-spring', labelKey: 'rot.clim.preset.drySpring', condition: 'DRIER', months: [3, 4, 5] },
  { id: 'wet-autumn', labelKey: 'rot.clim.preset.wetAutumn', condition: 'WETTER', months: [9, 10, 11] },
  { id: 'hot-summer', labelKey: 'rot.clim.preset.hotSummer', condition: 'HOTTER', months: [6, 7, 8] },
  { id: 'cold-winter', labelKey: 'rot.clim.preset.coldWinter', condition: 'COOLER', months: [12, 1, 2] },
];

/**
 * Optional what-if climate flags (ABB-18 `HYPOTHETICAL` scenarios): a user-chosen assumption
 * about which months are drier/wetter/hotter/cooler than usual — never a forecast and never
 * observed data (`is_forecast: false`, `scenario_label: HYPOTHETICAL_SCENARIO`). These feed the
 * RISK_REDUCTION priority's exposure criterion, which is a calendar-overlap proxy, not a risk
 * estimate (docs/science/SCENARIOS_SENSITIVITY.md). Real observed episodes from `GET
 * /api/climate` (`HISTORICAL_EPISODE`) would need a case-bound location and are deferred; see
 * the handoff notes in this PR.
 */
export function ClimateScenarioEditor({ scenarios, onChange }: { scenarios: HypotheticalScenario[]; onChange: (s: HypotheticalScenario[]) => void }) {
  const { t } = useI18n();
  const active = new Set(scenarios.map((s) => s.id));

  const toggle = (preset: typeof PRESETS[number]) => {
    if (active.has(preset.id)) {
      onChange(scenarios.filter((s) => s.id !== preset.id));
      return;
    }
    const scenario: HypotheticalScenario = {
      scenario_type: 'HYPOTHETICAL', id: preset.id, label: t(preset.labelKey),
      flags: [{ condition: preset.condition, months: preset.months }],
    };
    onChange([...scenarios, scenario]);
  };

  return (
    <div>
      <p className="muted">{t('rot.clim.hint')}</p>
      <div className="actions">
        {PRESETS.map((p) => (
          <Button key={p.id} variant={active.has(p.id) ? 'primary' : 'secondary'} icon={active.has(p.id) ? <X aria-hidden="true" /> : <Plus aria-hidden="true" />} onClick={() => toggle(p)}>
            {t(p.labelKey)}
          </Button>
        ))}
      </div>
    </div>
  );
}
