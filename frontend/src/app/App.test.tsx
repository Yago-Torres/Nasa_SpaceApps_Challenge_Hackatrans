import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, configure, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../i18n/I18n';
import { App } from './App';
import type { ClimateResponse } from '../api/types';

// TEST-ONLY fixture. Values are synthetic and exist only to exercise rendering paths.
const month = (m: number, rain: number | null, tmax: number | null) => ({
  month: m, precipitation_mm: rain === null ? null : 40 + rain, reference_precipitation_mm: rain === null ? null : 40,
  precipitation_anomaly_mm: rain, max_temperature_c: tmax === null ? null : 25 + tmax, reference_max_temperature_c: tmax === null ? null : 25, max_temperature_anomaly_c: tmax,
});
const FIXTURE: ClimateResponse = {
  kind: 'observation', dataset: 'NASA POWER daily point', source_url: 'https://power.larc.nasa.gov/docs/services/api/temporal/daily/',
  data_sha256: 'a'.repeat(64), request_params: { latitude: 41.6, longitude: -0.9, parameters: 'PRECTOTCORR,T2M_MAX' },
  event_year: 2022, reference_start: 2010, reference_end: 2021,
  monthly: Array.from({ length: 12 }, (_, i) => month(i + 1, i === 8 ? null : i % 2 ? -10 : 5, i === 8 ? null : 1)),
  disclaimer: 'Gridded regional meteorology, not a field reading.',
};

function renderApp(lang: 'en' | 'es' = 'en') {
  return render(<I18nProvider lang={lang}><App /></I18nProvider>);
}

// Slower CI runners: async queries wait longer instead of relying on timing.
configure({ asyncUtilTimeout: 5000 });

beforeEach(() => {
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  window.location.hash = '';
});

describe('App shell', () => {
  it('offers a skip link and the seven primary destinations', () => {
    renderApp();
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveProperty('hash', '#content');
    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    expect(within(within(nav).getByRole('list')).getAllByRole('link')).toHaveLength(7);
  });

  it('navigates with the keyboard and moves focus to the new page heading', async () => {
    const user = userEvent.setup();
    renderApp();
    const link = within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: /Evidence/ });
    link.focus();
    await user.keyboard('{Enter}');
    window.dispatchEvent(new HashChangeEvent('hashchange'));
    const heading = await screen.findByRole('heading', { level: 1, name: 'Evidence' });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(link.getAttribute('aria-current')).toBe('page');
  });

  it('switches every main label to Spanish', async () => {
    const user = userEvent.setup();
    renderApp();
    await user.click(screen.getByRole('button', { name: 'ES' }));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Investiga una cosecha fallida con datos de la NASA');
    expect(screen.getByRole('navigation', { name: 'Navegación principal' })).toBeTruthy();
    expect(document.documentElement.lang).toBe('es');
  });

  it('marks unbuilt screens as pending instead of showing sample data', () => {
    window.location.hash = '#/collaboration';
    renderApp();
    expect(screen.getByText('Not built yet')).toBeTruthy();
    expect(screen.queryByRole('table')).toBeNull();
  });
});

describe('Investigation states', () => {
  it('validates fields, focuses the first error and sends no request', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const user = userEvent.setup();
    window.location.hash = '#/investigation';
    renderApp();
    await user.type(screen.getByLabelText('Latitude'), '200');
    await user.click(screen.getByRole('button', { name: 'Fetch NASA weather' }));
    expect(screen.getByText('Use a number from −90 to 90.')).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByLabelText('Latitude'));
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('shows the backend error and no values when NASA POWER fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'NASA POWER source unavailable' }), { status: 502 }));
    const user = userEvent.setup();
    window.location.hash = '#/investigation';
    renderApp();
    await user.type(screen.getByLabelText('Latitude'), '41.6');
    await user.type(screen.getByLabelText('Longitude'), '-0.9');
    await user.type(screen.getByLabelText('Year of the incident'), '2022');
    await user.click(screen.getByRole('button', { name: 'Fetch NASA weather' }));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('HTTP 502: NASA POWER source unavailable');
    expect(screen.queryByRole('group', { name: /Monthly rain difference/ })).toBeNull();
  });

  it('renders the record with its source, an Observed label and the missing month as partial', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(FIXTURE), { status: 200 }));
    const user = userEvent.setup();
    window.location.hash = '#/investigation';
    renderApp();
    await user.type(screen.getByLabelText('Latitude'), '41.6');
    await user.type(screen.getByLabelText('Longitude'), '-0.9');
    await user.type(screen.getByLabelText('Year of the incident'), '2022');
    await user.click(screen.getByRole('button', { name: 'Fetch NASA weather' }));
    expect(await screen.findByRole('group', { name: /Monthly rain difference, 2022/ })).toBeTruthy();
    expect(screen.getAllByText(/Observed/).length).toBeGreaterThan(0);
    expect(screen.getByText('Part of the record is missing')).toBeTruthy();
    expect(screen.getByRole('img', { name: 'September: no data' })).toBeTruthy();
    expect(screen.getByText(FIXTURE.disclaimer)).toBeTruthy();
    expect(String((vi.mocked(fetch).mock.calls[0] ?? [])[0])).toContain('reference_start=2010');
  });
});
