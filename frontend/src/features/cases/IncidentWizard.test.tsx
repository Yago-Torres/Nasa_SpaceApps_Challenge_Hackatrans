import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, configure, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../../i18n/I18n';
import { App } from '../../app/App';
import { setCaseRepository } from '../../cases/repository';
import { clearSession, resetSessionCache, setSession } from '../../api/session';
import { emptyCase, roundToCell, type Rounding } from '../../cases/model';
import { toCaseCreate } from '../../cases/mapping';
import type { CaseCreate, CaseView, FieldInput, Role, SessionOut, UserOut } from '../../api/types';

/* ── TEST-ONLY fake of /api/v1/auth and /api/v1/cases ────────────────────────────────────
 * In-memory stand-in reached through a fetch mock. It follows the documented contract
 * (ADR-0004): bearer tokens, 401/404/409/429/503, version checks and server-side redaction
 * for reviewers. Every account, token, coordinate and text here is synthetic. */

type Call = { method: string; path: string; body: unknown; auth: string | null };
type Override = (method: string, path: string) => Response | undefined;

const json = (status: number, data: unknown, headers?: Record<string, string>) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', ...headers } });

function createFakeCaseApi() {
  let seq = 0;
  const uuid = () => `00000000-0000-4000-8000-${String(++seq).padStart(12, '0')}`;
  const users = new Map<string, { password: string; user: UserOut }>();
  const tokens = new Map<string, string>();
  const cases = new Map<string, CaseView>();
  const roles = new Map<string, Role>();
  const calls: Call[] = [];
  let override: Override | null = null;

  function addUser(email: string, password: string, displayName = 'Synthetic tester') {
    const user: UserOut = { id: uuid(), email, display_name: displayName, created_at: '2026-11-14T09:00:00Z' };
    users.set(email, { password, user });
    return user;
  }

  function session(user: UserOut): SessionOut {
    const token = `synthetic-token-${++seq}`;
    tokens.set(token, user.id);
    return { access_token: token, token_type: 'bearer', expires_at: new Date(Date.now() + 12 * 3600_000).toISOString(), user };
  }

  function seed(body: CaseCreate, role: Role = 'OWNER'): CaseView {
    const now = new Date().toISOString();
    const view: CaseView = {
      schema_version: '1.0', id: uuid(), title: body.title, incident_start: body.incident_start, incident_end: body.incident_end ?? null,
      fields: body.fields.map((f) => ({
        schema_version: '1.0', id: uuid(), label: f.label, privacy_tier: f.privacy_tier, latitude: f.latitude ?? null, longitude: f.longitude ?? null,
        region_label: f.region_label, area_hectares: f.area_hectares ?? null, limitations: f.limitations ?? [], location_precision: 'EXACT',
        rounding_deg: f.rounding_deg ?? (f.privacy_tier === 'APPROXIMATE' ? 0.1 : null), precise_location_consent: f.precise_location_consent ?? false,
      })),
      crop_history: body.crop_history ?? [], incident_notes: body.incident_notes ?? null, visibility: 'PRIVATE',
      created_at: now, updated_at: now, version: 1, status: 'DRAFT', archived_at: null,
      owner: { id: 'synthetic-owner', display_name: role === 'OWNER' ? 'Synthetic tester' : 'Another synthetic owner' }, my_role: 'OWNER',
    };
    cases.set(view.id, view);
    roles.set(view.id, role);
    return view;
  }

  /** The view as the caller may see it (server-side redaction, ADR-0004). */
  function visible(view: CaseView): CaseView {
    const role = roles.get(view.id) ?? 'OWNER';
    const precise = role === 'OWNER' || role === 'EDITOR';
    return {
      ...view, my_role: role,
      fields: view.fields.map((f) => {
        if (f.latitude === null || f.longitude === null) return { ...f, location_precision: 'NONE' };
        if (precise || f.precise_location_consent) return { ...f, location_precision: 'EXACT' };
        if (f.privacy_tier === 'APPROXIMATE') {
          const r = (f.rounding_deg ?? 0.1) as Rounding;
          return { ...f, latitude: roundToCell(f.latitude, r), longitude: roundToCell(f.longitude, r), location_precision: 'APPROXIMATE' };
        }
        return { ...f, latitude: null, longitude: null, location_precision: f.privacy_tier === 'REGION_ONLY' ? 'REGION_ONLY' : 'NONE' };
      }),
    };
  }

  /** Another person saves: bumps the version and changes the title. */
  function editElsewhere(id: string, title: string) {
    const v = cases.get(id)!;
    cases.set(id, { ...v, title, version: v.version + 1, updated_at: new Date().toISOString() });
  }

  async function handle(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const url = new URL(String(input instanceof Request ? input.url : input), 'http://localhost');
    const method = (init?.method ?? 'GET').toUpperCase();
    const headers = (init?.headers ?? {}) as Record<string, string>;
    const body: unknown = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    const auth = headers.Authorization ?? null;
    calls.push({ method, path: url.pathname + url.search, body, auth });
    const forced = override?.(method, url.pathname);
    if (forced) return forced;
    const path = url.pathname;

    if (path === '/api/v1/auth/login' && method === 'POST') {
      const { email, password } = body as { email: string; password: string };
      const found = users.get(email.trim().toLowerCase());
      if (!found || found.password !== password) return json(401, { detail: 'Invalid email or password.' });
      return json(200, session(found.user));
    }
    if (path === '/api/v1/auth/register' && method === 'POST') {
      const { email, password, display_name } = body as { email: string; password: string; display_name: string };
      if (users.has(email)) return json(409, { detail: 'An account with this email already exists.' });
      return json(201, addUser(email, password, display_name));
    }
    const token = auth?.startsWith('Bearer ') ? auth.slice(7) : null;
    if (!token || !tokens.has(token)) return json(401, { detail: 'Authentication required.' }, { 'WWW-Authenticate': 'Bearer' });
    if (path === '/api/v1/auth/logout') {
      tokens.delete(token);
      return new Response(null, { status: 204 });
    }

    if (path === '/api/v1/cases' && method === 'GET') return json(200, { items: [...cases.values()].map(visible) });
    if (path === '/api/v1/cases' && method === 'POST') return json(201, visible(seed(body as CaseCreate)));

    const m = /^\/api\/v1\/cases\/([^/]+)(?:\/fields\/([^/]+))?$/.exec(path);
    const current = m ? cases.get(m[1]) : undefined;
    if (!m || !current) return json(404, { detail: 'Case not found.' });
    if (method === 'GET' && !m[2]) return json(200, visible(current));
    const role = roles.get(current.id) ?? 'OWNER';
    if (role !== 'OWNER' && role !== 'EDITOR') return json(403, { detail: 'Your role on this case does not allow this action.' });
    const version = method === 'DELETE' ? Number(url.searchParams.get('version')) : (body as { version: number }).version;
    if (version !== current.version) {
      return json(409, { detail: `The case changed since you loaded it (current version ${current.version}). Reload and retry.` });
    }
    if (method === 'DELETE' && !m[2]) {
      cases.delete(current.id);
      return new Response(null, { status: 204 });
    }
    const changes = { ...(body as Record<string, unknown>) };
    delete changes.version;
    const next: CaseView = m[2]
      ? { ...current, fields: current.fields.map((f) => (f.id === m[2] ? ({ ...f, ...(changes as Partial<FieldInput>) } as typeof f) : f)) }
      : { ...current, ...(changes as Partial<CaseView>) };
    next.version = current.version + 1;
    next.updated_at = new Date().toISOString();
    cases.set(current.id, next);
    return json(200, visible(next));
  }

  return {
    handle, calls, cases, tokens, addUser, seed, editElsewhere,
    setOverride(fn: Override | null) {
      override = fn;
    },
  };
}

