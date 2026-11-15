import { ApiError } from '../../../api/client';
import { clearSession, getSession } from '../../../api/session';

/** Shapes of backend/agroblackbox/api/reports.py (ABB-26). Nothing here is computed in the browser. */
export type ReportFormat = 'markdown' | 'html' | 'json' | 'pdf';
export type ReportChangeItem = { section: string; change: 'ADDED' | 'REMOVED' | 'CHANGED'; id: string; label: string };
export type ReportChanges = {
  initial: boolean; previous_version: number | null; previous_case_version?: number; case_version: number | null; items: ReportChangeItem[];
};
export type ReportView = {
  id: string; case_id: string; version: number; generated_at: string; language?: 'en' | 'es'; status: 'PRELIMINARY' | 'REVIEWED';
  case_version: number | null; generated_by: { id: string; display_name: string } | null; formats: ReportFormat[];
  checksum_sha256: string | null; html_sha256: string | null; pdf_sha256?: string | null; snapshot_sha256: string | null; sources_sha256: string | null;
  source_manifest_ids: string[]; changes: ReportChanges | null; limitations: string[]; downloads: Partial<Record<ReportFormat, string>>;
};
export type VerifyResult = { version: number; valid: boolean; checks: Record<string, boolean>; detail: string };

async function call(path: string, init: RequestInit = {}): Promise<Response> {
  const session = getSession();
  if (!session) throw new ApiError('HTTP 401: Authentication required.', 401, path, 'Authentication required.');
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers: { Accept: 'application/json', ...(init.headers as Record<string, string>), Authorization: `Bearer ${session.token}` } });
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') throw err;
    throw new ApiError('network', null, path);
  }
  if (!response.ok) {
    let detail: string | null = null;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch { /* non-JSON error body */ }
    if (response.status === 401) clearSession();
    throw new ApiError(detail ? `HTTP ${response.status}: ${detail}` : `HTTP ${response.status}`, response.status, path, detail);
  }
  return response;
}

const base = (id: string) => `/api/v1/cases/${encodeURIComponent(id)}/reports`;

export const reportsApi = {
  async list(caseId: string, signal?: AbortSignal): Promise<ReportView[]> {
    return ((await (await call(base(caseId), { signal })).json()) as { items: ReportView[] }).items;
  },
  /** Stores a new immutable version built by the server from the case as it is now. */
  async create(caseId: string, language: 'en' | 'es'): Promise<ReportView> {
    return (await (await call(base(caseId), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ language }) })).json()) as ReportView;
  },
  async verify(caseId: string, version: number): Promise<VerifyResult> {
    return (await (await call(`${base(caseId)}/${version}/verify`)).json()) as VerifyResult;
  },
  /** Exactly the stored bytes, plus the server's SHA-256 header. */
  async download(caseId: string, version: number, format: ReportFormat): Promise<{ blob: Blob; sha256: string | null; filename: string }> {
    const response = await call(`${base(caseId)}/${version}/download?format=${format}`);
    const ext = format === 'markdown' ? 'md' : format;
    return { blob: await response.blob(), sha256: response.headers.get('X-Report-SHA256'), filename: `cropstory-case-report-v${version}.${ext}` };
  },
};
