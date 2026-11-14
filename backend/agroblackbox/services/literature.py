"""Scholarly metadata discovery (OpenAlex) and DOI verification (Crossref) — ABB-13.

Scope: bibliographic identity only. Every record produced here is
``LITERATURE_METADATA`` (see docs/science/SCIENTIFIC_POLICY.md): it shows that a
work with this metadata exists, NOT that it supports any agricultural claim.
Findings, study context and transferability belong to human review (ABB-14).

Rules enforced in code:
- A DOI is only reported when the upstream source supplied a syntactically valid
  one; none is ever inferred or constructed from a title.
- Crossref is queried per DOI; its absence/outage is reported as a status, never
  hidden and never turned into "verified".
- Upstream failures raise ``LiteratureSourceError`` with a public message that
  never contains request URLs, API keys or contact addresses.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import math
import os
import re
import unicodedata
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from ..resilience import diskcache
from ..resilience.tasks import TaskRegistry

OPENALEX_WORKS_URL = 'https://api.openalex.org/works'
CROSSREF_WORKS_URL = 'https://api.crossref.org/works/'
DOI_RESOLVER = 'https://doi.org/'
PROCESSING_VERSION = 'abb13-literature-0.1.0'
PROJECT_URL = 'https://github.com/Yago-Torres/Nasa_SpaceApps_Challenge_Hackatrans'
MAX_RESULTS = 6
CROSSREF_CONCURRENCY = 3
REQUEST_TIMEOUT = httpx.Timeout(20.0)
OPENALEX_SELECT = 'id,doi,title,display_name,publication_year,authorships,primary_location,open_access,type'

# ---------------------------------------------------------------- ABB-27 resilience
#
# Upstream quota/etiquette, as documented 2026-11-14 (no fabricated numbers; a source
# page that did not publish a figure is noted as such rather than guessed):
# - OpenAlex (https://help.openalex.org/how-to-use-the-api/rate-limits-and-authentication):
#   10 requests/second without an API key (30/s with a free key, 50/s on an annual
#   plan); a documented, dollar-denominated daily budget rather than a fixed request
#   count. We stay well under this with a per-process registry (one logical search in
#   flight at a time per query) plus a cache that avoids re-asking for the same query.
# - Crossref (https://www.crossref.org/documentation/retrieve-metadata/rest-api/ and
#   its "tips for using the REST API" page): no fixed numeric limit is published;
#   Crossref instead asks callers to "use the REST API responsibly", to back off on
#   HTTP 429, and recommends a "polite pool" via a `mailto` parameter/User-Agent
#   (already supported here through CROSSREF_MAILTO) and explicitly recommends
#   caching results and avoiding redundant requests, which this cache implements.
#
# A bounded retry with backoff (mirrors services.power's MAX_ATTEMPTS/BACKOFF_SECONDS)
# covers OpenAlex timeouts/network errors/HTTP 429/5xx; Crossref per-DOI verification
# keeps its existing fast degrade-to-VERIFICATION_UNAVAILABLE behavior (ABB-13), since
# that is a best-effort enrichment already covered by the DOI-status contract and is
# re-attempted on the caller's next, separately cached search.
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)  # wait before attempt 2 and attempt 3
MAX_RETRY_AFTER_SECONDS = 10.0
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# On-disk TTL cache for whole search results, keyed by the normalized query. Chosen
# conservatively short relative to NASA POWER's 24h (climate observations are static;
# OpenAlex indexes new/updated works continuously), to avoid redundant downloads for
# repeated identical searches within a session without serving stale bibliographic
# matches for too long. Revisit alongside a future ABB-13 review.
#
# lookup_paper (below) deliberately gets in-flight deduplication only, NOT this kind
# of disk cache: a degraded Crossref verification (VERIFICATION_UNAVAILABLE) is a
# valid, non-fabricated PaperRecord, and caching it would make that degraded status
# artificially sticky for WORK_CACHE_TTL_SECONDS. api/evidence.py already owns a
# DB-backed re-verification/staleness policy for registered papers (``_refreshable``,
# ABB-14) that depends on being able to ask again immediately; a second, independent
# cache underneath it would silently fight that policy (caught by
# test_evidence_claims.py::test_unverified_paper_is_reverified_on_next_registration
# while building this).
SEARCH_CACHE = Path(__file__).resolve().parents[2] / '.cache' / 'literature' / 'search'
SEARCH_CACHE_TTL_SECONDS = 3600


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get('Retry-After')
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None  # HTTP-date form not supported; fall back to our own backoff
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


class _RetryableOpenAlexError(Exception):
    """Internal: an OpenAlex failure worth a bounded retry (timeout, network error,
    429, 5xx). Carries the ``LiteratureSourceError`` to raise if retries are exhausted."""

    def __init__(self, public: 'LiteratureSourceError', *, retry_after: float | None = None):
        super().__init__(public.public_message)
        self.public = public
        self.retry_after = retry_after


# Dedup only (max_attempts=1): the retry loop above already runs inside each factory
# passed to these registries, exactly like services.power.
_SEARCH_REGISTRY: TaskRegistry[Any] = TaskRegistry(name='OpenAlex search', max_attempts=1)
_WORK_REGISTRY: TaskRegistry[Any] = TaskRegistry(name='OpenAlex/Crossref lookup', max_attempts=1)

_DOI_RE = re.compile(r'^10\.\d{4,9}/\S+$')
_DOI_PREFIX_RE = re.compile(r'^(?:https?://)?(?:dx\.)?doi\.org/|^doi:\s*', re.IGNORECASE)
_TAG_RE = re.compile(r'<[^>]+>')

DoiStatus = Literal[
    'VERIFIED_CROSSREF',        # DOI registered in Crossref and titles agree
    'METADATA_MISMATCH',        # DOI registered in Crossref but metadata disagrees: human check
    'NOT_FOUND_IN_CROSSREF',    # Crossref 404: other agency (e.g. DataCite) or wrong DOI
    'VERIFICATION_UNAVAILABLE', # Crossref unreachable / rate limited / invalid reply
    'MALFORMED_DOI',            # source gave a DOI value that is not a valid DOI
    'NO_DOI',                   # source gave no DOI; none inferred
]

_CAVEATS: dict[str, str] = {
    'VERIFIED_CROSSREF': 'DOI registered in Crossref and title matches. Bibliographic identity only; '
                         "the paper's findings and local applicability have not been reviewed.",
    'METADATA_MISMATCH': 'DOI is registered in Crossref but its metadata does not match the search record. '
                         'Do not cite until a person checks which work is meant.',
    'NOT_FOUND_IN_CROSSREF': 'Crossref has no record for this DOI. It may be registered with another agency '
                             '(e.g. DataCite) or be incorrect; it is NOT verified.',
    'VERIFICATION_UNAVAILABLE': 'Crossref could not be consulted in this request; the DOI is NOT verified.',
    'MALFORMED_DOI': 'The source supplied a malformed DOI value; it was discarded and none was inferred.',
    'NO_DOI': 'The source supplies no DOI and none was inferred. Identify the work by its OpenAlex ID.',
}

SEARCH_LIMITATIONS = [
    'Results are bibliographic matches ranked by OpenAlex relevance, which may include full-text matches; '
    'relevance is not evidence of support for any claim.',
    'No abstract or full text is interpreted. Findings, study context and transferability require human review.',
    'DOI verification checks Crossref only; DOIs from other registration agencies are reported as not found.',
    'A small fixed number of results is returned; absence of a paper here is not absence of literature.',
]


class LiteratureSourceError(Exception):
    """Upstream literature source failed. ``public_message`` is safe to show to clients."""

    def __init__(self, public_message: str):
        super().__init__(public_message)
        self.public_message = public_message


class Author(BaseModel):
    name: str
    orcid: str | None = None


class LicenseInfo(BaseModel):
    value: str
    reported_by: Literal['OpenAlex', 'Crossref']
    content_version: str | None = None


class SourceRetrieval(BaseModel):
    """Provenance of one upstream request. Never contains credentials or contact data."""
    source: Literal['OpenAlex', 'Crossref']
    endpoint: str
    record_id: str | None = None
    retrieved_at: datetime
    http_status: int | None = None
    outcome: str


class PaperRecord(BaseModel):
    # Fields kept from the development-baseline contract (frontend uses `doi` as a link).
    title: str
    year: int | None = None
    doi: str | None = Field(default=None, description='Resolvable https://doi.org/ URL, only if a valid DOI was supplied by a source.')
    openalex_id: str | None = None
    kind: Literal['literature'] = 'literature'
    source: str = 'OpenAlex metadata'
    caveat: str
    # ABB-13 additions.
    source_kind: Literal['LITERATURE_METADATA'] = 'LITERATURE_METADATA'
    evidence_status: Literal['BIBLIOGRAPHIC_MATCH_ONLY'] = 'BIBLIOGRAPHIC_MATCH_ONLY'
    doi_id: str | None = Field(default=None, description='Normalized lowercase DOI, e.g. 10.1038/xyz.')
    doi_status: DoiStatus
    authors: list[Author] = Field(default_factory=list)
    venue: str | None = None
    publication_type: str | None = None
    licenses: list[LicenseInfo] = Field(default_factory=list, description='As reported by sources; empty means unknown, not unrestricted.')
    landing_page_url: str | None = None
    is_open_access: bool | None = None
    metadata_discrepancies: list[str] = Field(default_factory=list)
    retrievals: list[SourceRetrieval]
    processing_version: str = PROCESSING_VERSION


class DoiVerification(BaseModel):
    doi_id: str
    status: Literal['VERIFIED_CROSSREF', 'NOT_FOUND_IN_CROSSREF', 'VERIFICATION_UNAVAILABLE']
    retrieval: SourceRetrieval
    crossref_doi: str | None = None
    title: str | None = None
    year: int | None = None
    venue: str | None = None
    authors: list[Author] = Field(default_factory=list)
    licenses: list[LicenseInfo] = Field(default_factory=list)
    publication_type: str | None = None


class LiteratureSearchResult(BaseModel):
    query: str
    results: list[PaperRecord]
    source_kind: Literal['LITERATURE_METADATA'] = 'LITERATURE_METADATA'
    retrieved_at: datetime
    providers: list[str] = Field(default_factory=lambda: ['OpenAlex', 'Crossref'])
    total_openalex_matches: int | None = None
    duplicates_removed: int = 0
    limitations: list[str] = Field(default_factory=lambda: list(SEARCH_LIMITATIONS))
    processing_version: str = PROCESSING_VERSION


# ---------------------------------------------------------------- helpers

def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_doi(raw: Any) -> str | None:
    """Return a lowercase bare DOI (``10.xxxx/...``) or None if ``raw`` is not a valid DOI."""
    if not isinstance(raw, str):
        return None
    value = _DOI_PREFIX_RE.sub('', raw.strip()).strip().lower()
    return value if _DOI_RE.match(value) else None


def doi_url(doi_id: str) -> str:
    return DOI_RESOLVER + quote(doi_id, safe="/:;()._-~")


def clean_text(value: Any) -> str | None:
    """Strip markup/entities and collapse whitespace (Crossref titles may contain JATS tags)."""
    if not isinstance(value, str):
        return None
    text = ' '.join(html.unescape(_TAG_RE.sub('', value)).split())
    return text or None


def _title_key(title: str) -> str:
    text = unicodedata.normalize('NFKD', title).casefold()
    return re.sub(r'[^0-9a-z]+', '', ''.join(c for c in text if not unicodedata.combining(c)))


def titles_match(a: str | None, b: str | None) -> bool:
    """Conservative: equal after normalization, or one is a prefix of the other (subtitle omitted)."""
    if not a or not b:
        return False
    ka, kb = _title_key(a), _title_key(b)
    if not ka or not kb:
        return False
    short, long_ = sorted((ka, kb), key=len)
    return ka == kb or (len(short) >= 20 and long_.startswith(short))


def _user_agent() -> str:
    mailto = os.getenv('CROSSREF_MAILTO', '').strip()
    contact = f'; mailto:{mailto}' if mailto else ''
    return f'CropStory/{PROCESSING_VERSION} (+{PROJECT_URL}{contact})'


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True,
                             headers={'User-Agent': _user_agent()})


def _first(seq: Any) -> Any:
    return seq[0] if isinstance(seq, list) and seq else None


# ---------------------------------------------------------------- Crossref

def _crossref_year(message: dict) -> int | None:
    for key in ('issued', 'published', 'published-print', 'published-online'):
        parts = (message.get(key) or {}).get('date-parts')
        year = _first(_first(parts))
        if isinstance(year, int):
            return year
    return None


def _crossref_authors(message: dict) -> list[Author]:
    authors = []
    for a in message.get('author') or []:
        name = clean_text(' '.join(p for p in (a.get('given'), a.get('family')) if isinstance(p, str))) \
            or clean_text(a.get('name'))
        if name:
            authors.append(Author(name=name, orcid=a.get('ORCID') if isinstance(a.get('ORCID'), str) else None))
    return authors


async def verify_doi(doi: str, client: httpx.AsyncClient | None = None) -> DoiVerification:
    """Look up one DOI in Crossref. Never raises for upstream failures; reports a status instead."""
    doi_id = normalize_doi(doi)
    if doi_id is None:
        raise ValueError('Not a valid DOI')
    endpoint = CROSSREF_WORKS_URL + quote(doi_id, safe='/')
    own_client = client is None
    client = client or _make_client()
    status_code: int | None = None
    try:
        response = await client.get(endpoint)
        status_code = response.status_code
        if status_code == 404:
            return DoiVerification(doi_id=doi_id, status='NOT_FOUND_IN_CROSSREF',
                                   retrieval=_retrieval('Crossref', endpoint, doi_id, 404, 'not_found'))
        if status_code == 429:
            return DoiVerification(doi_id=doi_id, status='VERIFICATION_UNAVAILABLE',
                                   retrieval=_retrieval('Crossref', endpoint, doi_id, 429, 'rate_limited'))
        response.raise_for_status()
        message = response.json().get('message')
        if not isinstance(message, dict) or not isinstance(message.get('DOI'), str):
            raise ValueError('unexpected Crossref payload')
    except (httpx.HTTPError, ValueError):
        return DoiVerification(doi_id=doi_id, status='VERIFICATION_UNAVAILABLE',
                               retrieval=_retrieval('Crossref', endpoint, doi_id, status_code, 'error'))
    finally:
        if own_client:
            await client.aclose()
    licenses = [LicenseInfo(value=lic['URL'], reported_by='Crossref', content_version=lic.get('content-version'))
                for lic in message.get('license') or [] if isinstance(lic, dict) and isinstance(lic.get('URL'), str)]
    return DoiVerification(
        doi_id=doi_id, status='VERIFIED_CROSSREF',
        retrieval=_retrieval('Crossref', endpoint, doi_id, status_code, 'found'),
        crossref_doi=message['DOI'].lower(),
        title=clean_text(_first(message.get('title'))),
        year=_crossref_year(message),
        venue=clean_text(_first(message.get('container-title'))),
        authors=_crossref_authors(message),
        licenses=licenses,
        publication_type=message.get('type') if isinstance(message.get('type'), str) else None,
    )


def _retrieval(source, endpoint, record_id, status, outcome) -> SourceRetrieval:
    return SourceRetrieval(source=source, endpoint=endpoint, record_id=record_id,
                           retrieved_at=_now(), http_status=status, outcome=outcome)


# ---------------------------------------------------------------- OpenAlex

async def _openalex_search_once(query: str, client: httpx.AsyncClient) -> tuple[list[dict], int | None, SourceRetrieval]:
    """One OpenAlex attempt. Raises ``_RetryableOpenAlexError`` for timeout/network/429/5xx
    (ABB-27: the caller retries those with bounded backoff); any other failure (bad
    payload shape, a non-429 4xx) is permanent and raised directly."""
    params: dict[str, Any] = {'search': query, 'per_page': MAX_RESULTS, 'select': OPENALEX_SELECT}
    api_key = os.getenv('OPENALEX_API_KEY', '').strip()
    if api_key:
        params['api_key'] = api_key
    try:
        response = await client.get(OPENALEX_WORKS_URL, params=params)
    except httpx.TimeoutException as e:
        raise _RetryableOpenAlexError(
            LiteratureSourceError('OpenAlex source unavailable: request timed out.')) from e
    except httpx.HTTPError as e:
        raise _RetryableOpenAlexError(
            LiteratureSourceError('OpenAlex source unavailable: network error.')) from e
    if response.status_code == 429:
        error = LiteratureSourceError('OpenAlex source unavailable: rate limit reached, retry later.')
        delay = _retry_after(response)
        if delay is not None and delay > MAX_RETRY_AFTER_SECONDS:
            raise error  # respect the server: never retry earlier than it asked
        raise _RetryableOpenAlexError(error, retry_after=delay)
    if response.status_code in RETRYABLE_STATUS:  # 5xx (429 already handled above)
        raise _RetryableOpenAlexError(
            LiteratureSourceError(f'OpenAlex source unavailable: HTTP {response.status_code}.'))
    if response.status_code >= 400:
        raise LiteratureSourceError(f'OpenAlex source unavailable: HTTP {response.status_code}.')
    try:
        payload = response.json()
        works = payload['results']
        if not isinstance(works, list):
            raise ValueError
    except (ValueError, KeyError, TypeError) as e:
        raise LiteratureSourceError('OpenAlex source returned an unexpected response.') from e
    count = (payload.get('meta') or {}).get('count')
    retrieval = _retrieval('OpenAlex', OPENALEX_WORKS_URL, None, response.status_code, f'{len(works)} works')
    return [w for w in works if isinstance(w, dict)], count if isinstance(count, int) else None, retrieval


async def _openalex_search(query: str, client: httpx.AsyncClient) -> tuple[list[dict], int | None, SourceRetrieval]:
    """OpenAlex search with bounded retry and backoff (ABB-27), mirroring
    ``services.power``'s MAX_ATTEMPTS/BACKOFF_SECONDS pattern including honouring a
    short ``Retry-After`` on HTTP 429."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await _openalex_search_once(query, client)
        except _RetryableOpenAlexError as e:
            if attempt == MAX_ATTEMPTS:
                raise e.public from e
            delay = e.retry_after if e.retry_after is not None else BACKOFF_SECONDS[attempt - 1]
            await _sleep(delay)
    raise AssertionError('unreachable')  # pragma: no cover


