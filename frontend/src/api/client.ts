import type {
  CaseCreate, CaseList, CaseUpdate, CaseView, ClimateResponse, CropCatalog, FieldPatch, HypothesisCreate, HypothesisList,
  HypothesisStatusChange, HypothesisTemplateCatalog, HypothesisTemplateRequest, HypothesisView, LoginRequest, Paper,
  RegisterRequest, ReportRequest, ReportResponse, Rotation, RotationCompareRequest, RotationComparison,
  ScenarioAnalysis, ScenarioAnalysisRequest, SensitivityAnalysis, SensitivityRequest, SessionOut, Timeline, UserOut,
  PermissionGrant, PermissionView, ActivityPage, CommentCreate, CommentEdit, CommentList, CommentRevisionView, CommentView,
  InvitationCreate, InvitationDecision, InvitationList, InvitationView, ReceivedInvitationList, SharedCaseView,
  ShareLinkCreate, ShareLinkCreated, ShareLinkList, ApplicabilityReport, ApplicabilityRequest, ClaimCreate, ClaimEventView,
  ClaimList, ClaimView, DisagreementList, EvidenceGraph, EvidenceTrace, PaperRegistration, PaperView,
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
  /** GET /api/v1/hypothesis-templates (ABB-10). Static catalogue, not case-bound, no auth required. */
  hypothesisTemplates(signal?: AbortSignal) {
    return request<HypothesisTemplateCatalog>('/api/v1/hypothesis-templates', { signal });
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
  permissions(id: string, signal?: AbortSignal) {
    return request<PermissionView[]>(`${casePath(id)}/permissions`, { auth: true, signal });
  },
  grantPermission(id: string, body: PermissionGrant) {
    return request<PermissionView>(`${casePath(id)}/permissions`, { method: 'POST', auth: true, json: body });
  },
  revokePermission(id: string, userId: string) {
    return request<void>(`${casePath(id)}/permissions/${encodeURIComponent(userId)}`, { method: 'DELETE', auth: true });
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
  /** GET /api/v1/cases/{id}/timeline (ABB-10/ABB-22): every member, coordinates redacted server-side. */
  timeline(id: string, signal?: AbortSignal) {
    return request<Timeline>(`${casePath(id)}/timeline`, { auth: true, signal });
  },
  hypotheses(id: string, signal?: AbortSignal) {
    return request<HypothesisList>(`${casePath(id)}/hypotheses`, { auth: true, signal });
  },
  createHypothesis(id: string, body: HypothesisCreate) {
    return request<HypothesisView>(`${casePath(id)}/hypotheses`, { method: 'POST', auth: true, json: body });
  },
  addHypothesisTemplates(id: string, body: HypothesisTemplateRequest) {
    return request<HypothesisList>(`${casePath(id)}/hypotheses/templates`, { method: 'POST', auth: true, json: body });
  },
  evaluateHypothesis(id: string, hypothesisId: string, body: HypothesisStatusChange) {
    return request<HypothesisView>(`${casePath(id)}/hypotheses/${encodeURIComponent(hypothesisId)}/status`, { method: 'POST', auth: true, json: body });
  },
};

/**
 * /api/v1/rotations (ABB-17/ABB-18, ABB-24 comparator). Stateless: every call sends the
 * whole profile; nothing is persisted server-side. No auth (same as /api/v1/crop-catalog).
 */
export const rotationsApi = {
  cropCatalog(signal?: AbortSignal) {
    return request<CropCatalog>('/api/v1/crop-catalog', { signal });
  },
  compare(body: RotationCompareRequest, signal?: AbortSignal) {
    return request<RotationComparison>('/api/v1/rotations/compare', { method: 'POST', json: body, signal });
  },
  scenarios(body: ScenarioAnalysisRequest, signal?: AbortSignal) {
    return request<ScenarioAnalysis>('/api/v1/rotations/scenarios', { method: 'POST', json: body, signal });
  },
  sensitivity(body: SensitivityRequest, signal?: AbortSignal) {
    return request<SensitivityAnalysis>('/api/v1/rotations/sensitivity', { method: 'POST', json: body, signal });
  },
};

/**
 * Collaboration (ABB-25, docs/architecture/COLLABORATION.md). Invitations, comments, activity and
 * share links are case-scoped and authenticated; `shared` is the public, account-free read of a
 * consented share link. Comment bodies, notes and labels are plain text: render them as text.
 */
export const collabApi = {
  invitations(caseId: string, signal?: AbortSignal) {
    return request<InvitationList>(`${casePath(caseId)}/invitations`, { auth: true, signal });
  },
  invite(caseId: string, body: InvitationCreate) {
    return request<InvitationView>(`${casePath(caseId)}/invitations`, { method: 'POST', auth: true, json: body });
  },
  revokeInvitation(caseId: string, invitationId: string) {
    return request<void>(`${casePath(caseId)}/invitations/${encodeURIComponent(invitationId)}`, { method: 'DELETE', auth: true });
  },
  /** Pending invitations addressed to the signed-in account's e-mail. */
  received(signal?: AbortSignal) {
    return request<ReceivedInvitationList>('/api/v1/invitations', { auth: true, signal });
  },
  accept(invitationId: string) {
    return request<InvitationDecision>(`/api/v1/invitations/${encodeURIComponent(invitationId)}/accept`, { method: 'POST', auth: true });
  },
  decline(invitationId: string) {
    return request<InvitationDecision>(`/api/v1/invitations/${encodeURIComponent(invitationId)}/decline`, { method: 'POST', auth: true });
  },
  comments(caseId: string, signal?: AbortSignal, offset = 0) {
    const params = new URLSearchParams({ limit: '200', offset: String(offset) });
    return request<CommentList>(`${casePath(caseId)}/comments?${params}`, { auth: true, signal });
  },
  comment(caseId: string, body: CommentCreate) {
    return request<CommentView>(`${casePath(caseId)}/comments`, { method: 'POST', auth: true, json: body });
  },
  editComment(caseId: string, commentId: string, body: CommentEdit) {
    return request<CommentView>(`${casePath(caseId)}/comments/${encodeURIComponent(commentId)}`, { method: 'PATCH', auth: true, json: body });
  },
  deleteComment(caseId: string, commentId: string) {
    return request<void>(`${casePath(caseId)}/comments/${encodeURIComponent(commentId)}`, { method: 'DELETE', auth: true });
  },
  revisions(caseId: string, commentId: string, signal?: AbortSignal) {
    return request<CommentRevisionView[]>(`${casePath(caseId)}/comments/${encodeURIComponent(commentId)}/revisions`, { auth: true, signal });
  },
  activity(caseId: string, offset = 0, signal?: AbortSignal) {
    const params = new URLSearchParams({ limit: '25', offset: String(offset), order: 'desc' });
    return request<ActivityPage>(`${casePath(caseId)}/activity?${params}`, { auth: true, signal });
  },
  shareLinks(caseId: string, signal?: AbortSignal) {
    return request<ShareLinkList>(`${casePath(caseId)}/share-links`, { auth: true, signal });
  },
  createShareLink(caseId: string, body: ShareLinkCreate) {
    return request<ShareLinkCreated>(`${casePath(caseId)}/share-links`, { method: 'POST', auth: true, json: body });
  },
  revokeShareLink(caseId: string, linkId: string) {
    return request<void>(`${casePath(caseId)}/share-links/${encodeURIComponent(linkId)}`, { method: 'DELETE', auth: true });
  },
  /** Public, no account: the token is the only credential, so it is never logged or stored. */
  shared(token: string, signal?: AbortSignal) {
    return request<SharedCaseView>(`/api/v1/shared/${encodeURIComponent(token)}`, { signal, referrerPolicy: 'no-referrer', cache: 'no-store' });
  },
};

/**
 * Case evidence (ABB-14 claims, ABB-15 disagreements/applicability, ABB-16 graph; ABB-23 UI).
 * Read routes serve every member; writes follow each route's role rules on the server.
 */
export const evidenceApi = {
  claims(caseId: string, signal?: AbortSignal) {
    return request<ClaimList>(`${casePath(caseId)}/claims`, { auth: true, signal });
  },
  claimHistory(caseId: string, claimId: string, signal?: AbortSignal) {
    return request<ClaimEventView[]>(`${casePath(caseId)}/claims/${encodeURIComponent(claimId)}/history`, { auth: true, signal });
  },
  /** Registers a work by DOI or OpenAlex id; the server fetches and verifies its metadata (no metadata is sent). */
  registerPaper(body: PaperRegistration) {
    return request<PaperView>('/api/v1/evidence/papers', { method: 'POST', auth: true, json: body });
  },
  createClaim(caseId: string, body: ClaimCreate) {
    return request<ClaimView>(`${casePath(caseId)}/claims`, { method: 'POST', auth: true, json: body });
  },
  disagreements(caseId: string, signal?: AbortSignal) {
    return request<DisagreementList>(`${casePath(caseId)}/claims/disagreements`, { auth: true, signal });
  },
  applicability(caseId: string, claimId: string, body: ApplicabilityRequest) {
    return request<ApplicabilityReport>(`${casePath(caseId)}/claims/${encodeURIComponent(claimId)}/applicability`, { method: 'POST', auth: true, json: body });
  },
  graph(caseId: string, signal?: AbortSignal) {
    return request<EvidenceGraph>(`${casePath(caseId)}/evidence-graph`, { auth: true, signal });
  },
  trace(caseId: string, nodeId: string, signal?: AbortSignal) {
    return request<EvidenceTrace>(`${casePath(caseId)}/evidence-graph/trace/${encodeURIComponent(nodeId)}`, { auth: true, signal });
  },
};
