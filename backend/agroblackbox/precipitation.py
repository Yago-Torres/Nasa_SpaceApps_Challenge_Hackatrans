"""GET /api/precipitation/gpm (ABB-09): GPM IMERG Final monthly precipitation at a point,
side by side with NASA POWER monthly totals for the same year.

The two products are compared month by month on their own grids (IMERG 0.1° cell, POWER
½° × ⅝° cell); nothing is regridded or interpolated, and differences are descriptive.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .schemas import Resolution, SourceManifest
from .services import gpm, power

router = APIRouter(tags=['precipitation (ABB-09)'])


class _Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class GpmMonth(_Model):
    month: int = Field(ge=1, le=12)
    status: Literal['OBSERVED', 'MISSING', 'NOT_AVAILABLE', 'NOT_READ']
    reason: str | None
    granule_id: str | None
    hours: int = Field(description='Hours in the month used to turn the mean rate into a total.')
    rate_mm_per_hour: float | None = Field(description='IMERG monthly mean precipitation rate (mm/hr) as published.')
    precipitation_mm: float | None = Field(description='rate × hours in the month (mm).')
    random_error_mm: float | None = Field(description='IMERG random-error estimate (RMS) × hours (mm).')
    quality_index: float | None = Field(description='IMERG precipitationQualityIndex (dimensionless; higher is better).')
    gauge_weight_percent: float | None = Field(description='Relative weight of rain gauges in the estimate (%).')
    data_sha256: str | None
    power_precipitation_mm: float | None = Field(description='NASA POWER PRECTOTCORR monthly total for the same '
                                                             'month (mm), complete months only.')
    difference_mm: float | None = Field(description='GPM minus POWER (mm), only when both are present.')


class PowerComparison(_Model):
    status: Literal['COMPARED', 'UNAVAILABLE']
    reason: str | None
    dataset: str
    parameter: Literal['PRECTOTCORR']
    spatial_resolution: str
    data_sha256: str | None
    retrieved_at: datetime | None
    months_compared: int
    gpm_total_mm: float | None = Field(description='Sum over the months where both products have a value.')
    power_total_mm: float | None


class GpmCell(_Model):
    latitude: float
    longitude: float
    size_degrees: float


class PrecipitationResponse(_Model):
    kind: Literal['observation']
    source_kind: Literal['OBSERVED']
    dataset: str
    source_url: str
    request_params: dict[str, str | float]
    year: int
    cell: GpmCell
    retrieved_at: datetime
    spatial_resolution: Resolution
    temporal_resolution: Resolution
    provenance: SourceManifest
    monthly: list[GpmMonth]
    comparison: PowerComparison
    summary: dict[str, int | float | None]
    method: dict[str, str]
    cache: dict[str, int | bool]
    limitations: list[str]
    disclaimer: str


SPATIAL_RESOLUTION = Resolution(
    value=0.1, unit='degree',
    description=('0.1° × 0.1° IMERG grid cell (about 11 km × 11 km at the equator, narrower in longitude toward '
                 'the poles) that contains the point; a satellite-gauge estimate for the cell, not a gauge reading.'))
TEMPORAL_RESOLUTION = Resolution(
    value=1, unit='month',
    description='Calendar months (UTC) from the IMERG Final monthly product; the mean rate is converted to a total.')
METHOD = {
    'id': 'gpm-imerg-monthly-point-cell-v1',
    'cell': 'The 0.1° cell whose bounds contain the point; its centre is checked in every answer.',
    'total': 'precipitation_mm = monthly mean rate (mm/hr) × days in month × 24.',
    'error': 'random_error_mm = IMERG randomError (RMS, mm/hr) × hours; it is IMERG\'s own error estimate.',
    'comparison': ('POWER PRECTOTCORR daily values summed per calendar month (UTC) only when every day is present; '
                   'difference = GPM − POWER. No regridding, interpolation or bias correction.'),
    'processing_version': gpm.PROCESSING_VERSION,
}
LIMITATIONS = [
    'IMERG is a merged satellite (microwave and infrared) and rain-gauge estimate for a 0.1° cell, not a '
    'measurement in the field; convective storms smaller than the cell are smoothed.',
    'The random error is IMERG\'s own estimate; it does not cover every source of error.',
    'Where few gauges exist (low gauge weight), monthly totals rely more on satellites and can be biased.',
    'POWER and IMERG use different grids (½° × ⅝° and 0.1°) and methods; a difference between them describes '
    'disagreement between products, not which one is right or what happened to a crop.',
    'Months without a published IMERG Final granule or with fill values are missing data, not zero rain.',
]


def _power_monthly(record: power.PowerRecord, year: int) -> dict[int, float | None]:
    series = record.parameter.get('PRECTOTCORR', {})
    fill = record.fill_value
    out: dict[int, float | None] = {}
    for month in range(1, 13):
        days = calendar.monthrange(year, month)[1]
        values = [series.get(f'{year}{month:02d}{d:02d}') for d in range(1, days + 1)]
        ok = all(v is not None and v != fill and v >= 0 for v in values)
        out[month] = round(sum(values), 1) if ok else None
    return out


async def _comparison(latitude: float, longitude: float, year: int) -> tuple[PowerComparison, dict[int, float | None]]:
    base = dict(dataset=power.DATASET_LABEL, parameter='PRECTOTCORR',
                spatial_resolution='0.5° × 0.625° (MERRA-2 grid)')
    if year < 1981:
        return PowerComparison(status='UNAVAILABLE', reason='NASA POWER daily data start in 1981.', data_sha256=None,
                               retrieved_at=None, months_compared=0, gpm_total_mm=None, power_total_mm=None,
                               **base), {}
    try:
        record = await power.fetch_power(latitude, longitude, year, year, year)
    except power.PowerSourceError as e:
        return PowerComparison(status='UNAVAILABLE', reason=e.public_message, data_sha256=None, retrieved_at=None,
                               months_compared=0, gpm_total_mm=None, power_total_mm=None, **base), {}
    return PowerComparison(status='COMPARED', reason=None, data_sha256=record.sha256,
                           retrieved_at=record.retrieved_at, months_compared=0, gpm_total_mm=None,
                           power_total_mm=None, **base), _power_monthly(record, year)


async def build_precipitation_response(series: gpm.GpmSeries, compare_power: bool) -> PrecipitationResponse:
    if compare_power:
        comparison, power_months = await _comparison(series.latitude, series.longitude, series.year)
    else:
        comparison, power_months = PowerComparison(
            status='UNAVAILABLE', reason='Comparison not requested.', dataset=power.DATASET_LABEL,
            parameter='PRECTOTCORR', spatial_resolution='0.5° × 0.625° (MERRA-2 grid)', data_sha256=None,
            retrieved_at=None, months_compared=0, gpm_total_mm=None, power_total_mm=None), {}
    monthly = []
    for m in series.months:
        p = power_months.get(m.month)
        diff = round(m.precipitation_mm - p, 1) if m.precipitation_mm is not None and p is not None else None
        monthly.append(GpmMonth(month=m.month, status=m.status, reason=m.reason, granule_id=m.granule_id,
                                hours=m.hours, rate_mm_per_hour=m.rate_mm_per_hour,
                                precipitation_mm=m.precipitation_mm, random_error_mm=m.random_error_mm,
                                quality_index=m.quality_index, gauge_weight_percent=m.gauge_weight_percent,
                                data_sha256=m.data_sha256, power_precipitation_mm=p, difference_mm=diff))
    both = [m for m in monthly if m.difference_mm is not None]
    if comparison.status == 'COMPARED':
        comparison.months_compared = len(both)
        if both:
            comparison.gpm_total_mm = round(sum(m.precipitation_mm for m in both), 1)
            comparison.power_total_mm = round(sum(m.power_precipitation_mm for m in both), 1)
        else:
            comparison.reason = 'No month has values from both products.'
    observed = [m for m in monthly if m.precipitation_mm is not None]
    params: dict[str, str | float] = {'latitude': series.latitude, 'longitude': series.longitude, 'year': series.year,
                                      'product': f'{gpm.SHORT_NAME} v{gpm.VERSION}',
                                      'variables': ','.join(gpm.VARIABLES)}
    canonical = json.dumps([m.model_dump(mode='json') for m in monthly], sort_keys=True).encode()
    sha = hashlib.sha256(canonical).hexdigest()
    limitations = list(LIMITATIONS)
    if any(m.status == 'NOT_AVAILABLE' for m in monthly):
        limitations.append('IMERG Final is published about 3.5 months after the month ends; recent months are '
                           'reported as not available.')
    if any(m.status == 'NOT_READ' for m in monthly):
        limitations.append('Some months could not be retrieved and are reported as NOT_READ.')
    manifest = SourceManifest(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f'{gpm.CMR_URL}?{json.dumps(params, sort_keys=True)}#sha256={sha}'),
        provider=gpm.PROVIDER, dataset=gpm.DATASET_LABEL, source_uri=gpm.DOI_URL, query_parameters=dict(params),
        retrieved_at=series.retrieved_at, checksum_sha256=sha, dataset_version='IMERG V07 Final',
        processing_version=gpm.PROCESSING_VERSION, license='NASA EOSDIS open data (no restrictions on reuse)',
        spatial_resolution=SPATIAL_RESOLUTION, temporal_resolution=TEMPORAL_RESOLUTION, limitations=limitations)
    counts = {s: sum(1 for m in monthly if m.status == s) for s in ('OBSERVED', 'MISSING', 'NOT_AVAILABLE', 'NOT_READ')}
    return PrecipitationResponse(
        kind='observation', source_kind='OBSERVED', dataset=gpm.DATASET_LABEL, source_url=gpm.DOI_URL,
        request_params=params, year=series.year,
        cell=GpmCell(latitude=series.cell_latitude, longitude=series.cell_longitude, size_degrees=gpm.GRID_STEP),
        retrieved_at=series.retrieved_at, spatial_resolution=SPATIAL_RESOLUTION,
        temporal_resolution=TEMPORAL_RESOLUTION, provenance=manifest, monthly=monthly, comparison=comparison,
        summary={'observed': counts['OBSERVED'], 'missing': counts['MISSING'],
                 'not_available': counts['NOT_AVAILABLE'], 'not_read': counts['NOT_READ'],
                 'granules_found': series.granules_found,
                 'total_observed_mm': round(sum(m.precipitation_mm for m in observed), 1) if observed else None},
        method=METHOD,
        cache={'search_from_cache': series.search_from_cache, 'months_from_cache': series.months_from_cache,
               'upstream_requests': series.requests, 'units_checked': series.units_checked},
        limitations=limitations,
        disclaimer=('Observed satellite-gauge precipitation estimate (NASA GPM IMERG Final) for a 0.1° cell, shown '
                    'next to the NASA POWER regional value. Neither is a rain-gauge reading at the field.'))


@router.get('/api/precipitation/gpm', response_model=PrecipitationResponse)
async def precipitation_gpm(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180),
                            year: int = Query(ge=1998, le=2100),
                            compare_power: bool = Query(default=True, description='Add NASA POWER monthly totals.')):
    """GPM IMERG Final monthly precipitation for the 0.1° cell containing the point, with NASA POWER totals.

    503 when Earthdata access is not configured, 502 when NASA fails. No value is ever simulated."""
    try:
        gpm.validate_year(year, datetime.now(UTC))
    except ValueError as e:
        raise HTTPException(422, detail=f'Invalid year: {e}.') from e
    try:
        series = await gpm.fetch_gpm_year(latitude, longitude, year)
    except gpm.GpmNotConfigured as e:
        raise HTTPException(503, detail=e.public_message) from e
    except gpm.GpmSourceError as e:
        raise HTTPException(502, detail=e.public_message) from e
    return await build_precipitation_response(series, compare_power)
