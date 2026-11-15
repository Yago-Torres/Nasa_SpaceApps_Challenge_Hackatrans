"""GET /api/vegetation/hls (ABB-12): HLS v2.0 NDVI observations with QA at a point.

Every acquisition over the point is returned, usable or not, and the periods with no valid
observation are listed as gaps. Values are observed surface reflectance from a 3 × 3 pixel
(90 m) window; nothing is interpolated, smoothed or gap-filled.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .schemas import Resolution, SourceManifest
from .services import hls

router = APIRouter(tags=['vegetation (ABB-12)'])


class _Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class HlsPixelCounts(_Model):
    """Window pixels by HLS Fmask class (``clear`` = usable for NDVI)."""
    clear: int
    cloud: int
    cloud_shadow: int
    adjacent_cloud: int
    cirrus: int
    snow_ice: int
    water: int
    high_aerosol: int
    fill: int
    invalid_reflectance: int


class HlsObservation(_Model):
    date: date
    acquired_at: datetime
    product: Literal['HLSL30', 'HLSS30']
    sensor: str
    granule_id: str
    mgrs_tile: str
    scene_cloud_cover: float | None = Field(description='Whole-scene cloud cover (%) from CMR metadata, not the point.')
    status: Literal['VALID', 'OBSCURED', 'NO_DATA', 'NOT_READ']
    reason: str | None
    window_pixels: int
    pixels: HlsPixelCounts
    ndvi: float | None = Field(description='Median NDVI of the clear window pixels (dimensionless, −1…1).')
    ndvi_min: float | None
    ndvi_max: float | None
    red_reflectance: float | None = Field(description='Median surface reflectance of the red band (0–1).')
    nir_reflectance: float | None = Field(description='Median surface reflectance of the NIR band (0–1).')
    red_band: str
    nir_band: str
    epsg: int | None
    pixel_size_m: float | None
    data_sha256: str | None = Field(description='SHA-256 over the SHA-256 of every compressed tile read.')


class HlsGap(_Model):
    start: date
    end: date
    days: int


class HlsSummary(_Model):
    acquisitions: int
    valid: int
    obscured: int
    no_data: int
    not_read: int
    granules_found: int
    gap_days: int
    longest_gap_days: int


class HlsMethod(_Model):
    id: str
    window: str
    clear_rule: str
    ndvi_formula: str
    bands: dict[str, dict[str, str]]
    reflectance_scale: float
    valid_reflectance_range: list[int]
    acquisition_rule: str
    processing_version: str


class HlsCacheStatus(_Model):
    search_from_cache: bool
    scenes_from_cache: int
    upstream_requests: int


class VegetationResponse(_Model):
    kind: Literal['observation']
    source_kind: Literal['OBSERVED']
    dataset: str
    source_url: str
    request_params: dict[str, str | float]
    start: date
    end: date
    retrieved_at: datetime
    spatial_resolution: Resolution
    temporal_resolution: Resolution
    provenance: SourceManifest
    observations: list[HlsObservation]
    gaps: list[HlsGap]
    summary: HlsSummary
    method: HlsMethod
    cache: HlsCacheStatus
    limitations: list[str]
    disclaimer: str


SPATIAL_RESOLUTION = Resolution(
    value=30, unit='m',
    description=('30 m HLS pixels on the Sentinel-2 MGRS/UTM grid; values summarise a 3 × 3 pixel window '
                 '(about 90 m × 90 m) around the location, not a whole field.'))
TEMPORAL_RESOLUTION = Resolution(
    value=None, unit='acquisition',
    description=('Individual satellite overpasses (Landsat 8/9 and Sentinel-2A/B/C combined: typically every '
                 '2–4 days, irregular, and frequently obscured by clouds). Not aggregated.'))
METHOD = HlsMethod(
    id='hls-ndvi-point-window-v1',
    window='3 × 3 pixels centred on the pixel that contains the location, clipped to the raster.',
    clear_rule=(f'Fmask bits cloud, cloud shadow, adjacent to cloud/shadow, cirrus, snow/ice and water set to 0, '
                f'aerosol level not high, and red/NIR reflectance within the valid range. An acquisition is VALID '
                f'when more than {int(hls.MIN_CLEAR_FRACTION * 100)}% of the in-footprint window pixels are clear.'),
    ndvi_formula='NDVI = (NIR − red) / (NIR + red) per clear pixel; the median is reported with min and max.',
    bands={p: {'red': s['red'], 'nir': s['nir'], 'qa': 'Fmask'} for p, s in hls.PRODUCTS.items()},
    reflectance_scale=hls.REFLECTANCE_SCALE, valid_reflectance_range=list(hls.REFLECTANCE_VALID),
    acquisition_rule=('One result per overpass: when the location falls in overlapping MGRS tiles, the first tile '
                      '(by granule id) with data at the location is used.'),
    processing_version=hls.PROCESSING_VERSION)
LIMITATIONS = [
    'NDVI is a greenness index of the canopy at 30 m; it is not a measure of soil health, yield or crop damage, '
    'and it cannot by itself say why vegetation changed.',
    'The 3 × 3 window (about 90 m) can mix the field with roads, margins or neighbouring parcels.',
    'Fmask cloud and shadow detection misses some thin clouds and shadows and flags some clear pixels; '
    'a VALID observation can still be contaminated.',
    'HLS harmonises Landsat and Sentinel-2 reflectance, but small sensor differences remain; compare dates from '
    'one product when the difference matters.',
    'Dates without a VALID observation are missing data, not zero vegetation.',
    'Whole-scene cloud cover comes from CMR metadata and does not describe the location.',
]


def _observation(scene: hls.SceneResult) -> HlsObservation:
    acquired = datetime.fromisoformat(scene.acquired_at)
    return HlsObservation(
        date=acquired.date(), acquired_at=acquired, product=scene.product, sensor=scene.sensor,
        granule_id=scene.granule_id, mgrs_tile=scene.mgrs_tile, scene_cloud_cover=scene.scene_cloud_cover,
        status=scene.status, reason=scene.reason, window_pixels=scene.window_pixels,
        pixels=HlsPixelCounts(**scene.pixels), ndvi=scene.ndvi, ndvi_min=scene.ndvi_min, ndvi_max=scene.ndvi_max,
        red_reflectance=scene.red_reflectance, nir_reflectance=scene.nir_reflectance, red_band=scene.red_band,
        nir_band=scene.nir_band, epsg=scene.epsg, pixel_size_m=scene.pixel_size_m, data_sha256=scene.data_sha256)


def build_vegetation_response(series: hls.HlsSeries) -> VegetationResponse:
    observations = sorted((_observation(s) for s in series.scenes), key=lambda o: (o.acquired_at, o.product))
    gaps = [HlsGap(start=a, end=b, days=(b - a).days + 1) for a, b in hls.gaps(series)]
    counts = hls.summary_counts(series)
    params: dict[str, str | float] = {'latitude': series.latitude, 'longitude': series.longitude,
                                      'start': series.start.isoformat(), 'end': series.end.isoformat(),
                                      'products': ','.join(f'{p} v{s["version"]}' for p, s in hls.PRODUCTS.items())}
    canonical = json.dumps([o.model_dump(mode='json') for o in observations], sort_keys=True).encode()
    sha = hashlib.sha256(canonical).hexdigest()
    limitations = list(LIMITATIONS)
    if counts['not_read']:
        limitations.append(f'{counts["not_read"]} acquisition(s) could not be read and are reported as NOT_READ.')
    if (datetime.now(UTC).date() - series.end).days < 7:
        limitations.append('HLS scenes appear a few days after acquisition; the last days of the range may still '
                           'be missing.')
    manifest = SourceManifest(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f'{hls.CMR_URL}?{json.dumps(params, sort_keys=True)}#sha256={sha}'),
        provider=hls.PROVIDER, dataset=hls.DATASET_LABEL, source_uri=hls.DOCS_URL, query_parameters=dict(params),
        retrieved_at=series.retrieved_at, checksum_sha256=sha, dataset_version='HLS v2.0',
        processing_version=hls.PROCESSING_VERSION, license='NASA EOSDIS open data (no restrictions on reuse)',
        spatial_resolution=SPATIAL_RESOLUTION, temporal_resolution=TEMPORAL_RESOLUTION, limitations=limitations)
    return VegetationResponse(
        kind='observation', source_kind='OBSERVED', dataset=hls.DATASET_LABEL, source_url=hls.DOCS_URL,
        request_params=params, start=series.start, end=series.end, retrieved_at=series.retrieved_at,
        spatial_resolution=SPATIAL_RESOLUTION, temporal_resolution=TEMPORAL_RESOLUTION, provenance=manifest,
        observations=observations, gaps=gaps,
        summary=HlsSummary(**counts, granules_found=series.granules_found, gap_days=sum(g.days for g in gaps),
                           longest_gap_days=max((g.days for g in gaps), default=0)),
        method=METHOD,
        cache=HlsCacheStatus(search_from_cache=series.search_from_cache, scenes_from_cache=series.scenes_from_cache,
                             upstream_requests=series.requests),
        limitations=limitations,
        disclaimer=('Observed satellite surface reflectance (NASA HLS v2.0). NDVI describes canopy greenness in a '
                    '90 m window; it does not diagnose causes and is not a field measurement.'))


@router.get('/api/vegetation/hls', response_model=VegetationResponse)
async def vegetation_hls(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180),
                         start: date = Query(description='First day (UTC), inclusive.'),
                         end: date = Query(description=f'Last day (UTC), inclusive; at most {hls.MAX_RANGE_DAYS} days.')):
    """NASA HLS v2.0 NDVI and Fmask QA for every overpass at a location in a date range.

    503 when Earthdata access is not configured on the server, 502 when NASA fails or answers
    something unusable. No value is ever simulated."""
    if abs(latitude) > 80:
        raise HTTPException(422, detail='HLS uses UTM tiles; latitudes beyond ±80° are not supported.')
    try:
        hls.validate_range(start, end, datetime.now(UTC).date())
    except ValueError as e:
        raise HTTPException(422, detail=f'Invalid date range: {e}.') from e
    try:
        series = await hls.fetch_hls_series(latitude, longitude, start, end)
    except hls.HlsNotConfigured as e:
        raise HTTPException(503, detail=e.public_message) from e
    except hls.HlsSourceError as e:
        raise HTTPException(502, detail=e.public_message) from e
    return build_vegetation_response(series)
