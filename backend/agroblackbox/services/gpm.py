"""NASA GPM IMERG Final monthly precipitation at a point (ABB-09).

Pipeline for one location and calendar year:

1. Discover the ``GPM_3IMERGM`` v07 monthly granules of the year in NASA CMR (public metadata).
2. Read the 0.1° grid cell that contains the point from each granule through the GES DISC
   OPeNDAP server (an ASCII subset of four variables plus the cell-centre coordinates), with
   the ``EARTHDATA_TOKEN`` bearer token. One small request per month.
3. Convert the monthly mean rate (mm/hr) to a monthly total (mm) by multiplying by the hours of
   the month; the IMERG random-error estimate is converted the same way. Fill values become
   missing data, never numbers.

The returned cell centre is checked against the requested point (it must be the containing
0.1° cell). The units are checked against the dataset attributes (DAS) in parallel with the
month reads, and no value is accepted or cached until that check passes; a passed check is
cached per product version. GES DISC can take tens of seconds per answer, so reads have a long
timeout that is not retried, and the year has a time budget after which unread months are
reported as NOT_READ (they are cached when read, so a retry completes them).
``GpmSourceError.public_message`` never contains URLs, coordinates or upstream bodies.
"""
from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import logging
import math
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from .. import __version__

logger = logging.getLogger(__name__)

PROVIDER = 'NASA GES DISC'
SHORT_NAME = 'GPM_3IMERGM'
VERSION = '07'
DATASET_LABEL = 'GPM IMERG Final Precipitation L3 1 month 0.1 degree x 0.1 degree V07 (GPM_3IMERGM)'
DOI_URL = 'https://doi.org/10.5067/GPM/IMERG/3B-MONTH/07'
CMR_URL = 'https://cmr.earthdata.nasa.gov/search/granules.json'
DATA_PREFIX = 'https://data.gesdisc.earthdata.nasa.gov/data/'
OPENDAP_PREFIX = 'https://gpm1.gesdisc.eosdis.nasa.gov/opendap/'
AUTH_HOSTS = frozenset({'gpm1.gesdisc.eosdis.nasa.gov', 'data.gesdisc.earthdata.nasa.gov'})
PROCESSING_VERSION = f'agroblackbox-{__version__}+abb09-gpm-1'

GRID_STEP = 0.1
N_LON, N_LAT = 3600, 1800
FILL_THRESHOLD = -9999.0          # _FillValue -9999.9 (float) / -9999 (int16)
VARIABLES = ('precipitation', 'randomError', 'precipitationQualityIndex', 'gaugeRelativeWeighting')
EXPECTED_UNITS = {'precipitation': 'mm/hr', 'randomError': 'mm/hr', 'gaugeRelativeWeighting': 'percent'}
FIRST_YEAR = 1998

CACHE = Path(__file__).resolve().parents[2] / '.cache' / 'gpm'
SEARCH_TTL_SECONDS = 86_400
MONTH_TTL_SECONDS = 30 * 86_400
UNITS_TTL_SECONDS = 30 * 86_400
CACHE_FORMAT = 1

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
# GES DISC OPeNDAP opens the cloud-hosted granule before it answers: on 2026-11-15 the first byte of a
# DAS took 23-50 s, so a 30 s read limit failed every request. A timed-out read is not retried (that
# only repeats the wait), a slow connection (TLS took ~3.5 s, longer under load) is; the whole year must
# finish within TIME_BUDGET_SECONDS. More parallel requests made GES DISC answer 503, so it stays at 4.
# The demo is served through a Cloudflare tunnel, which ends a request with HTTP 524 after 100 s, so the
# budget (and the read limit inside it) keeps the whole API response below that.
REQUEST_TIMEOUT = httpx.Timeout(75.0, connect=20.0)
CONCURRENCY = 4
TIME_BUDGET_SECONDS = 85.0
PROXY_LIMIT_SECONDS = 100.0   # Cloudflare's origin response timeout (non-Enterprise plans)
BUDGET_REASON = 'Not read within the time limit of this request (NASA GES DISC was slow); retry to complete it.'

