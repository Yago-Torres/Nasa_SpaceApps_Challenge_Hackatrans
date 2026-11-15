"""ABB-09 offline tests: GPM IMERG monthly adapter, POWER comparison and API.

All values are SYNTHETIC answers in the exact OPeNDAP ASCII / DAS / CMR shapes observed on 2026-11-15; no test
reads NASA data. The real service is exercised by ``test_real_sources_smoke.py`` through the manual
``earthdata-smoke`` workflow, and the OPeNDAP reading was cross-checked against the full HDF5 granule with h5py.
"""
from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime

import httpx
import pytest

from agroblackbox.app import app
from agroblackbox.services import gpm, power

LAT, LON, YEAR = 41.65, -0.88, 2022
I, J = gpm.cell_indices(LAT, LON)
CELL_LAT, CELL_LON = gpm.cell_center(I, J)

DAS = b'''Attributes {
    precipitation {
        String Units "mm/hr";
        String units "mm/hr";
        Float32 _FillValue -9999.900391;
    }
    gaugeRelativeWeighting {
        String Units "percent";
        String units "percent";
        Int16 _FillValue -9999;
    }
    randomError {
        String Units "mm/hr";
        String units "mm/hr";
    }
}
'''


def ascii_answer(rate=0.032, error=0.006, quality=0.9, gauge=90, lat=CELL_LAT, lon=CELL_LON, name='x.HDF5') -> bytes:
    return (f'Dataset: {name}\nprecipitation[0][0], {rate}\nrandomError[0][0], {error}\n'
            f'precipitationQualityIndex[0][0], {quality}\ngaugeRelativeWeighting[0][0], {gauge}\n'
            f'lat, {lat}\nlon, {lon}\n').encode()


def granule_name(month: int, letter='B') -> str:
    return f'3B-MO.MS.MRG.3IMERG.{YEAR}{month:02d}01-S000000-E235959.{month:02d}.V07{letter}.HDF5'


def cmr_entry(month: int, letter='B', *, host='https://data.gesdisc.earthdata.nasa.gov/data/'):
    name = granule_name(month, letter)
    return {'title': f'GPM_3IMERGM.07:{name}',
            'links': [{'href': f'{host}GPM_L3/GPM_3IMERGM.07/{YEAR}/{name}'},
                      {'href': f's3://gesdisc-cumulus-prod-protected/GPM_L3/GPM_3IMERGM.07/{YEAR}/{name}'}]}


class FakeNasa:
    def __init__(self, months=range(1, 13), *, answers=None, fail=None, das=DAS, entries=None):
        self.entries = entries if entries is not None else [cmr_entry(m) for m in months]
        self.answers = answers or {}
        self.fail = fail or {}
        self.das = das
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == 'cmr.earthdata.nasa.gov':
            return httpx.Response(200, json={'feed': {'entry': self.entries}})
        assert request.url.host == 'gpm1.gesdisc.eosdis.nasa.gov'
        path = request.url.path
        if path.endswith('.das'):
            return httpx.Response(200, content=self.das)
        month = int(path.rsplit('/', 1)[-1].split('.')[4][4:6])
        if month in self.fail:
            return httpx.Response(self.fail[month])
        return httpx.Response(200, content=self.answers.get(month, ascii_answer()))

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler), follow_redirects=True)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(gpm, 'CACHE', tmp_path / 'gpm')
    monkeypatch.setenv('EARTHDATA_TOKEN', 'test-token-not-real')

    async def no_sleep(_):
        return None
    monkeypatch.setattr(gpm, '_sleep', no_sleep)


async def run(fake: FakeNasa, lat=LAT, lon=LON, year=YEAR):
    async with fake.client() as client:
        return await gpm.fetch_gpm_year(lat, lon, year, client=client)


# --------------------------------------------------------------------------- grid and parsing

@pytest.mark.parametrize('lat,lon,expected', [
    (41.65, -0.88, (1791, 1316)), (-89.99, -180.0, (0, 0)), (90.0, 180.0, (3599, 1799)),
    (0.0, 0.0, (1800, 900)), (-0.01, -0.01, (1799, 899)), (41.7, -3.95, (1760, 1317)),
])
def test_cell_indices_contain_the_point(lat, lon, expected):
    assert gpm.cell_indices(lat, lon) == expected
    i, j = expected
    c_lat, c_lon = gpm.cell_center(i, j)
    assert abs(c_lat - lat) <= 0.05 + 1e-9 or lat in (90.0, -89.99)
    assert abs(c_lon - lon) <= 0.05 + 1e-9 or lon in (180.0, -180.0)


