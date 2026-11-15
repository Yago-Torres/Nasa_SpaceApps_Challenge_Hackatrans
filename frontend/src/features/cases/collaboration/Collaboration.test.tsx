import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, configure, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../../../i18n/I18n';
import { clearSession, resetSessionCache, setSession } from '../../../api/session';
import type {
  ActivityPage, CaseView, CommentView, InvitationView, PermissionView, ReceivedInvitationView, Role, SharedCaseView, ShareLinkCreated,
} from '../../../api/types';
import { CollaborationPanel } from '../CollaborationPanel';
import { DiscussionPanel } from '../DiscussionPanel';
import { Collaboration } from '../../Collaboration';
import { SharedCase } from '../../SharedCase';

/* ── TEST-ONLY synthetic fixtures, shaped like backend/agroblackbox/api/collaboration_dto.py ── */

const CASE_ID = '11111111-1111-4111-8111-111111111111';
const USER = { id: 'u1', email: 'owner@example.org', display_name: 'Synthetic owner', created_at: '2026-01-01T00:00:00Z' };

function caseView(role: Role, archived = false): CaseView {
  return {
    schema_version: '1.0', id: CASE_ID, title: 'Synthetic plot', incident_start: '2022-04-01', incident_end: '2022-06-30',
    fields: [{ schema_version: '1.0', id: 'f1', label: 'North field', privacy_tier: 'APPROXIMATE', latitude: 41.6, longitude: -0.9,
      region_label: 'Synthetic region', area_hectares: null, limitations: [], location_precision: role === 'OWNER' ? 'EXACT' : 'APPROXIMATE', rounding_deg: 0.1, precise_location_consent: false }],
    crop_history: [], incident_notes: 'Synthetic notes.', visibility: 'PRIVATE',
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', version: 1, status: 'INVESTIGATING',
    archived_at: archived ? '2026-01-03T00:00:00Z' : null, owner: { id: 'u1', display_name: 'Synthetic owner' }, my_role: role,
  };
}

const MEMBERS: PermissionView[] = [
  { user_id: 'u1', display_name: 'Synthetic owner', email: 'owner@example.org', role: 'OWNER' },
  { user_id: 'u2', display_name: 'Synthetic reviewer', email: 'reviewer@example.org', role: 'REVIEWER' },
];

function invitation(overrides: Partial<InvitationView> = {}): InvitationView {
  return {
    id: 'inv-1', case_id: CASE_ID, email: 'guest@example.org', role: 'VIEWER', note: null, status: 'PENDING',
    invited_by: { id: 'u1', display_name: 'Synthetic owner' }, created_at: '2026-01-02T00:00:00Z', expires_at: '2026-01-16T00:00:00Z',
    responded_at: null, revoked_at: null, ...overrides,
  };
}

function comment(overrides: Partial<CommentView> = {}): CommentView {
  return {
    id: 'c1', case_id: CASE_ID, target: { kind: 'CASE', id: null }, parent_id: null, author: { id: 'u2', display_name: 'Synthetic reviewer' },
    body: 'Synthetic comment.', body_format: 'text/plain', created_at: '2026-01-02T10:00:00Z', edited_at: null, version: 1,
    revision_count: 0, reply_count: 0, deleted: false, deleted_at: null, deleted_by: null, can_edit: false, can_delete: false, ...overrides,
  };
}

const EMPTY_ACTIVITY: ActivityPage = { items: [], total: 0, limit: 25, offset: 0, order: 'desc', sources: ['CASE_HISTORY', 'CLAIM_EVENT', 'DISAGREEMENT_REVIEW', 'COMMENT'] };

// findBy*/waitFor default to 1 s; the full suite under WSL load (and shared CI runners) can exceed that.
configure({ asyncUtilTimeout: 5000 });

const json = (status: number, data: unknown) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
type Call = { method: string; path: string; body: unknown; auth: string | null };

/** Records every request and answers from `routes` (first matching "METHOD path-suffix"). */
function mockFetch(routes: Record<string, (body: unknown) => Response>) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input);
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    const headers = (init?.headers ?? {}) as Record<string, string>;
    calls.push({ method, path, body, auth: headers.Authorization ?? null });
    const key = Object.keys(routes).find((k) => {
      const [m, suffix] = k.split(' ');
      return m === method && path.split('?')[0].endsWith(suffix);
    });
    return key ? routes[key](body) : json(404, { detail: `unexpected ${method} ${path} in test` });
  });
  return calls;
}