_GRANULE = re.compile(r'^(?:GPM_3IMERGM\.07:)?(3B-MO\.MS\.MRG\.3IMERG\.(\d{4})(\d{2})01-S000000-E235959\.(\d{2})\.V07[A-Z]\.HDF5)$')
_ASCII_LINE = re.compile(r'^([A-Za-z]+)(?:\[\d+\])*,\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*$')


class GpmSourceError(Exception):
    """GPM could not be retrieved or was unusable. ``public_message`` is safe for clients."""

    def __init__(self, public_message: str, *, reason: str):
        super().__init__(public_message)
        self.public_message = public_message
        self.reason = reason


class GpmNotConfigured(GpmSourceError):
    def __init__(self):
        super().__init__('GPM precipitation is not available on this server: NASA Earthdata access is not '
                         'configured (EARTHDATA_TOKEN).', reason='not_configured')


@dataclass(frozen=True)
class Granule:
    granule_id: str
    month: int
    opendap_url: str


@dataclass
class MonthResult:
    month: int
    status: str                      # OBSERVED | MISSING | NOT_AVAILABLE | NOT_READ
    reason: str | None
    granule_id: str | None
    hours: int
    rate_mm_per_hour: float | None = None
    precipitation_mm: float | None = None
    random_error_mm: float | None = None
    quality_index: float | None = None
    gauge_weight_percent: float | None = None
    data_sha256: str | None = None


@dataclass(frozen=True)
class GpmSeries:
    latitude: float
    longitude: float
    year: int
    cell_latitude: float
    cell_longitude: float
    months: list[MonthResult]
    granules_found: int
    retrieved_at: datetime
    search_from_cache: bool
    months_from_cache: int
    requests: int
    units_checked: bool              # the values read live in this request passed the units check
    units_from_cache: bool = False   # ... through a check cached for this product version


# --------------------------------------------------------------------------- seams for tests

def _now() -> datetime:
    return datetime.now(UTC)


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _token() -> str:
    return os.getenv('EARTHDATA_TOKEN', '').strip()


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True,
                             headers={'User-Agent': f'CropStory/{PROCESSING_VERSION}'})


# --------------------------------------------------------------------------- grid

def cell_indices(latitude: float, longitude: float) -> tuple[int, int]:
    """(lon_index, lat_index) of the 0.1° IMERG cell containing the point (edges clamped)."""
    i = min(max(math.floor((longitude + 180.0) / GRID_STEP + 1e-9), 0), N_LON - 1)
    j = min(max(math.floor((latitude + 90.0) / GRID_STEP + 1e-9), 0), N_LAT - 1)
    return i, j


def cell_center(i: int, j: int) -> tuple[float, float]:
    """(latitude, longitude) of the cell centre."""
    return round(-90.0 + (j + 0.5) * GRID_STEP, 2), round(-180.0 + (i + 0.5) * GRID_STEP, 2)


def month_hours(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1] * 24


# --------------------------------------------------------------------------- cache