def test_live_probe_cell_matches_the_index_formula():
    # 2026-11-15 probe: precipitation[0][1760][1300] answered lat 40.05, lon -3.95
    assert gpm.cell_center(1760, 1300) == (40.05, -3.95)


@pytest.mark.parametrize('year,month,hours', [(2022, 6, 720), (2022, 2, 672), (2024, 2, 696), (2022, 1, 744)])
def test_month_hours(year, month, hours):
    assert gpm.month_hours(year, month) == hours


def test_parse_ascii_and_reject_odd_answers():
    values = gpm.parse_ascii(ascii_answer(rate='3.2e-02'))
    assert values['precipitation'] == pytest.approx(0.032) and values['lat'] == CELL_LAT
    for bad in (b'<html>login</html>', b'Dataset: x\nprecipitation[0][0], abc\n',
                b'Dataset: x\nprecipitation[0][0], 1\n', b'\xff\xfe'):
        with pytest.raises(gpm.GpmSourceError, match='unexpected'):
            gpm.parse_ascii(bad)


def test_units_are_checked_against_the_attributes():
    gpm.check_units(DAS)
    with pytest.raises(gpm.GpmSourceError, match='units'):
        gpm.check_units(DAS.replace(b'String units "mm/hr";\n        Float32', b'String units "mm/day";\n        Float32'))
    with pytest.raises(gpm.GpmSourceError, match='units'):
        gpm.check_units(b'Attributes {}')


def test_parse_granules_keeps_valid_entries_and_the_latest_processing_letter():
    entries = [cmr_entry(1, 'A'), cmr_entry(1, 'B'), cmr_entry(2), cmr_entry(3, host='https://evil.example/data/'),
               {'title': 'GPM_3IMERGM.07:3B-MO.MS.MRG.3IMERG.20210101-S000000-E235959.01.V07B.HDF5', 'links': []},
               {'title': 'something else'}, 'not-a-dict']
    granules = gpm.parse_granules(json.dumps({'feed': {'entry': entries}}).encode(), YEAR)
    assert [(g.month, g.granule_id[-9:]) for g in granules] == [(1, 'V07B.HDF5'), (2, 'V07B.HDF5')]
    assert granules[0].opendap_url.startswith('https://gpm1.gesdisc.eosdis.nasa.gov/opendap/GPM_L3/GPM_3IMERGM.07/2022/')
    with pytest.raises(gpm.GpmSourceError, match='CMR'):
        gpm.parse_granules(b'{"feed": {"entry": 3}}', YEAR)


# --------------------------------------------------------------------------- pipeline

@pytest.mark.asyncio
async def test_twelve_months_converted_from_rate_to_totals_with_error_and_provenance():
    answers = {2: ascii_answer(rate=0.1, error=0.02), 6: ascii_answer(rate=0.032, error=0.006)}
    fake = FakeNasa(answers=answers)
    series = await run(fake)
    assert [m.month for m in series.months] == list(range(1, 13)) and series.units_checked
    feb, jun = series.months[1], series.months[5]
    assert feb.status == 'OBSERVED' and feb.hours == 672 and feb.precipitation_mm == 67.2 and feb.random_error_mm == 13.4
    assert jun.precipitation_mm == 23.0 and jun.random_error_mm == 4.3 and jun.gauge_weight_percent == 90
    assert len(jun.data_sha256) == 64 and (series.cell_latitude, series.cell_longitude) == (CELL_LAT, CELL_LON)
    assert series.requests == 14   # CMR + DAS + 12 months


@pytest.mark.asyncio
async def test_fill_values_are_missing_not_zero():
    fake = FakeNasa(answers={3: ascii_answer(rate=-9999.9, error=-9999.9, gauge=-9999),
                             4: ascii_answer(error=-9999.9, gauge=-9999)})
    series = await run(fake)
    march, april = series.months[2], series.months[3]
    assert march.status == 'MISSING' and march.precipitation_mm is None and 'fill' in march.reason
    assert april.status == 'OBSERVED' and april.random_error_mm is None and april.gauge_weight_percent is None


