"""ABB-08 anomaly engine tests. All inputs are SYNTHETIC daily series with known results."""
import calendar
import math
import random

import pytest

from agroblackbox.services.metrics import (
    MIN_REFERENCE_YEARS,
    VARIABLES,
    analyze_power,
    classify_month,
    summarize_power,
)
from agroblackbox.services.report import build_report
from agroblackbox.services.rotations import rotation_examples

TOL = 1e-9  # explicit tolerance for exact synthetic arithmetic (values are rounded to 0.01 in output)
PRECIP = VARIABLES[0]


def daily(years, rain=lambda y, m, d: 1.0, tmax=lambda y, m, d: 20.0):
    """Complete daily PRECTOTCORR/T2M_MAX series for whole years (leap days included)."""
    out = {'PRECTOTCORR': {}, 'T2M_MAX': {}}
    for y in years:
        for m in range(1, 13):
            for d in range(1, calendar.monthrange(y, m)[1] + 1):
                key = f'{y:04d}{m:02d}{d:02d}'
                out['PRECTOTCORR'][key] = rain(y, m, d)
                out['T2M_MAX'][key] = tmax(y, m, d)
    return out


def test_monthly_anomalies_known_result():
    # Reference Jan rain 1, 2, 3 mm/day -> 31, 62, 93 mm; event 0.5 mm/day -> 15.5 mm.
    rain = {2019: 1.0, 2020: 2.0, 2021: 3.0, 2022: 0.5}
    temp = {2019: 20.0, 2020: 21.0, 2021: 22.0, 2022: 25.0}
    obs = daily([2019, 2020, 2021, 2022], rain=lambda y, m, d: rain[y], tmax=lambda y, m, d: temp[y])
    out = analyze_power(obs, 2022, 2019, 2021)
    jan = out['monthly'][0]
    assert jan['precipitation_mm'] == pytest.approx(15.5, abs=TOL)
    assert jan['reference_precipitation_mm'] == pytest.approx(62.0, abs=TOL)
    assert jan['precipitation_anomaly_mm'] == pytest.approx(-46.5, abs=TOL)
    assert jan['max_temperature_anomaly_c'] == pytest.approx(4.0, abs=TOL)
    q = jan['quality']['precipitation']
    assert q['status'] == 'complete' and q['flags'] == [] and q['anomaly_computed']
    assert q['reference'] == {'status': 'complete', 'years_expected': 3, 'sample_count': 3, 'years_excluded': [],
                              'standard_deviation': 31.0, 'minimum': 31.0, 'maximum': 93.0, 'reason': None}
    # February 2020 is a leap month: 29 days x 2 mm.
    feb = out['monthly'][1]
    assert feb['quality']['precipitation']['reference']['sample_count'] == 3
    assert feb['reference_precipitation_mm'] == pytest.approx((28 * 1 + 29 * 2 + 28 * 3) / 3, abs=0.005)
    assert out['quality']['status'] == 'complete'


def test_matches_independent_calculation_on_random_series():
    rng = random.Random(20261114)
    years = list(range(2010, 2023))
    obs = daily(years, rain=lambda *a: round(rng.uniform(0, 12), 2), tmax=lambda *a: round(rng.uniform(-5, 38), 2))
    rows = summarize_power(obs, 2022, 2010, 2021)
    for m in range(1, 13):
        def month_sum(y):
            return sum(v for k, v in obs['PRECTOTCORR'].items() if k.startswith(f'{y}{m:02d}'))

        def month_mean(y):
            vals = [v for k, v in obs['T2M_MAX'].items() if k.startswith(f'{y}{m:02d}')]
            return sum(vals) / len(vals)
        ref_r = sum(month_sum(y) for y in range(2010, 2022)) / 12
        ref_t = sum(month_mean(y) for y in range(2010, 2022)) / 12
        assert rows[m - 1]['precipitation_anomaly_mm'] == pytest.approx(month_sum(2022) - ref_r, abs=0.006)
        assert rows[m - 1]['max_temperature_anomaly_c'] == pytest.approx(month_mean(2022) - ref_t, abs=0.006)