/* ── Test setup ─────────────────────────────────────────────────────────────────────────── */

// Slower CI runners: wait for elements instead of relying on timing.
configure({ asyncUtilTimeout: 5000 });

const EMAIL = 'tester@example.org';
const PASSWORD = 'synthetic-password-1';
let api: ReturnType<typeof createFakeCaseApi>;

function go(hash: string) {
  act(() => {
    window.location.hash = hash;
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  });
}

function renderApp(lang: 'en' | 'es' = 'en') {
  return render(<I18nProvider lang={lang}><App /></I18nProvider>);
}

/** Sign in without the form (the form has its own test). */
async function signedIn() {
  api.addUser(EMAIL, PASSWORD);
  const r = await api.handle('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ email: EMAIL, password: PASSWORD }) });
  setSession((await r.json()) as SessionOut);
}

function syntheticCase(title = 'Synthetic test plot') {
  const c = emptyCase();
  c.title = title;
  c.location = { ...c.location, latitude: '41.6537', longitude: '-0.8773' };
  c.crops = [{ id: 'y1', year: '2022', crop: 'durum wheat', notes: '' }];
  c.incidentYear = '2022';
  c.symptoms = 'Synthetic symptom description.';
  return toCaseCreate(c);
}

const allStorage = (s: Storage) => Array.from({ length: s.length }, (_, i) => `${s.key(i)}=${s.getItem(s.key(i)!)}`).join('\n');

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  resetSessionCache();
  clearSession();
  setCaseRepository(null);
  api = createFakeCaseApi();
  vi.spyOn(globalThis, 'fetch').mockImplementation(api.handle);
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  window.location.hash = '';
});