@pytest.mark.asyncio
async def test_unpublished_months_are_not_available():
    series = await run(FakeNasa(months=range(1, 10)))
    assert [m.status for m in series.months[9:]] == ['NOT_AVAILABLE'] * 3
    assert all(m.precipitation_mm is None and m.reason for m in series.months[9:])


@pytest.mark.asyncio
async def test_wrong_cell_or_negative_rate_is_not_accepted():
    fake = FakeNasa(answers={5: ascii_answer(lat=CELL_LAT + 0.1), 6: ascii_answer(rate=-1.0)})
    series = await run(fake)
    assert series.months[4].status == 'NOT_READ' and 'different grid cell' in series.months[4].reason
    assert series.months[5].status == 'NOT_READ' and 'negative' in series.months[5].reason
    assert series.months[0].status == 'OBSERVED'


@pytest.mark.asyncio
async def test_one_failing_month_is_reported_and_retried():
    fake = FakeNasa(fail={7: 503})
    series = await run(fake)
    assert series.months[6].status == 'NOT_READ' and 'HTTP 503' in series.months[6].reason
    assert sum(1 for r in fake.requests if f'{YEAR}0701' in r.url.path) == gpm.MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_every_month_failing_is_an_honest_error():
    with pytest.raises(gpm.GpmSourceError) as info:
        await run(FakeNasa(fail={m: 500 for m in range(1, 13)}))
    assert info.value.reason == 'upstream_error'


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [401, 403])
async def test_refused_credentials_stop_everything(status):
    with pytest.raises(gpm.GpmSourceError) as info:
        await run(FakeNasa(fail={m: status for m in range(1, 13)}))
    assert info.value.reason == 'unauthorized' and 'terms' in info.value.public_message


@pytest.mark.asyncio
async def test_a_redirect_to_the_login_page_is_unauthorized_and_the_token_is_not_forwarded():
    class Login(FakeNasa):
        def handler(self, request):
            if request.url.host == 'urs.earthdata.nasa.gov':
                self.requests.append(request)
                return httpx.Response(200, content=b'<html>Earthdata Login</html>')
            if request.url.path.endswith('.das'):
                return httpx.Response(302, headers={'Location': 'https://urs.earthdata.nasa.gov/oauth/authorize'})
            return super().handler(request)
    fake = Login()
    with pytest.raises(gpm.GpmSourceError) as info:
        await run(fake)
    assert info.value.reason == 'unauthorized'
    login = [r for r in fake.requests if r.url.host == 'urs.earthdata.nasa.gov']
    assert login and all('authorization' not in r.headers for r in login)


@pytest.mark.asyncio
async def test_token_only_goes_to_ges_disc():
    fake = FakeNasa()
    await run(fake)
    for r in fake.requests:
        assert ('authorization' in r.headers) == (r.url.host in gpm.AUTH_HOSTS)


@pytest.mark.asyncio
async def test_wrong_units_stop_before_any_value_is_accepted():
    fake = FakeNasa(das=DAS.replace(b'"mm/hr"', b'"mm/day"'))
    with pytest.raises(gpm.GpmSourceError, match='units'):
        await run(fake)
    assert not (gpm.CACHE / 'months').exists() and not (gpm.CACHE / 'units').exists()   # nothing accepted


class SlowNasa(FakeNasa):
    """GES DISC answering slowly (2026-11-15: 23-50 s per DAS) or timing out, in scaled-down time."""

    def __init__(self, *, das_delay=0.0, month_delay=None, timeout_months=(), **kw):
        super().__init__(**kw)
        self.das_delay, self.month_delay, self.timeout_months = das_delay, month_delay or {}, set(timeout_months)

    async def handler(self, request):
        import asyncio
        path = request.url.path
        if path.endswith('.das'):
            await asyncio.sleep(self.das_delay)
        elif request.url.host != 'cmr.earthdata.nasa.gov':
            month = int(path.rsplit('/', 1)[-1].split('.')[4][4:6])
            if month in self.timeout_months:
                self.requests.append(request)
                raise httpx.ReadTimeout('slow', request=request)
            await asyncio.sleep(self.month_delay.get(month, 0.0))
        return super().handler(request)


