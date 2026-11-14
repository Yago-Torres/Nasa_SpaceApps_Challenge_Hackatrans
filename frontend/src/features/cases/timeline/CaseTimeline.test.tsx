import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../../../i18n/I18n';
import { clearSession, resetSessionCache, setSession } from '../../../api/session';
import type {
  CaseView, HypothesisList, HypothesisTemplateCatalog, HypothesisView, Timeline,
} from '../../../api/types';
import { CaseTimeline } from './CaseTimeline';

/* ── TEST-ONLY synthetic fixtures ──────────────────────────────────────────────────────────
 * Shaped exactly like the documented ABB-10 contract (docs/science/TIMELINE_HYPOTHESES.md,
 * backend/agroblackbox/api/forensics_dto.py). Every id, value and date here is synthetic;
 * the app itself never ships sample data (only *.test.tsx fixtures do). */

const CASE_ID = '11111111-1111-4111-8111-111111111111';
const USER = { id: 'u1', email: 'owner@example.org', display_name: 'Synthetic owner', created_at: '2026-01-01T00:00:00Z' };

const CASE_VIEW: CaseView = {
  schema_version: '1.0', id: CASE_ID, title: 'Synthetic plot', incident_start: '2022-04-01', incident_end: '2022-06-30',
  fields: [{ schema_version: '1.0', id: 'f1', label: 'North field', privacy_tier: 'APPROXIMATE', latitude: 41.6, longitude: -0.9,
    region_label: 'Not shared by the owner', area_hectares: null, limitations: [], location_precision: 'EXACT', rounding_deg: 0.1, precise_location_consent: false }],
  crop_history: [], incident_notes: 'Yellowing leaves from mid-April.', visibility: 'PRIVATE',
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', version: 1, status: 'INVESTIGATING', archived_at: null,
  owner: { id: 'u1', display_name: 'Synthetic owner' }, my_role: 'OWNER',
};

const ANOMALY_ID = '22222222-2222-4222-8222-222222222222';
const OBSERVATION_ID = '66666666-6666-4666-8666-666666666666';