describe('ABB-21 / ABB-06 incident wizard on the case API', { timeout: 30000 }, () => {
  it('signs in, creates a case, lists it with status and role, then reopens and edits it with its version', async () => {
    api.addUser(EMAIL, PASSWORD);
    const user = userEvent.setup();
    window.location.hash = '#/cases';
    renderApp();

    // Signed out: the list asks to sign in.
    expect(await screen.findByRole('heading', { name: 'Sign in to keep your cases' })).toBeTruthy();
    await user.type(screen.getByLabelText('Email'), EMAIL);
    await user.type(screen.getByLabelText('Password'), PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('No cases yet. Create one to record an incident.')).toBeTruthy();
    expect(screen.getByText('Signed in as Synthetic tester')).toBeTruthy();

    // The token is kept for this tab only, never in localStorage.
    const token = [...api.tokens.keys()][0];
    expect(allStorage(sessionStorage)).toContain(token);
    expect(allStorage(localStorage)).not.toContain(token);

    // Step 1: where (default privacy tier is "Approximate area", 0.1°)
    go('#/cases/new');
    await user.type(await screen.findByLabelText('Case name'), 'Wheat loss, north plot');
    await user.type(screen.getByLabelText('Latitude'), '41.6537');
    await user.type(screen.getByLabelText('Longitude'), '-0.8773');
    expect(screen.getByText(/Reviewers see: 41[.,]650, −0[.,]850/)).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    // Step 2: crops
    await user.type(await screen.findByLabelText('Year'), '2022');
    await user.type(screen.getByLabelText('Crop'), 'durum wheat');
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    // Step 3: incident
    await user.type(await screen.findByLabelText('Year of the incident'), '2022');
    await user.type(screen.getByLabelText('What you saw'), 'Yellowing from the edges in May.');
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    // Step 4: constraints (optional), then review lists the gaps as missing data
    await screen.findByRole('heading', { level: 2, name: 'Constraints' });
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByText('Whether the field is irrigated')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Save case' }));
    expect(await screen.findByRole('button', { name: 'Investigate with NASA data' })).toBeTruthy();

    // Exactly one create, with the documented mapping and the bearer token.
    const creates = api.calls.filter((c) => c.method === 'POST' && c.path === '/api/v1/cases');
    expect(creates).toHaveLength(1);
    expect(creates[0].auth).toBe(`Bearer ${token}`);
    expect(creates[0].body).toMatchObject({
      title: 'Wheat loss, north plot', incident_start: '2022-01-01', incident_end: null,
      fields: [{ privacy_tier: 'APPROXIMATE', rounding_deg: 0.1, latitude: 41.6537, longitude: -0.8773, precise_location_consent: false }],
    });
    await waitFor(() => expect([...api.cases.values()][0].crop_history).toEqual(['2022: durum wheat']));

    // List: status and role from the server, shared only as the rounded cell centre.
    go('#/cases');
    const row = await screen.findByRole('row', { name: /Wheat loss, north plot/ });
    expect(row.textContent).toContain('Draft');
    expect(row.textContent).toContain('Owner');
    expect(row.textContent).toMatch(/41[.,]65, −0[.,]85 \(±0[.,]05°\)/);
    expect(row.textContent).not.toContain('41.6537');

    // Reopen and edit: the PATCH carries the version that was read.
    await user.click(within(row).getByRole('link', { name: 'Edit' }));
    const title = await screen.findByLabelText('Case name');
    expect((title as HTMLInputElement).value).toBe('Wheat loss, north plot');
    expect(screen.getByRole('heading', { level: 1, name: 'Wheat loss, north plot' })).toBeTruthy();
    const versionBefore = [...api.cases.values()][0].version;
    const patchesBefore = api.calls.filter((c) => c.method === 'PATCH').length;
    await user.clear(title);
    await user.type(title, 'Wheat loss, lower plot');
    await user.click(screen.getByRole('button', { name: /Review and share/ }));
    await user.click(await screen.findByRole('button', { name: 'Save case' }));
    await screen.findByRole('button', { name: 'Investigate with NASA data' });
    await waitFor(() => expect([...api.cases.values()][0].title).toBe('Wheat loss, lower plot'));
    const patch = api.calls.filter((c) => c.method === 'PATCH').slice(patchesBefore)
      .find((c) => (c.body as { title?: string }).title === 'Wheat loss, lower plot');
    expect(patch?.body).toMatchObject({ version: versionBefore });

    go('#/cases');
    expect(await screen.findByRole('row', { name: /Wheat loss, lower plot/ })).toBeTruthy();
  });

  it('keeps what was typed when a field is invalid and focuses the first error', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/cases/new';
    renderApp();
    await user.type(await screen.findByLabelText('Case name'), 'Barley patch');
    await user.type(screen.getByLabelText('Latitude'), '95');
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByText('Use a number from −90 to 90.')).toBeTruthy();
    expect(screen.getByText('Use a number from −180 to 180.')).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText('Latitude')));
    expect((screen.getByLabelText('Case name') as HTMLInputElement).value).toBe('Barley patch');
    expect((screen.getByLabelText('Latitude') as HTMLInputElement).value).toBe('95');
  });

  it('moves focus to the new step heading as part of the step change, never later while the user types', async () => {
    // Regression (CI): focus used to move in a later animation frame; on a slow runner it
    // arrived after typing in the new step had started and swallowed keystrokes.
    const user = userEvent.setup();
    window.location.hash = '#/cases/new';
    renderApp();
    await user.type(await screen.findByLabelText('Case name'), 'Synthetic plot');
    await user.type(screen.getByLabelText('Latitude'), '41.6');
    await user.type(screen.getByLabelText('Longitude'), '-0.9');
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(document.activeElement).toBe(screen.getByRole('heading', { level: 2, name: 'What was grown' }));
    await user.type(screen.getByLabelText('Year'), '2022');
    await new Promise((resolve) => window.setTimeout(resolve, 50)); // a late focus move would land here
    expect(document.activeElement).toBe(screen.getByLabelText('Year'));
    expect((screen.getByLabelText('Year') as HTMLInputElement).value).toBe('2022');
  });

  it('signed out, the wizard keeps the answers on the page and asks to sign in before saving (ES)', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/cases/new';
    renderApp('es');
    expect(await screen.findByText('Inicia sesión para guardar este caso. Hasta entonces, tus respuestas se quedan en esta página.')).toBeTruthy();
    await user.type(screen.getByLabelText('Nombre del caso'), 'Parcela sintética');
    expect((screen.getByLabelText('Nombre del caso') as HTMLInputElement).value).toBe('Parcela sintética');
    expect(api.calls.filter((c) => c.path.startsWith('/api/v1/cases'))).toHaveLength(0);
  });

  it('a 401 while saving signs the user out, keeps the answers and forgets the token', async () => {
    await signedIn();
    const user = userEvent.setup();
    window.location.hash = '#/cases/new';
    renderApp();
    await user.type(await screen.findByLabelText('Case name'), 'Synthetic plot');
    await user.type(screen.getByLabelText('Latitude'), '41.6');
    await user.type(screen.getByLabelText('Longitude'), '-0.9');
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    await user.type(await screen.findByLabelText('Year'), '2022');
    await user.type(screen.getByLabelText('Crop'), 'barley');
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    api.tokens.clear(); // the server revoked the session
    await user.type(await screen.findByLabelText('Year of the incident'), '2022'); // now ready: autosave runs
    expect(await screen.findByText('Your session ended. Sign in again to save; your answers are kept on this page.')).toBeTruthy();
    expect((screen.getByLabelText('Year of the incident') as HTMLInputElement).value).toBe('2022');
    expect(allStorage(sessionStorage)).not.toContain('synthetic-token');
    expect(screen.getByRole('link', { name: 'Sign in' })).toBeTruthy();
  });

  it('a stale version (409) reloads the case and lets the user load the saved version', async () => {
    await signedIn();
    const seeded = api.seed(syntheticCase('Synthetic plot A'));
    const user = userEvent.setup();
    window.location.hash = `#/cases/${seeded.id}`;
    renderApp();
    const title = await screen.findByLabelText('Case name');
    api.editElsewhere(seeded.id, 'Changed by another person');
    await user.type(title, ' (mine)');
    expect(await screen.findByText('Someone else saved this case first')).toBeTruthy();
    expect(screen.getByText(/The server now has version 2\./)).toBeTruthy();
    expect((screen.getByLabelText('Case name') as HTMLInputElement).value).toBe('Synthetic plot A (mine)');
    await user.click(screen.getByRole('button', { name: 'Load the saved version' }));
    await waitFor(() => expect((screen.getByLabelText('Case name') as HTMLInputElement).value).toBe('Changed by another person'));
    expect(api.cases.get(seeded.id)!.title).toBe('Changed by another person');
  });

  it('a stale version can also be overwritten explicitly, with the new version', async () => {
    await signedIn();
    const seeded = api.seed(syntheticCase('Synthetic plot B'));
    const user = userEvent.setup();
    window.location.hash = `#/cases/${seeded.id}`;
    renderApp();
    const title = await screen.findByLabelText('Case name');
    api.editElsewhere(seeded.id, 'Changed by another person');
    await user.type(title, ' (mine)');
    await user.click(await screen.findByRole('button', { name: 'Save my version over it' }));
    await waitFor(() => expect(api.cases.get(seeded.id)!.title).toBe('Synthetic plot B (mine)'));
    const last = api.calls.filter((c) => c.method === 'PATCH' && (c.body as { title?: string }).title === 'Synthetic plot B (mine)').pop();
    expect(last?.body).toMatchObject({ version: 2 });
  });

  it('shows that server storage is unavailable (503) instead of any list', async () => {
    await signedIn();
    api.setOverride((_m, path) => (path.startsWith('/api/v1/cases') ? json(503, { detail: 'Persistent storage is not available on this server.' }) : undefined));
    window.location.hash = '#/cases';
    renderApp();
    expect(await screen.findByText('Case storage is not available on this server')).toBeTruthy();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('shows the lockout wait the server sent (429 Retry-After) and keeps the email', async () => {
    api.addUser(EMAIL, PASSWORD);
    api.setOverride((m, path) => (m === 'POST' && path === '/api/v1/auth/login'
      ? json(429, { detail: 'Too many failed sign-in attempts. Try again later.' }, { 'Retry-After': '900' }) : undefined));
    const user = userEvent.setup();
    window.location.hash = '#/cases';
    renderApp();
    await user.type(await screen.findByLabelText('Email'), EMAIL);
    await user.type(screen.getByLabelText('Password'), PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText(/try again in 15 minutes/)).toBeTruthy();
    expect((screen.getByLabelText('Email') as HTMLInputElement).value).toBe(EMAIL);
  });

  it('a reviewer sees the case read-only with the location the server redacted', async () => {
    await signedIn();
    const seeded = api.seed(syntheticCase('Shared synthetic plot'), 'REVIEWER');
    window.location.hash = '#/cases';
    renderApp();
    const row = await screen.findByRole('row', { name: /Shared synthetic plot/ });
    expect(row.textContent).toContain('Reviewer');
    expect(row.textContent).toMatch(/41[.,]65, −0[.,]85 \(±0[.,]05°\)/);
    expect(within(row).queryByRole('button', { name: 'Delete' })).toBeNull();
    go(`#/cases/${seeded.id}`);
    expect(await screen.findByText('You can read this case. Your role (Reviewer) cannot edit it.')).toBeTruthy();
    expect(screen.queryByLabelText('Case name')).toBeNull();
    expect(document.body.textContent).not.toContain('41.6537');
    expect(document.body.textContent).not.toContain('41,6537');
  });

  it('offers to delete cases left by the old browser-only storage', async () => {
    localStorage.setItem('abb-dev-cases-v1', JSON.stringify([{ id: 'local-1' }]));
    const user = userEvent.setup();
    window.location.hash = '#/cases';
    renderApp();
    await user.click(await screen.findByRole('button', { name: 'Delete browser copies' }));
    expect(localStorage.getItem('abb-dev-cases-v1')).toBeNull();
  });
});