def _openalex_authors(work: dict) -> list[Author]:
    authors = []
    for authorship in work.get('authorships') or []:
        author = (authorship or {}).get('author') or {}
        name = clean_text(author.get('display_name'))
        if name:
            authors.append(Author(name=name, orcid=author.get('orcid') if isinstance(author.get('orcid'), str) else None))
    return authors


def _base_record(work: dict, search_retrieval: SourceRetrieval) -> dict | None:
    title = clean_text(work.get('title')) or clean_text(work.get('display_name'))
    if not title:
        return None
    location = work.get('primary_location') or {}
    venue = clean_text((location.get('source') or {}).get('display_name'))
    raw_doi = work.get('doi')
    doi_id = normalize_doi(raw_doi)
    discrepancies = []
    if raw_doi and doi_id is None:
        doi_status = 'MALFORMED_DOI'
        discrepancies.append('OpenAlex DOI value is malformed and was discarded.')
    else:
        doi_status = 'NO_DOI' if doi_id is None else 'VERIFICATION_UNAVAILABLE'
    licenses = [LicenseInfo(value=location['license'], reported_by='OpenAlex')] \
        if isinstance(location.get('license'), str) else []
    year = work.get('publication_year')
    openalex_id = work.get('id') if isinstance(work.get('id'), str) else None
    return {
        'title': title, 'year': year if isinstance(year, int) else None,
        'doi_id': doi_id, 'doi': doi_url(doi_id) if doi_id else None, 'doi_status': doi_status,
        'openalex_id': openalex_id,
        'authors': _openalex_authors(work), 'venue': venue,
        'publication_type': work.get('type') if isinstance(work.get('type'), str) else None,
        'licenses': licenses,
        'landing_page_url': location.get('landing_page_url') if isinstance(location.get('landing_page_url'), str) else None,
        'is_open_access': (work.get('open_access') or {}).get('is_oa'),
        'metadata_discrepancies': discrepancies,
        'retrievals': [search_retrieval.model_copy(update={'record_id': openalex_id})],
    }