const renderEn = (ui: React.ReactElement) => render(<I18nProvider lang="en">{ui}</I18nProvider>);

beforeEach(() => {
  resetSessionCache();
  setSession({ access_token: 'synthetic-token', token_type: 'bearer', expires_at: new Date(Date.now() + 3600_000).toISOString(), user: USER });
});

afterEach(() => {
  cleanup();
  clearSession();
  resetSessionCache();
  vi.restoreAllMocks();
});

describe('Collaborators tab (ABB-25)', () => {
  it('lets the owner send a revocable invitation with a role, note and expiry', async () => {
    let invitations: InvitationView[] = [];
    const calls = mockFetch({
      [`GET /cases/${CASE_ID}`]: () => json(200, caseView('OWNER')),
      'GET /permissions': () => json(200, MEMBERS),
      'GET /invitations': () => json(200, { items: invitations }),
      'POST /invitations': (b) => { invitations = [invitation({ email: (b as { email: string }).email, role: 'REVIEWER', note: 'Synthetic note' })]; return json(201, invitations[0]); },
      'DELETE /invitations/inv-1': () => { invitations = [invitation({ status: 'REVOKED', revoked_at: '2026-01-03T00:00:00Z' })]; return new Response(null, { status: 204 }); },
      'GET /share-links': () => json(200, { items: [] }),
    });
    const user = userEvent.setup();
    renderEn(<CollaborationPanel caseId={CASE_ID} />);

    expect(await screen.findByText('Synthetic reviewer')).toBeTruthy();
    expect(screen.getByText('No e-mail is sent and addresses are not verified')).toBeTruthy();
    const form = screen.getByRole('heading', { name: 'Invitations' }).closest('section')!;
    await user.type(within(form).getByLabelText('Email'), 'guest@example.org');
    await user.selectOptions(within(form).getByLabelText('Role'), 'REVIEWER');
    await user.type(within(form).getByLabelText('Note for the person (optional)'), 'Synthetic note');
    await user.click(within(form).getByRole('button', { name: 'Send invitation' }));

    expect(await within(form).findByText('Invitation recorded for guest@example.org')).toBeTruthy();
    const post = calls.find((c) => c.method === 'POST' && c.path.endsWith('/invitations'))!;
    expect(post.body).toEqual({ email: 'guest@example.org', role: 'REVIEWER', note: 'Synthetic note', expires_in_days: 14 });
    expect(await within(form).findByText('Pending')).toBeTruthy();

    await user.click(within(form).getByRole('button', { name: 'Revoke invitation' }));
    expect(await within(form).findByText('Revoked')).toBeTruthy();
    expect(within(form).queryByRole('button', { name: 'Revoke invitation' })).toBeNull();
  });

  it('creates a share link only with explicit consent, sends every section choice and shows the link once', async () => {
    const created: ShareLinkCreated = {
      id: 'l1', case_id: CASE_ID, label: null, consent_statement: 'Synthetic consent statement.', status: 'ACTIVE', created_by: { id: 'u1', display_name: 'Synthetic owner' },
      created_at: '2026-01-02T00:00:00Z', expires_at: '2026-01-16T00:00:00Z', revoked_at: null, token: 'synthetic-token-abc', path: '/api/v1/shared/synthetic-token-abc',
      sections: { incident_notes: false, field_labels: false, location_detail: 'REGION', hypotheses: true, evidence_claims: false, conclusions: false, member_names: false, comments: false },
    };
    let links: unknown[] = [];
    const calls = mockFetch({
      [`GET /cases/${CASE_ID}`]: () => json(200, caseView('OWNER')),
      'GET /permissions': () => json(200, MEMBERS),
      'GET /invitations': () => json(200, { items: [] }),
      'GET /share-links': () => json(200, { items: links }),
      'POST /share-links': () => { const { token: _t, path: _p, ...view } = created; links = [view]; return json(201, created); },
    });
    const user = userEvent.setup();
    renderEn(<CollaborationPanel caseId={CASE_ID} />);
    const section = (await screen.findByRole('heading', { name: 'Share links' })).closest('section')!;
    await user.click(within(section).getByRole('button', { name: 'Create a share link' }));

    // Nothing is pre-selected.
    for (const box of within(section).getAllByRole('checkbox')) expect((box as HTMLInputElement).checked).toBe(false);
    await user.click(within(section).getByRole('checkbox', { name: /^Hypotheses/ }));
    await user.click(within(section).getByRole('radio', { name: /Region name only/ }));
    await user.click(within(section).getByRole('button', { name: 'Create link' }));
    expect(await within(section).findByText('Confirm your consent to create the link.')).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);

    await user.click(within(section).getByRole('checkbox', { name: /I agree that anyone holding this link/ }));
    await user.click(within(section).getByRole('button', { name: 'Create link' }));
    const linkBox = await within(section).findByLabelText('Share link');
    expect((linkBox as HTMLInputElement).value).toMatch(/#\/shared\/synthetic-token-abc$/);
    const post = calls.find((c) => c.method === 'POST')!;
    expect(post.body).toEqual({
      consent: true, label: null, expires_in_days: 14,
      sections: { incident_notes: false, field_labels: false, location_detail: 'REGION', hypotheses: true, evidence_claims: false, conclusions: false, member_names: false, comments: false },
    });
    expect(await within(section).findByText('Active')).toBeTruthy();
    await user.click(within(section).getByRole('button', { name: 'Hide link' }));
    expect(within(section).queryByLabelText('Share link')).toBeNull();
  });

  it('does not show or request owner-only invitations and links for a viewer', async () => {
    const calls = mockFetch({
      [`GET /cases/${CASE_ID}`]: () => json(200, caseView('VIEWER')),
      'GET /permissions': () => json(200, MEMBERS.map((m) => ({ ...m, email: null }))),
    });
    renderEn(<CollaborationPanel caseId={CASE_ID} />);
    expect(await screen.findByText('Invitations and share links are managed by the owner')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Send invitation' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Revoke/ })).toBeNull();
    expect(calls.some((c) => c.path.includes('/invitations') || c.path.includes('/share-links'))).toBe(false);
  });
});

describe('Discussion tab (ABB-25)', () => {
  it('renders comment text as text (no markup), posts, replies and records edits with the version', async () => {
    let comments: CommentView[] = [
      comment({ body: '<img src=x onerror="alert(1)"> <b>bold?</b>' }),
      comment({ id: 'c2', parent_id: 'c1', author: { id: 'u1', display_name: 'Synthetic owner' }, body: 'Synthetic reply.', can_edit: true, can_delete: true, version: 2, revision_count: 1, edited_at: '2026-01-02T12:00:00Z' }),
      comment({ id: 'c3', body: null, deleted: true, deleted_at: '2026-01-02T13:00:00Z', deleted_by: { id: 'u1', display_name: 'Synthetic owner' } }),
    ];
    const calls = mockFetch({
      [`GET /cases/${CASE_ID}`]: () => json(200, caseView('VIEWER')),
      'GET /comments': () => json(200, { items: comments, total: comments.length, limit: 200, offset: 0 }),
      'POST /comments': (b) => { const c = comment({ id: `c${comments.length + 1}`, body: (b as { body: string }).body }); comments = [...comments, c]; return json(201, c); },
      'PATCH /comments/c2': () => json(200, comments[1]),
      'GET /comments/c2/revisions': () => json(200, [{ revision: 1, body: 'Synthetic first text.', body_format: 'text/plain', replaced_at: '2026-01-02T12:00:00Z', edited_by: { id: 'u1', display_name: 'Synthetic owner' } }]),
      'GET /activity': () => json(200, EMPTY_ACTIVITY),
    });
    const user = userEvent.setup();
    const { container } = renderEn(<DiscussionPanel caseId={CASE_ID} />);

    expect(await screen.findByText('<img src=x onerror="alert(1)"> <b>bold?</b>')).toBeTruthy();
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('blockquote b')).toBeNull();
    expect(screen.getByText(/Comment deleted by Synthetic owner/)).toBeTruthy();

    // A viewer can comment (the Issue: "un invitado puede comentar").
    await user.type(screen.getByLabelText('Add a comment'), 'Synthetic new comment');
    await user.click(screen.getByRole('button', { name: 'Post comment' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true));
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ body: 'Synthetic new comment' });

    // Replies carry only parent_id (they inherit the target).
    const first = screen.getAllByRole('article', { name: 'Comment by Synthetic reviewer' })[0];
    await user.click(within(first).getByRole('button', { name: 'Reply' }));
    await user.type(within(first).getByLabelText('Reply to Synthetic reviewer'), 'Synthetic answer');
    await user.click(within(first).getByRole('button', { name: 'Send reply' }));
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST')).toHaveLength(2));
    expect(calls.filter((c) => c.method === 'POST')[1].body).toEqual({ body: 'Synthetic answer', parent_id: 'c1' });

    // The author edits with the version read; earlier text stays readable.
    const own = screen.getByRole('article', { name: 'Comment by Synthetic owner' });
    await user.click(within(own).getByRole('button', { name: 'Earlier versions (1)' }));
    expect(await within(own).findByText('Synthetic first text.')).toBeTruthy();
    await user.click(within(own).getByRole('button', { name: 'Edit' }));
    const box = within(own).getByLabelText(/Edit your comment/);
    await user.clear(box);
    await user.type(box, 'Synthetic corrected reply');
    await user.click(within(own).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true));
    expect(calls.find((c) => c.method === 'PATCH')!.body).toEqual({ version: 2, body: 'Synthetic corrected reply' });
  });

  it('shows the audit trail with author, translated action and the evidence recorded, and unknown actions by their code', async () => {
    const activity: ActivityPage = {
      ...EMPTY_ACTIVITY, total: 2,
      items: [
        { id: 'history:h1', source: 'CASE_HISTORY', kind: 'HYPOTHESIS_EVALUATED', category: 'REVIEW', actor: { id: 'u2', display_name: 'Synthetic reviewer' },
          created_at: '2026-01-02T09:00:00Z', target: { kind: 'HYPOTHESIS', id: 'h1' }, note: 'Synthetic evaluation note',
          evidence: { supporting_evidence_ids: ['a1'], missing_evidence: ['Soil moisture readings'] }, changes: null },
        { id: 'claim-event:e1', source: 'CLAIM_EVENT', kind: 'CLAIM_SYNTHETIC_ACTION', category: 'EVIDENCE', actor: null,
          created_at: '2026-01-01T09:00:00Z', target: { kind: 'CLAIM', id: 'k1' }, note: null, evidence: null, changes: null },
      ],
    };
    mockFetch({
      [`GET /cases/${CASE_ID}`]: () => json(200, caseView('REVIEWER')),
      'GET /comments': () => json(200, { items: [], total: 0, limit: 200, offset: 0 }),
      'GET /activity': () => json(200, activity),
    });
    const user = userEvent.setup();
    renderEn(<DiscussionPanel caseId={CASE_ID} />);
    const section = (await screen.findByRole('heading', { name: 'Activity' })).closest('section')!;
    expect(await within(section).findByText('evaluated a hypothesis')).toBeTruthy();
    expect(within(section).getByText('Synthetic reviewer')).toBeTruthy();
    expect(within(section).getByText('Synthetic evaluation note')).toBeTruthy();
    expect(within(section).getByText('CLAIM_SYNTHETIC_ACTION')).toBeTruthy();
    expect(within(section).getByText('Deleted account')).toBeTruthy();
    await user.click(within(section).getByText('Recorded evidence'));
    expect(within(section).getByText('["Soil moisture readings"]')).toBeTruthy();
  });

  it('replaces the composer with an explanation on an archived case', async () => {
    mockFetch({
      [`GET /cases/${CASE_ID}`]: () => json(200, caseView('EDITOR', true)),
      'GET /comments': () => json(200, { items: [], total: 0, limit: 200, offset: 0 }),
      'GET /activity': () => json(200, EMPTY_ACTIVITY),
    });
    renderEn(<DiscussionPanel caseId={CASE_ID} />);
    expect(await screen.findByText('This case is archived')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Post comment' })).toBeNull();
  });
});

