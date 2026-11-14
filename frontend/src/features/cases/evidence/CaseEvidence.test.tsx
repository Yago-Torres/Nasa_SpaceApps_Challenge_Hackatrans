import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, configure, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { I18nProvider } from '../../../i18n/I18n';
import { clearSession, resetSessionCache, setSession } from '../../../api/session';
import type {
  ApplicabilityReport, CaseView, ClaimList, ClaimView, DisagreementList, EvidenceGraph, EvidenceTrace, GraphEdge, GraphNode, Role,
} from '../../../api/types';
import { CaseEvidence } from './CaseEvidence';

/* ── TEST-ONLY synthetic fixtures shaped like evidence_dto.py, comparability_dto.py and graph_dto.py.
 * Every DOI, title and id here is synthetic (10.5555 is the DOI test prefix). ── */

const CASE_ID = '11111111-1111-4111-8111-111111111111';
const USER = { id: 'u1', email: 'owner@example.org', display_name: 'Synthetic owner', created_at: '2026-01-01T00:00:00Z' };
const DOI_A = 'https://doi.org/10.5555/synthetic-a';

function caseView(role: Role): CaseView {
  return {
    schema_version: '1.0', id: CASE_ID, title: 'Synthetic plot', incident_start: '2022-04-01', incident_end: '2022-06-30',
    fields: [{ schema_version: '1.0', id: 'f1', label: 'North field', privacy_tier: 'APPROXIMATE', latitude: 41.6, longitude: -0.9, region_label: 'Synthetic region',
      area_hectares: null, limitations: [], location_precision: 'APPROXIMATE', rounding_deg: 0.1, precise_location_consent: false }],
    crop_history: [], incident_notes: '', visibility: 'PRIVATE', created_at: USER.created_at, updated_at: USER.created_at, version: 1,
    status: 'INVESTIGATING', archived_at: null, owner: { id: 'u1', display_name: 'Synthetic owner' }, my_role: role,
  };
}

function claim(id: string, reviewed: boolean, overrides: Partial<ClaimView> = {}): ClaimView {
  return {
    schema_version: '1.0', id, paper_id: `p-${id}`, source_kind: reviewed ? 'LITERATURE_REVIEWED' : 'LITERATURE_METADATA',
    claim_text: `Synthetic claim ${id}`, study_context: 'Synthetic field trial context.', review_status: reviewed ? 'ACCEPTED' : 'PENDING',
    reviewed_by: reviewed ? 'u2' : null, reviewed_at: reviewed ? '2026-01-03T00:00:00Z' : null, limitations: ['Synthetic limitation.'],
    case_id: CASE_ID, version: 1, is_reviewed: reviewed, reviewer: reviewed ? { id: 'u2', display_name: 'Synthetic reviewer' } : null,
    created_by: { id: 'u1', display_name: 'Synthetic owner' }, created_at: '2026-01-02T00:00:00Z', updated_at: '2026-01-02T00:00:00Z',
    paper: { id: `p-${id}`, title: `Synthetic paper ${id}`, year: 2020, doi: reviewed ? DOI_A : null, doi_id: reviewed ? '10.5555/synthetic-a' : null,
      doi_status: reviewed ? 'VERIFIED_CROSSREF' : 'NO_DOI', openalex_id: null, is_open_access: null, licenses: [], caveat: 'Bibliographic metadata only.' },
    study_design: 'FIELD_EXPERIMENT',
    context: { population: null, crops: ['wheat'], soils: [], region: null, climate: null, management: null, water_regime: 'RAINFED',
      soil_texture_classes: [], soil_ph_min: null, soil_ph_max: null, geographic_scope: 'NOT_REPORTED', countries: ['ES'], climate_classes: ['Csa'] },
    reported_outcome: { outcome: null, comparison: null, effect_as_stated: null, units_as_stated: null, uncertainty_as_stated: null, sample_as_stated: null },
    source_locator: { page: null, section: null, figure_or_table: null }, quoted_fragment: null,
    evidence_basis: reviewed ? 'FULL_TEXT' : 'METADATA_ONLY', access_basis: reviewed ? 'OPEN_ACCESS_LICENSE' : 'NONE', content_license: null,
    origin: 'MANUAL', origin_ref: null, intervention: null, comparator: null, outcome_variable: null, effect_direction: 'NOT_STATED',
    warnings: [], can_edit: false, can_review: false, ...overrides,
  };
}