def test_partial_event_month_is_not_aggregated():
    obs = daily([2019, 2020, 2021, 2022])
    for d in (1, 2, 3):  # 3 days removed from Jan 2022
        del obs['PRECTOTCORR'][f'202201{d:02d}']
    jan = analyze_power(obs, 2022, 2019, 2021)['monthly'][0]
    assert jan['precipitation_mm'] is None and jan['precipitation_anomaly_mm'] is None
    assert jan['reference_precipitation_mm'] == pytest.approx(31.0, abs=TOL)  # reference still shown
    q = jan['quality']['precipitation']
    assert (q['status'], q['valid_days'], q['missing_days'], q['absent_days']) == ('partial', 28, 3, 3)
    assert q['reason'] == '28 of 31 days valid: 3 days not returned by the source.'
    assert q['flags'] == ['EVENT_MONTH_PARTIAL'] and not q['anomaly_computed']
    assert jan['max_temperature_anomaly_c'] == pytest.approx(0.0, abs=TOL)  # other variable unaffected


def test_fill_values_are_missing_never_data():
    obs = daily([2019, 2020, 2021, 2022])
    obs['PRECTOTCORR']['20220315'] = -999.0
    obs['T2M_MAX']['20220316'] = -999
    out = analyze_power(obs, 2022, 2019, 2021)
    mar = out['monthly'][2]
    assert mar['precipitation_mm'] is None and mar['max_temperature_c'] is None
    q = mar['quality']['precipitation']
    assert q['fill_value_days'] == 1 and 'FILL_VALUES_PRESENT' in q['flags']
    assert 'fill value (-999)' in q['reason']
    assert all(-999 not in (r['precipitation_mm'], r['max_temperature_c']) for r in out['monthly'])
    assert any('fill values (-999)' in w for w in out['quality']['warnings'])


def test_custom_fill_value_from_header_is_honoured():
    obs = daily([2019, 2020, 2021, 2022])
    obs['T2M_MAX']['20220410'] = -99.0  # outside plausible range anyway, but counted as fill when declared
    q = analyze_power(obs, 2022, 2019, 2021, fill_value=-99.0)['monthly'][3]['quality']['max_temperature']
    assert q['fill_value_days'] == 1 and q['invalid_days'] == 0


def test_leap_year_requires_29_february_days():
    obs = daily([2017, 2018, 2019, 2020])
    _, cov = classify_month(obs['PRECTOTCORR'], 2020, 2, PRECIP)
    assert cov['expected_days'] == 29 and cov['status'] == 'complete'
    del obs['PRECTOTCORR']['20200229']
    feb = analyze_power(obs, 2020, 2017, 2019)['monthly'][1]
    assert feb['quality']['precipitation']['status'] == 'partial'
    assert feb['quality']['precipitation']['expected_days'] == 29
    assert feb['precipitation_mm'] is None
    # Non-leap February is complete with 28 days and spurious 29th keys are ignored.
    _, cov = classify_month({**obs['PRECTOTCORR'], '20190229': 5.0}, 2019, 2, PRECIP)
    assert cov['expected_days'] == 28 and cov['status'] == 'complete'


def test_missing_month_and_out_of_range_values():
    obs = daily([2019, 2020, 2021, 2022])
    for k in [k for k in obs['PRECTOTCORR'] if k.startswith('202206')]:
        del obs['PRECTOTCORR'][k]
    obs['PRECTOTCORR']['20220710'] = -3.0  # negative precipitation is implausible
    obs['T2M_MAX']['20220711'] = float('nan')
    out = analyze_power(obs, 2022, 2019, 2021)
    jun, jul = out['monthly'][5], out['monthly'][6]
    assert jun['quality']['precipitation']['status'] == 'missing'
    assert jun['quality']['precipitation']['flags'] == ['EVENT_MONTH_MISSING']
    assert jul['quality']['precipitation']['invalid_days'] == 1
    assert jul['quality']['max_temperature']['invalid_days'] == 1
    assert out['quality']['status'] == 'partial'
    assert out['quality']['variables']['precipitation']['missing_months'] == 1


def test_incomplete_reference_years_are_excluded_and_counted():
    obs = daily(range(2018, 2023), rain=lambda y, m, d: float(y - 2017))
    del obs['PRECTOTCORR']['20190105']  # 2019 Jan incomplete
    out = analyze_power(obs, 2022, 2018, 2021)
    jan = out['monthly'][0]
    ref = jan['quality']['precipitation']['reference']
    assert ref['status'] == 'reduced' and ref['sample_count'] == 3 and ref['years_excluded'] == [2019]
    assert 'REFERENCE_YEARS_EXCLUDED' in jan['quality']['precipitation']['flags']
    assert jan['reference_precipitation_mm'] == pytest.approx(31 * (1 + 3 + 4) / 3, abs=0.005)
    assert out['monthly'][1]['quality']['precipitation']['reference']['sample_count'] == 4
    assert any('reference years with incomplete data were excluded in 1 month' in w for w in out['quality']['warnings'])