describe('Collaboration page: invitations for me (ABB-25)', () => {
  const received: ReceivedInvitationView = {
    id: 'inv-9', case: { id: CASE_ID, title: 'Synthetic plot' }, role: 'REVIEWER', note: 'Synthetic note for the reviewer',
    invited_by: { id: 'u1', display_name: 'Synthetic owner' }, created_at: '2026-01-02T00:00:00Z', expires_at: '2026-01-16T00:00:00Z',
  };

  it('asks to sign in when signed out', () => {
    clearSession();
    renderEn(<Collaboration />);
    expect(screen.getByText('Sign in with the address you were invited with to see your invitations.')).toBeTruthy();
  });

  it('accepts an invitation and links to the case', async () => {
    const calls = mockFetch({
      'GET /api/v1/invitations': () => json(200, { items: [received] }),
      'POST /invitations/inv-9/accept': () => json(200, { invitation_id: 'inv-9', case_id: CASE_ID, status: 'ACCEPTED', role: 'REVIEWER' }),
    });
    const user = userEvent.setup();
    renderEn(<Collaboration />);
    expect(await screen.findByText(/Synthetic owner invites you as Reviewer/)).toBeTruthy();
    expect(screen.getByText('Synthetic note for the reviewer')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: 'Accept invitation' }));
    expect(await screen.findByText('You joined “Synthetic plot”')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open case' }).getAttribute('href')).toBe(`#/cases/${CASE_ID}`);
    expect(calls.find((c) => c.method === 'POST')!.path).toBe('/api/v1/invitations/inv-9/accept');
    expect(screen.getByText('No pending invitations')).toBeTruthy();
  });
});