const CLAIMS: ClaimList = { items: [claim('c1', true), claim('c2', false)], reviewed_count: 1, unreviewed_count: 1, limitations: ['Synthetic list limitation.'] };

function node(id: string, type: GraphNode['node_type'], kind: GraphNode['kind'], label: string, extra: Partial<GraphNode['provenance']> = {}, status: string | null = null): GraphNode {
  return {
    id, node_type: type, kind, label, entity_id: null, status, active: true, original_evidence: ['SOURCE_MANIFEST', 'FARMER_REPORT', 'PAPER'].includes(type),
    linkable: true, start: null, end: null, limitations: ['Synthetic node limitation.'], details: {},
    provenance: {
      source_kind: kind, description: `${label} provenance`, case_id: CASE_ID, case_version: 1, source_manifest_id: null, observation_id: null,
      anomaly_id: null, claim_id: null, paper_id: null, hypothesis_id: null, conclusion_id: null, field_id: null, field_label: null, region_label: null,
      provider: null, dataset: null, dataset_version: null, source_uri: null, retrieved_at: null, checksum_sha256: null, content_sha256: null,
      processing_version: null, revision: null, spatial_resolution: null, temporal_resolution: null, doi: null, doi_id: null, doi_status: null,
      openalex_id: null, origin: null, created_by: null, created_at: null, reviewed_by: null, reviewed_at: null, evaluated_by: null, evaluated_at: null, ...extra,
    },
  };
}
function edge(id: string, from: string, to: string, relation: GraphEdge['relation']): GraphEdge {
  return { id, from, to, relation, origin: 'STRUCTURAL', note: null, review_status: 'NOT_APPLICABLE', record_id: null, conclusion_id: null, version: null,
    author: null, created_at: null, reviewed_by: null, reviewed_at: null, review_note: null, can_edit: false, can_review: false };
}

const MANIFEST = node('manifest:m1', 'SOURCE_MANIFEST', 'OBSERVED', 'NASA POWER retrieval');
const OTHER = node('farmer:incident', 'FARMER_REPORT', 'FARMER_REPORTED', 'Reported incident');
const PAPER = node('paper:p1', 'PAPER', 'LITERATURE_METADATA', 'Synthetic paper c2', { doi: 'https://doi.org/10.5555/synthetic-b', doi_status: 'VERIFIED_CROSSREF' });
const CLAIM_NODE = node('claim:c2', 'EVIDENCE_CLAIM', 'LITERATURE_METADATA', 'Synthetic claim c2', { claim_id: 'c2' }, 'PENDING');
const HYP = node('hypothesis:h1', 'HYPOTHESIS', 'HYPOTHESIS', 'Water deficit', {}, 'OPEN');
const CONC = node('conclusion:k1', 'CONCLUSION', 'CONCLUSION', 'Synthetic conclusion', {}, 'PENDING');
const EDGES = [edge('e1', CLAIM_NODE.id, PAPER.id, 'CITES'), edge('e2', CLAIM_NODE.id, HYP.id, 'SUPPORTS'), edge('e3', HYP.id, CONC.id, 'SUPPORTS'), edge('e4', MANIFEST.id, HYP.id, 'SUPPORTS')];
const GRAPH: EvidenceGraph = {
  case_id: CASE_ID, case_version: 1, generated_at: USER.created_at, include_superseded: false, nodes: [MANIFEST, OTHER, PAPER, CLAIM_NODE, HYP, CONC], edges: EDGES,
  counts: { total_nodes: 6, total_edges: 4, nodes_by_kind: {}, nodes_by_type: {}, edges_by_relation: {}, edges_by_origin: {} },
  relations: [], orphan_references: [], limitations: ['Links do not establish causation.'],
};
const TRACE: EvidenceTrace = {
  case_id: CASE_ID, generated_at: USER.created_at, root: CONC, complete: false, original_evidence: [MANIFEST.id, PAPER.id], dead_ends: ['hypothesis:h1'],
  paths: [{ steps: [{ node_id: CONC.id, edge_id: null, relation: null }, { node_id: HYP.id, edge_id: 'e3', relation: 'SUPPORTS' }, { node_id: CLAIM_NODE.id, edge_id: 'e2', relation: 'SUPPORTS' }, { node_id: PAPER.id, edge_id: 'e1', relation: 'CITES' }], ends_at_original_evidence: true }],
  truncated: false, nodes: [CONC, HYP, CLAIM_NODE, PAPER, MANIFEST], edges: EDGES, limiting_edges: [], contradiction_edges: [],
  summary: { reaches_observed_data: true, reaches_farmer_report: false, reaches_literature: true, reviewed_claim_ids: [], unreviewed_claim_ids: [CLAIM_NODE.id],
    unevaluated_hypothesis_ids: [HYP.id], superseded_node_ids: [], missing_data_node_ids: [] },
  review_blockers: ['Synthetic blocker: literature claim not reviewed.'], limitations: [],
};
const DISAGREEMENTS: DisagreementList = {
  schema_version: '1.0', case_id: CASE_ID, method_version: 'synthetic', limitations: ['A candidate is not a contradiction.'], claims_not_compared: [],
  items: [{
    schema_version: '1.0', id: 'd1', case_id: CASE_ID, kind: 'OPPOSITE_DIRECTION', status: 'CANDIDATE', matched_on: { intervention: 'cover crop', outcome_variable: 'yield' },
    claim_a: { claim_id: 'c1', claim_version: 1, claim_text: 'Synthetic claim c1', intervention: 'cover crop', comparator: null, outcome_variable: 'yield', effect_direction: 'INCREASE',
      study_design: 'FIELD_EXPERIMENT', review_status: 'ACCEPTED', is_reviewed: true, source_kind: 'LITERATURE_REVIEWED', paper: claim('c1', true).paper },
    claim_b: { claim_id: 'c2', claim_version: 2, claim_text: 'Synthetic claim c2', intervention: 'cover crop', comparator: null, outcome_variable: 'yield', effect_direction: 'DECREASE',
      study_design: 'META_ANALYSIS', review_status: 'PENDING', is_reviewed: false, source_kind: 'LITERATURE_METADATA', paper: claim('c2', false).paper },
    both_claims_reviewed: false,
    comparability_notes: [{ dimension: 'WATER_REGIME', status: 'MISMATCH', claim_a_value: 'Rainfed', claim_b_value: 'Irrigated', reason: 'Synthetic: different water regimes.' }],
    current_review: null,
    reviews: [{ id: 'r1', decision: 'INCONCLUSIVE', note: 'Synthetic reviewer note on the pair.', reviewer: { id: 'u2', display_name: 'Synthetic reviewer' }, reviewed_at: '2026-01-03T00:00:00Z', claim_a_version: 1, claim_b_version: 1, applies_to_current_versions: false }],
    warnings: ['Synthetic warning.'], can_review: false,
  }],
};