def _merge_crossref(record: dict, check: DoiVerification) -> dict:
    record['retrievals'].append(check.retrieval)
    if check.status != 'VERIFIED_CROSSREF':
        record['doi_status'] = check.status
        return record
    record['source'] = 'OpenAlex metadata; DOI checked in Crossref'
    discrepancies = record['metadata_discrepancies']
    if check.crossref_doi and check.crossref_doi != record['doi_id']:
        discrepancies.append(f'Crossref canonical DOI is {check.crossref_doi}.')
    if not titles_match(record['title'], check.title):
        record['doi_status'] = 'METADATA_MISMATCH'
        discrepancies.append(f'Title differs: OpenAlex "{record["title"]}" vs Crossref "{check.title}".')
        return record  # keep OpenAlex fields; a person must decide which work is meant
    record['doi_status'] = 'VERIFIED_CROSSREF'
    # Crossref is the DOI registration record: authoritative for identity metadata.
    if check.year is not None and record['year'] is not None and check.year != record['year']:
        discrepancies.append(f'Publication year differs: OpenAlex {record["year"]}, Crossref {check.year} (issued).')
    record['title'] = check.title or record['title']
    record['year'] = check.year if check.year is not None else record['year']
    record['venue'] = check.venue or record['venue']
    record['authors'] = check.authors or record['authors']
    record['publication_type'] = check.publication_type or record['publication_type']
    record['licenses'] = record['licenses'] + check.licenses
    return record


