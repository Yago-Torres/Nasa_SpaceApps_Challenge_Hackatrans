"""ABB-07 NASA POWER adapter + /api/climate tests. Fully offline (httpx.MockTransport).

Payloads are SYNTHETIC; their header/parameters shape mirrors a live POWER daily point
response (API v2.10.3, sources MERRA2/POWER, fill_value -999.0) inspected on 2026-11-14.
"""
import asyncio
import calendar
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from agroblackbox import app as app_module
from agroblackbox.services import power

T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def payload(years=(2019, 2020, 2021, 2022), *, rain=1.0, tmax=20.0, header=True, units=True, overrides=None):
    series = {'PRECTOTCORR': {}, 'T2M_MAX': {}}
    for y in years:
        for m in range(1, 13):
            for d in range(1, calendar.monthrange(y, m)[1] + 1):
                key = f'{y:04d}{m:02d}{d:02d}'
                series['PRECTOTCORR'][key] = rain
                series['T2M_MAX'][key] = tmax
    for (name, key), value in (overrides or {}).items():
        series[name][key] = value
    body = {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-0.9, 41.6, 250.0]},
            'properties': {'parameter': series}, 'messages': [], 'times': {'data': 0.1, 'process': 0.01}}
    if header:
        body['header'] = {'title': 'NASA/POWER Source Native Resolution Daily Data',
                          'api': {'version': 'v2.10.3', 'name': 'POWER Daily API'},
                          'sources': ['MERRA2', 'POWER'], 'fill_value': -999.0, 'time_standard': 'UTC',
                          'start': f'{min(years)}0101', 'end': f'{max(years)}1231'}
    if units:
        body['parameters'] = {'PRECTOTCORR': {'units': 'mm/day', 'longname': 'Precipitation Corrected'},
                              'T2M_MAX': {'units': 'C', 'longname': 'Temperature at 2 Meters Maximum'}}
    return body


class Upstream:
    """Replays a scripted sequence of responses/exceptions and records requests."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []

    def __call__(self, request):
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, httpx.Response):
            return reply
        return httpx.Response(200, json=reply)


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Isolated cache dir, frozen clock and recorded (instant) sleeps."""
    state = {'now': T0, 'sleeps': []}
    monkeypatch.setattr(power, 'CACHE', tmp_path / 'power')
    monkeypatch.setattr(power, '_now', lambda: state['now'])

    async def fake_sleep(seconds):
        state['sleeps'].append(seconds)
    monkeypatch.setattr(power, '_sleep', fake_sleep)

    def use(upstream):
        monkeypatch.setattr(power, '_make_client', lambda: httpx.AsyncClient(transport=httpx.MockTransport(upstream)))
        return upstream
    state['use'] = use
    return state


def fetch(*args):
    return asyncio.run(power.fetch_power(*(args or (41.6, -0.9, 2022, 2019, 2021))))


# ---------------------------------------------------------------- success and provenance

def test_success_records_request_provenance_and_metadata(env):
    up = env['use'](Upstream(payload()))
    rec = fetch()
    assert len(up.requests) == 1
    q = dict(up.requests[0].url.params)
    assert q == {'latitude': '41.6', 'longitude': '-0.9', 'parameters': 'PRECTOTCORR,T2M_MAX', 'community': 'AG',
                 'start': '20190101', 'end': '20221231', 'time-standard': 'UTC', 'format': 'JSON'}
    assert up.requests[0].url.host == 'power.larc.nasa.gov'
    assert rec.retrieved_at == T0 and rec.retrieved_at.tzinfo is not None
    assert not rec.served_from_cache and rec.cache_age_seconds is None and rec.upstream_attempts == 1
    assert len(rec.sha256) == 64
    assert rec.header.api_version == 'v2.10.3' and rec.header.sources == ['MERRA2', 'POWER']
    assert rec.header.fill_value == -999.0 and rec.fill_value == -999.0 and rec.header.time_standard == 'UTC'
    assert rec.variables['PRECTOTCORR'].units == 'mm/day' and rec.variables['PRECTOTCORR'].units_reported_by_source
    assert rec.variables['T2M_MAX'].longname == 'Temperature at 2 Meters Maximum'


