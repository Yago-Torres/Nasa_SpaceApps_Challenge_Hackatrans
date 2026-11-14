"""NASA POWER daily point adapter (ABB-07).

Responsibilities:

- Build the exact, reproducible request (UTC daily values, AG community).
- Bounded retries with backoff for timeouts, network errors, HTTP 429 and 5xx.
- Strict response-shape validation (dates, numeric values, units, time standard) before
  anything is cached.
- On-disk TTL cache keyed by the request, with a metadata sidecar that keeps the original
  retrieval time and checksum, so cached answers report their true age.
- Provenance: SHA-256 of the raw bytes, retrieval time (UTC), POWER header metadata
  (API version, sources, fill value, time standard) and per-parameter units.

Fill values are never converted into data here: they are passed through untouched and
``services.metrics`` classifies them as missing. ``PowerSourceError.public_message`` never
contains URLs, query strings or upstream bodies.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .. import __version__
from ..resilience.tasks import TaskRegistry

logger = logging.getLogger(__name__)

PROVIDER = 'NASA POWER'
DATASET_LABEL = 'NASA POWER daily point'
DATASET = 'NASA POWER Daily Point API (temporal/daily/point), AG community'
BASE = 'https://power.larc.nasa.gov/api/temporal/daily/point'
DOCS_URL = 'https://power.larc.nasa.gov/docs/services/api/temporal/daily/'
METHODOLOGY_URL = 'https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/'
PARAMETERS = ('PRECTOTCORR', 'T2M_MAX')
# Units documented by POWER and observed in a live response header (2026-11-14).
EXPECTED_UNITS = {'PRECTOTCORR': 'mm/day', 'T2M_MAX': 'C'}
COMMUNITY = 'AG'
DEFAULT_FILL_VALUE = -999.0
PROCESSING_VERSION = f'agroblackbox-{__version__}+abb07-power-1'

CACHE = Path(__file__).resolve().parents[2] / '.cache' / 'power'
CACHE_TTL_SECONDS = 86_400
CACHE_FORMAT = 1

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)  # wait before attempt 2 and attempt 3
MAX_RETRY_AFTER_SECONDS = 10.0
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
REQUEST_TIMEOUT = httpx.Timeout(55.0, connect=10.0)

_DATE_KEY = re.compile(r'^\d{8}$')

# ABB-27: deduplicates concurrent identical requests (same lat/lon/years) so that N
# callers racing for a cache-cold request trigger exactly one upstream download; the
# download itself keeps its own bounded retry/backoff (MAX_ATTEMPTS/BACKOFF_SECONDS
# above), so this registry runs each logical request at most once (max_attempts=1).
_REGISTRY: TaskRegistry[PowerRecord] = TaskRegistry(name='NASA POWER', max_attempts=1)


class PowerSourceError(Exception):
    """NASA POWER failed or answered something unusable. ``public_message`` is safe for clients."""

    def __init__(self, public_message: str, *, reason: str):
        super().__init__(public_message)
        self.public_message = public_message
        self.reason = reason


@dataclass(frozen=True)
class PowerVariable:
    name: str
    units: str
    longname: str | None
    units_reported_by_source: bool


@dataclass(frozen=True)
class PowerHeader:
    title: str | None = None
    api_name: str | None = None
    api_version: str | None = None
    sources: list[str] = field(default_factory=list)
    fill_value: float | None = None
    time_standard: str | None = None
    start: str | None = None
    end: str | None = None


@dataclass(frozen=True)
class ParsedPayload:
    parameter: dict[str, dict[str, Any]]
    header: PowerHeader
    variables: dict[str, PowerVariable]
    messages: list[str]


@dataclass(frozen=True)
class PowerRecord:
    parameter: dict[str, dict[str, Any]]
    sha256: str
    request_params: dict[str, str | float]
    retrieved_at: datetime
    served_from_cache: bool
    cache_age_seconds: float | None
    upstream_attempts: int
    header: PowerHeader
    variables: dict[str, PowerVariable]
    messages: list[str]

    @property
    def fill_value(self) -> float:
        return self.header.fill_value if self.header.fill_value is not None else DEFAULT_FILL_VALUE


# --------------------------------------------------------------------------- seams for tests

def _now() -> datetime:
    return datetime.now(UTC)


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True,
                             headers={'User-Agent': f'CropStory/{PROCESSING_VERSION}'})


# --------------------------------------------------------------------------- request

def build_params(latitude: float, longitude: float, event_year: int, ref_start: int,
                 ref_end: int) -> dict[str, str | float]:
    return {
        'latitude': latitude, 'longitude': longitude,
        'parameters': ','.join(PARAMETERS), 'community': COMMUNITY,
        'start': f'{min(event_year, ref_start):04d}0101',
        'end': f'{max(event_year, ref_end):04d}1231',
        'time-standard': 'UTC', 'format': 'JSON',
    }


def cache_key(params: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()


# --------------------------------------------------------------------------- validation

def _invalid(detail: str) -> PowerSourceError:
    logger.warning('Rejected NASA POWER payload: %s', detail)
    return PowerSourceError('NASA POWER returned an unexpected or incomplete response.', reason='invalid_response')


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _text(v: Any, limit: int = 200) -> str | None:
    return v[:limit] if isinstance(v, str) else None


def parse_payload(raw: bytes) -> ParsedPayload:
    """Validate the POWER JSON shape. Raises PowerSourceError; never repairs values."""
    try:
        record = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as e:
        raise _invalid(f'not JSON ({type(e).__name__})') from e
    if not isinstance(record, dict):
        raise _invalid('top level is not an object')
    props = record.get('properties')
    parameter = props.get('parameter') if isinstance(props, dict) else None
    if not isinstance(parameter, dict):
        raise _invalid('properties.parameter missing')
    for name in PARAMETERS:
        series = parameter.get(name)
        if not isinstance(series, dict):
            raise _invalid(f'parameter {name} missing')
        for key, value in series.items():
            if not _DATE_KEY.match(key):
                raise _invalid(f'{name} has a non-daily key')
            if value is not None and not _is_number(value):
                raise _invalid(f'{name} has a non-numeric value')

    raw_header = record.get('header') if isinstance(record.get('header'), dict) else {}
    api = raw_header.get('api') if isinstance(raw_header.get('api'), dict) else {}
    fill = raw_header.get('fill_value')
    if fill is not None and (not _is_number(fill) or not math.isfinite(fill)):
        raise _invalid('header.fill_value is not numeric')
    time_standard = raw_header.get('time_standard')
    if time_standard is not None and str(time_standard).upper() != 'UTC':
        raise _invalid('time standard is not UTC')
    sources = raw_header.get('sources')
    header = PowerHeader(
        title=_text(raw_header.get('title')), api_name=_text(api.get('name')), api_version=_text(api.get('version')),
        sources=[s[:80] for s in sources if isinstance(s, str)] if isinstance(sources, list) else [],
        fill_value=float(fill) if fill is not None else None, time_standard=_text(time_standard),
        start=_text(raw_header.get('start')), end=_text(raw_header.get('end')),
    )

    meta = record.get('parameters') if isinstance(record.get('parameters'), dict) else {}
    variables: dict[str, PowerVariable] = {}
    for name in PARAMETERS:
        info = meta.get(name) if isinstance(meta.get(name), dict) else {}
        units = info.get('units')
        if units is not None and units != EXPECTED_UNITS[name]:
            raise _invalid(f'{name} reported unexpected units')
        variables[name] = PowerVariable(name=name, units=EXPECTED_UNITS[name], longname=_text(info.get('longname')),
                                        units_reported_by_source=units is not None)

    messages = record.get('messages')
    messages = [m[:500] for m in messages if isinstance(m, str)] if isinstance(messages, list) else []
    return ParsedPayload(parameter, header, variables, messages)


# --------------------------------------------------------------------------- cache

def _cache_paths(key: str) -> tuple[Path, Path]:
    return CACHE / f'{key}.json', CACHE / f'{key}.meta.json'


def _read_cache(key: str, now: datetime) -> tuple[bytes, datetime, float] | None:
    data_path, meta_path = _cache_paths(key)
    try:
        if not (data_path.exists() and meta_path.exists()):
            return None  # legacy cache files without a sidecar are refetched
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        if meta.get('format') != CACHE_FORMAT:
            return None
        retrieved_at = datetime.fromisoformat(meta['retrieved_at'])
        if retrieved_at.tzinfo is None:
            return None
        age = (now - retrieved_at).total_seconds()
        if age < 0 or age >= CACHE_TTL_SECONDS:
            return None
        raw = data_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != meta.get('sha256'):
            return None
        return raw, retrieved_at.astimezone(UTC), age
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def _write_cache(key: str, raw: bytes, sha: str, retrieved_at: datetime) -> None:
    data_path, meta_path = _cache_paths(key)
    sidecar = json.dumps({'format': CACHE_FORMAT, 'sha256': sha, 'retrieved_at': retrieved_at.isoformat()})
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        for path, content in ((data_path, raw), (meta_path, sidecar.encode())):
            tmp = path.with_name(path.name + '.tmp')
            tmp.write_bytes(content)
            os.replace(tmp, path)
    except OSError as e:  # a cache failure must not fail a valid live answer
        logger.warning('Could not write NASA POWER cache: %s', type(e).__name__)


# --------------------------------------------------------------------------- download

def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get('Retry-After')
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None  # HTTP-date form not supported; fall back to our own backoff
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


async def _download(client: httpx.AsyncClient, params: dict[str, Any]) -> tuple[bytes, int]:
    """GET with at most MAX_ATTEMPTS attempts. Returns (raw body, attempts used)."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        delay: float | None = None
        cause: BaseException | None = None
        try:
            response = await client.get(BASE, params=params)
        except httpx.TimeoutException as e:
            failure = PowerSourceError('NASA POWER did not respond in time; retry later.', reason='timeout')
            cause = e
        except httpx.RequestError as e:
            failure = PowerSourceError('NASA POWER could not be reached (network error).', reason='network')
            cause = e
        else:
            status = response.status_code
            if status == 200:
                return response.content, attempt
            if status not in RETRYABLE_STATUS:
                raise PowerSourceError(f'NASA POWER rejected the request (HTTP {status}).', reason='rejected')
            if status == 429:
                failure = PowerSourceError('NASA POWER rate limit reached; retry later.', reason='rate_limited')
                delay = _retry_after(response)
                if delay is not None and delay > MAX_RETRY_AFTER_SECONDS:
                    raise failure  # respect the server: never retry earlier than it asked
            else:
                failure = PowerSourceError(f'NASA POWER is unavailable (HTTP {status}).', reason='upstream_error')
        if attempt == MAX_ATTEMPTS:
            raise failure from cause
        await _sleep(delay if delay is not None else BACKOFF_SECONDS[attempt - 1])
    raise AssertionError('unreachable')  # pragma: no cover


