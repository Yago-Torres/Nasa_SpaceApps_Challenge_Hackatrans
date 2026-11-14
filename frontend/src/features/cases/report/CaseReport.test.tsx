import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../../../i18n/I18n';
import { clearSession, resetSessionCache, setSession } from '../../../api/session';
import type { CaseView, Role } from '../../../api/types';
import { CaseReport } from './CaseReport';
import type { ReportView } from './reportApi';

/* TEST-ONLY synthetic fixtures, shaped like backend/agroblackbox/api/reports.py (ABB-26). */
const CASE_ID = '11111111-1111-4111-8111-111111111111';
const USER = { id: 'u1', email: 'owner@example.org', display_name: 'Synthetic owner', created_at: '2026-01-01T00:00:00Z' };
const HASH = 'a'.repeat(64);

function caseView(role: Role): CaseView {
  return {
    schema_version: '1.0', id: CASE_ID, title: 'Synthetic plot', incident_start: '2022-04-01', incident_end: '2022-06-30',
    fields: [{ schema_version: '1.0', id: 'f1', label: 'North field', privacy_tier: 'APPROXIMATE', latitude: 41.6, longitude: -0.9,
      region_label: 'Synthetic region', area_hectares: null, limitations: [], location_precision: 'APPROXIMATE', rounding_deg: 0.1, precise_location_consent: false }],
    crop_history: [], incident_notes: 'Synthetic notes.', visibility: 'PRIVATE', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    version: 4, status: 'INVESTIGATING', archived_at: null, owner: { id: 'u1', display_name: 'Synthetic owner' }, my_role: role,
  };
}

function report(version: number, over: Partial<ReportView> = {}): ReportView {
  const base = `/api/v1/cases/${CASE_ID}/reports/${version}/download`;
  return {
    id: `r${version}`, case_id: CASE_ID, version, generated_at: `2026-11-1${version}T10:00:00Z`, status: 'PRELIMINARY', case_version: 4,
    generated_by: { id: 'u1', display_name: 'Synthetic owner' }, formats: ['markdown', 'html', 'json'], checksum_sha256: HASH,
    html_sha256: HASH, snapshot_sha256: HASH, sources_sha256: 'b'.repeat(64), source_manifest_ids: ['m1'], limitations: ['L'],
    changes: { initial: version === 1, previous_version: version === 1 ? null : version - 1, previous_case_version: 3, case_version: 4, items: [] },
    downloads: { markdown: `${base}?format=markdown`, html: `${base}?format=html`, json: `${base}?format=json` }, ...over,
  };
}

const json = (status: number, data: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', ...headers } });
type Call = { method: string; path: string; auth: string | null };

function mockFetch(routes: Record<string, () => Response>) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input);
    const method = init?.method ?? 'GET';
    calls.push({ method, path, auth: ((init?.headers ?? {}) as Record<string, string>).Authorization ?? null });
    const key = Object.keys(routes).find((k) => {
      const [m, suffix] = k.split(' ');
      return m === method && path.endsWith(suffix);
    });
    return key ? routes[key]() : json(404, { detail: `unexpected ${method} ${path} in test` });
  });
  return calls;
}

const renderEn = () => render(<I18nProvider lang="en"><CaseReport caseId={CASE_ID} /></I18nProvider>);

beforeEach(() => {
  resetSessionCache();
  setSession({ access_token: 'synthetic-token', token_type: 'bearer', expires_at: new Date(Date.now() + 3600_000).toISOString(), user: USER });
});
afterEach(() => { cleanup(); clearSession(); resetSessionCache(); vi.restoreAllMocks(); });

