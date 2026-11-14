import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../i18n/I18n';
import { Rotations } from './Rotations';
import { resetRotationsState } from './rotations/store';
import type { CropCatalog, ScenarioAnalysis } from '../api/types';

/* ── TEST-ONLY fetch fixtures for /api/v1/crop-catalog and /api/v1/rotations/scenarios ──
 * Synthetic data only, matching the documented contract (ABB-11/17/18). The app itself never
 * ships sample data; this fixture exists only inside this test file. */

const catalog: CropCatalog = { schema_version: '1.0', catalog_version: 'crop-catalog-0.1.0', entries: [], sources: [], limitations: [] };

function fakeStrategy(overrides: Partial<ScenarioAnalysis['comparison']['strategies'][number]> = {}) {
  return {
    schema_version: '1.0' as const,
    id: 'current', name: 'Current', strategy_kind: 'CURRENT' as const, is_current: true,
    source_kind: 'MODEL_SCENARIO' as const, sequence_origin: 'FARMER_REPORTED' as const,
    selection_rule: 'Derived from crop history.',
    cycle: [[{ crop_code: null, crop_label: 'Durum wheat', botanical_family: 'Poaceae', is_legume: false }]],
    years: [['Durum wheat'], ['Barley']],
    start_season_year: 2022,
    transitions: [], entry_transition: null,
    screening_result: 'PASSES_DECLARED_CONSTRAINTS' as const,
    constraint_checks: [],
    comparison: {
      basis: 'DECLARED_INPUTS_AND_RULES' as const, cycle_years: 2, distinct_crops: 2, distinct_families: 1,
      families: ['Poaceae'], includes_legume: false, legume_years_per_cycle: 0, consecutive_same_family: 1,
      months_with_crop: null, longest_fallow_gap: null, crops_new_to_farm: [], market_status: [], not_evaluable: [],
    },
    priorities_addressed: [], possible_benefits: [], risks: [],
    assumptions: ['One main crop per year.'], conditions_requiring_review: ['Soil suitability not evaluated.'],
    limitations: ['Descriptive comparison only.'], evidence_refs: [], verified_impact: null,
    ...overrides,
  };
}

