"""NASA HLS v2.0 vegetation observations at a point (ABB-12).

Pipeline for one location and date range (at most ``MAX_RANGE_DAYS``):

1. Discover HLSL30 (Landsat 8/9 OLI) and HLSS30 (Sentinel-2 MSI) v2.0 granules covering the
   point through NASA CMR (public metadata, no credentials).
2. Group them by acquisition (product + date + time); a point near an MGRS tile edge is covered
   by several tiles of the same acquisition, and only one is used.
3. For each acquisition, read the ``Fmask`` QA band in a 3 × 3 pixel window (90 m × 90 m)
   around the point straight from the Cloud-Optimized GeoTIFF with HTTP range requests and the
   ``EARTHDATA_TOKEN`` bearer token. Only when enough pixels are clear are the red and NIR
   bands read, and NDVI = (NIR − red) / (NIR + red) is computed per clear pixel.
4. Every acquisition is reported, usable or not, and the periods without any valid
   observation are listed as gaps. Nothing is interpolated or filled.

The token is sent only to the LP DAAC data host; redirects to the signed CloudFront URL drop it
(httpx removes ``Authorization`` on cross-origin redirects). ``HlsSourceError.public_message``
never contains URLs, coordinates or upstream bodies.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import statistics
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from .. import __version__
from . import geotiff

logger = logging.getLogger(__name__)

PROVIDER = 'NASA LP DAAC'
DATASET_LABEL = 'NASA HLS v2.0 (HLSL30 + HLSS30) surface reflectance, point window'
DOCS_URL = 'https://lpdaac.usgs.gov/products/hlsl30v002/'
S30_DOCS_URL = 'https://lpdaac.usgs.gov/products/hlss30v002/'
USER_GUIDE_URL = 'https://lpdaac.usgs.gov/documents/1698/HLS_User_Guide_V2.pdf'
CMR_URL = 'https://cmr.earthdata.nasa.gov/search/granules.json'
DATA_HOST = 'data.lpdaac.earthdatacloud.nasa.gov'
PROCESSING_VERSION = f'agroblackbox-{__version__}+abb12-hls-1'

PRODUCTS = {
    'HLSL30': {'version': '2.0', 'sensor': 'Landsat 8/9 OLI', 'red': 'B04', 'nir': 'B05'},
    'HLSS30': {'version': '2.0', 'sensor': 'Sentinel-2 MSI', 'red': 'B04', 'nir': 'B8A'},
}
REFLECTANCE_SCALE = 0.0001
REFLECTANCE_FILL = -9999
REFLECTANCE_VALID = (-100, 16000)   # HLS v2.0 User Guide, valid range of scaled reflectance
FMASK_FILL = 255
WINDOW = 1                          # pixels on each side of the centre: 3 × 3 window
MIN_CLEAR_FRACTION = 0.5            # more than half of the in-footprint window pixels must be clear
MAX_RANGE_DAYS = 92
MAX_GRANULES = 400
FULLY_CLOUDY_SCENE = 100.0

CACHE = Path(__file__).resolve().parents[2] / '.cache' / 'hls'
SEARCH_TTL_SECONDS = 86_400
SCENE_TTL_SECONDS = 30 * 86_400
CACHE_FORMAT = 1

HEADER_BYTES = 32_768
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
CONCURRENCY = 6

_GRANULE_ID = re.compile(r'^HLS\.(L30|S30)\.T(\d{2}[A-Z]{3})\.(\d{4})(\d{3})T(\d{6})\.v2\.0$')
_FMASK_BITS = (  # (bit, class) in priority order, HLS v2.0 User Guide table 9
    (1, 'cloud'), (3, 'cloud_shadow'), (2, 'adjacent_cloud'), (0, 'cirrus'), (4, 'snow_ice'), (5, 'water'))
CLASSES = ('clear', 'cloud', 'cloud_shadow', 'adjacent_cloud', 'cirrus', 'snow_ice', 'water', 'high_aerosol',
           'fill', 'invalid_reflectance')


class HlsSourceError(Exception):
    """HLS could not be retrieved or was unusable. ``public_message`` is safe for clients."""

    def __init__(self, public_message: str, *, reason: str):
        super().__init__(public_message)
        self.public_message = public_message
        self.reason = reason


class HlsNotConfigured(HlsSourceError):
    def __init__(self):
        super().__init__('HLS observations are not available on this server: NASA Earthdata access is not '
                         'configured (EARTHDATA_TOKEN).', reason='not_configured')


@dataclass(frozen=True)
class Granule:
    granule_id: str
    product: str
    mgrs_tile: str
    acquired_at: datetime
    scene_cloud_cover: float | None
    assets: dict[str, str]  # band name → https URL on DATA_HOST

    @property
    def acquisition_key(self) -> tuple[str, str]:
        return self.product, self.acquired_at.isoformat()


@dataclass
class SceneResult:
    granule_id: str
    product: str
    sensor: str
    mgrs_tile: str
    acquired_at: str
    scene_cloud_cover: float | None
    status: str                       # VALID | OBSCURED | NO_DATA | NOT_READ
    reason: str | None
    window_pixels: int
    pixels: dict[str, int] = field(default_factory=dict)
    ndvi: float | None = None
    ndvi_min: float | None = None
    ndvi_max: float | None = None
    red_reflectance: float | None = None
    nir_reflectance: float | None = None
    red_band: str = ''
    nir_band: str = ''
    epsg: int | None = None
    pixel_size_m: float | None = None
    data_sha256: str | None = None
    tiles_read: int = 0


@dataclass(frozen=True)
class HlsSeries:
    latitude: float
    longitude: float
    start: date
    end: date
    scenes: list[SceneResult]
    granules_found: int
    retrieved_at: datetime
    search_from_cache: bool
    scenes_from_cache: int
    requests: int


# --------------------------------------------------------------------------- seams for tests

def _now() -> datetime:
    return datetime.now(UTC)


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _token() -> str:
    return os.getenv('EARTHDATA_TOKEN', '').strip()


def is_configured() -> bool:
    return bool(_token())


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True,
                             headers={'User-Agent': f'CropStory/{PROCESSING_VERSION}'})


# --------------------------------------------------------------------------- cache

def _key(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _read_cache(kind: str, key: str, ttl: int) -> Any | None:
    path = CACHE / kind / f'{key}.json'
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
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
    except OSError as e:  # a cache failure must not fail a valid live answer
        logger.warning('Could not write HLS cache: %s', type(e).__name__)


# --------------------------------------------------------------------------- HTTP

class _Http:
    """Bounded retries and request counting; the bearer token goes only to the LP DAAC data host."""

    def __init__(self, client: httpx.AsyncClient, token: str):
        self.client, self.token = client, token
        self.requests = 0
        self.limit = asyncio.Semaphore(CONCURRENCY)

    async def get(self, url: str, *, params: dict[str, Any] | None = None, byte_range: tuple[int, int] | None = None,
                  source: str) -> bytes:
        parts = urlsplit(url)
        headers = {}
        if parts.hostname == DATA_HOST:
            if parts.scheme != 'https':
                raise HlsSourceError('HLS returned an unexpected data location.', reason='invalid_response')
            headers['Authorization'] = f'Bearer {self.token}'
        if byte_range is not None:
            headers['Range'] = f'bytes={byte_range[0]}-{byte_range[1]}'
        for attempt in range(1, MAX_ATTEMPTS + 1):
            cause: BaseException | None = None
            async with self.limit:
                self.requests += 1
                try:
                    async with self.client.stream('GET', url, params=params, headers=headers) as response:
                        status = response.status_code
                        if status == 200 and byte_range is not None:
                            # the server ignored Range: never download a whole multi-megabyte file
                            raise HlsSourceError('HLS ignored a partial-content request.', reason='invalid_response')
                        body = await response.aread() if status in (200, 206) else b''
                except httpx.TimeoutException as e:
                    failure, cause = HlsSourceError(f'{source} did not respond in time; retry later.',
                                                    reason='timeout'), e
                except httpx.RequestError as e:
                    failure, cause = HlsSourceError(f'{source} could not be reached (network error).',
                                                    reason='network'), e
                else:
                    if status in (200, 206):
                        return body
                    if status in (401, 403):
                        raise HlsSourceError(
                            'NASA Earthdata refused the server credentials for HLS (token expired or LP DAAC access '
                            'not authorised for the account).', reason='unauthorized')
                    if status not in RETRYABLE_STATUS:
                        raise HlsSourceError(f'{source} rejected the request (HTTP {status}).', reason='rejected')
                    failure = HlsSourceError(
                        f'{source} rate limit reached; retry later.' if status == 429 else
                        f'{source} is unavailable (HTTP {status}).',
                        reason='rate_limited' if status == 429 else 'upstream_error')
            if attempt == MAX_ATTEMPTS:
                raise failure from cause
            await _sleep(BACKOFF_SECONDS[attempt - 1])
        raise AssertionError('unreachable')  # pragma: no cover


# --------------------------------------------------------------------------- discovery

def parse_granules(payload: bytes, product: str) -> list[Granule]:
    """Validate a CMR granules.json answer. Raises HlsSourceError on an unexpected shape."""
    try:
        feed = json.loads(payload)['feed']
        entries = feed['entry']
    except (ValueError, KeyError, TypeError) as e:
        raise HlsSourceError('NASA CMR returned an unexpected response.', reason='invalid_response') from e
    if not isinstance(entries, list):
        raise HlsSourceError('NASA CMR returned an unexpected response.', reason='invalid_response')
    bands = {'Fmask', PRODUCTS[product]['red'], PRODUCTS[product]['nir']}
    granules = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = entry.get('title') or entry.get('producer_granule_id')
        match = _GRANULE_ID.match(title) if isinstance(title, str) else None
        if not match or f'HLS{match.group(1)}' != product:
            continue
        year, doy, hms = int(match.group(3)), int(match.group(4)), match.group(5)
        acquired = datetime(year, 1, 1, int(hms[:2]), int(hms[2:4]), int(hms[4:]), tzinfo=UTC) + timedelta(days=doy - 1)
        assets = {}
        for link in entry.get('links') or []:
            href = link.get('href') if isinstance(link, dict) else None
            if not isinstance(href, str) or not href.startswith(f'https://{DATA_HOST}/'):
                continue
            for band in bands:
                if href.endswith(f'{title}.{band}.tif'):
                    assets[band] = href
        cloud = entry.get('cloud_cover')
        try:
            cloud_cover = float(cloud) if cloud is not None else None
        except (TypeError, ValueError):
            cloud_cover = None
        if cloud_cover is not None and not (0 <= cloud_cover <= 100):
            cloud_cover = None
        granules.append(Granule(granule_id=title, product=product, mgrs_tile=match.group(2), acquired_at=acquired,
                                scene_cloud_cover=cloud_cover, assets=assets))
    return granules


async def _search(http: _Http, product: str, latitude: float, longitude: float, start: date, end: date) -> list[dict]:
    params = {'short_name': product, 'version': PRODUCTS[product]['version'], 'point': f'{longitude},{latitude}',
              'temporal': f'{start.isoformat()}T00:00:00Z,{end.isoformat()}T23:59:59Z',
              'page_size': 2000, 'sort_key': 'start_date'}
    raw = await http.get(CMR_URL, params=params, source='NASA CMR')
    granules = parse_granules(raw, product)
    if len(granules) > MAX_GRANULES:
        raise HlsSourceError('Too many HLS scenes for one request; shorten the date range.', reason='too_many')
    return [{**asdict(g), 'acquired_at': g.acquired_at.isoformat()} for g in granules]


def _granule_from_dict(d: dict) -> Granule:
    return Granule(granule_id=d['granule_id'], product=d['product'], mgrs_tile=d['mgrs_tile'],
                   acquired_at=datetime.fromisoformat(d['acquired_at']), scene_cloud_cover=d['scene_cloud_cover'],
                   assets=dict(d['assets']))


# --------------------------------------------------------------------------- pixel reading

class _Band:
    def __init__(self, http: _Http, url: str):
        self.http, self.url = http, url
        self.layout: geotiff.TiffLayout | None = None
        self.raw_tiles: list[bytes] = []

    async def open(self) -> geotiff.TiffLayout:
        size = HEADER_BYTES
        while True:
            head = await self.http.get(self.url, byte_range=(0, size - 1), source='NASA LP DAAC')
            try:
                self.layout = geotiff.parse_header(head)
                return self.layout
            except geotiff.HeaderTruncated as e:
                if e.required > geotiff.MAX_HEADER_BYTES or len(head) < size:
                    raise HlsSourceError('An HLS file had an unexpected structure.', reason='invalid_response') from e
                size = max(e.required, size * 2)
            except geotiff.GeoTiffError as e:
                logger.warning('Rejected HLS GeoTIFF: %s', e)
                raise HlsSourceError('An HLS file had an unexpected structure.', reason='invalid_response') from e

    async def read(self, pixels: list[tuple[int, int]]) -> dict[tuple[int, int], int]:
        layout = self.layout
        assert layout is not None
        tiles: dict[int, Any] = {}
        for col, row in pixels:
            tiles.setdefault(layout.tile_index(col, row), None)
        for index in tiles:
            offset, count = layout.tile_offsets[index], layout.tile_byte_counts[index]
            if count == 0:
                tiles[index] = None  # sparse tile: entirely nodata
                continue
            raw = await self.http.get(self.url, byte_range=(offset, offset + count - 1), source='NASA LP DAAC')
            if len(raw) != count:
                raise HlsSourceError('An HLS file returned an incomplete tile.', reason='invalid_response')
            self.raw_tiles.append(raw)
            try:
                tiles[index] = geotiff.decode_tile(raw, layout)
            except geotiff.GeoTiffError as e:
                logger.warning('Rejected HLS tile: %s', e)
                raise HlsSourceError('An HLS file had an unexpected structure.', reason='invalid_response') from e
        values = {}
        for col, row in pixels:
            tile = tiles[layout.tile_index(col, row)]
            if tile is None:
                values[(col, row)] = int(layout.nodata) if layout.nodata is not None else 0
            else:
                values[(col, row)] = tile[(row % layout.tile_height) * layout.tile_width + col % layout.tile_width]
        return values


def classify_fmask(value: int) -> str:
    """HLS v2.0 Fmask bits → one class. Bits 6–7 = 3 is high aerosol (unreliable reflectance)."""
    if value == FMASK_FILL:
        return 'fill'
    for bit, name in _FMASK_BITS:
        if value >> bit & 1:
            return name
    if value >> 6 & 3 == 3:
        return 'high_aerosol'
    return 'clear'


def window_pixels(layout: geotiff.TiffLayout, latitude: float, longitude: float) -> list[tuple[int, int]]:
    x, y = geotiff.latlon_to_utm(latitude, longitude, layout.epsg)
    col, row = layout.pixel_of(x, y)
    return [(c, r) for r in range(row - WINDOW, row + WINDOW + 1) for c in range(col - WINDOW, col + WINDOW + 1)
            if 0 <= c < layout.width and 0 <= r < layout.height]


def ndvi_of(red: int, nir: int) -> float | None:
    lo, hi = REFLECTANCE_VALID
    if red == REFLECTANCE_FILL or nir == REFLECTANCE_FILL or not (lo <= red <= hi and lo <= nir <= hi):
        return None
    if red + nir <= 0:
        return None
    return (nir - red) / (nir + red)


async def _read_scene(http: _Http, granule: Granule, latitude: float, longitude: float) -> SceneResult:
    spec = PRODUCTS[granule.product]
    result = SceneResult(granule_id=granule.granule_id, product=granule.product, sensor=spec['sensor'],
                         mgrs_tile=granule.mgrs_tile, acquired_at=granule.acquired_at.isoformat(),
                         scene_cloud_cover=granule.scene_cloud_cover, status='NOT_READ', reason=None, window_pixels=0,
                         pixels={k: 0 for k in CLASSES}, red_band=spec['red'], nir_band=spec['nir'])
    if not {'Fmask', spec['red'], spec['nir']} <= set(granule.assets):
        result.reason = 'The scene metadata does not list the Fmask, red and NIR files.'
        return result
    if granule.scene_cloud_cover is not None and granule.scene_cloud_cover >= FULLY_CLOUDY_SCENE:
        result.status, result.reason = 'OBSCURED', 'Scene metadata reports 100% cloud cover; pixels were not read.'
        return result

    fmask = _Band(http, granule.assets['Fmask'])
    layout = await fmask.open()
    pixels = window_pixels(layout, latitude, longitude)
    result.epsg, result.pixel_size_m, result.window_pixels = layout.epsg, layout.pixel_size_x, len(pixels)
    if not pixels:
        result.status, result.reason = 'NO_DATA', 'The location is outside this MGRS tile.'
        return result
    classes = {p: classify_fmask(v) for p, v in (await fmask.read(pixels)).items()}
    for name in classes.values():
        result.pixels[name] += 1
    in_footprint = [p for p in pixels if classes[p] != 'fill']
    clear = [p for p in in_footprint if classes[p] == 'clear']
    tiles = list(fmask.raw_tiles)
    if not in_footprint:
        result.status, result.reason = 'NO_DATA', 'The location is outside the scene footprint (fill pixels).'
    elif len(clear) / len(in_footprint) <= MIN_CLEAR_FRACTION:
        result.status = 'OBSCURED'
        worst = max((k for k in CLASSES if k not in ('clear', 'fill')), key=lambda k: result.pixels[k])
        result.reason = (f'Only {len(clear)} of {len(in_footprint)} window pixels are clear; '
                         f'most common QA class: {worst.replace("_", " ")}.')
    else:
        red_band, nir_band = _Band(http, granule.assets[spec['red']]), _Band(http, granule.assets[spec['nir']])
        red_layout, nir_layout = await red_band.open(), await nir_band.open()
        for other in (red_layout, nir_layout):
            if (other.epsg, other.origin_x, other.origin_y, other.pixel_size_x, other.width) != (
                    layout.epsg, layout.origin_x, layout.origin_y, layout.pixel_size_x, layout.width):
                raise HlsSourceError('HLS bands of one scene are not co-registered.', reason='invalid_response')
        reds, nirs = await red_band.read(clear), await nir_band.read(clear)
        tiles += red_band.raw_tiles + nir_band.raw_tiles
        values = []
        for p in clear:
            v = ndvi_of(reds[p], nirs[p])
            if v is None:
                result.pixels['clear'] -= 1
                result.pixels['invalid_reflectance'] += 1
            else:
                values.append((v, reds[p], nirs[p]))
        if len(values) / len(in_footprint) <= MIN_CLEAR_FRACTION:
            result.status = 'OBSCURED'
            result.reason = f'Only {len(values)} of {len(in_footprint)} window pixels have valid clear reflectance.'
        else:
            ndvis = [v[0] for v in values]
            result.status = 'VALID'
            result.ndvi = round(statistics.median(ndvis), 4)
            result.ndvi_min, result.ndvi_max = round(min(ndvis), 4), round(max(ndvis), 4)
            result.red_reflectance = round(statistics.median(v[1] for v in values) * REFLECTANCE_SCALE, 4)
            result.nir_reflectance = round(statistics.median(v[2] for v in values) * REFLECTANCE_SCALE, 4)
    digest = hashlib.sha256()
    for raw in tiles:
        digest.update(hashlib.sha256(raw).digest())
    result.data_sha256 = digest.hexdigest()
    result.tiles_read = len(tiles)
    return result


FATAL_REASONS = frozenset({'unauthorized', 'not_configured'})


async def _scene_for_acquisition(http: _Http, candidates: list[Granule], latitude: float, longitude: float,
                                 counter: list[int], errors: list[HlsSourceError]) -> SceneResult:
    """Use the first tile whose footprint has data at the point; cached per granule and pixel location."""
    last: SceneResult | None = None
    for granule in candidates:
        key = _key({'granule': granule.granule_id, 'lat': round(latitude, 6), 'lon': round(longitude, 6),
                    'window': WINDOW, 'processing': PROCESSING_VERSION})
        cached = _read_cache('scenes', key, SCENE_TTL_SECONDS)
        if cached is not None:
            counter[0] += 1
            scene = SceneResult(**cached)
        else:
            try:
                scene = await _read_scene(http, granule, latitude, longitude)
            except HlsSourceError as e:
                if e.reason in FATAL_REASONS:
                    raise
                errors.append(e)  # one unreadable scene is reported, not hidden and not fatal
                spec = PRODUCTS[granule.product]
                return SceneResult(granule_id=granule.granule_id, product=granule.product, sensor=spec['sensor'],
                                   mgrs_tile=granule.mgrs_tile, acquired_at=granule.acquired_at.isoformat(),
                                   scene_cloud_cover=granule.scene_cloud_cover, status='NOT_READ',
                                   reason=f'Retrieval failed: {e.public_message}', window_pixels=0,
                                   pixels={k: 0 for k in CLASSES}, red_band=spec['red'], nir_band=spec['nir'])
            if scene.status != 'NOT_READ':
                _write_cache('scenes', key, asdict(scene))
        if scene.status != 'NO_DATA':
            return scene
        last = scene
    assert last is not None
    return last


def validate_range(start: date, end: date, today: date) -> None:
    if end < start:
        raise ValueError('end must not be before start')
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f'the date range is limited to {MAX_RANGE_DAYS} days')
    if start < date(2013, 4, 11):
        raise ValueError('HLS starts in April 2013')
    if end > today:
        raise ValueError('end must not be in the future')


async def fetch_hls_series(latitude: float, longitude: float, start: date, end: date, *,
                           client: httpx.AsyncClient | None = None) -> HlsSeries:
    """All HLS acquisitions over the point in [start, end] with QA and NDVI. Raises HlsSourceError."""
    token = _token()
    if not token:
        raise HlsNotConfigured()
    own_client = client is None
    client = client or _make_client()
    http = _Http(client, token)
    try:
        search_key = _key({'lat': round(latitude, 6), 'lon': round(longitude, 6), 'start': start, 'end': end,
                           'products': sorted(PRODUCTS)})
        found = _read_cache('search', search_key, SEARCH_TTL_SECONDS)
        search_from_cache = found is not None
        if found is None:
            found = []
            for product in PRODUCTS:
                found += await _search(http, product, latitude, longitude, start, end)
            _write_cache('search', search_key, found)
        granules = [_granule_from_dict(g) for g in found]
        groups: dict[tuple[str, str], list[Granule]] = {}
        for g in sorted(granules, key=lambda g: (g.acquired_at, g.product, g.granule_id)):
            groups.setdefault(g.acquisition_key, []).append(g)
        counter, errors = [0], []
        scenes = await asyncio.gather(*(_scene_for_acquisition(http, group, latitude, longitude, counter, errors)
                                        for group in groups.values()))
    finally:
        if own_client:
            await client.aclose()
    if scenes and len(errors) == len(scenes):
        raise errors[0]  # nothing could be read: an honest failure, not an empty series
    return HlsSeries(latitude=latitude, longitude=longitude, start=start, end=end, scenes=list(scenes),
                     granules_found=len(granules), retrieved_at=_now(), search_from_cache=search_from_cache,
                     scenes_from_cache=counter[0], requests=http.requests)


def gaps(series: HlsSeries) -> list[tuple[date, date]]:
    """Maximal date intervals inside [start, end] with no VALID observation (inclusive)."""
    valid_days = sorted({datetime.fromisoformat(s.acquired_at).date() for s in series.scenes if s.status == 'VALID'})
    out, cursor = [], series.start
    for day in valid_days:
        if day > cursor:
            out.append((cursor, day - timedelta(days=1)))
        cursor = max(cursor, day + timedelta(days=1))
    if cursor <= series.end:
        out.append((cursor, series.end))
    return out


def summary_counts(series: HlsSeries) -> dict[str, int]:
    counts = {'acquisitions': len(series.scenes), 'valid': 0, 'obscured': 0, 'no_data': 0, 'not_read': 0}
    for s in series.scenes:
        counts[s.status.lower()] += 1
    return counts
