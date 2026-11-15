import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../../../i18n/I18n';
import { clearSession, resetSessionCache, setSession } from '../../../api/session';
import { CaseUncertainty } from './CaseUncertainty';

const ID = '11111111-1111-4111-8111-111111111111';
const USER = { id: 'u1', email: 'owner@example.org', display_name: 'Owner', created_at: '2026-01-01T00:00:00Z' };
const CASE = { schema_version: '1.0', id: ID, title: 'Synthetic case', incident_start: '2022-04-01', incident_end: null,
  fields: [{ schema_version: '1.0', id: 'f1', label: 'Field', privacy_tier: 'REGION_ONLY', latitude: null, longitude: null, region_label: 'Synthetic region', area_hectares: null, limitations: [], location_precision: 'REGION_ONLY', rounding_deg: null, precise_location_consent: false }], crop_history: [], incident_notes: null,
  visibility: 'PRIVATE', created_at: USER.created_at, updated_at: USER.created_at, version: 1, status: 'INVESTIGATING', archived_at: null,
  owner: { id: 'u1', display_name: 'Owner' }, my_role: 'OWNER' };
const QUESTION = { id: 'SOIL_ANALYSIS', origin: 'CATALOGUE', kind: 'LOCAL_INFORMATION', category: 'SOIL', question: 'Is there a soil analysis?',
  why_it_matters: 'Soil limitations otherwise remain unknown.', addresses: ['Missing soil data'], addresses_gap_ids: ['g1'], measurement: 'Laboratory pH with method.', units: ['pH'],
  answer_route: null, answerable_here: true, would_change: [], would_change_statement: 'Adds local context.', open_hypotheses_linked: 0, other_items_linked: 1,
  priority_basis: 'One linked item.', position: 1, tied_with: [], resolution: { status: 'OPEN', current_answer_id: null, updated_at: null, note: null }, currently_generated: true };
const REPORT = { case_id: ID, case_version: 1, generated_at: USER.created_at, method_version: 'synthetic', stored: false,
  inputs: { farm_profile_supplied: false, country_code: null, koppen_climate: null, rotation_status: null },
  summary: { gaps: 1, gaps_by_cause: { MISSING_CASE_DATA: 1 }, questions: 1, open_questions: 1, gaps_not_answerable_locally: 0 },
  gaps: [{ id: 'g1', key: 'soil', kind: 'MISSING_DATA', category: 'SOIL', cause: 'MISSING_CASE_DATA', answerable_locally: true, title: 'Soil data missing', description: 'No analysis recorded.', sources: [], question_ids: ['SOIL_ANALYSIS'], would_change: [], limitations: [] }],
  questions: [QUESTION], prioritisation: { rule_id: 'synthetic', status: 'NO_BASIS_TO_PRIORITISE', statement: 'There is no basis to prioritise.', steps: [], is_value_of_information: false }, limitations: ['No value-of-information score.'] };

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
beforeEach(() => { resetSessionCache(); setSession({ access_token: 'token', token_type: 'bearer', expires_at: '2099-01-01T00:00:00Z', user: USER }); });
afterEach(() => { cleanup(); clearSession(); resetSessionCache(); vi.restoreAllMocks(); });

describe('Uncertainty Hunter UI (ABB-19 / ABB-33)', () => {
  it('shows the no-priority caveat and records a local answer without inventing a score', async () => {
    const calls: { path: string; body?: unknown }[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input); const body = init?.body ? JSON.parse(String(init.body)) : undefined; calls.push({ path, body });
      if (path.endsWith(`/cases/${ID}`)) return json(200, CASE);
      if (path.endsWith('/uncertainty/answers') && (init?.method ?? 'GET') === 'GET') return json(200, { items: [], limitations: [] });
      if (path.endsWith('/uncertainty')) return json(200, REPORT);
      if (path.endsWith('/uncertainty/questions/SOIL_ANALYSIS/answers')) return json(201, { id: 'a1' });
      return json(404, { detail: 'unexpected test route' });
    });
    const user = userEvent.setup(); render(<I18nProvider lang="en"><CaseUncertainty caseId={ID} /></I18nProvider>);
    expect(await screen.findByText('There is no basis to prioritise.')).toBeTruthy();
    expect(screen.queryByText(/score:/i)).toBeNull();
    const card = screen.getByRole('heading', { name: 'Is there a soil analysis?' }).closest('article')!;
    await user.type(within(card).getByLabelText('Local answer'), 'pH 7.1 in the laboratory report');
    await user.click(within(card).getByRole('button', { name: 'Save local answer' }));
    const post = calls.find((c) => c.path.endsWith('/uncertainty/questions/SOIL_ANALYSIS/answers'));
    expect(post?.body).toMatchObject({ value_text: 'pH 7.1 in the laboratory report', origin: 'FARMER_REPORTED', replaces_answer_id: null });
  });
});
