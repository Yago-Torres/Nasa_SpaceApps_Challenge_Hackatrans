import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../../../i18n/I18n';
import { clearSession, resetSessionCache, setSession } from '../../../api/session';
import type { CaseView, EvidenceGraph, EvidenceTrace, GraphNode } from '../../../api/types';
import { CaseEvidenceGraph } from './CaseEvidenceGraph';

const CASE_ID = '11111111-1111-4111-8111-111111111111';
const USER = { id: 'u1', email: 'owner@example.org', display_name: 'Owner', created_at: '2026-01-01T00:00:00Z' };
const CASE_VIEW = {
  schema_version: '1.0', id: CASE_ID, title: 'Synthetic case', incident_start: '2026-01-01', incident_end: '2026-01-02',
  fields: [], crop_history: [], incident_notes: '', visibility: 'PRIVATE', created_at: USER.created_at,
  updated_at: USER.created_at, version: 1, status: 'INVESTIGATING', archived_at: null,
  owner: { id: 'u1', display_name: 'Owner' }, my_role: 'OWNER',
} as CaseView;

function node(id: string, kind: GraphNode['kind'], label: string, doi: string | null = null): GraphNode {
  return { id, node_type: kind, kind, label, status: null, active: true, original_evidence: true, linkable: true,
    provenance: { source_kind: kind, description: `${label} provenance`, provider: null, dataset: null,
      source_uri: null, retrieved_at: null, processing_version: null, doi, doi_id: null, doi_status: null,
      openalex_id: null, reviewed_by: null, reviewed_at: null },
    limitations: ['Synthetic test limitation.'], details: {} };
}

const PAPER = node('paper:22222222-2222-4222-8222-222222222222', 'LITERATURE_METADATA', 'Metadata paper', 'https://doi.org/10.1000/example');
const CONCLUSION = node('conclusion:33333333-3333-4333-8333-333333333333', 'CONCLUSION', 'Human conclusion');
const GRAPH: EvidenceGraph = { case_id: CASE_ID, generated_at: USER.created_at, nodes: [PAPER, CONCLUSION],
  edges: [{ id: 'e1', from: PAPER.id, to: CONCLUSION.id, relation: 'SUPPORTS', origin: 'MANUAL', note: null, review_status: 'PENDING' }],
  counts: { total_nodes: 2, total_edges: 1, nodes_by_kind: {} }, orphan_references: [],
  limitations: ['Relationships do not establish causation.'] };
const TRACE: EvidenceTrace = { root: CONCLUSION, complete: false, original_evidence: [PAPER.id], dead_ends: [],
  nodes: [PAPER, CONCLUSION], edges: GRAPH.edges, limiting_edges: [], contradiction_edges: [],
  review_blockers: ['The literature claim is not reviewed.'], limitations: [] };
const json = (status: number, value: unknown) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  resetSessionCache();
  setSession({ access_token: 'synthetic-token', token_type: 'bearer', expires_at: new Date(Date.now() + 3600_000).toISOString(), user: USER });
});
afterEach(() => { cleanup(); clearSession(); resetSessionCache(); vi.restoreAllMocks(); });

describe('CaseEvidenceGraph (ABB-23)', () => {
  it('keeps metadata-only literature distinct and preserves the registered DOI URL', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith(`/api/v1/cases/${CASE_ID}`)) return json(200, CASE_VIEW);
      if (path.endsWith('/evidence-graph')) return json(200, GRAPH);
      if (path.includes('/evidence-graph/trace/')) return json(200, TRACE);
      return json(404, { detail: 'unexpected test path' });
    });
    const user = userEvent.setup();
    render(<I18nProvider lang="en"><CaseEvidenceGraph caseId={CASE_ID} /></I18nProvider>);
    const table = await screen.findByRole('table');
    expect(within(table).getByText('Metadata only')).toBeTruthy();
    await user.click(within(table).getByRole('button', { name: 'Metadata paper' }));
    expect((await screen.findByRole('link', { name: 'https://doi.org/10.1000/example' })).getAttribute('href')).toBe('https://doi.org/10.1000/example');
  });

  it('opens a conclusion trace and exposes incomplete review blockers', async () => {
    let traceRequest = '';
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith(`/api/v1/cases/${CASE_ID}`)) return json(200, CASE_VIEW);
      if (path.endsWith('/evidence-graph')) return json(200, GRAPH);
      if (path.includes('/evidence-graph/trace/')) { traceRequest = path; return json(200, TRACE); }
      return json(404, { detail: 'unexpected test path' });
    });
    const user = userEvent.setup();
    render(<I18nProvider lang="en"><CaseEvidenceGraph caseId={CASE_ID} /></I18nProvider>);
    const table = await screen.findByRole('table');
    await user.click(within(table).getByRole('button', { name: 'Human conclusion' }));
    expect(await screen.findByText('Trace is incomplete')).toBeTruthy();
    expect(screen.getByText('The literature claim is not reviewed.')).toBeTruthy();
    expect(traceRequest).toContain('conclusion%3A33333333-3333-4333-8333-333333333333');
  });
});