// findBy*/waitFor default to 1 s; the full suite under WSL load (and shared CI runners) can exceed that.
configure({ asyncUtilTimeout: 5000 });

const json = (status: number, data: unknown) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
type Call = { method: string; path: string; body: unknown };
function mockFetch(routes: Record<string, (body: unknown) => Response>) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input);
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ method, path, body });
    const key = Object.keys(routes).find((k) => {
      const [m, suffix] = k.split(' ');
      return m === method && path.split('?')[0].endsWith(suffix);
    });
    return key ? routes[key](body) : json(404, { detail: `unexpected ${method} ${path} in test` });
  });
  return calls;
}
const base = (role: Role = 'OWNER') => ({
  [`GET /cases/${CASE_ID}`]: () => json(200, caseView(role)),
  'GET /claims': () => json(200, CLAIMS),
  'GET /claims/disagreements': () => json(200, DISAGREEMENTS),
  'GET /evidence-graph': () => json(200, GRAPH),
  [`GET /evidence-graph/trace/${encodeURIComponent(CONC.id)}`]: () => json(200, TRACE),
});
const renderTab = () => render(<I18nProvider lang="en"><CaseEvidence caseId={CASE_ID} /></I18nProvider>);

beforeEach(() => {
  resetSessionCache();
  setSession({ access_token: 'synthetic-token', token_type: 'bearer', expires_at: new Date(Date.now() + 3600_000).toISOString(), user: USER });
});
afterEach(() => { cleanup(); clearSession(); resetSessionCache(); vi.restoreAllMocks(); });