# ---------------------------------------------------------------- public API

def _search_cache_key(query: str) -> str:
    return diskcache.cache_key({'resource': 'openalex_search', 'query': ' '.join(query.split()).casefold()})


async def _search_literature_uncached(query: str, client: httpx.AsyncClient | None) -> LiteratureSearchResult:
    """Actually call OpenAlex and verify each DOI in Crossref. Only the caller that wins
    the ``_SEARCH_REGISTRY`` dedup race for this (normalized) query runs this; concurrent
    identical searches share its result instead of each calling OpenAlex (ABB-27)."""
    own_client = client is None
    client = client or _make_client()
    try:
        works, total, search_retrieval = await _openalex_search(query, client)
        records, seen, duplicates = [], set(), 0
        for work in works:
            record = _base_record(work, search_retrieval)
            if record is None:
                continue
            key = record['doi_id'] or record['openalex_id'] or _title_key(record['title'])
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            records.append(record)

        semaphore = asyncio.Semaphore(CROSSREF_CONCURRENCY)

        async def check(record: dict) -> dict:
            if record['doi_id'] is None:
                return record
            async with semaphore:
                return _merge_crossref(record, await verify_doi(record['doi_id'], client))

        records = await asyncio.gather(*(check(r) for r in records))
    finally:
        if own_client:
            await client.aclose()
    papers = [PaperRecord(**r, caveat=_CAVEATS[r['doi_status']]) for r in records]
    return LiteratureSearchResult(query=query, results=papers, retrieved_at=_now(),
                                  total_openalex_matches=total, duplicates_removed=duplicates)