function timelineFixture(): Timeline {
  return {
    case_id: CASE_ID, case_version: 1, generated_at: '2026-01-02T00:00:00Z', incident_start: '2022-04-01', incident_end: '2022-06-30',
    layers: [
      { kind: 'OBSERVED', description: 'Monthly NASA POWER values and their descriptive anomalies.', event_count: 1 },
      { kind: 'FARMER_REPORTED', description: 'Information reported by the case team.', event_count: 1 },
      { kind: 'HYPOTHESIS', description: 'Candidate explanations with their human evaluation.', event_count: 0 },
      { kind: 'MISSING_DATA', description: 'Periods or measurements without usable evidence.', event_count: 1 },
    ],
    events: [
      {
        id: ANOMALY_ID, kind: 'OBSERVED', event_type: 'CLIMATE_ANOMALY', start: '2022-04-01', end: '2022-04-30',
        title: 'Precipitation, April 2022: 4.00 mm (anomaly −46.00 mm vs 2010–2021 mean)',
        description: 'Monthly precipitation was 2 or more reference standard deviations from the reference mean.',
        overlaps_incident: true,
        observed: {
          variable: 'precipitation', variable_label: 'Precipitation', source_parameter: 'PRECTOTCORR', value: 4, units: 'mm',
          reference_value: 50, anomaly: -46, reference_start: 2010, reference_end: 2021, reference_sample_count: 12,
          reference_standard_deviation: 15, reference_minimum: 20, reference_maximum: 80,
        },
        departure: { rule_id: 'abb10-departure-vs-reference-sd-1', severity: 'LARGE_DEPARTURE', direction: 'BELOW_REFERENCE', departure_in_reference_sd: -3.07, outside_reference_range: true, reason: null },
        data_quality: { status: 'complete', reference_status: 'complete', flags: [], reason: null },
        provenance: {
          source_kind: 'OBSERVED', description: 'NASA POWER daily point data aggregated to a calendar month.', case_id: CASE_ID, case_version: 1,
          source_manifest_id: 'm1', observation_id: OBSERVATION_ID, anomaly_id: ANOMALY_ID, hypothesis_id: null, field_id: 'f1', field_label: 'North field',
          provider: 'NASA POWER', dataset: 'NASA POWER daily point', dataset_version: null, source_uri: 'https://power.larc.nasa.gov',
          retrieved_at: '2026-01-02T00:00:00Z', checksum_sha256: 'a'.repeat(64), processing_version: '1',
          spatial_resolution: { value: null, unit: 'deg', description: '0.5° × 0.625°' }, temporal_resolution: { value: 1, unit: 'month', description: 'monthly' },
        },
        limitations: ['OBSERVED values describe a NASA POWER grid cell, not the field.'],
      },
      {
        id: '33333333-3333-4333-8333-333333333333', kind: 'FARMER_REPORTED', event_type: 'INCIDENT_PERIOD', start: '2022-04-01', end: '2022-06-30',
        title: 'Reported incident period', description: 'Yellowing leaves from mid-April.', overlaps_incident: true,
        provenance: { source_kind: 'FARMER_REPORTED', description: 'Case record entered by the case team.', case_id: CASE_ID, case_version: 1, source_manifest_id: null, observation_id: null, anomaly_id: null, hypothesis_id: null, field_id: null, field_label: null, provider: null, dataset: null, dataset_version: null, source_uri: null, retrieved_at: null, checksum_sha256: null, processing_version: null, spatial_resolution: null, temporal_resolution: null },
        limitations: ['Reported by the case team; not independently verified.'],
      },
      {
        id: '44444444-4444-4444-8444-444444444444', kind: 'MISSING_DATA', event_type: 'NO_LOCAL_MEASUREMENTS', start: '2022-04-01', end: '2022-06-30',
        title: 'No field-scale measurements recorded', description: 'The case holds no rain-gauge, soil-moisture, irrigation or crop-stage records.', overlaps_incident: true,
        provenance: { source_kind: 'MISSING_DATA', description: 'Derived from the stored case evidence.', case_id: CASE_ID, case_version: 1, source_manifest_id: null, observation_id: null, anomaly_id: null, hypothesis_id: null, field_id: null, field_label: null, provider: null, dataset: null, dataset_version: null, source_uri: null, retrieved_at: null, checksum_sha256: null, processing_version: null, spatial_resolution: null, temporal_resolution: null },
        limitations: ['The current case model has no structured store for local measurements.'],
      },
    ],
    severity_rule: { id: 'abb10-departure-vs-reference-sd-1' },
    limitations: ['Layers are shown together for comparison; a temporal overlap between events is not evidence of a cause.'],
  };
}

function templateCatalog(): HypothesisTemplateCatalog {
  return {
    items: [{
      code: 'water_deficit', source_kind: 'HYPOTHESIS', title: 'Water deficit', statement: 'Water deficit may have contributed to the reported symptoms.',
      related_variables: ['precipitation'], missing_evidence: ['Soil moisture readings'], verification_questions: [{ question: 'Was irrigation reduced?', why_it_matters: 'Rules out management causes.' }],
      limitations: ['A hypothesis is not a demonstrated cause.', 'Default starting point; not derived from this case\'s evidence.'],
    }],
    limitations: ['A hypothesis is not a demonstrated cause.'],
  };
}

