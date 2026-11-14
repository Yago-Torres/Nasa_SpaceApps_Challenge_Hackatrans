import type { ClimateResponse, Paper, ReportRequest, ReportResponse, Rotation } from './types';

/** Error with the HTTP status and the backend's `detail`, so screens can say what failed. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly path: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
  /** True when the server was never reached (offline, backend down, CORS). */
  get isNetwork() {
    return this.status === null;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { headers: { Accept: 'application/json', ...init?.headers }, ...init });
  } catch {
    throw new ApiError('network', null, path);
  }
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = `${detail}: ${body.detail}`;
      else if (Array.isArray(body.detail)) detail = `${detail}: ${body.detail.map((d) => d?.msg ?? '').join('; ')}`;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, response.status, path);
  }
  return (await response.json()) as T;
}

export type ClimateQuery = { latitude: number; longitude: number; eventYear: number; referenceStart: number; referenceEnd: number };

export const api = {
  climate(q: ClimateQuery, signal?: AbortSignal) {
    const params = new URLSearchParams({
      latitude: String(q.latitude),
      longitude: String(q.longitude),
      event_year: String(q.eventYear),
      reference_start: String(q.referenceStart),
      reference_end: String(q.referenceEnd),
    });
    return request<ClimateResponse>(`/api/climate?${params}`, { signal });
  },
  async literature(query: string, signal?: AbortSignal) {
    const out = await request<{ results: Paper[] }>(`/api/literature?${new URLSearchParams({ query })}`, { signal });
    return out.results;
  },
  async rotationsDemo(signal?: AbortSignal) {
    const out = await request<{ rotations: Rotation[] }>('/api/rotations/demo', { signal });
    return out.rotations;
  },
  report(body: ReportRequest) {
    return request<ReportResponse>('/api/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  },
};
