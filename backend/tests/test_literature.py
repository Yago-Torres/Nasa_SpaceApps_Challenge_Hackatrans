"""ABB-13 literature tests. Fully offline: upstream APIs are simulated with httpx.MockTransport.

Fixture payloads are SYNTHETIC (shapes mirror OpenAlex/Crossref replies); the DOI
10.1038/s41467-022-32464-0 is real but its metadata here is only used as test data.
"""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from agroblackbox import app as app_module
from agroblackbox.services import literature as lit

REAL_DOI = '10.1038/s41467-022-32464-0'
TITLE = 'Global systematic review with meta-analysis reveals yield advantage of legume-based rotations and its drivers'


def oa_work(wid, title=TITLE, doi='https://doi.org/' + REAL_DOI, year=2022, license_='cc-by'):
    return {'id': f'https://openalex.org/{wid}', 'doi': doi, 'title': title, 'display_name': title,
            'publication_year': year, 'type': 'review',
            'authorships': [{'author': {'display_name': 'A. Researcher', 'orcid': None}}],
            'primary_location': {'license': license_, 'landing_page_url': 'https://example.org/landing',
                                 'source': {'display_name': 'Nature Communications'}},
            'open_access': {'is_oa': True}}


def crossref_message(doi=REAL_DOI, title=TITLE, year=2022):
    return {'status': 'ok', 'message': {
        'DOI': doi.upper(), 'title': [f'<i>{title}</i>'], 'container-title': ['Nature Communications'],
        'issued': {'date-parts': [[year, 8, 22]]}, 'type': 'journal-article',
        'author': [{'given': 'Ada', 'family': 'Researcher', 'ORCID': 'https://orcid.org/0000-0000-0000-0000'}],
        'license': [{'URL': 'https://creativecommons.org/licenses/by/4.0', 'content-version': 'vor'}]}}


class Upstream:
    """Routes simulated requests by host and records them."""

    def __init__(self, openalex, crossref=None):
        self.openalex, self.crossref, self.requests = openalex, crossref or {}, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == 'api.openalex.org':
            return self.openalex(request) if callable(self.openalex) else httpx.Response(200, json=self.openalex)
        if request.url.host == 'api.crossref.org':
            doi = request.url.path.removeprefix('/works/').lower()
            reply = self.crossref.get(doi, httpx.Response(404, text='Resource not found.'))
            if isinstance(reply, Exception):
                raise reply
            return reply
        raise AssertionError(f'unexpected host {request.url.host}')

    def hosts(self, host):
        return [r for r in self.requests if r.url.host == host]


def run_search(upstream, query='legume rotation yield'):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            return await lit.search_literature(query, client=client)
    return asyncio.run(go())


def openalex_payload(*works, count=None):
    return {'meta': {'count': count if count is not None else len(works)}, 'results': list(works)}


# ---------------------------------------------------------------- DOI normalization

@pytest.mark.parametrize('raw,expected', [
    ('https://doi.org/10.1038/S41467-022-32464-0', REAL_DOI),
    ('http://dx.doi.org/10.1038/s41467-022-32464-0', REAL_DOI),
    ('doi:10.1038/s41467-022-32464-0', REAL_DOI),
    ('  10.1038/s41467-022-32464-0 ', REAL_DOI),
    ('https://doi.org/not-a-doi', None),
    ('10.12/too-short-prefix', None),
    ('', None),
    (None, None),
    (12345, None),
])
def test_normalize_doi(raw, expected):
    assert lit.normalize_doi(raw) == expected


def test_titles_match_is_conservative():
    assert lit.titles_match('Crop rotations: a meta-analysis', 'CROP ROTATIONS — A META-ANALYSIS')
    assert lit.titles_match('Optimizing cover cropping application',
                            'Optimizing cover cropping application for sustainable crop production')
    assert not lit.titles_match('Cover crops and yield', 'Nitrogen leaching in maize')
    assert not lit.titles_match('Short', 'Short title with a completely different ending')
    assert not lit.titles_match(None, 'x')


# ---------------------------------------------------------------- search + verification