def _key(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _read_cache(kind: str, key: str, ttl: int) -> Any | None:
    try:
        record = json.loads((CACHE / kind / f'{key}.json').read_text(encoding='utf-8'))
        if record.get('format') != CACHE_FORMAT:
            return None
        stored = datetime.fromisoformat(record['stored_at'])
        age = (_now() - stored).total_seconds()
        if stored.tzinfo is None or age < 0 or age >= ttl:
            return None
        return record['value']
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(kind: str, key: str, value: Any) -> None:
    path = CACHE / kind / f'{key}.json'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(json.dumps({'format': CACHE_FORMAT, 'stored_at': _now().isoformat(), 'value': value}),
                       encoding='utf-8')
        os.replace(tmp, path)
    except OSError as e:
        logger.warning('Could not write GPM cache: %s', type(e).__name__)


# --------------------------------------------------------------------------- HTTP

class _Http:
    """Bounded retries; the bearer token goes only to the GES DISC hosts over HTTPS."""

    def __init__(self, client: httpx.AsyncClient, token: str):
        self.client, self.token = client, token
        self.requests = 0
        self.limit = asyncio.Semaphore(CONCURRENCY)

    async def get(self, url: str, *, params: dict[str, Any] | None = None, source: str) -> bytes:
        parts = urlsplit(url)
        headers = {}
        if parts.hostname in AUTH_HOSTS:
            if parts.scheme != 'https':
                raise GpmSourceError('GPM returned an unexpected data location.', reason='invalid_response')
            headers['Authorization'] = f'Bearer {self.token}'
        for attempt in range(1, MAX_ATTEMPTS + 1):
            cause: BaseException | None = None
            async with self.limit:
                self.requests += 1
                try:
                    response = await self.client.get(url, params=params, headers=headers)
                except (httpx.ConnectTimeout, httpx.PoolTimeout) as e:   # no work done upstream: retried
                    failure, cause = GpmSourceError(f'{source} could not be reached in time; retry later.',
                                                    reason='timeout'), e
                except httpx.TimeoutException as e:   # slow answer: not retried, a retry only repeats the wait
                    raise GpmSourceError(f'{source} did not respond in time; retry later.', reason='timeout') from e
                except httpx.RequestError as e:
                    failure, cause = GpmSourceError(f'{source} could not be reached (network error).',
                                                    reason='network'), e
                else:
                    status = response.status_code
                    if status == 200:
                        if response.url.host == 'urs.earthdata.nasa.gov':   # login page instead of data
                            raise GpmSourceError(self._denied(), reason='unauthorized')
                        return response.content
                    if status in (401, 403):
                        raise GpmSourceError(self._denied(), reason='unauthorized')
                    if status not in RETRYABLE_STATUS:
                        raise GpmSourceError(f'{source} rejected the request (HTTP {status}).', reason='rejected')
                    failure = GpmSourceError(
                        f'{source} rate limit reached; retry later.' if status == 429 else
                        f'{source} is unavailable (HTTP {status}).',
                        reason='rate_limited' if status == 429 else 'upstream_error')
            if attempt == MAX_ATTEMPTS:
                raise failure from cause
            await _sleep(BACKOFF_SECONDS[attempt - 1])
        raise AssertionError('unreachable')  # pragma: no cover

    @staticmethod
    def _denied() -> str:
        return ('NASA Earthdata refused the server credentials for GPM (token expired, or the GES DISC data '
                'terms are not accepted for the account).')


# --------------------------------------------------------------------------- discovery

def parse_granules(payload: bytes, year: int) -> list[Granule]:
    """Validate a CMR granules.json answer for GPM_3IMERGM v07 of one year."""
    try:
        entries = json.loads(payload)['feed']['entry']
    except (ValueError, KeyError, TypeError) as e:
        raise GpmSourceError('NASA CMR returned an unexpected response.', reason='invalid_response') from e
    if not isinstance(entries, list):
        raise GpmSourceError('NASA CMR returned an unexpected response.', reason='invalid_response')
    by_month: dict[int, Granule] = {}
    for entry in entries:
        title = entry.get('title') if isinstance(entry, dict) else None
        match = _GRANULE.match(title) if isinstance(title, str) else None
        if not match or int(match.group(2)) != year or match.group(3) != match.group(4):
            continue
        filename, month = match.group(1), int(match.group(3))
        for link in entry.get('links') or []:
            href = link.get('href') if isinstance(link, dict) else None
            if isinstance(href, str) and href.startswith(DATA_PREFIX) and href.endswith('/' + filename):
                path = href[len(DATA_PREFIX):]
                if not re.fullmatch(rf'GPM_L3/GPM_3IMERGM\.07/{year}/[A-Za-z0-9.\-]+', path):
                    continue
                granule = Granule(granule_id=filename, month=month, opendap_url=OPENDAP_PREFIX + path)
                if month not in by_month or granule.granule_id > by_month[month].granule_id:
                    by_month[month] = granule  # a later processing letter (V07B > V07A) supersedes
    return [by_month[m] for m in sorted(by_month)]


async def _search(http: _Http, year: int) -> list[Granule]:
    params = {'short_name': SHORT_NAME, 'version': VERSION, 'page_size': 50, 'sort_key': 'start_date',
              'temporal': f'{year}-01-01T00:00:00Z,{year}-12-31T23:59:59Z'}
    return parse_granules(await http.get(CMR_URL, params=params, source='NASA CMR'), year)


# --------------------------------------------------------------------------- reading

def parse_ascii(raw: bytes) -> dict[str, float]:
    """Parse an OPeNDAP DAP2 ASCII answer with one value per variable (``name[0][0], 1.5``)."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as e:
        raise GpmSourceError('GPM returned an unexpected response.', reason='invalid_response') from e
    values: dict[str, float] = {}
    lines = text.strip().splitlines()
    if not lines or not lines[0].startswith('Dataset:'):
        raise GpmSourceError('GPM returned an unexpected response.', reason='invalid_response')
    for line in lines[1:]:
        if not line.strip():
            continue
        match = _ASCII_LINE.match(line.strip())
        if not match:
            raise GpmSourceError('GPM returned an unexpected response.', reason='invalid_response')
        values[match.group(1)] = float(match.group(2))
    missing = {*VARIABLES, 'lat', 'lon'} - values.keys()
    if missing:
        raise GpmSourceError('GPM returned an unexpected response.', reason='invalid_response')
    return values


def check_units(das: bytes) -> None:
    """Fail when the dataset attributes report other units than the documented ones."""
    text = das.decode('utf-8', errors='replace')
    for name, unit in EXPECTED_UNITS.items():
        block = re.search(rf'^\s*{name} \{{(.*?)^\s*\}}', text, flags=re.M | re.S)
        units = re.search(r'String units "([^"]*)"', block.group(1)) if block else None
        if not units or units.group(1) != unit:
            logger.warning('Rejected GPM attributes: units of %s', name)
            raise GpmSourceError('GPM reported unexpected units.', reason='invalid_response')


def _constraint(i: int, j: int) -> str:
    cell = f'[0][{i}][{j}]'
    return ','.join([*(v + cell for v in VARIABLES), f'lat[{j}]', f'lon[{i}]'])


def _value(v: float) -> float | None:
    return None if v <= FILL_THRESHOLD or not math.isfinite(v) else v


async def _read_month(http: _Http, granule: Granule, year: int, i: int, j: int) -> MonthResult:
    hours = month_hours(year, granule.month)
    raw = await http.get(f'{granule.opendap_url}.ascii?{_constraint(i, j)}', source='NASA GES DISC')
    values = parse_ascii(raw)
    lat_c, lon_c = cell_center(i, j)
    if abs(values['lat'] - lat_c) > 0.011 or abs(values['lon'] - lon_c) > 0.011:
        logger.warning('Rejected GPM answer: cell centre mismatch')
        raise GpmSourceError('GPM returned a different grid cell than requested.', reason='invalid_response')
    result = MonthResult(month=granule.month, status='OBSERVED', reason=None, granule_id=granule.granule_id,
                         hours=hours, data_sha256=hashlib.sha256(raw).hexdigest())
    rate = _value(values['precipitation'])
    if rate is None:
        result.status, result.reason = 'MISSING', 'The granule has a fill value for this cell.'
        return result
    if rate < 0:
        raise GpmSourceError('GPM returned a negative precipitation rate.', reason='invalid_response')
    error = _value(values['randomError'])
    result.rate_mm_per_hour = rate
    result.precipitation_mm = round(rate * hours, 1)
    result.random_error_mm = round(error * hours, 1) if error is not None and error >= 0 else None
    result.quality_index = _value(values['precipitationQualityIndex'])
    gauge = _value(values['gaugeRelativeWeighting'])
    result.gauge_weight_percent = gauge if gauge is not None and 0 <= gauge <= 100 else None
    return result


FATAL_REASONS = frozenset({'unauthorized', 'not_configured'})


def validate_year(year: int, today: datetime) -> None:
    if year < FIRST_YEAR:
        raise ValueError(f'GPM IMERG monthly data start in {FIRST_YEAR}')
    if year > today.year:
        raise ValueError('the year must not be in the future')


async def fetch_gpm_year(latitude: float, longitude: float, year: int, *,
                         client: httpx.AsyncClient | None = None) -> GpmSeries:
    """Twelve monthly IMERG Final values for the 0.1° cell containing the point. Raises GpmSourceError."""
    token = _token()
    if not token:
        raise GpmNotConfigured()
    i, j = cell_indices(latitude, longitude)
    lat_c, lon_c = cell_center(i, j)
    own_client = client is None
    client = client or _make_client()
    http = _Http(client, token)
    errors: list[GpmSourceError] = []
    from_cache = [0]
    tasks: list[asyncio.Task] = []
    units_task: asyncio.Task | None = None
    try:
        search_key = _key({'year': year, 'product': f'{SHORT_NAME}.{VERSION}'})
        cached = _read_cache('search', search_key, SEARCH_TTL_SECONDS)
        search_from_cache = cached is not None
        if cached is None:
            granules = await _search(http, year)
            _write_cache('search', search_key, [asdict(g) for g in granules])
        else:
            granules = [Granule(**g) for g in cached]
        by_month = {g.month: g for g in granules}

        def month_key(granule: Granule) -> str:
            return _key({'granule': granule.granule_id, 'cell': [i, j], 'processing': PROCESSING_VERSION})

        live = [g for g in granules if _read_cache('months', month_key(g), MONTH_TTL_SECONDS) is None]
        units_key = _key({'units': f'{SHORT_NAME}.{VERSION}', 'processing': PROCESSING_VERSION})
        units_from_cache = bool(live) and _read_cache('units', units_key, UNITS_TTL_SECONDS) is True
        if live and not units_from_cache:
            async def verify_units() -> None:
                check_units(await http.get(f'{live[0].opendap_url}.das', source='NASA GES DISC'))
                _write_cache('units', units_key, True)
            units_task = asyncio.create_task(verify_units())   # runs alongside the month reads

        async def one(month: int) -> MonthResult:
            hours = month_hours(year, month)
            granule = by_month.get(month)
            if granule is None:
                return MonthResult(month=month, status='NOT_AVAILABLE', granule_id=None, hours=hours,
                                   reason='No IMERG Final granule is published for this month (not yet released '
                                          'or outside the record).')
            hit = _read_cache('months', month_key(granule), MONTH_TTL_SECONDS)
            if hit is not None:
                from_cache[0] += 1
                return MonthResult(**hit)
            try:
                result = await _read_month(http, granule, year, i, j)
            except GpmSourceError as e:
                if e.reason in FATAL_REASONS:
                    raise
                errors.append(e)
                return MonthResult(month=month, status='NOT_READ', granule_id=granule.granule_id, hours=hours,
                                   reason=f'Retrieval failed: {e.public_message}')
            if units_task is not None:
                await units_task   # no value is accepted (or cached) before the units are confirmed
            _write_cache('months', month_key(granule), asdict(result))
            return result

        tasks = [asyncio.create_task(one(m)) for m in range(1, 13)]
        waiting = [*tasks, *([units_task] if units_task else [])]
        done, pending = await asyncio.wait(waiting, timeout=TIME_BUDGET_SECONDS,
                                           return_when=asyncio.FIRST_EXCEPTION)
        failures = [t.exception() for t in done if not t.cancelled() and t.exception() is not None]
        if failures:
            units_failure = units_task.exception() if units_task in done and not units_task.cancelled() else None
            raise units_failure or failures[0]
        if units_task in pending:
            logger.warning('GPM units check did not finish within the time budget')
            raise GpmSourceError('NASA GES DISC did not respond in time; retry later.', reason='timeout')
        months = []
        for month, task in enumerate(tasks, start=1):
            if task in done:
                months.append(task.result())
            else:
                errors.append(GpmSourceError(BUDGET_REASON, reason='timeout'))
                months.append(MonthResult(month=month, status='NOT_READ', granule_id=by_month[month].granule_id,
                                          hours=month_hours(year, month), reason=BUDGET_REASON))
    finally:
        outstanding = [t for t in (*tasks, units_task) if t is not None and not t.done()]
        for t in outstanding:
            t.cancel()
        await asyncio.gather(*outstanding, return_exceptions=True)
        if own_client:
            await client.aclose()
    read_attempts = sum(1 for m in months if m.status in ('OBSERVED', 'MISSING', 'NOT_READ')) - from_cache[0]
    if errors and len(errors) == read_attempts:
        raise errors[0]  # nothing could be read live: an honest failure
    accepted_live = read_attempts > len(errors)
    return GpmSeries(latitude=latitude, longitude=longitude, year=year, cell_latitude=lat_c, cell_longitude=lon_c,
                     months=months, granules_found=len(granules), retrieved_at=_now(),
                     search_from_cache=search_from_cache, months_from_cache=from_cache[0], requests=http.requests,
                     units_checked=accepted_live, units_from_cache=accepted_live and units_from_cache)
