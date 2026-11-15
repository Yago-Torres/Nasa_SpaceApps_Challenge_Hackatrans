import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, configure, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../../i18n/I18n';
import { PrecipitationPanel, gpmYear } from './PrecipitationPanel';
import type { GpmMonth, PrecipitationResponse } from '../../api/types';

configure({ asyncUtilTimeout: 5000 });

/* ── TEST-ONLY fixture for GET /api/precipitation/gpm (ABB-09). SYNTHETIC values matching the documented
 * contract; the app never ships sample data. */
function month(m: number, gpm: number | null, power: number | null, status: GpmMonth['status'] = gpm === null ? 'NOT_AVAILABLE' : 'OBSERVED'): GpmMonth {
  return {
    month: m, status, reason: status === 'OBSERVED' ? null : 'No IMERG Final granule is published for this month.',
    granule_id: gpm === null ? null : `3B-MO.${m}.HDF5`, hours: 720, rate_mm_per_hour: gpm === null ? null : gpm / 720,
    precipitation_mm: gpm, random_error_mm: gpm === null ? null : 4, quality_index: null, gauge_weight_percent: gpm === null ? null : 90,
    data_sha256: gpm === null ? null : 'b'.repeat(64), power_precipitation_mm: power,
    difference_mm: gpm !== null && power !== null ? Math.round((gpm - power) * 10) / 10 : null,
  };
}
const response: PrecipitationResponse = {
  kind: 'observation', source_kind: 'OBSERVED', dataset: 'GPM IMERG Final Precipitation L3 1 month 0.1 degree x 0.1 degree V07 (GPM_3IMERGM)',
  source_url: 'https://doi.org/10.5067/GPM/IMERG/3B-MONTH/07',
  request_params: { latitude: 41.65, longitude: -0.88, year: 2022, product: 'GPM_3IMERGM v07' },
  year: 2022, cell: { latitude: 41.65, longitude: -0.85, size_degrees: 0.1 }, retrieved_at: '2026-11-15T12:00:00Z',
  spatial_resolution: { value: 0.1, unit: 'degree', description: '0.1° cell.' },
  temporal_resolution: { value: 1, unit: 'month', description: 'Months.' },
  provenance: {
    schema_version: '1.0', id: '11111111-1111-4111-8111-111111111111', provider: 'NASA GES DISC', dataset: 'GPM', source_uri: 'https://doi.org/x',
    query_parameters: {}, retrieved_at: '2026-11-15T12:00:00Z', checksum_sha256: 'c'.repeat(64), dataset_version: 'IMERG V07 Final',
    processing_version: 'test', license: null, spatial_resolution: { value: 0.1, unit: 'degree', description: 'x' },
    temporal_resolution: { value: 1, unit: 'month', description: 'x' }, limitations: ['Not a gauge.'],
  },
  monthly: [month(1, 16.4, 7.4), month(2, 4, 2.1), ...Array.from({ length: 9 }, (_, i) => month(i + 3, 20, 18)), month(12, null, 43.5)],
  comparison: {
    status: 'COMPARED', reason: null, dataset: 'NASA POWER daily point', parameter: 'PRECTOTCORR', spatial_resolution: '0.5° × 0.625° (MERRA-2 grid)',
    data_sha256: 'a'.repeat(64), retrieved_at: '2026-11-15T12:00:00Z', months_compared: 11, gpm_total_mm: 200.4, power_total_mm: 171.5,
  },
  summary: { observed: 11, missing: 0, not_available: 1, not_read: 0, granules_found: 11, total_observed_mm: 200.4 },
  method: {}, cache: { upstream_requests: 13 }, limitations: ['A difference describes disagreement between products.'], disclaimer: 'Observed.',
};

function stubFetch(status: number, body: unknown) {
  const fn = vi.fn(async (_input: RequestInfo | URL) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
  vi.stubGlobal('fetch', fn);
  return fn;
}
const renderPanel = (year = '2022') =>
  render(<I18nProvider lang="en"><PrecipitationPanel point={{ latitude: 41.65, longitude: -0.88 }} year={year} /></I18nProvider>);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('PrecipitationPanel (ABB-09)', () => {
  it('accepts the GPM year range only', () => {
    expect(gpmYear('2022', 2026)).toBe(2022);
    expect(gpmYear('1997', 2026)).toBeNull();
    expect(gpmYear('2027', 2026)).toBeNull();
    expect(gpmYear('20.5', 2026)).toBeNull();
  });

  it('shows both products, totals, missing months and the source', async () => {
    const fetchMock = stubFetch(200, response);
    renderPanel();
    await userEvent.click(screen.getByRole('button', { name: 'Fetch GPM rain for 2022' }));
    expect(await screen.findByText(/GPM 200\.4 mm, POWER 171\.5 mm/)).toBeTruthy();
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/precipitation/gpm?latitude=41.65&longitude=-0.88&year=2022');
    expect(screen.getByRole('img', { name: 'January: GPM 16.4 mm, POWER 7.4 mm' })).toBeTruthy();
    expect(screen.getByRole('img', { name: 'December: GPM no data, POWER 43.5 mm' })).toBeTruthy();
    expect(screen.getByText(/No value for: December/)).toBeTruthy();
    expect(screen.getByText('Source: NASA GPM IMERG')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Show as table' }));
    expect(screen.getByRole('cell', { name: '+9.0' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: 'Not published yet' })).toBeTruthy();
  });

  it('says GPM is unavailable on a 503 and draws nothing', async () => {
    stubFetch(503, { detail: 'GPM precipitation is not available on this server: NASA Earthdata access is not configured (EARTHDATA_TOKEN).' });
    renderPanel();
    await userEvent.click(screen.getByRole('button', { name: 'Fetch GPM rain for 2022' }));
    expect(await screen.findByText('GPM is not available on this server')).toBeTruthy();
    expect(screen.queryByRole('img', { name: /GPM/ })).toBeNull();
  });

  it('shows an error with retry when NASA fails', async () => {
    stubFetch(502, { detail: 'NASA GES DISC is unavailable (HTTP 503).' });
    renderPanel();
    await userEvent.click(screen.getByRole('button', { name: 'Fetch GPM rain for 2022' }));
    expect(await screen.findByText('NASA GPM data could not be loaded')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
  });

  it('asks for a valid year before fetching', () => {
    renderPanel('1990');
    expect(screen.getByText('Enter a valid point and a year from 1998 above first.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Fetch GPM/ })).toBeNull();
  });
});