function fakeResult(priorityCount: number): ScenarioAnalysis {
  return {
    schema_version: '1.0', status: 'ANALYSED', source_kind: 'MODEL_SCENARIO', input_sha256: 'a'.repeat(64),
    applied_inputs: {
      horizon_years: 4, priorities: Array.from({ length: priorityCount }, (_, i) => ({ criterion: 'SOIL_COVER' as const, rank: i + 1 })),
      priorities_from: 'PROFILE', water_regime: 'UNKNOWN', irrigation_allowance: null, water_from: 'PROFILE', scenario_ids: [],
    },
    scenarios: [],
    comparison: {
      schema_version: '1.0', status: 'COMPARED', source_kind: 'MODEL_SCENARIO', horizon_years: 4,
      strategies: [fakeStrategy()], explanation: ['Current rotation identified from two seasons.'],
      candidate_screening: [], incompatible_transitions: [], generation: null,
      profile_readiness: 'LIMITED_BY_MISSING_DATA', profile_issues: [], rule_set_version: 'abb17-rotation-rules-0.1.0',
      catalog_version: 'crop-catalog-0.1.0', limitations: ['Rule-based screening only.'],
    },
    exposure: [], ordering: null, trade_offs: [],
    separation: [{ part: 'comparison', kind: 'MODEL_SCENARIO', present: true, meaning: 'Rule-based strategies from declared inputs.' }],
    explanation: ['Analysed with the declared profile.'], rule_set_version: 'abb18-scenarios-0.1.0',
    limitations: ['What-if analysis only; verified_impact is null.'], verified_impact: null,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;
let scenarioCalls: number;

function installFetchMock() {
  scenarioCalls = 0;
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input instanceof Request ? input.url : input);
    if (url.includes('/api/v1/crop-catalog')) {
      return new Response(JSON.stringify(catalog), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (url.includes('/api/v1/rotations/scenarios')) {
      scenarioCalls += 1;
      const body = JSON.parse(String(init?.body ?? '{}'));
      const priorityCount = body.profile?.priorities?.length ?? 0;
      return new Response(JSON.stringify(fakeResult(priorityCount)), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response(JSON.stringify({ detail: 'not found in this test' }), { status: 404, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetchMock);
}

function renderScreen() {
  return render(<I18nProvider lang="en"><Rotations /></I18nProvider>);
}

beforeEach(() => {
  resetRotationsState();
  installFetchMock();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function cropHistorySection() {
  return screen.getByRole('heading', { name: /current rotation: crop history/i }).closest('section')!;
}

/** Fills the first crop-history row and adds + fills a second so the backend can identify a cycle. */
async function fillTwoSeasons(user: ReturnType<typeof userEvent.setup>) {
  const section = cropHistorySection();
  await user.type(within(section).getAllByLabelText('Crop', { exact: true })[0], 'Durum wheat');
  await user.type(within(section).getAllByLabelText('Season year')[0], '2022');
  await user.click(within(section).getByRole('button', { name: /add a season/i }));
  const crops = within(section).getAllByLabelText('Crop', { exact: true });
  await user.type(crops[crops.length - 1], 'Barley');
  const years = within(section).getAllByLabelText('Season year');
  await user.type(years[years.length - 1], '2023');
}

describe('Rotations (ABB-24 comparator)', () => {
  it('does not call the backend and shows field errors for a structurally invalid season year', async () => {
    const user = userEvent.setup();
    renderScreen();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled()); // crop catalog fetch on mount

    const section = cropHistorySection();
    await user.type(within(section).getAllByLabelText('Crop', { exact: true })[0], 'Durum wheat');
    await user.type(within(section).getAllByLabelText('Season year')[0], '20'); // out of the 1950-2100 range

    await user.click(screen.getByRole('button', { name: /compare strategies/i }));

    expect(await screen.findByText(/fields need fixing before comparing/i)).toBeTruthy();
    expect(screen.getByText('Use a year between 1950 and 2100.')).toBeTruthy();
    expect(scenarioCalls).toBe(0);
  });

  it('runs a real backend comparison and renders the strategy the backend returned', async () => {
    const user = userEvent.setup();
    renderScreen();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    await fillTwoSeasons(user);
    await user.click(screen.getByRole('button', { name: /compare strategies/i }));

    expect(await screen.findByText('Current rotation identified from two seasons.')).toBeTruthy();
    expect(scenarioCalls).toBe(1);
    const sent = JSON.parse(String((fetchMock.mock.calls.find(([u]) => String(u).includes('/scenarios')) ?? [])[1]?.body ?? '{}'));
    expect(sent.profile.crop_history).toHaveLength(2);
  });

  it('recomputes from the backend (not client-side) when a priority is added', async () => {
    const user = userEvent.setup();
    renderScreen();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    await fillTwoSeasons(user);
    await user.click(screen.getByRole('button', { name: /compare strategies/i }));
    await screen.findByText('Current rotation identified from two seasons.');
    expect(scenarioCalls).toBe(1);

    const prioritySection = screen.getByRole('heading', { name: /what matters most to you/i }).closest('section')!;
    await user.click(within(prioritySection).getByRole('button', { name: 'Soil cover' }));

    await waitFor(() => expect(scenarioCalls).toBe(2), { timeout: 3000 });
    const lastCall = fetchMock.mock.calls.filter(([u]) => String(u).includes('/scenarios')).at(-1)!;
    const sentBody = JSON.parse(String(lastCall[1]?.body ?? '{}'));
    expect(sentBody.profile.priorities).toEqual([{ criterion: 'SOIL_COVER', rank: 1 }]);
  });
});