def test_verified_record_merges_crossref_and_keeps_provenance():
    upstream = Upstream(openalex_payload(oa_work('W1')),
                        {REAL_DOI: httpx.Response(200, json=crossref_message())})
    result = run_search(upstream)
    assert len(result.results) == 1
    paper = result.results[0]
    assert paper.doi_status == 'VERIFIED_CROSSREF'
    assert paper.doi_id == REAL_DOI
    assert paper.doi == 'https://doi.org/' + REAL_DOI       # backward-compatible link field
    assert paper.title == TITLE                              # JATS markup stripped
    assert paper.authors[0].name == 'Ada Researcher'         # Crossref authoritative when verified
    assert {lic.reported_by for lic in paper.licenses} == {'OpenAlex', 'Crossref'}
    assert paper.source_kind == 'LITERATURE_METADATA'
    assert paper.evidence_status == 'BIBLIOGRAPHIC_MATCH_ONLY'
    assert [r.source for r in paper.retrievals] == ['OpenAlex', 'Crossref']
    assert all(r.retrieved_at.tzinfo is not None for r in paper.retrievals)
    assert 'not been reviewed' in paper.caveat
    assert result.limitations and result.total_openalex_matches == 1


def test_missing_doi_is_never_invented_and_crossref_not_called():
    upstream = Upstream(openalex_payload(oa_work('W2', title='Rotational effects of legumes on maize', doi=None)))
    paper = run_search(upstream).results[0]
    assert paper.doi is None and paper.doi_id is None
    assert paper.doi_status == 'NO_DOI'
    assert upstream.hosts('api.crossref.org') == []


def test_malformed_doi_is_discarded_not_repaired():
    upstream = Upstream(openalex_payload(oa_work('W3', doi='https://doi.org/garbage')))
    paper = run_search(upstream).results[0]
    assert paper.doi is None and paper.doi_status == 'MALFORMED_DOI'
    assert paper.metadata_discrepancies
    assert upstream.hosts('api.crossref.org') == []


def test_duplicates_removed_by_doi_and_openalex_id():
    upstream = Upstream(
        openalex_payload(oa_work('W1'), oa_work('W9'),  # same DOI, different OpenAlex record
                         oa_work('W5', title='Other paper about rotations', doi=None),
                         oa_work('W5', title='Other paper about rotations', doi=None)),
        {REAL_DOI: httpx.Response(200, json=crossref_message())})
    result = run_search(upstream)
    assert len(result.results) == 2
    assert result.duplicates_removed == 2
    assert len(upstream.hosts('api.crossref.org')) == 1


def test_crossref_404_is_reported_not_verified():
    upstream = Upstream(openalex_payload(oa_work('W1')))  # Crossref default: 404
    paper = run_search(upstream).results[0]
    assert paper.doi_status == 'NOT_FOUND_IN_CROSSREF'
    assert 'NOT verified' in paper.caveat


def test_crossref_title_mismatch_requires_human_check():
    upstream = Upstream(openalex_payload(oa_work('W1')),
                        {REAL_DOI: httpx.Response(200, json=crossref_message(title='Nitrogen leaching under irrigated maize'))})
    paper = run_search(upstream).results[0]
    assert paper.doi_status == 'METADATA_MISMATCH'
    assert paper.title == TITLE  # not silently overwritten
    assert any('Title differs' in d for d in paper.metadata_discrepancies)


def test_crossref_year_discrepancy_is_recorded():
    upstream = Upstream(openalex_payload(oa_work('W1', year=2021)),
                        {REAL_DOI: httpx.Response(200, json=crossref_message(year=2022))})
    paper = run_search(upstream).results[0]
    assert paper.doi_status == 'VERIFIED_CROSSREF' and paper.year == 2022
    assert any('year differs' in d for d in paper.metadata_discrepancies)


@pytest.mark.parametrize('reply', [
    httpx.Response(429, text='slow down'),
    httpx.Response(500, text='boom'),
    httpx.Response(200, text='not json'),
    httpx.Response(200, json={'message': {'no': 'doi'}}),
    httpx.ConnectTimeout('timeout'),
])
def test_crossref_failure_degrades_to_unverified(reply):
    upstream = Upstream(openalex_payload(oa_work('W1')), {REAL_DOI: reply})
    paper = run_search(upstream).results[0]
    assert paper.doi_status == 'VERIFICATION_UNAVAILABLE'
    assert paper.retrievals[-1].source == 'Crossref'