def test_missing_header_uses_documented_defaults_and_says_so(env):
    env['use'](Upstream(payload(header=False, units=False)))
    rec = fetch()
    assert rec.header.fill_value is None and rec.fill_value == power.DEFAULT_FILL_VALUE
    assert not rec.variables['T2M_MAX'].units_reported_by_source and rec.variables['T2M_MAX'].units == 'C'


# ---------------------------------------------------------------- cache

def test_cache_hit_reports_original_retrieval_time_and_age(env):
    up = env['use'](Upstream(payload()))
    first = fetch()
    env['now'] = T0 + timedelta(hours=2)
    second = fetch()
    assert len(up.requests) == 1
    assert second.served_from_cache and second.upstream_attempts == 0
    assert second.retrieved_at == T0 and second.cache_age_seconds == 7200
    assert second.sha256 == first.sha256


def test_expired_corrupt_and_legacy_cache_entries_are_refetched(env):
    up = env['use'](Upstream(payload()))
    fetch()
    env['now'] = T0 + timedelta(seconds=power.CACHE_TTL_SECONDS)
    assert not fetch().served_from_cache  # expired
    data_path, meta_path = power._cache_paths(power.cache_key(power.build_params(41.6, -0.9, 2022, 2019, 2021)))
    data_path.write_bytes(data_path.read_bytes() + b' ')
    assert not fetch().served_from_cache  # checksum mismatch
    meta_path.unlink()
    assert not fetch().served_from_cache  # legacy entry without sidecar
    assert len(up.requests) == 4
    assert fetch().served_from_cache


def test_invalid_payload_is_never_cached(env):
    up = env['use'](Upstream(httpx.Response(200, content=b'<html>maintenance</html>'), payload()))
    with pytest.raises(power.PowerSourceError):
        fetch()
    assert not power.CACHE.exists() or not list(power.CACHE.iterdir())
    assert not fetch().served_from_cache
    assert len(up.requests) == 2


# ---------------------------------------------------------------- in-flight deduplication (ABB-27)

def test_concurrent_identical_requests_trigger_one_upstream_call(env):
    """Two concurrent fetch_power() calls for identical parameters, with nothing yet
    in the on-disk cache, must result in exactly one NASA POWER request: the second
    caller joins the first's in-flight task instead of downloading again."""
    calls = []
    release = asyncio.Event()

    async def slow_upstream(request):
        calls.append(request)
        await release.wait()
        return httpx.Response(200, json=payload())

    env['use'](slow_upstream)

    async def go():
        t1 = asyncio.ensure_future(power.fetch_power(41.6, -0.9, 2022, 2019, 2021))
        t2 = asyncio.ensure_future(power.fetch_power(41.6, -0.9, 2022, 2019, 2021))
        await asyncio.sleep(0)  # let both callers reach the registry and join one task
        release.set()
        return await asyncio.gather(t1, t2)

    rec1, rec2 = asyncio.run(go())
    assert len(calls) == 1
    assert rec1.sha256 == rec2.sha256 and not rec1.served_from_cache and not rec2.served_from_cache


def test_concurrent_different_requests_are_not_deduplicated(env):
    """Different parameters must never share a dedup slot."""
    up = env['use'](Upstream(payload(), payload()))

    async def go():
        return await asyncio.gather(
            power.fetch_power(41.6, -0.9, 2022, 2019, 2021),
            power.fetch_power(10.0, 10.0, 2022, 2019, 2021),
        )

    asyncio.run(go())
    assert len(up.requests) == 2


def test_concurrent_requests_share_an_upstream_failure(env):
    """If the single shared download fails, every waiting caller gets the same clean,
    recoverable error - never a fabricated value for the callers that did not "own"
    the request."""
    calls = []
    release = asyncio.Event()

    async def failing_upstream(request):
        calls.append(request)
        await release.wait()
        return httpx.Response(503)

    env['use'](failing_upstream)

    async def go():
        async def call():
            with pytest.raises(power.PowerSourceError):
                await power.fetch_power(41.6, -0.9, 2022, 2019, 2021)

        t1 = asyncio.ensure_future(call())
        t2 = asyncio.ensure_future(call())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(t1, t2)

    asyncio.run(go())
    # the shared download still gets its own bounded retries (MAX_ATTEMPTS), just once
    assert len(calls) == power.MAX_ATTEMPTS


# ---------------------------------------------------------------- retries and errors