async def search_literature(query: str, client: httpx.AsyncClient | None = None) -> LiteratureSearchResult:
    """Search OpenAlex, deduplicate, verify each DOI in Crossref.

    Raises ``LiteratureSourceError`` on OpenAlex failure; never fabricates results.

    ABB-27: cached on disk per normalized query for ``SEARCH_CACHE_TTL_SECONDS``, so a
    repeated identical search within that window never re-downloads. A cache miss is
    deduplicated across concurrent callers (``_SEARCH_REGISTRY``): only one of them
    actually reaches OpenAlex/Crossref for a given query at a time.
    """
    key = _search_cache_key(query)
    hit = diskcache.read_ttl_cache(SEARCH_CACHE, key, SEARCH_CACHE_TTL_SECONDS, _now())
    if hit is not None:
        try:
            return LiteratureSearchResult.model_validate_json(hit.raw)
        except ValueError:
            pass  # corrupt or unreadable cache entry: refetch instead of failing

    async def factory() -> LiteratureSearchResult:
        result = await _search_literature_uncached(query, client)
        diskcache.write_ttl_cache(SEARCH_CACHE, key, result.model_dump_json().encode(), result.retrieved_at)
        return result

    return await _SEARCH_REGISTRY.run(key, factory)


async def query_literature(query: str) -> list[dict]:
    """Backward-compatible helper returning plain dicts."""
    result = await search_literature(query)
    return [p.model_dump(mode='json') for p in result.results]