describe('Case evidence tab (ABB-23)', () => {
  it('marks not-reviewed claims unmistakably and keeps registered DOIs exactly as the backend sent them', async () => {
    mockFetch(base());
    const user = userEvent.setup();
    renderTab();
    const section = (await screen.findByRole('heading', { name: 'Studies in this case' })).closest('section')!;
    const reviewed = await within(section).findByRole('article', { name: 'Synthetic claim c1' });
    const pending = within(section).getByRole('article', { name: 'Synthetic claim c2' });
    expect(within(reviewed).getByText(/Reviewed literature · by Synthetic reviewer/)).toBeTruthy();
    expect(within(reviewed).queryByText(/Not reviewed/)).toBeNull();
    expect(within(pending).getByText('Not reviewed · pending review')).toBeTruthy();
    expect(within(pending).queryByText(/Reviewed literature/)).toBeNull();
    expect(within(section).getByText('1 not reviewed')).toBeTruthy();
    // DOI: the registered URL verbatim; no DOI means no link at all (never invented).
    expect(within(reviewed).getByRole('link', { name: /doi:10\.5555\/synthetic-a/ }).getAttribute('href')).toBe(DOI_A);
    expect(within(pending).getByText('No DOI registered')).toBeTruthy();
    expect(within(pending).queryByRole('link', { name: /doi/ })).toBeNull();
    // Filter shows only not-reviewed claims.
    await user.click(within(section).getByRole('button', { name: 'Not reviewed (1)' }));
    expect(within(section).queryByRole('article', { name: 'Synthetic claim c1' })).toBeNull();
    expect(within(section).getByRole('article', { name: 'Synthetic claim c2' })).toBeTruthy();
  });

  it('opens the evidence behind a conclusion: trace, original evidence with DOI, unreviewed literature and blockers', async () => {
    const calls = mockFetch(base());
    const user = userEvent.setup();
    const { container } = renderTab();
    const graph = (await screen.findByRole('heading', { name: 'Evidence graph' })).closest('section')!;
    await user.click(await within(graph).findByRole('button', { name: 'Open the evidence behind it' }));
    const detail = (await screen.findByRole('heading', { level: 2, name: 'Synthetic conclusion' })).closest('section')!;
    expect(await within(detail).findByText('The trace is incomplete')).toBeTruthy();
    expect(calls.some((c) => c.path.endsWith(`/evidence-graph/trace/${encodeURIComponent(CONC.id)}`))).toBe(true);
    expect(within(detail).getByText('Synthetic blocker: literature claim not reviewed.')).toBeTruthy();
    expect(within(detail).getByText('1 not reviewed')).toBeTruthy();
    expect(within(detail).getByRole('link', { name: /doi:10\.5555\/synthetic-b/ }).getAttribute('href')).toBe('https://doi.org/10.5555/synthetic-b');
    // Nodes outside the trace are dimmed; the unreviewed claim node is drawn as unreviewed.
    expect(container.querySelector('.eg-node.is-dim[aria-label^="Reported incident"]')).not.toBeNull();
    expect(container.querySelector('.eg-node.is-unreviewed[aria-label^="Synthetic claim c2"]')).not.toBeNull();
    // From the trace, the unreviewed study opens its card.
    await user.click(within(detail).getAllByRole('button', { name: 'Open study card' })[0]);
    await waitFor(() => expect(document.activeElement?.id).toBe('claim-c2'));
  });

  it('shows disagreements as candidates with the recorded differences and reviewer notes, stale ones marked', async () => {
    mockFetch(base('VIEWER'));
    renderTab();
    const section = (await screen.findByRole('heading', { name: 'Disagreements between studies' })).closest('section')!;
    expect(await within(section).findByText('Candidate, not confirmed')).toBeTruthy();
    expect(within(section).getByText('Synthetic: different water regimes.')).toBeTruthy();
    expect(within(section).getByText('Synthetic reviewer note on the pair.')).toBeTruthy();
    expect(within(section).getByText(/no longer applies/)).toBeTruthy();
    expect(within(section).getByText('Not reviewed · pending review')).toBeTruthy();
    // Viewers cannot add studies.
    expect(screen.queryByRole('button', { name: 'Add a study' })).toBeNull();
  });

  it('checks transferability with the optional country and climate, refusing an invalid country code', async () => {
    const report: ApplicabilityReport = {
      schema_version: '1.0', case_id: CASE_ID, claim_id: 'c1', claim_version: 1, claim_review_status: 'ACCEPTED', is_reviewed: true, study_design: 'FIELD_EXPERIMENT',
      paper: claim('c1', true).paper, transfer_status: 'DIFFERENCES_FOUND', differing_dimensions: ['CLIMATE'], unknown_dimensions: [], notes: ['Synthetic transfer note.'],
      stored: false, method_version: 'synthetic', limitations: ['No applicability score is computed.'],
      dimensions: [{ dimension: 'CLIMATE', status: 'MISMATCH', study_value: 'Csa', case_value: 'BSk', case_value_source: 'given in the request', reason: 'Synthetic: different climate.' }],
    };
    const calls = mockFetch({ ...base(), 'POST /claims/c1/applicability': () => json(200, report) });
    const user = userEvent.setup();
    renderTab();
    const card = await screen.findByRole('article', { name: 'Synthetic claim c1' });
    await user.click(within(card).getByRole('button', { name: 'Check transferability to this case' }));
    await user.type(within(card).getByLabelText('Country of the case'), 'E1');
    await user.click(within(card).getByRole('button', { name: 'Compare conditions' }));
    expect(within(card).getByText('Use a two-letter country code.')).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
    await user.clear(within(card).getByLabelText('Country of the case'));
    await user.type(within(card).getByLabelText('Country of the case'), 'es');
    await user.selectOptions(within(card).getByLabelText('Climate class (Köppen–Geiger)'), 'BSk');
    await user.click(within(card).getByRole('button', { name: 'Compare conditions' }));
    expect(await within(card).findByText('The study conditions differ from this case')).toBeTruthy();
    expect(within(card).getByText('Synthetic: different climate.')).toBeTruthy();
    expect(calls.find((c) => c.method === 'POST')!.body).toEqual({ country_code: 'ES', koppen_climate: 'BSk' });
  });

  it('adds a searched study by its DOI as a not-reviewed claim, validating before any request', async () => {
    let claims = CLAIMS;
    const calls = mockFetch({
      ...base('EDITOR'),
      'GET /claims': () => json(200, claims),
      'GET /api/literature': () => json(200, { results: [{ title: 'Synthetic search result', year: 2021, doi: 'https://doi.org/10.5555/found', openalex_id: 'https://openalex.org/W1', kind: 'literature', source: 'OpenAlex', caveat: 'Metadata only.', doi_status: 'VERIFIED_CROSSREF' }] }),
      'POST /api/v1/evidence/papers': () => json(201, { id: 'p-new', title: 'Synthetic search result' }),
      'POST /claims': (b) => { const created = claim('c3', false, { claim_text: (b as { claim_text: string }).claim_text }); claims = { ...claims, items: [...claims.items, created], unreviewed_count: 2 }; return json(201, created); },
    });
    const user = userEvent.setup();
    renderTab();
    const section = (await screen.findByRole('heading', { name: 'Studies in this case' })).closest('section')!;
    await user.click(await within(section).findByRole('button', { name: 'Add a study' }));
    await user.type(within(section).getByLabelText('Scientific question'), 'synthetic cover crop');
    await user.click(within(section).getByRole('button', { name: 'Search studies' }));
    await user.click(await within(section).findByRole('button', { name: 'Use this study' }));
    expect(within(section).getByText('It will be saved as not reviewed')).toBeTruthy();
    await user.click(within(section).getByRole('button', { name: 'Add study to case' }));
    expect(within(section).getByText('Write at least one limitation.')).toBeTruthy();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);

    await user.type(within(section).getByLabelText('Claim'), 'Synthetic claim to check');
    await user.type(within(section).getByLabelText('Study context'), 'Synthetic context');
    await user.type(within(section).getByLabelText('Limitations'), 'Only the title was read');
    await user.click(within(section).getByRole('button', { name: 'Add study to case' }));
    expect(await within(section).findByText('Added “Synthetic search result”')).toBeTruthy();
    expect(calls.find((c) => c.path.endsWith('/api/v1/evidence/papers'))!.body).toEqual({ doi: 'https://doi.org/10.5555/found' });
    expect(calls.find((c) => c.method === 'POST' && c.path.endsWith('/claims'))!.body).toEqual({
      paper_id: 'p-new', claim_text: 'Synthetic claim to check', study_context: 'Synthetic context', evidence_basis: 'METADATA_ONLY', access_basis: 'NONE',
      limitations: ['Only the title was read'],
    });
    expect(await within(section).findByRole('article', { name: 'Synthetic claim to check' })).toBeTruthy();
  });

  it('shows an honest error with retry when the graph cannot be loaded, never sample nodes', async () => {
    mockFetch({ ...base(), 'GET /evidence-graph': () => json(503, { detail: 'Storage unavailable.' }) });
    const { container } = renderTab();
    expect(await screen.findByText('The evidence graph could not be loaded')).toBeTruthy();
    expect(container.querySelector('.eg-node')).toBeNull();
  });
});