def test_retries_5xx_with_backoff_then_succeeds(env):
    up = env['use'](Upstream(httpx.Response(503), httpx.Response(502), payload()))
    rec = fetch()
    assert rec.upstream_attempts == 3 and len(up.requests) == 3
    assert env['sleeps'] == [1.0, 2.0]


def test_429_honours_short_retry_after(env):
    up = env['use'](Upstream(httpx.Response(429, headers={'Retry-After': '3'}), payload()))
    assert fetch().upstream_attempts == 2
    assert env['sleeps'] == [3.0] and len(up.requests) == 2


def test_429_with_long_retry_after_is_not_retried(env):
    up = env['use'](Upstream(httpx.Response(429, headers={'Retry-After': '120'})))
    with pytest.raises(power.PowerSourceError) as e:
        fetch()
    assert e.value.reason == 'rate_limited' and len(up.requests) == 1 and env['sleeps'] == []


def test_retries_are_bounded(env):
    up = env['use'](Upstream(httpx.Response(500)))
    with pytest.raises(power.PowerSourceError) as e:
        fetch()
    assert len(up.requests) == power.MAX_ATTEMPTS
    assert e.value.public_message == 'NASA POWER is unavailable (HTTP 500).'


@pytest.mark.parametrize('exc,reason', [(httpx.ReadTimeout('slow'), 'timeout'),
                                        (httpx.ConnectError('refused'), 'network')])
def test_timeouts_and_network_errors(env, exc, reason):
    up = env['use'](Upstream(exc))
    with pytest.raises(power.PowerSourceError) as e:
        fetch()
    assert e.value.reason == reason and len(up.requests) == power.MAX_ATTEMPTS


def test_client_errors_are_not_retried(env):
    up = env['use'](Upstream(httpx.Response(422, json={'messages': ['bad request']})))
    with pytest.raises(power.PowerSourceError) as e:
        fetch()
    assert e.value.reason == 'rejected' and len(up.requests) == 1


@pytest.mark.parametrize('mutate', [
    lambda b: b.pop('properties'),
    lambda b: b['properties']['parameter'].pop('T2M_MAX'),
    lambda b: b['properties']['parameter']['PRECTOTCORR'].update({'2022-01-01': 1.0}),
    lambda b: b['properties']['parameter']['PRECTOTCORR'].update({'20220101': 'n/a'}),
    lambda b: b['properties']['parameter']['T2M_MAX'].update({'20220101': True}),
    lambda b: b['parameters']['PRECTOTCORR'].update({'units': 'kg m-2 s-1'}),
    lambda b: b['header'].update({'time_standard': 'LST'}),
    lambda b: b['header'].update({'fill_value': 'none'}),
])
def test_incomplete_or_unexpected_responses_are_rejected(env, mutate):
    body = payload()
    mutate(body)
    env['use'](Upstream(body))
    with pytest.raises(power.PowerSourceError) as e:
        fetch()
    assert e.value.reason == 'invalid_response'


def test_public_errors_never_contain_urls_or_query(env):
    for reply in (httpx.Response(500), httpx.ReadTimeout('https://power.larc.nasa.gov/?latitude=41.6'),
                  httpx.Response(200, content=b'{}')):
        env['use'](Upstream(reply))
        with pytest.raises(power.PowerSourceError) as e:
            fetch()
        assert 'http' not in e.value.public_message and '41.6' not in e.value.public_message


# ---------------------------------------------------------------- endpoint

async def call(path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_module.app), base_url='http://test') as c:
        return await c.get(path)


URL = '/api/climate?latitude=41.6&longitude=-0.9&event_year=2022&reference_start=2019&reference_end=2021'