# ---------------------------------------------------------------- single-work lookup (ABB-14)

_OPENALEX_ID_RE = re.compile(r'^(?:https?://(?:www\.)?openalex\.org/)?(w\d{1,12})$', re.IGNORECASE)


class PaperNotFoundError(LiteratureSourceError):
    """Neither OpenAlex nor Crossref knows the requested identifier."""


def normalize_openalex_id(raw: Any) -> str | None:
    """Return ``https://openalex.org/W…`` (the form OpenAlex search returns) or None."""
    if not isinstance(raw, str):
        return None
    match = _OPENALEX_ID_RE.match(raw.strip())
    return f'https://openalex.org/{match.group(1).upper()}' if match else None


async def _openalex_work(path: str, client: httpx.AsyncClient) -> tuple[dict | None, SourceRetrieval]:
    """Fetch one OpenAlex work. Never raises: failures are reported in the retrieval outcome."""
    endpoint = f'{OPENALEX_WORKS_URL}/{path}'
    params: dict[str, Any] = {'select': OPENALEX_SELECT}
    api_key = os.getenv('OPENALEX_API_KEY', '').strip()
    if api_key:
        params['api_key'] = api_key
    status_code: int | None = None
    try:
        response = await client.get(endpoint, params=params)
        status_code = response.status_code
        if status_code == 404:
            return None, _retrieval('OpenAlex', endpoint, None, 404, 'not_found')
        if status_code == 429:
            return None, _retrieval('OpenAlex', endpoint, None, 429, 'rate_limited')
        response.raise_for_status()
        work = response.json()
        if not isinstance(work, dict) or not isinstance(work.get('id'), str):
            raise ValueError('unexpected OpenAlex payload')
    except (httpx.HTTPError, ValueError):
        return None, _retrieval('OpenAlex', endpoint, None, status_code, 'error')
    return work, _retrieval('OpenAlex', endpoint, work['id'], status_code, 'found')