async def _download_and_cache(key: str, params: dict[str, Any],
                              client: httpx.AsyncClient | None) -> PowerRecord:
    """Perform the actual upstream fetch for one cache key. Only the caller that wins
    the ``_REGISTRY`` race for ``key`` ever runs this; concurrent callers for the same
    key share its result instead (ABB-27 deduplication)."""
    own_client = client is None
    client = client or _make_client()
    try:
        raw, attempts = await _download(client, params)
    finally:
        if own_client:
            await client.aclose()
    retrieved_at = _now()
    parsed = parse_payload(raw)  # validated before caching: invalid payloads are never stored
    sha = hashlib.sha256(raw).hexdigest()
    _write_cache(key, raw, sha, retrieved_at)
    return PowerRecord(parsed.parameter, sha256=sha, request_params=params, retrieved_at=retrieved_at,
                       served_from_cache=False, cache_age_seconds=None, upstream_attempts=attempts,
                       header=parsed.header, variables=parsed.variables, messages=parsed.messages)


async def fetch_power(latitude: float, longitude: float, event_year: int, ref_start: int, ref_end: int,
                      *, client: httpx.AsyncClient | None = None) -> PowerRecord:
    """Return validated POWER daily data plus provenance. Raises PowerSourceError.

    Concurrent calls with identical parameters (same cache key) are deduplicated: only
    one of them actually downloads from NASA POWER (``_REGISTRY``), the rest await that
    same result. If a ``client`` is supplied by a caller that loses the dedup race, it
    is simply never used for this call (no second request is made, nothing is leaked).
    """
    params = build_params(latitude, longitude, event_year, ref_start, ref_end)
    key = cache_key(params)

    cached = _read_cache(key, _now())
    if cached is not None:
        raw, retrieved_at, age = cached
        try:
            parsed = parse_payload(raw)
        except PowerSourceError:
            pass  # corrupt or outdated cache entry: refetch instead of failing
        else:
            return PowerRecord(parsed.parameter, sha256=hashlib.sha256(raw).hexdigest(), request_params=params,
                               retrieved_at=retrieved_at, served_from_cache=True,
                               cache_age_seconds=round(age, 3), upstream_attempts=0, header=parsed.header,
                               variables=parsed.variables, messages=parsed.messages)

    return await _REGISTRY.run(key, lambda: _download_and_cache(key, params, client))