@pytest.mark.asyncio
async def test_a_timed_out_read_is_not_retried_and_only_that_month_is_lost():
    fake = SlowNasa(timeout_months={4})
    series = await run(fake)
    assert series.months[3].status == 'NOT_READ' and 'did not respond in time' in series.months[3].reason
    assert sum(1 for r in fake.requests if f'{YEAR}0401' in r.url.path) == 1
    assert sum(m.status == 'OBSERVED' for m in series.months) == 11


@pytest.mark.asyncio
async def test_a_slow_units_check_runs_alongside_the_month_reads(monkeypatch):
    monkeypatch.setattr(gpm, 'TIME_BUDGET_SECONDS', 5.0)
    import time
    start = time.monotonic()
    series = await run(SlowNasa(das_delay=0.4, month_delay={m: 0.4 for m in range(1, 6)}))
    # DAS + 5 slow months fit in the 6 concurrent slots: ~0.4 s, versus >= 0.8 s for DAS-then-months
    assert time.monotonic() - start < 0.7
    assert series.units_checked and not series.units_from_cache
    assert all(m.status == 'OBSERVED' for m in series.months)


@pytest.mark.asyncio
async def test_months_beyond_the_time_budget_are_not_read_and_a_retry_completes_them(monkeypatch):
    monkeypatch.setattr(gpm, 'TIME_BUDGET_SECONDS', 0.3)
    first = await run(SlowNasa(month_delay={11: 5.0, 12: 5.0}))
    assert [m.status for m in first.months[10:]] == ['NOT_READ', 'NOT_READ']
    assert all('time limit' in m.reason and m.precipitation_mm is None for m in first.months[10:])
    assert all(m.status == 'OBSERVED' for m in first.months[:10]) and first.units_checked
    fake = SlowNasa()
    second = await run(fake)
    assert second.months_from_cache == 10 and all(m.status == 'OBSERVED' for m in second.months)
    assert not any(r.url.path.endswith('.das') for r in fake.requests)   # units check cached
    assert second.units_checked and second.units_from_cache


@pytest.mark.asyncio
async def test_units_check_beyond_the_time_budget_is_an_error_and_accepts_nothing(monkeypatch):
    monkeypatch.setattr(gpm, 'TIME_BUDGET_SECONDS', 0.3)
    with pytest.raises(gpm.GpmSourceError) as info:
        await run(SlowNasa(das_delay=5.0))
    assert info.value.reason == 'timeout'
    assert not (gpm.CACHE / 'months').exists()


@pytest.mark.asyncio
async def test_nothing_read_within_the_budget_is_an_honest_timeout(monkeypatch):
    monkeypatch.setattr(gpm, 'TIME_BUDGET_SECONDS', 0.3)
    with pytest.raises(gpm.GpmSourceError) as info:
        await run(SlowNasa(month_delay={m: 5.0 for m in range(1, 13)}))
    assert info.value.reason == 'timeout' and 'time limit' in info.value.public_message


def test_read_timeout_allows_the_slow_answers_seen_on_ges_disc():
    assert gpm.REQUEST_TIMEOUT.read >= 90 and gpm.TIME_BUDGET_SECONDS > gpm.REQUEST_TIMEOUT.read


@pytest.mark.asyncio
async def test_cache_serves_a_second_request_without_upstream_calls():
    first = await run(FakeNasa())
    fake = FakeNasa()
    second = await run(fake)
    assert fake.requests == [] and second.requests == 0 and second.months_from_cache == 12
    assert second.search_from_cache and not second.units_checked
    assert [m.precipitation_mm for m in second.months] == [m.precipitation_mm for m in first.months]


@pytest.mark.asyncio
async def test_missing_token():
    import os
    os.environ.pop('EARTHDATA_TOKEN')
    with pytest.raises(gpm.GpmNotConfigured):
        await run(FakeNasa())


def test_year_validation():
    now = datetime(2026, 11, 15, tzinfo=UTC)
    gpm.validate_year(1998, now)
    gpm.validate_year(2026, now)
    for year in (1997, 2027):
        with pytest.raises(ValueError):
            gpm.validate_year(year, now)


# --------------------------------------------------------------------------- API with POWER comparison