def test_empty_search_returns_no_content():
    result = run_search(Upstream(openalex_payload()))
    assert result.results == []


@pytest.mark.parametrize('reply', [
    httpx.Response(429, text='rate limited'),
    httpx.Response(503, text='down'),
    httpx.Response(200, text='<html>not json</html>'),
    httpx.Response(200, json={'meta': {}}),
])
def test_openalex_failure_raises_without_fabricated_results(reply):
    with pytest.raises(lit.LiteratureSourceError):
        run_search(Upstream(lambda request: reply))


def test_openalex_network_error_raises():
    def boom(request):
        raise httpx.ConnectError('down', request=request)
    with pytest.raises(lit.LiteratureSourceError):
        run_search(Upstream(boom))


# ---------------------------------------------------------------- secrets / privacy

def test_secrets_never_leak_in_error_or_crossref_requests(monkeypatch):
    monkeypatch.setenv('OPENALEX_API_KEY', 'SECRET-TEST-KEY')
    upstream = Upstream(lambda request: httpx.Response(429))
    with pytest.raises(lit.LiteratureSourceError) as err:
        run_search(upstream)
    assert 'SECRET-TEST-KEY' not in err.value.public_message
    assert 'api.openalex.org' not in err.value.public_message
    assert upstream.requests[0].url.params['api_key'] == 'SECRET-TEST-KEY'  # sent upstream only


def test_crossref_request_carries_no_api_key_and_no_contact_by_default(monkeypatch):
    monkeypatch.setenv('OPENALEX_API_KEY', 'SECRET-TEST-KEY')
    monkeypatch.delenv('CROSSREF_MAILTO', raising=False)
    upstream = Upstream(openalex_payload(oa_work('W1')),
                        {REAL_DOI: httpx.Response(200, json=crossref_message())})
    paper = run_search(upstream).results[0]
    crossref_request = upstream.hosts('api.crossref.org')[0]
    assert 'api_key' not in str(crossref_request.url)
    assert 'mailto' not in lit._user_agent()
    assert all('SECRET' not in r.endpoint for r in paper.retrievals)


# ---------------------------------------------------------------- HTTP endpoint

def _patch_client(monkeypatch, upstream):
    monkeypatch.setattr(lit, '_make_client', lambda: httpx.AsyncClient(transport=httpx.MockTransport(upstream)))


def test_endpoint_502_hides_secret(monkeypatch):
    monkeypatch.setenv('OPENALEX_API_KEY', 'SECRET-TEST-KEY')
    _patch_client(monkeypatch, Upstream(lambda request: httpx.Response(429)))
    response = TestClient(app_module.app).get('/api/literature', params={'query': 'legume rotation'})
    assert response.status_code == 502
    assert 'SECRET-TEST-KEY' not in response.text
    assert 'rate limit' in response.json()['detail']


def test_endpoint_keeps_baseline_fields_and_adds_provenance(monkeypatch):
    _patch_client(monkeypatch, Upstream(openalex_payload(oa_work('W1')),
                                        {REAL_DOI: httpx.Response(200, json=crossref_message())}))
    response = TestClient(app_module.app).get('/api/literature', params={'query': 'legume rotation'})
    assert response.status_code == 200
    body = response.json()
    paper = body['results'][0]
    for field in ('title', 'year', 'doi', 'openalex_id', 'kind', 'source', 'caveat'):
        assert field in paper  # development-baseline contract used by frontend/report
    assert paper['doi'].startswith('https://doi.org/')
    assert paper['doi_status'] == 'VERIFIED_CROSSREF'
    assert body['source_kind'] == 'LITERATURE_METADATA'
    json.dumps(body)  # serializable for report payloads


def test_endpoint_validates_query_length():
    client = TestClient(app_module.app)
    assert client.get('/api/literature', params={'query': 'ab'}).status_code == 422
    assert client.get('/api/literature', params={'query': 'x' * 181}).status_code == 422