def _crossref_only_record(check: DoiVerification, openalex_retrieval: SourceRetrieval) -> dict | None:
    if check.status != 'VERIFIED_CROSSREF' or not check.title:
        return None
    doi_id = normalize_doi(check.crossref_doi) or check.doi_id
    discrepancies = [f'Crossref canonical DOI is {doi_id}.'] if doi_id != check.doi_id else []
    return {
        'title': check.title, 'year': check.year, 'doi_id': doi_id, 'doi': doi_url(doi_id),
        'doi_status': 'VERIFIED_CROSSREF', 'openalex_id': None, 'authors': check.authors,
        'venue': check.venue, 'publication_type': check.publication_type, 'licenses': check.licenses,
        'landing_page_url': None, 'is_open_access': None, 'metadata_discrepancies': discrepancies,
        'retrievals': [openalex_retrieval, check.retrieval],
        'source': 'Crossref metadata (no OpenAlex record available)',
    }


def _work_dedup_key(*, doi_id: str | None, openalex_id: str | None) -> str:
    return diskcache.cache_key({'resource': 'openalex_work', 'doi_id': doi_id, 'openalex_id': openalex_id})


async def lookup_paper(
    *, doi: str | None = None, openalex_id: str | None = None, client: httpx.AsyncClient | None = None,
) -> PaperRecord:
    """Resolve ONE work by DOI or OpenAlex ID from the upstream sources (never from client metadata).

    The DOI is checked in Crossref with the same rules as the search (title agreement, canonical
    DOI). Raises ``ValueError`` for malformed identifiers, ``PaperNotFoundError`` when no source
    knows the work and ``LiteratureSourceError`` when the sources cannot be consulted.

    ABB-27: concurrent identical lookups are deduplicated (``_WORK_REGISTRY``), so two
    callers racing to resolve the same not-yet-registered identifier trigger only one
    upstream round trip. Deliberately NOT disk-cached (unlike ``search_literature``):
    ``api/evidence.py`` already owns a DB-backed re-verification/staleness policy for
    registered papers that depends on being able to ask again immediately when a
    previous attempt degraded to ``VERIFICATION_UNAVAILABLE``; a cache here would make
    that degraded status artificially sticky and fight that policy.
    """
    if (doi is None) == (openalex_id is None):
        raise ValueError('Provide exactly one of doi or openalex_id')
    if doi is not None:
        key_doi_id = normalize_doi(doi)
        if key_doi_id is None:
            raise ValueError('Not a valid DOI')
        dedup_key = _work_dedup_key(doi_id=key_doi_id, openalex_id=None)
    else:
        key_work_id = normalize_openalex_id(openalex_id)
        if key_work_id is None:
            raise ValueError('Not a valid OpenAlex work ID')
        dedup_key = _work_dedup_key(doi_id=None, openalex_id=key_work_id)

    async def factory() -> PaperRecord:
        return await _lookup_paper_uncached(doi=doi, openalex_id=openalex_id, client=client)

    return await _WORK_REGISTRY.run(dedup_key, factory)