def test_insufficient_reference_years_give_no_anomaly():
    obs = daily([2019, 2020, 2021, 2022])
    del obs['T2M_MAX']['20200820']
    aug = analyze_power(obs, 2022, 2019, 2021)['monthly'][7]
    q = aug['quality']['max_temperature']
    assert q['reference']['status'] == 'insufficient' and q['reference']['sample_count'] == MIN_REFERENCE_YEARS - 1
    assert aug['reference_max_temperature_c'] is None and aug['max_temperature_anomaly_c'] is None
    assert aug['max_temperature_c'] == pytest.approx(20.0, abs=TOL)  # observed value still reported
    assert 'REFERENCE_INSUFFICIENT' in q['flags']
    assert q['anomaly_reason'].startswith('Reference value unavailable')


def test_reference_window_is_labelled_and_method_described():
    out = analyze_power(daily(range(2009, 2023)), 2022, 2010, 2021)
    method = out['method']
    assert method['reference_is_climatological_normal'] is False
    assert method['reference_label'].startswith('Short reference window (12 years)')
    assert method['minimum_reference_years'] == 3 and method['daily_time_standard'] == 'UTC'
    assert 'complete daily coverage' in method['description']
    assert any('not a 30-year climatological normal' in w for w in out['quality']['warnings'])
    long = analyze_power(daily(range(1981, 2016)), 2015, 1981, 2014)['method']
    assert long['reference_label'].startswith('Multi-decadal reference window (34 years)')
    assert long['reference_is_climatological_normal'] is False


def test_no_causal_language_in_generated_text():
    out = analyze_power(daily([2019, 2020, 2021, 2022]), 2022, 2019, 2021)
    text = (out['method']['description'] + ' '.join(out['quality']['warnings'])).lower()
    for word in ('caused', 'because of the drought', 'led to', 'responsible for', 'probability'):
        assert word not in text


@pytest.mark.parametrize('args,message', [((2022, 2019, 2022), 'Event year'), ((2022, 2020, 2021), 'at least 3')])
def test_invalid_reference_windows(args, message):
    with pytest.raises(ValueError, match=message):
        analyze_power(daily([2019, 2020, 2021, 2022]), *args)


def test_no_event_year_precipitation_raises():
    obs = daily([2019, 2020, 2021])
    obs['T2M_MAX'].update(daily([2022])['T2M_MAX'])
    with pytest.raises(ValueError, match='No usable precipitation'):
        analyze_power(obs, 2022, 2019, 2021)
    obs['PRECTOTCORR'].update({k: -999.0 for k in daily([2022])['PRECTOTCORR']})
    with pytest.raises(ValueError, match='No usable precipitation'):
        analyze_power(obs, 2022, 2019, 2021)


def test_rounding_uses_unrounded_differences():
    obs = daily([2019, 2020, 2021, 2022], tmax=lambda y, m, d: 20.004 if y == 2022 else 20.0)
    jan = summarize_power(obs, 2022, 2019, 2021)[0]
    assert jan['max_temperature_c'] == 20.0 and math.isclose(jan['max_temperature_anomaly_c'], 0.0)


def test_rotations_ambiguous_impact_is_not_invented():
    examples = rotation_examples()
    assert len(examples) == 3
    assert examples[0]['id'] == 'current'
    assert all(r['verified_impact'] is None for r in examples)


def test_report_is_marked_preliminary():
    report = build_report({'location_label': 'Test', 'climate': {}})
    assert 'Preliminary autogenerated technical case investigation' in report


def test_report_explains_period_method_and_quality():
    out = analyze_power(daily([2019, 2020, 2021, 2022]), 2022, 2019, 2021)
    climate = {'reference_start': 2019, 'reference_end': 2021, 'monthly': out['monthly'],
               'method': out['method'], 'quality': out['quality'], 'retrieved_at': '2026-11-14T12:00:00Z'}
    report = build_report({'location_label': 'Test', 'climate': climate})
    assert 'Anomaly method (abb08-monthly-anomaly-qc-1)' in report
    assert 'Short reference window (3 years)' in report
    assert 'complete, n=3 ref. years / complete, n=3 ref. years' in report
    assert 'Retrieved at (UTC): 2026-11-14T12:00:00Z' in report