function hypothesisView(overrides: Partial<HypothesisView> = {}): HypothesisView {
  return {
    id: '55555555-5555-4555-8555-555555555555', case_id: CASE_ID, statement: 'Water deficit may have contributed to the reported symptoms.',
    supporting_evidence_ids: [], contradicting_evidence_ids: [], missing_evidence: ['Soil moisture readings'],
    limitations: ['A hypothesis is not a demonstrated cause.'], status: 'OPEN', title: 'Water deficit', origin: 'TEMPLATE', template_code: 'water_deficit',
    verification_questions: [{ question: 'Was irrigation reduced?', why_it_matters: 'Rules out management causes.' }],
    evaluation_note: null, evaluated_by: null, evaluated_at: null, version: 1, created_by: { id: 'u1', display_name: 'Synthetic owner' },
    created_at: '2026-01-02T00:00:00Z', updated_at: '2026-01-02T00:00:00Z', evidence: [],
    ...overrides,
  };
}

const json = (status: number, data: unknown) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

function renderTimeline() {
  return render(<I18nProvider lang="en"><CaseTimeline caseId={CASE_ID} /></I18nProvider>);
}

beforeEach(() => {
  resetSessionCache();
  setSession({ access_token: 'synthetic-token', token_type: 'bearer', expires_at: new Date(Date.now() + 3600_000).toISOString(), user: USER });
});

afterEach(() => {
  cleanup();
  clearSession();
  resetSessionCache();
});

