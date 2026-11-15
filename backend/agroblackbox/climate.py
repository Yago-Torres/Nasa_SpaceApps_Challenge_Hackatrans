"""GET /api/climate (ABB-07 provenance + ABB-08 quality control).

Backward compatible with the development baseline: every key the React client reads keeps
its meaning; provenance, resolutions, quality flags and the anomaly method are additive.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .schemas import Resolution, SourceManifest
from .services import power
from .services.forensics import default_reference_window
from .services.metrics import MIN_REFERENCE_YEARS, NORMAL_PERIOD_YEARS, VARIABLES, analyze_power

router = APIRouter(tags=['climate (ABB-07, ABB-08)'])

# Without explicit reference years, the event year is compared with the years just before it, so
# every year from FIRST_EVENT_YEAR can be investigated (a fixed window would exclude its own years).
DEFAULT_REFERENCE_YEARS = 10
POWER_FIRST_YEAR = 1981
FIRST_EVENT_YEAR = POWER_FIRST_YEAR + MIN_REFERENCE_YEARS   # 1984: 1981-1983 is the shortest valid window


class _Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ReferenceCoverage(_Model):
    status: Literal['complete', 'reduced', 'insufficient']
    years_expected: int
    sample_count: int = Field(description='Reference years with complete daily coverage used for this month.')
    years_excluded: list[int]
    standard_deviation: float | None = Field(description='Sample SD of the monthly reference values (n-1).')
    minimum: float | None
    maximum: float | None
    reason: str | None


class VariableMonthQuality(_Model):
    status: Literal['complete', 'partial', 'missing'] = Field(description='Event-year daily coverage of the month.')
    reason: str | None
    expected_days: int
    valid_days: int
    missing_days: int
    fill_value_days: int
    absent_days: int
    invalid_days: int
    flags: list[str]
    reference: ReferenceCoverage
    anomaly_computed: bool
    anomaly_reason: str | None
    units: str


class MonthQuality(_Model):
    precipitation: VariableMonthQuality
    max_temperature: VariableMonthQuality


class ClimateMonth(_Model):
    month: int = Field(ge=1, le=12)
    precipitation_mm: float | None
    reference_precipitation_mm: float | None
    precipitation_anomaly_mm: float | None
    max_temperature_c: float | None
    reference_max_temperature_c: float | None
    max_temperature_anomaly_c: float | None
    quality: MonthQuality


class VariableQualityCounts(_Model):
    complete_months: int
    partial_months: int
    missing_months: int
    anomalies_computed: int
    months_with_reference_years_excluded: int
    months_with_insufficient_reference: int


class ClimateQuality(_Model):
    status: Literal['complete', 'partial', 'insufficient']
    fill_value: float
    variables: dict[str, VariableQualityCounts]
    warnings: list[str]


class AnomalyMethod(_Model):
    id: str
    description: str
    anomaly_formula: str
    event_year: int
    reference_start: int
    reference_end: int
    reference_years: int
    minimum_reference_years: int
    reference_is_climatological_normal: bool
    reference_label: str
    completeness_rule: str
    daily_time_standard: Literal['UTC']
    aggregations: dict[str, str]
    valid_ranges: dict[str, dict[str, float | str]]
    uncertainty: str
    processing_version: str


class ClimateVariable(_Model):
    key: str
    source_parameter: str
    source_longname: str | None
    source_units: str
    units_reported_by_source: bool
    monthly_aggregation: str
    monthly_units: str
    anomaly_units: str


class PowerUpstreamMetadata(_Model):
    """Metadata exactly as reported in the NASA POWER response header (null when absent)."""
    title: str | None
    api_name: str | None
    api_version: str | None
    sources: list[str]
    fill_value: float | None
    time_standard: str | None
    start: str | None
    end: str | None
    messages: list[str]


class CacheStatus(_Model):
    served_from_cache: bool
    cache_age_seconds: float | None
    ttl_seconds: int
    upstream_attempts: int = Field(description='HTTP attempts for this answer (0 when served from cache).')


class ClimateResponse(_Model):
    # --- baseline keys (unchanged meaning) ---
    kind: Literal['observation']
    dataset: str
    source_url: str
    data_sha256: str
    request_params: dict[str, str | float]
    event_year: int
    reference_start: int
    reference_end: int
    monthly: list[ClimateMonth]
    disclaimer: str
    # --- ABB-07 provenance (additive) ---
    source_kind: Literal['OBSERVED']
    retrieved_at: datetime
    spatial_resolution: Resolution
    temporal_resolution: Resolution
    provenance: SourceManifest
    upstream: PowerUpstreamMetadata
    cache: CacheStatus
    variables: list[ClimateVariable]
    # --- ABB-08 quality control and method (additive) ---
    method: AnomalyMethod
    quality: ClimateQuality
    limitations: list[str]


SPATIAL_RESOLUTION = Resolution(
    value=None, unit='degree',
    description=('0.5° latitude × 0.625° longitude grid (½° × ⅝°, GMAO MERRA-2 native meteorological grid, per '
                 'NASA POWER methodology documentation consulted 2026-11-14). Regional grid-cell value, not a '
                 'field measurement. Grid size is not reported in the API response.'))
TEMPORAL_RESOLUTION = Resolution(
    value=1, unit='day',
    description='Daily values on UTC days (time-standard=UTC), aggregated by this service to calendar months.')


def _limitations(record: power.PowerRecord, method: dict[str, Any]) -> list[str]:
    items = [
        'NASA POWER values describe a ½° × ⅝° regional grid cell, not a field or rain-gauge measurement.',
        'PRECTOTCORR is a bias-corrected reanalysis precipitation estimate (MERRA-2), not a station reading.',
        'Daily values use UTC days, which may not match local calendar days.',
        method['reference_label'],
        'Anomalies are descriptive differences from a reference mean without significance testing; '
        'they do not establish causes of crop damage.',
    ]
    if record.header.api_version:
        items.append('dataset_version is the POWER API version reported in the response header; the response '
                     'does not report a data release version.')
    if not all(v.units_reported_by_source for v in record.variables.values()):
        items.append('Some units were not reported in the response and are taken from NASA POWER documentation.')
    if record.header.sources and not any('MERRA' in s.upper() for s in record.header.sources):
        items.append('The response did not list MERRA-2 as a source; the stated grid resolution may not apply.')
    end = record.request_params.get('end')
    if isinstance(end, str):
        end_date = date(int(end[:4]), int(end[4:6]), int(end[6:]))
        if (record.retrieved_at.date() - end_date).days < 62:
            items.append('The requested period ends less than about two months before retrieval; NASA POWER '
                         'recommends ending climate analyses about 2 months behind near real time because recent '
                         'days come from a near-real-time product.')
    return items


def _manifest_id(sha: str, params: dict[str, Any]) -> uuid.UUID:
    canonical = '&'.join(f'{k}={params[k]}' for k in sorted(params))
    return uuid.uuid5(uuid.NAMESPACE_URL, f'{power.BASE}?{canonical}#sha256={sha}')


def build_climate_response(record: power.PowerRecord, analysis: dict[str, Any], event_year: int,
                           reference_start: int, reference_end: int) -> ClimateResponse:
    method = {**analysis['method'], 'processing_version': power.PROCESSING_VERSION}
    limitations = _limitations(record, method)
    header = record.header
    dataset_version = ' '.join(p for p in (header.api_name, header.api_version) if p) or None
    manifest = SourceManifest(
        id=_manifest_id(record.sha256, record.request_params), provider=power.PROVIDER, dataset=power.DATASET,
        source_uri=power.BASE, query_parameters=dict(record.request_params), retrieved_at=record.retrieved_at,
        checksum_sha256=record.sha256, dataset_version=dataset_version,
        processing_version=power.PROCESSING_VERSION, license=None,
        spatial_resolution=SPATIAL_RESOLUTION, temporal_resolution=TEMPORAL_RESOLUTION, limitations=limitations)
    variables = [
        ClimateVariable(key=s.key, source_parameter=s.source_parameter,
                        source_longname=record.variables[s.source_parameter].longname,
                        source_units=record.variables[s.source_parameter].units,
                        units_reported_by_source=record.variables[s.source_parameter].units_reported_by_source,
                        monthly_aggregation=s.aggregation_text, monthly_units=s.monthly_units,
                        anomaly_units=s.monthly_units)
        for s in VARIABLES]
    n_ref = reference_end - reference_start + 1
    disclaimer = ('Gridded regional meteorology, not a field reading. Anomalies are descriptive and do not '
                  'establish crop-failure causes. '
                  + ('Short reference period, not a climatological normal.' if n_ref < NORMAL_PERIOD_YEARS
                     else 'Reference period is not an official WMO climatological normal.'))
    return ClimateResponse(
        kind='observation', dataset=power.DATASET_LABEL, source_url=power.DOCS_URL, data_sha256=record.sha256,
        request_params=dict(record.request_params), event_year=event_year, reference_start=reference_start,
        reference_end=reference_end, monthly=analysis['monthly'], disclaimer=disclaimer,
        source_kind='OBSERVED', retrieved_at=record.retrieved_at, spatial_resolution=SPATIAL_RESOLUTION,
        temporal_resolution=TEMPORAL_RESOLUTION, provenance=manifest,
        upstream=PowerUpstreamMetadata(title=header.title, api_name=header.api_name, api_version=header.api_version,
                                       sources=list(header.sources), fill_value=header.fill_value,
                                       time_standard=header.time_standard, start=header.start, end=header.end,
                                       messages=list(record.messages)),
        cache=CacheStatus(served_from_cache=record.served_from_cache, cache_age_seconds=record.cache_age_seconds,
                          ttl_seconds=power.CACHE_TTL_SECONDS, upstream_attempts=record.upstream_attempts),
        variables=variables, method=method, quality=analysis['quality'], limitations=limitations)


@router.get('/api/climate', response_model=ClimateResponse)
async def climate(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180),
                  event_year: int = Query(ge=POWER_FIRST_YEAR, le=2100,
                                          description='Up to the current year; months not yet complete get no value.'),
                  reference_start: int | None = Query(
                      default=None, ge=POWER_FIRST_YEAR, le=2100,
                      description=f'Default: the {DEFAULT_REFERENCE_YEARS} years before event_year (from 1981).'),
                  reference_end: int | None = Query(default=None, ge=POWER_FIRST_YEAR, le=2100,
                                                    description='Default: event_year - 1.')):
    """NASA POWER daily point data aggregated to monthly anomalies with provenance and quality flags.

    Upstream failures return 502 with a short generic message; no value is ever simulated."""
    current_year = date.today().year
    if event_year > current_year:
        raise HTTPException(422, detail='Event year cannot be in the future.')
    if (reference_start is None) != (reference_end is None):
        raise HTTPException(422, detail='Send both reference years or neither.')
    if reference_start is None or reference_end is None:
        reference_start, reference_end = default_reference_window(
            event_year, years=DEFAULT_REFERENCE_YEARS, earliest=POWER_FIRST_YEAR)
    if reference_end > current_year:
        raise HTTPException(422, detail='Reference years cannot be in the future.')
    if reference_end < reference_start or reference_start <= event_year <= reference_end:
        raise HTTPException(422, detail='Reference years must be ordered and exclude event year.')
    if reference_end - reference_start + 1 < MIN_REFERENCE_YEARS:
        raise HTTPException(422, detail='At least 3 reference years required')
    try:
        record = await power.fetch_power(latitude, longitude, event_year, reference_start, reference_end)
    except power.PowerSourceError as e:
        raise HTTPException(502, detail=e.public_message) from e
    try:
        analysis = analyze_power(record.parameter, event_year, reference_start, reference_end,
                                 fill_value=record.fill_value)
    except ValueError as e:  # messages are generated by metrics.py and contain no upstream data
        raise HTTPException(502, detail=f'NASA POWER data unusable: {e}.') from e
    return build_climate_response(record, analysis, event_year, reference_start, reference_end)