def test_endpoint_keeps_baseline_keys_and_adds_provenance(env):
    env['use'](Upstream(payload(overrides={('PRECTOTCORR', '20220315'): -999.0})))
    r = asyncio.run(call(URL))
    assert r.status_code == 200
    body = r.json()
    # baseline keys consumed by the React client keep their meaning
    assert body['kind'] == 'observation' and body['dataset'] == 'NASA POWER daily point'
    assert body['source_url'] == 'https://power.larc.nasa.gov/docs/services/api/temporal/daily/'
    assert len(body['data_sha256']) == 64 and body['request_params']['community'] == 'AG'
    assert (body['event_year'], body['reference_start'], body['reference_end']) == (2022, 2019, 2021)
    assert len(body['monthly']) == 12 and 'disclaimer' in body
    jan = body['monthly'][0]
    assert jan['precipitation_anomaly_mm'] == 0.0 and jan['max_temperature_anomaly_c'] == 0.0
    # ABB-07 provenance
    assert body['source_kind'] == 'OBSERVED'
    assert body['retrieved_at'] == '2026-11-14T12:00:00Z'
    assert body['spatial_resolution']['unit'] == 'degree' and '0.625°' in body['spatial_resolution']['description']
    assert body['temporal_resolution'] == {'value': 1.0, 'unit': 'day', 'description': power_temporal()}
    prov = body['provenance']
    assert prov['provider'] == 'NASA POWER' and prov['source_uri'] == power.BASE
    assert prov['checksum_sha256'] == body['data_sha256'] and prov['retrieved_at'] == body['retrieved_at']
    assert prov['dataset_version'] == 'POWER Daily API v2.10.3'
    assert prov['processing_version'] == power.PROCESSING_VERSION and prov['schema_version'] == '1.0'
    assert prov['query_parameters']['time-standard'] == 'UTC' and prov['limitations']
    assert body['upstream']['sources'] == ['MERRA2', 'POWER'] and body['upstream']['fill_value'] == -999.0
    assert body['cache'] == {'served_from_cache': False, 'cache_age_seconds': None,
                             'ttl_seconds': power.CACHE_TTL_SECONDS, 'upstream_attempts': 1}
    assert {v['source_parameter']: v['source_units'] for v in body['variables']} == {'PRECTOTCORR': 'mm/day',
                                                                                     'T2M_MAX': 'C'}
    # ABB-08 quality and method; fill value is missing data, never a value
    mar = body['monthly'][2]
    assert mar['precipitation_mm'] is None and mar['precipitation_anomaly_mm'] is None
    assert mar['quality']['precipitation']['status'] == 'partial'
    assert mar['quality']['precipitation']['fill_value_days'] == 1
    assert '-999' not in json.dumps([m['precipitation_mm'] for m in body['monthly']])
    assert body['method']['reference_is_climatological_normal'] is False
    assert body['quality']['status'] == 'partial' and body['quality']['warnings']
    assert any('not a 30-year climatological normal' in x for x in body['limitations'])
    # second call is served from cache and says so
    env['now'] = T0 + timedelta(minutes=5)
    cached = asyncio.run(call(URL)).json()
    assert cached['cache']['served_from_cache'] and cached['cache']['cache_age_seconds'] == 300
    assert cached['retrieved_at'] == '2026-11-14T12:00:00Z'


def power_temporal():
    from agroblackbox.climate import TEMPORAL_RESOLUTION
    return TEMPORAL_RESOLUTION.description


def test_endpoint_upstream_failure_is_502_without_simulated_values(env):
    env['use'](Upstream(httpx.Response(503)))
    r = asyncio.run(call(URL))
    assert r.status_code == 502
    assert r.json() == {'detail': 'NASA POWER is unavailable (HTTP 503).'}


def test_endpoint_no_event_data_is_502(env):
    env['use'](Upstream(payload(years=(2019, 2020, 2021))))
    r = asyncio.run(call(URL))
    assert r.status_code == 502
    assert 'No usable precipitation observations' in r.json()['detail']
    assert 'http' not in r.json()['detail']


@pytest.mark.parametrize('query', [
    'latitude=41.6&longitude=-0.9&event_year=2020&reference_start=2019&reference_end=2021',
    'latitude=41.6&longitude=-0.9&event_year=2022&reference_start=2020&reference_end=2021',
    'latitude=91&longitude=-0.9&event_year=2022',
    'latitude=41.6&longitude=-0.9&event_year=1980',
])
def test_endpoint_rejects_invalid_requests_without_calling_upstream(env, query):
    up = env['use'](Upstream(payload()))
    assert asyncio.run(call(f'/api/climate?{query}')).status_code == 422
    assert up.requests == []


def test_openapi_documents_typed_climate_response():
    schema = app_module.app.openapi()
    op = schema['paths']['/api/climate']['get']
    ref = op['responses']['200']['content']['application/json']['schema']['$ref']
    assert ref.endswith('/ClimateResponse')