describe('CaseTimeline (ABB-22)', () => {
  it('shows the permanent legend with real layer counts and never interpolates a gap', async () => {
    let hypotheses: HypothesisView[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith(`/api/v1/cases/${CASE_ID}`)) return json(200, CASE_VIEW);
      if (path.endsWith('/timeline')) return json(200, timelineFixture());
      if (path.endsWith('/hypotheses')) return json(200, { items: hypotheses, limitations: [] } satisfies HypothesisList);
      return json(404, { detail: 'unexpected path in test' });
    });
    renderTimeline();
    expect(await screen.findByRole('heading', { level: 1, name: 'Synthetic plot' })).toBeTruthy();
    // Permanent legend: four layers, each with its real backend count (never a guessed number).
    expect(screen.getByText('Observed · 1')).toBeTruthy();
    expect(screen.getByText('Farmer reported · 1')).toBeTruthy();
    expect(screen.getByText('Hypothesis · 0')).toBeTruthy();
    expect(screen.getByText('Missing data · 1')).toBeTruthy();
    // No hypotheses yet: the empty state shows, never sample rows.
    expect(screen.getByText('No hypotheses yet')).toBeTruthy();
  });

  it('inspects a finding back to its full provenance, raw value and severity label (click-through)', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith(`/api/v1/cases/${CASE_ID}`)) return json(200, CASE_VIEW);
      if (path.endsWith('/timeline')) return json(200, timelineFixture());
      if (path.endsWith('/hypotheses')) return json(200, { items: [], limitations: [] } satisfies HypothesisList);
      return json(404, { detail: 'unexpected path in test' });
    });
    const user = userEvent.setup();
    renderTimeline();
    await screen.findByRole('heading', { level: 1, name: 'Synthetic plot' });
    await user.click(screen.getByRole('button', { name: 'Show as table' }));
    const table = screen.getByRole('table', { name: 'Case timeline' });
    await user.click(within(table).getByRole('button', { name: /Precipitation, April 2022/ }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Source of the selected finding' })).toBeTruthy();
    expect(screen.getByText('−46.00 mm')).toBeTruthy(); // the real anomaly value, verbatim
    expect(screen.getByText(/2 or more reference standard deviations \(−3.07 SD\)/)).toBeTruthy();
    expect(screen.getByText(/a{16}…/)).toBeTruthy(); // truncated checksum from provenance
  });

  it('maps linked observation evidence to its anomaly event before opening provenance', async () => {
    const linked = hypothesisView({
      supporting_evidence_ids: [OBSERVATION_ID],
      evidence: [{
        id: OBSERVATION_ID, evidence_type: 'OBSERVATION', kind: 'OBSERVED',
        label: 'Observation: precipitation, Apr 2022', start: '2022-04-01', end: '2022-04-30', active: true,
      }],
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith(`/api/v1/cases/${CASE_ID}`)) return json(200, CASE_VIEW);
      if (path.endsWith('/timeline')) return json(200, timelineFixture());
      if (path.endsWith('/hypotheses')) return json(200, { items: [linked], limitations: [] } satisfies HypothesisList);
      return json(404, { detail: 'unexpected path in test' });
    });
    const user = userEvent.setup();
    renderTimeline();
    await screen.findByRole('heading', { level: 1, name: 'Synthetic plot' });
    await user.click(screen.getByRole('button', { name: /Observation: precipitation/ }));
    expect(await screen.findByRole('heading', { level: 2, name: 'Source of the selected finding' })).toBeTruthy();
    expect(screen.getByText('NASA POWER')).toBeTruthy();
  });

  it('shows the backend error detail verbatim and no timeline when the case API fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith(`/api/v1/cases/${CASE_ID}`)) return json(200, CASE_VIEW);
      if (path.endsWith('/timeline')) return json(502, { detail: 'Could not reach the case timeline service.' });
      if (path.endsWith('/hypotheses')) return json(200, { items: [], limitations: [] } satisfies HypothesisList);
      return json(404, { detail: 'unexpected path in test' });
    });
    renderTimeline();
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('HTTP 502: Could not reach the case timeline service.');
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('lets an OWNER add a starting-template hypothesis and see it listed as OPEN', async () => {
    let added: HypothesisView[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.endsWith(`/api/v1/cases/${CASE_ID}`)) return json(200, CASE_VIEW);
      if (path.endsWith('/timeline')) return json(200, timelineFixture());
      if (path.endsWith('/hypothesis-templates')) return json(200, templateCatalog());
      if (path.endsWith('/hypotheses/templates') && init?.method === 'POST') {
        added = [hypothesisView()];
        return json(201, { items: added, limitations: [] } satisfies HypothesisList);
      }
      if (path.endsWith('/hypotheses')) return json(200, { items: added, limitations: [] } satisfies HypothesisList);
      return json(404, { detail: 'unexpected path in test' });
    });
    const user = userEvent.setup();
    renderTimeline();
    await screen.findByRole('heading', { level: 1, name: 'Synthetic plot' });
    await user.click(screen.getByRole('button', { name: 'Add a hypothesis' }));
    await user.click(await screen.findByRole('button', { name: 'Add: Water deficit' }));
    expect(await screen.findByText('Not evaluated')).toBeTruthy();
    expect(screen.getByText('Water deficit may have contributed to the reported symptoms.')).toBeTruthy();
    // Never a confidence score or probability next to the hypothesis.
    expect(document.body.textContent).not.toMatch(/%\s*(confidence|probability)/i);
  });

  it('shows a retryable error when the hypothesis template catalogue fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith(`/api/v1/cases/${CASE_ID}`)) return json(200, CASE_VIEW);
      if (path.endsWith('/timeline')) return json(200, timelineFixture());
      if (path.endsWith('/hypothesis-templates')) return json(503, { detail: 'Template catalogue unavailable.' });
      if (path.endsWith('/hypotheses')) return json(200, { items: [], limitations: [] } satisfies HypothesisList);
      return json(404, { detail: 'unexpected path in test' });
    });
    const user = userEvent.setup();
    renderTimeline();
    await screen.findByRole('heading', { level: 1, name: 'Synthetic plot' });
    await user.click(screen.getByRole('button', { name: 'Add a hypothesis' }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Starting templates could not be loaded');
    // Shared case error copy deliberately turns 503 into the actionable storage message
    // instead of exposing the backend detail verbatim.
    expect(alert.textContent).toContain('Case storage is not available on this server');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
    expect(screen.queryByText('Every starting template has been added.')).toBeNull();
  });

  it('asks a signed-out viewer to sign in instead of showing any case data', async () => {
    clearSession();
    resetSessionCache();
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    renderTimeline();
    expect(await screen.findByRole('heading', { name: 'Sign in to keep your cases' })).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