def power_record(year=YEAR, daily=1.0, holes=()):
    import calendar
    series = {}
    for month in range(1, 13):
        for d in range(1, calendar.monthrange(year, month)[1] + 1):
            key = f'{year}{month:02d}{d:02d}'
            series[key] = -999.0 if key in holes else daily
    return power.PowerRecord(parameter={'PRECTOTCORR': series, 'T2M_MAX': {}}, sha256='a' * 64,
                             request_params={}, retrieved_at=datetime(2026, 11, 15, tzinfo=UTC),
                             served_from_cache=False, cache_age_seconds=None, upstream_attempts=1,
                             header=power.PowerHeader(fill_value=-999.0), variables={}, messages=[])


async def api_get(monkeypatch, fake, params, power_result):
    monkeypatch.setattr(gpm, '_make_client', fake.client)

    async def fake_power(*args, **kwargs):
        if isinstance(power_result, Exception):
            raise power_result
        return power_result
    monkeypatch.setattr(power, 'fetch_power', fake_power)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
        return await c.get('/api/precipitation/gpm', params=params)


PARAMS = {'latitude': LAT, 'longitude': LON, 'year': YEAR}


@pytest.mark.asyncio
async def test_api_compares_with_power_month_by_month(monkeypatch):
    rec = power_record(daily=0.5, holes=('20220815',))
    response = await api_get(monkeypatch, FakeNasa(answers={6: ascii_answer(rate=0.032)}), PARAMS, rec)
    assert response.status_code == 200, response.text
    body = response.json()
    june, august = body['monthly'][5], body['monthly'][7]
    assert june['precipitation_mm'] == 23.0 and june['power_precipitation_mm'] == 15.0 and june['difference_mm'] == 8.0
    assert august['power_precipitation_mm'] is None and august['difference_mm'] is None   # incomplete POWER month
    comp = body['comparison']
    assert comp['status'] == 'COMPARED' and comp['months_compared'] == 11 and comp['data_sha256'] == 'a' * 64
    assert comp['gpm_total_mm'] == round(sum(m['precipitation_mm'] for m in body['monthly'] if m['difference_mm'] is not None), 1)
    assert body['cell'] == {'latitude': CELL_LAT, 'longitude': CELL_LON, 'size_degrees': 0.1}
    assert body['provenance']['provider'] == 'NASA GES DISC' and body['spatial_resolution']['value'] == 0.1
    assert any('not which one is right' in item for item in body['limitations'])
    assert body['summary']['observed'] == 12 and body['cache']['units_checked'] is True


@pytest.mark.asyncio
async def test_api_keeps_gpm_when_power_fails(monkeypatch):
    shutil.rmtree(gpm.CACHE, ignore_errors=True)
    err = power.PowerSourceError('NASA POWER is unavailable (HTTP 503).', reason='upstream_error')
    body = (await api_get(monkeypatch, FakeNasa(), PARAMS, err)).json()
    assert body['comparison']['status'] == 'UNAVAILABLE' and 'HTTP 503' in body['comparison']['reason']
    assert all(m['power_precipitation_mm'] is None and m['difference_mm'] is None for m in body['monthly'])
    assert body['monthly'][0]['precipitation_mm'] is not None


@pytest.mark.asyncio
async def test_api_without_comparison_and_status_codes(monkeypatch):
    body = (await api_get(monkeypatch, FakeNasa(), {**PARAMS, 'compare_power': 'false'}, power_record())).json()
    assert body['comparison']['status'] == 'UNAVAILABLE' and body['comparison']['reason'] == 'Comparison not requested.'
    response = await api_get(monkeypatch, FakeNasa(), {**PARAMS, 'year': 1997}, power_record())
    assert response.status_code == 422
    response = await api_get(monkeypatch, FakeNasa(), {**PARAMS, 'year': 2099}, power_record())
    assert response.status_code == 422 and 'future' in response.text
    monkeypatch.delenv('EARTHDATA_TOKEN')
    response = await api_get(monkeypatch, FakeNasa(), PARAMS, power_record())
    assert response.status_code == 503 and 'EARTHDATA_TOKEN' in response.text
    monkeypatch.setenv('EARTHDATA_TOKEN', 'x')
    shutil.rmtree(gpm.CACHE, ignore_errors=True)
    response = await api_get(monkeypatch, FakeNasa(fail={m: 403 for m in range(1, 13)}), PARAMS, power_record())
    detail = response.json()['detail']
    assert response.status_code == 502 and 'gesdisc' not in detail and str(LAT) not in detail
