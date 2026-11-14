import type {
  CaseCreate, CaseList, CaseUpdate, CaseView, ClimateResponse, FieldPatch, LoginRequest, Paper,
  RegisterRequest, ReportRequest, ReportResponse, Rotation, SessionOut, UserOut,
} from './types';
import { clearSession, getSession } from './session';

/** Error with the HTTP status and the backend's `detail`, so screens can say what failed. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly path: string,
    /** The backend `detail` string, when it sent one. */
    readonly detail: string | null = null,
    /** Seconds from a `Retry-After` header (429 account lockout). */
    readonly retryAfter: number | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
  }
  /** True when the server was never reached (offline, backend down, CORS). */
  get isNetwork() {
    return this.status === null;
  }
}

type RequestOptions = RequestInit & {
  /** Send `Authorization: Bearer <token>`. A 401 answer signs the user out. */
  auth?: boolean;
  /** JSON request body. */
  json?: unknown;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { auth, json, headers: extra, ...init } = options;
  const headers: Record<string, string> = { Accept: 'application/json', ...(extra as Record<string, string> | undefined) };
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(json);
  }
  if (auth) {
    const session = getSession();
    if (!session) throw new ApiError('HTTP 401: Authentication required.', 401, path, 'Authentication required.');
    headers.Authorization = `Bearer ${session.token}`;
  }
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') throw err;
    throw new ApiError('network', null, path);
  }
  if (!response.ok) {
    let detail: string | null = null;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d) => d?.msg ?? '').join('; ');
    } catch {
      /* non-JSON error body */
    }
    const seconds = Number.parseInt(response.headers?.get('Retry-After') ?? '', 10);
    if (auth && response.status === 401) clearSession();
    throw new ApiError(detail ? `HTTP ${response.status}: ${detail}` : `HTTP ${response.status}`, response.status, path, detail, Number.isFinite(seconds) ? seconds : null);
  }
  if (response.status === 204) return undefined as T;
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
    return request<ReportResponse>('/api/report', { method: 'POST', json: body });
  },
};

/** /api/v1/auth (ABB-05). */
export const authApi = {
  register(body: RegisterRequest) {
    return request<UserOut>('/api/v1/auth/register', { method: 'POST', json: body });
  },
  login(body: LoginRequest) {
    return request<SessionOut>('/api/v1/auth/login', { method: 'POST', json: body });
  },
  logout() {
    return request<void>('/api/v1/auth/logout', { method: 'POST', auth: true });
  },
};

const casePath = (id: string) => `/api/v1/cases/${encodeURIComponent(id)}`;

/** /api/v1/cases (ABB-06). Every mutation sends the version the client read. */
export const casesApi = {
  list(signal?: AbortSignal) {
    return request<CaseList>('/api/v1/cases', { auth: true, signal });
  },
  get(id: string, signal?: AbortSignal) {
    return request<CaseView>(casePath(id), { auth: true, signal });
  },
  create(body: CaseCreate) {
    return request<CaseView>('/api/v1/cases', { method: 'POST', auth: true, json: body });
  },
  update(id: string, body: CaseUpdate) {
    return request<CaseView>(casePath(id), { method: 'PATCH', auth: true, json: body });
  },
  updateField(id: string, fieldId: string, body: FieldPatch) {
    return request<CaseView>(`${casePath(id)}/fields/${encodeURIComponent(fieldId)}`, { method: 'PATCH', auth: true, json: body });
  },
  remove(id: string, version: number) {
    return request<void>(`${casePath(id)}?${new URLSearchParams({ version: String(version) })}`, { method: 'DELETE', auth: true });
  },
};