async def _lookup_paper_uncached(
    *, doi: str | None = None, openalex_id: str | None = None, client: httpx.AsyncClient | None = None,
) -> PaperRecord:
    """The actual upstream resolution for ``lookup_paper``; see its docstring. Only the
    caller that wins the dedup race for this identifier runs this."""
    own_client = client is None
    client = client or _make_client()
    try:
        if doi is not None:
            doi_id = normalize_doi(doi)
            if doi_id is None:
                raise ValueError('Not a valid DOI')
            work, oa_retrieval = await _openalex_work('doi:' + quote(doi_id, safe='/'), client)
            check = await verify_doi(doi_id, client)
            record = _base_record(work, oa_retrieval) if work else None
            if record is not None and record['doi_id'] != doi_id:
                # OpenAlex resolved the DOI to a work that reports another DOI: do not mix identities.
                oa_retrieval = oa_retrieval.model_copy(update={'outcome': 'doi_mismatch_ignored'})
                record = None
            if record is not None:
                record = _merge_crossref(record, check)
            else:
                record = _crossref_only_record(check, oa_retrieval)
            if record is None:
                if oa_retrieval.outcome in ('not_found', 'doi_mismatch_ignored') \
                        and check.status == 'NOT_FOUND_IN_CROSSREF':
                    raise PaperNotFoundError('No OpenAlex or Crossref record exists for this DOI; nothing was stored.')
                raise LiteratureSourceError(
                    'Literature sources unavailable: the DOI could not be resolved now; nothing was stored.')
        else:
            work_id = normalize_openalex_id(openalex_id)
            if work_id is None:
                raise ValueError('Not a valid OpenAlex work ID')
            work, oa_retrieval = await _openalex_work(work_id.rsplit('/', 1)[1], client)
            if work is None:
                if oa_retrieval.outcome == 'not_found':
                    raise PaperNotFoundError('OpenAlex has no work with this ID; nothing was stored.')
                raise LiteratureSourceError('OpenAlex source unavailable: the work could not be retrieved now.')
            record = _base_record(work, oa_retrieval)
            if record is None:
                raise LiteratureSourceError('OpenAlex returned a work without a title; nothing was stored.')
            if record['doi_id'] is not None:
                record = _merge_crossref(record, await verify_doi(record['doi_id'], client))
    finally:
        if own_client:
            await client.aclose()
    return PaperRecord(**record, caveat=_CAVEATS[record['doi_status']])