describe('Case report tab (ABB-26)', () => {
  it('lists stored versions with date, hashes and the relevant changes, newest first', async () => {
    mockFetch({
      [`GET /cases/${CASE_ID}`]: () => json(200, caseView('OWNER')),
      'GET /reports': () => json(200, { items: [
        report(2, { changes: { initial: false, previous_version: 1, previous_case_version: 3, case_version: 4,
          items: [{ section: 'claims', change: 'CHANGED', id: 'c1', label: 'Synthetic claim' }] } }),
        report(1),
      ] }),
    });
    renderEn();
    const v2 = (await screen.findByRole('heading', { name: 'Version 2' })).closest('article')!;
    expect(within(v2).getByText('Synthetic claim')).toBeTruthy();
    expect(within(v2).getByText('CHANGED')).toBeTruthy();
    expect(within(v2).getAllByText(/aaaaaaaaaaaaaaaa…/).length).toBe(1);
    const v1 = screen.getByRole('heading', { name: 'Version 1' }).closest('article')!;
    expect(within(v1).getByText(/First stored version/)).toBeTruthy();
    expect(screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual(['Version 2', 'Version 1']);
    expect(screen.getByText(/Print → Save as PDF/)).toBeTruthy();
  });

  it('generates a version on the server and shows it, sending the bearer token and no client data', async () => {
    let items: ReportView[] = [];
    const calls = mockFetch({
      [`GET /cases/${CASE_ID}`]: () => json(200, caseView('EDITOR')),
      'GET /reports': () => json(200, { items }),
      'POST /reports': () => { items = [report(1)]; return json(201, items[0]); },
    });
    const user = userEvent.setup();
    renderEn();
    expect(await screen.findByText('No report has been generated yet')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Generate new version' }));
    expect(await screen.findByText('Version 1 stored.')).toBeTruthy();
    expect(await screen.findByRole('heading', { name: 'Version 1' })).toBeTruthy();
    const post = calls.find((c) => c.method === 'POST')!;
    expect(post.path).toBe(`/api/v1/cases/${CASE_ID}/reports`);
    expect(post.auth).toBe('Bearer synthetic-token');
  });

  it('downloads the stored Markdown, HTML and JSON with the token', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:synthetic');
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const calls = mockFetch({
      [`GET /cases/${CASE_ID}`]: () => json(200, caseView('OWNER')),
      'GET /reports': () => json(200, { items: [report(1)] }),
      'GET /download?format=markdown': () => new Response('# Synthetic', { headers: { 'X-Report-SHA256': HASH } }),
      'GET /download?format=html': () => new Response('<!doctype html>', { headers: { 'X-Report-SHA256': HASH } }),
      'GET /download?format=json': () => new Response('{}', { headers: { 'X-Report-SHA256': HASH } }),
    });
    const user = userEvent.setup();
    renderEn();
    await user.click(await screen.findByRole('button', { name: 'Markdown' }));
    expect(await screen.findByText('Downloaded cropstory-case-report-v1.md')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'HTML' }));
    expect(await screen.findByText('Downloaded cropstory-case-report-v1.html')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'JSON snapshot' }));
    expect(await screen.findByText('Downloaded cropstory-case-report-v1.json')).toBeTruthy();
    expect(click).toHaveBeenCalledTimes(3);
    expect(calls.filter((c) => c.path.includes('/download')).every((c) => c.auth === 'Bearer synthetic-token')).toBe(true);
  });

  it('shows an integrity failure from the server without hiding it', async () => {
    mockFetch({
      [`GET /cases/${CASE_ID}`]: () => json(200, caseView('OWNER')),
      'GET /reports': () => json(200, { items: [report(1)] }),
      'GET /verify': () => json(200, { version: 1, valid: false, checks: { markdown_sha256: false }, detail: 'Stored content does not match its recorded hashes; do not rely on this version.' }),
    });
    const user = userEvent.setup();
    renderEn();
    await user.click(await screen.findByRole('button', { name: 'Verify integrity' }));
    expect(await screen.findByText('Stored content does not match its hashes')).toBeTruthy();
  });

  it('viewers can read but get no generate button', async () => {
    mockFetch({
      [`GET /cases/${CASE_ID}`]: () => json(200, caseView('VIEWER')),
      'GET /reports': () => json(200, { items: [report(1)] }),
    });
    renderEn();
    expect(await screen.findByRole('heading', { name: 'Version 1' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Generate new version' })).toBeNull();
    expect(screen.getByText('Your role can read and download reports but not generate them.')).toBeTruthy();
  });

  it('reports a backend failure with retry and never invents versions', async () => {
    mockFetch({
      [`GET /cases/${CASE_ID}`]: () => json(200, caseView('OWNER')),
      'GET /reports': () => json(503, { detail: 'Storage unavailable' }),
    });
    renderEn();
    expect(await screen.findByText('The report action failed')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: /Version/ })).toBeNull();
    await waitFor(() => expect(screen.queryByText('Loading report versions…')).toBeNull());
  });
});