describe('Shared view (ABB-25)', () => {
  const view: SharedCaseView = {
    kind: 'CROPSTORY_SHARED_CASE', generated_at: '2026-01-02T00:00:00Z', link_expires_at: '2026-01-16T00:00:00Z',
    sections: { incident_notes: false, field_labels: false, location_detail: 'APPROXIMATE', hypotheses: false, evidence_claims: false, conclusions: false, member_names: false, comments: true },
    case: { title: 'Synthetic plot', status: 'INVESTIGATING', incident_start: '2022-04-01', incident_end: null, crop_history: ['2021: Barley'], incident_notes: null, case_version: 3, updated_at: '2026-01-02T00:00:00Z' },
    fields: [{ label: 'Field 1', region_label: null, location_precision: 'APPROXIMATE', latitude: 41.65, longitude: -0.85, rounding_deg: 0.1 }],
    hypotheses: null, evidence_claims: null, conclusions: null,
    comments: [{ ref: 'C1', reply_to: null, author: 'Member 1', target_kind: 'CASE', body: '<script>alert(1)</script>', body_format: 'text/plain', created_at: '2026-01-02T00:00:00Z', edited: false }],
    limitations: ['Synthetic limitation.'],
  };

  it('renders only what was shared, without an account, with text-only comments', async () => {
    clearSession();
    const calls = mockFetch({ 'GET /api/v1/shared/tok-1': () => json(200, view) });
    const { container } = renderEn(<SharedCase token="tok-1" />);
    expect(await screen.findByRole('heading', { level: 1, name: 'Synthetic plot' })).toBeTruthy();
    expect(screen.getByText(/around 41\.65, -0\.85|around 41\.65, −0\.85/)).toBeTruthy();
    expect(screen.getAllByText('Not shared by the owner.')).toHaveLength(3);
    expect(screen.getByText('<script>alert(1)</script>')).toBeTruthy();
    expect(container.querySelector('script')).toBeNull();
    expect(calls[0].auth).toBeNull();
  });

  it('shows server pseudonyms and statuses in Spanish when the page is in Spanish', async () => {
    const withHypothesis: SharedCaseView = {
      ...view,
      sections: { ...view.sections, hypotheses: true },
      hypotheses: [{ title: 'Synthetic dry spring', statement: 'May have contributed.', status: 'OPEN', evaluation_note: null,
        supporting_evidence_count: 0, contradicting_evidence_count: 0, missing_evidence: [], limitations: [] }],
    };
    mockFetch({ 'GET /api/v1/shared/tok-es': () => json(200, withHypothesis) });
    render(<I18nProvider lang="es"><SharedCase token="tok-es" /></I18nProvider>);
    expect(await screen.findByText('Parcela 1')).toBeTruthy();
    expect(screen.getByText('Miembro 1')).toBeTruthy();
    expect(screen.getByText('abierta')).toBeTruthy();
    expect(screen.queryByText('Field 1')).toBeNull();
    expect(screen.queryByText('OPEN')).toBeNull();
  });

  it('says the link does not work for an unknown, expired or revoked token', async () => {
    mockFetch({ 'GET /api/v1/shared/gone': () => json(404, { detail: 'Not found.' }) });
    renderEn(<SharedCase token="gone" />);
    expect(await screen.findByText('This link does not work')).toBeTruthy();
  });
});
