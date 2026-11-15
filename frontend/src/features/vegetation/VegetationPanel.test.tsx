import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, configure, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../../i18n/I18n';
import { VegetationPanel, validateRange } from './VegetationPanel';
import type { HlsObservation, VegetationResponse } from '../../api/types';

configure({ asyncUtilTimeout: 5000 });

/* ── TEST-ONLY fixture for GET /api/vegetation/hls (ABB-12). SYNTHETIC values matching the documented
 * contract; the app never ships sample data. */
const pixels = { clear: 0, cloud: 0, cloud_shadow: 0, adjacent_cloud: 0, cirrus: 0, snow_ice: 0, water: 0, high_aerosol: 0, fill: 0, invalid_reflectance: 0 };
function obs(date: string, status: HlsObservation['status'], ndvi: number | null): HlsObservation {
  return {
    date, acquired_at: `${date}T10:55:02Z`, product: 'HLSL30', sensor: 'Landsat 8/9 OLI', granule_id: `HLS.L30.T30TXM.${date}.v2.0`,
    mgrs_tile: '30TXM', scene_cloud_cover: 10, status, reason: status === 'VALID' ? null : 'Only 0 of 9 window pixels are clear.',
    window_pixels: 9, pixels: { ...pixels, clear: status === 'VALID' ? 9 : 0, cloud: status === 'VALID' ? 0 : 9 },
    ndvi, ndvi_min: ndvi, ndvi_max: ndvi, red_reflectance: ndvi === null ? null : 0.08, nir_reflectance: ndvi === null ? null : 0.24,
    red_band: 'B04', nir_band: 'B05', epsg: 32630, pixel_size_m: 30, data_sha256: 'b'.repeat(64),
  };
}
const response: VegetationResponse = {
  kind: 'observation', source_kind: 'OBSERVED', dataset: 'NASA HLS v2.0 (HLSL30 + HLSS30) surface reflectance, point window',
  source_url: 'https://lpdaac.usgs.gov/products/hlsl30v002/',
  request_params: { latitude: 41.65, longitude: -0.88, start: '2023-06-01', end: '2023-06-30', products: 'HLSL30 v2.0,HLSS30 v2.0' },
  start: '2023-06-01', end: '2023-06-30', retrieved_at: '2026-11-15T11:00:00Z',
  spatial_resolution: { value: 30, unit: 'm', description: '30 m pixels, 3 × 3 window.' },
  temporal_resolution: { value: null, unit: 'acquisition', description: 'Overpasses.' },
  provenance: {
    schema_version: '1.0', id: '11111111-1111-4111-8111-111111111111', provider: 'NASA LP DAAC', dataset: 'HLS', source_uri: 'https://lpdaac.usgs.gov/',
    query_parameters: {}, retrieved_at: '2026-11-15T11:00:00Z', checksum_sha256: 'c'.repeat(64), dataset_version: 'HLS v2.0',
    processing_version: 'test', license: null, spatial_resolution: { value: 30, unit: 'm', description: '30 m' },
    temporal_resolution: { value: null, unit: 'acquisition', description: 'x' }, limitations: ['NDVI is not soil health.'],
  },
  observations: [obs('2023-06-03', 'VALID', 0.5), obs('2023-06-12', 'OBSCURED', null)],
  gaps: [{ start: '2023-06-01', end: '2023-06-02', days: 2 }, { start: '2023-06-04', end: '2023-06-30', days: 27 }],
  summary: { acquisitions: 2, valid: 1, obscured: 1, no_data: 0, not_read: 0, granules_found: 2, gap_days: 29, longest_gap_days: 27 },
  method: { id: 'm', window: 'w', clear_rule: 'c', ndvi_formula: 'n', bands: {}, reflectance_scale: 0.0001, valid_reflectance_range: [-100, 16000], acquisition_rule: 'a', processing_version: 'p' },
  cache: { search_from_cache: false, scenes_from_cache: 0, upstream_requests: 12 },
  limitations: ['NDVI is canopy greenness, not soil health.'],
  disclaimer: 'Observed.',
};

function stubFetch(status: number, body: unknown) {
  const fn = vi.fn(async (_input: RequestInfo | URL) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
  vi.stubGlobal('fetch', fn);
  return fn;
}

function renderPanel() {
  return render(
    <I18nProvider lang="en">
      <VegetationPanel point={{ latitude: 41.65, longitude: -0.88 }} year="2023" />
    </I18nProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('VegetationPanel (ABB-12)', () => {
  it('validates the date range like the API', () => {
    expect(validateRange({ start: '2023-04-01', end: '2023-07-01' }, '2026-11-15')).toEqual({});
    expect(validateRange({ start: '2023-04-01', end: '2023-07-02' }, '2026-11-15')).toEqual({ span: true });
    expect(validateRange({ start: '2013-01-01', end: '2013-02-01' }, '2026-11-15')).toEqual({ start: true });
    expect(validateRange({ start: '2026-11-01', end: '2026-11-20' }, '2026-11-15')).toEqual({ end: true });
    expect(validateRange({ start: '', end: '' }, '2026-11-15')).toEqual({ start: true, end: true });
  });

  it('suggests the spring of the incident year and shows observations, gaps and the source', async () => {
    const fetchMock = stubFetch(200, response);
    renderPanel();
    expect(screen.getByLabelText('From')).toHaveProperty('value', '2023-04-01');
    await userEvent.click(screen.getByRole('button', { name: 'Fetch HLS vegetation' }));
    expect(await screen.findByText(/2 overpasses from/)).toBeTruthy();
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/vegetation/hls?latitude=41.65&longitude=-0.88&start=2023-04-01&end=2023-06-30');
    expect(screen.getByText(/Days without a valid observation: 29/)).toBeTruthy();
    expect(screen.getByRole('img', { name: /NDVI 0\.50, 9 of 9 pixels clear/ })).toBeTruthy();
    expect(screen.getByRole('img', { name: /Hidden by clouds or other/ })).toBeTruthy();
    expect(screen.getByText('Source: NASA HLS')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: 'Show as table' }));
    expect(screen.getByRole('cell', { name: 'no data' })).toBeTruthy();
  });

  it('says HLS is unavailable on a 503 and draws nothing', async () => {
    stubFetch(503, { detail: 'HLS observations are not available on this server: NASA Earthdata access is not configured (EARTHDATA_TOKEN).' });
    renderPanel();
    await userEvent.click(screen.getByRole('button', { name: 'Fetch HLS vegetation' }));
    expect(await screen.findByText('HLS is not available on this server')).toBeTruthy();
    expect(screen.queryByRole('img', { name: /NDVI/ })).toBeNull();
    expect(screen.queryByText('Source: NASA HLS')).toBeNull();
  });

  it('shows an error with retry when NASA fails', async () => {
    stubFetch(502, { detail: 'NASA LP DAAC is unavailable (HTTP 503).' });
    renderPanel();
    await userEvent.click(screen.getByRole('button', { name: 'Fetch HLS vegetation' }));
    expect(await screen.findByText('NASA HLS data could not be loaded')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
  });

  it('asks for a point before anything else', () => {
    render(<I18nProvider lang="en"><VegetationPanel point={null} year="" /></I18nProvider>);
    expect(screen.getByText('Enter a valid latitude and longitude above first.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Fetch HLS vegetation' })).toBeNull();
  });
});
