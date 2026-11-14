"""Monthly anomaly engine with scientific quality control (ABB-08).

Descriptive statistics only: an anomaly is the difference between an event-year monthly
value and the mean of the same calendar month over explicit reference years. No
significance test, trend, forecast or causal attribution is computed here.

Method (see docs/science/CLIMATE_ANOMALIES.md):

1. Each daily value is classified: valid, NASA POWER fill value, not returned (absent or
   null) or invalid (non-finite or outside a gross physical range). Only valid days count.
2. A month is ``complete`` when every calendar day (leap days included) is valid,
   ``partial`` when some are valid and ``missing`` when none are.
3. Monthly values are aggregated only for complete months (precipitation: sum of daily
   totals; maximum temperature: mean of daily maxima). Partial months are never
   aggregated, so a short month cannot masquerade as a dry or cool month.
4. The reference value for a calendar month uses only reference years whose month is
   complete; at least ``MIN_REFERENCE_YEARS`` are required, otherwise it is null.
5. The anomaly is ``observed - reference mean`` in the variable's monthly units.
"""
from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from statistics import mean, stdev
from typing import Any

METHOD_ID = 'abb08-monthly-anomaly-qc-1'
MIN_REFERENCE_YEARS = 3
# WMO climatological standard normals are 30-year periods; shorter windows are not normals.
NORMAL_PERIOD_YEARS = 30
DEFAULT_FILL_VALUE = -999.0


@dataclass(frozen=True)
class VariableSpec:
    key: str
    label: str
    source_parameter: str
    daily_units: str
    aggregation: str  # 'sum' | 'mean'
    monthly_units: str
    valid_min: float
    valid_max: float
    observed_field: str
    reference_field: str
    anomaly_field: str

    @property
    def aggregation_text(self) -> str:
        if self.aggregation == 'sum':
            return f'sum of daily {self.source_parameter} ({self.daily_units} x 1 day) over a complete month'
        return f'arithmetic mean of daily {self.source_parameter} over a complete month'


# Gross-error bounds only (values outside are physically implausible for a daily grid value);
# they are not climatological thresholds and do not flag extremes.
VARIABLES: tuple[VariableSpec, ...] = (
    VariableSpec('precipitation', 'Precipitation', 'PRECTOTCORR', 'mm/day', 'sum', 'mm', 0.0, 2000.0,
                 'precipitation_mm', 'reference_precipitation_mm', 'precipitation_anomaly_mm'),
    VariableSpec('max_temperature', 'Maximum temperature at 2 m', 'T2M_MAX', '°C', 'mean', '°C', -95.0, 65.0,
                 'max_temperature_c', 'reference_max_temperature_c', 'max_temperature_anomaly_c'),
)


def _round(v: float | None) -> float | None:
    return round(v, 2) if v is not None else None


def _plural(n: int, word: str) -> str:
    return f'{n} {word}' + ('' if n == 1 else 's')


def classify_month(series: dict[str, Any], year: int, month: int, spec: VariableSpec,
                   fill_value: float = DEFAULT_FILL_VALUE) -> tuple[list[float], dict[str, Any]]:
    """Return (valid daily values, coverage record) for one variable, year and month."""
    expected = calendar.monthrange(year, month)[1]
    values: list[float] = []
    fill = absent = invalid = 0
    for day in range(1, expected + 1):
        raw = series.get(f'{year:04d}{month:02d}{day:02d}')
        if raw is None:
            absent += 1
        elif isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
            invalid += 1
        elif math.isclose(raw, fill_value, abs_tol=1e-9):
            fill += 1
        elif not spec.valid_min <= raw <= spec.valid_max:
            invalid += 1
        else:
            values.append(float(raw))
    valid = len(values)
    status = 'complete' if valid == expected else 'missing' if valid == 0 else 'partial'
    reason = None
    if status != 'complete':
        parts = [p for n, p in ((fill, f'{_plural(fill, "day")} with the NASA POWER fill value ({fill_value:g})'),
                                (absent, f'{_plural(absent, "day")} not returned by the source'),
                                (invalid, f'{_plural(invalid, "day")} non-finite or outside the plausible range'))
                 if n]
        reason = f'{valid} of {expected} days valid: ' + '; '.join(parts) + '.'
    return values, {
        'status': status, 'reason': reason, 'expected_days': expected, 'valid_days': valid,
        'missing_days': expected - valid, 'fill_value_days': fill, 'absent_days': absent, 'invalid_days': invalid,
    }


def _aggregate(values: list[float], spec: VariableSpec) -> float:
    return math.fsum(values) if spec.aggregation == 'sum' else math.fsum(values) / len(values)


def _variable_month(parameter: dict, spec: VariableSpec, month: int, event_year: int, ref_years: list[int],
                    fill_value: float) -> tuple[dict[str, float | None], dict[str, Any]]:
    series = parameter.get(spec.source_parameter) or {}
    values, coverage = classify_month(series, event_year, month, spec, fill_value)
    observed = _aggregate(values, spec) if coverage['status'] == 'complete' else None
    fill_days = coverage['fill_value_days']

    samples: list[float] = []
    excluded: list[int] = []
    for year in ref_years:
        ref_values, ref_cov = classify_month(series, year, month, spec, fill_value)
        fill_days += ref_cov['fill_value_days']
        if ref_cov['status'] == 'complete':
            samples.append(_aggregate(ref_values, spec))
        else:
            excluded.append(year)
    n = len(samples)
    reference = mean(samples) if n >= MIN_REFERENCE_YEARS else None
    if n >= MIN_REFERENCE_YEARS:
        ref_status = 'complete' if not excluded else 'reduced'
    else:
        ref_status = 'insufficient'
    ref_reason = None
    if excluded:
        ref_reason = (f'{_plural(len(excluded), "reference year")} excluded for incomplete daily data '
                      f'({", ".join(map(str, excluded))}); {n} of {len(ref_years)} used.')
    if ref_status == 'insufficient':
        ref_reason = (ref_reason + ' ' if ref_reason else '') + \
            f'Fewer than {MIN_REFERENCE_YEARS} complete reference years; no reference value computed.'

    flags: list[str] = []
    if coverage['status'] == 'partial':
        flags.append('EVENT_MONTH_PARTIAL')
    elif coverage['status'] == 'missing':
        flags.append('EVENT_MONTH_MISSING')
    if fill_days:
        flags.append('FILL_VALUES_PRESENT')
    if excluded:
        flags.append('REFERENCE_YEARS_EXCLUDED')
    if ref_status == 'insufficient':
        flags.append('REFERENCE_INSUFFICIENT')

    anomaly = observed - reference if observed is not None and reference is not None else None
    if anomaly is not None:
        anomaly_reason = None
    elif observed is None:
        anomaly_reason = 'Event-year month is not complete, so no monthly value or anomaly is computed.'
    else:
        anomaly_reason = 'Reference value unavailable (insufficient complete reference years).'

    quality = {
        **coverage,
        'flags': flags,
        'reference': {
            'status': ref_status, 'years_expected': len(ref_years), 'sample_count': n,
            'years_excluded': excluded,
            'standard_deviation': _round(stdev(samples)) if n >= 2 and reference is not None else None,
            'minimum': _round(min(samples)) if reference is not None else None,
            'maximum': _round(max(samples)) if reference is not None else None,
            'reason': ref_reason,
        },
        'anomaly_computed': anomaly is not None,
        'anomaly_reason': anomaly_reason,
        'units': spec.monthly_units,
    }
    fields = {spec.observed_field: _round(observed), spec.reference_field: _round(reference),
              spec.anomaly_field: _round(anomaly)}
    return fields, quality


def reference_label(n_years: int) -> str:
    if n_years < NORMAL_PERIOD_YEARS:
        return (f'Short reference window ({n_years} years): a descriptive comparison period, '
                f'not a {NORMAL_PERIOD_YEARS}-year climatological normal.')
    return (f'Multi-decadal reference window ({n_years} years): not an official WMO climatological '
            'standard normal.')


def describe_method(event_year: int, reference_start: int, reference_end: int) -> dict[str, Any]:
    n = reference_end - reference_start + 1
    return {
        'id': METHOD_ID,
        'description': (
            f'Monthly anomaly = event-year ({event_year}) monthly value minus the arithmetic mean of the same '
            f'calendar month over the reference years {reference_start}-{reference_end} that have complete daily '
            f'coverage. Months with any fill-value, missing or implausible day are not aggregated; a reference '
            f'value needs at least {MIN_REFERENCE_YEARS} complete reference years. Plain difference in the '
            'variable units: no standardisation, significance test or causal attribution.'),
        'anomaly_formula': 'anomaly = observed_month - mean(reference_months_with_complete_coverage)',
        'event_year': event_year,
        'reference_start': reference_start,
        'reference_end': reference_end,
        'reference_years': n,
        'minimum_reference_years': MIN_REFERENCE_YEARS,
        'reference_is_climatological_normal': False,
        'reference_label': reference_label(n),
        'completeness_rule': ('A month is aggregated only when every calendar day (leap days included) has a '
                              'valid value; partial months are reported with day counts and a null value.'),
        'daily_time_standard': 'UTC',
        'aggregations': {s.key: s.aggregation_text for s in VARIABLES},
        'valid_ranges': {s.key: {'min': s.valid_min, 'max': s.valid_max, 'units': s.daily_units}
                         for s in VARIABLES},
        'uncertainty': ('Reference spread is reported as sample standard deviation, minimum and maximum of the '
                        'monthly reference values with their sample count; no confidence interval is computed.'),
    }


def analyze_power(parameter: dict, event_year: int, reference_start: int, reference_end: int,
                  *, fill_value: float = DEFAULT_FILL_VALUE) -> dict[str, Any]:
    """Return monthly rows with per-variable quality, a quality summary and the method."""
    if reference_start <= event_year <= reference_end:
        raise ValueError('Event year cannot be included in reference years')
    if reference_end - reference_start + 1 < MIN_REFERENCE_YEARS:
        raise ValueError(f'Use at least {MIN_REFERENCE_YEARS} reference years')
    ref_years = list(range(reference_start, reference_end + 1))

    rows: list[dict[str, Any]] = []
    for month in range(1, 13):
        row: dict[str, Any] = {'month': month}
        quality: dict[str, Any] = {}
        for spec in VARIABLES:
            fields, quality[spec.key] = _variable_month(parameter, spec, month, event_year, ref_years, fill_value)
            row.update(fields)
        row['quality'] = quality
        rows.append(row)

    if not any(r['quality']['precipitation']['valid_days'] for r in rows):
        raise ValueError('No usable precipitation observations for event year')
    return {'monthly': rows, 'quality': summarize_quality(rows, reference_end - reference_start + 1, fill_value),
            'method': describe_method(event_year, reference_start, reference_end)}


def summarize_quality(rows: list[dict[str, Any]], n_reference_years: int, fill_value: float) -> dict[str, Any]:
    per_variable: dict[str, dict[str, int]] = {}
    warnings: list[str] = []
    fill_total = 0
    for spec in VARIABLES:
        q = [r['quality'][spec.key] for r in rows]
        counts = {
            'complete_months': sum(m['status'] == 'complete' for m in q),
            'partial_months': sum(m['status'] == 'partial' for m in q),
            'missing_months': sum(m['status'] == 'missing' for m in q),
            'anomalies_computed': sum(m['anomaly_computed'] for m in q),
            'months_with_reference_years_excluded': sum(bool(m['reference']['years_excluded']) for m in q),
            'months_with_insufficient_reference': sum(m['reference']['status'] == 'insufficient' for m in q),
        }
        per_variable[spec.key] = counts
        fill_total += sum('FILL_VALUES_PRESENT' in m['flags'] for m in q)
        incomplete = counts['partial_months'] + counts['missing_months']
        if incomplete:
            warnings.append(f'{spec.label}: {_plural(incomplete, "event-year month")} without complete daily '
                            'coverage; their monthly values and anomalies are null.')
        if counts['months_with_reference_years_excluded']:
            warnings.append(f'{spec.label}: reference years with incomplete data were excluded in '
                            f'{_plural(counts["months_with_reference_years_excluded"], "month")}; see the '
                            'per-month reference sample counts.')
        if counts['months_with_insufficient_reference']:
            warnings.append(f'{spec.label}: {_plural(counts["months_with_insufficient_reference"], "month")} '
                            f'had fewer than {MIN_REFERENCE_YEARS} complete reference years; no anomaly computed.')
    if fill_total:
        warnings.append(f'NASA POWER fill values ({fill_value:g}) were treated as missing data, never as values.')
    if n_reference_years < NORMAL_PERIOD_YEARS:
        warnings.append(reference_label(n_reference_years))

    all_complete = all(
        c['complete_months'] == 12 and c['anomalies_computed'] == 12 and not c['months_with_reference_years_excluded']
        for c in per_variable.values())
    any_computed = any(c['anomalies_computed'] for c in per_variable.values())
    return {
        'status': 'complete' if all_complete else 'partial' if any_computed else 'insufficient',
        'fill_value': fill_value,
        'variables': per_variable,
        'warnings': warnings,
    }


def summarize_power(parameter: dict, event_year: int, reference_start: int, reference_end: int,
                    *, fill_value: float = DEFAULT_FILL_VALUE) -> list[dict[str, Any]]:
    """Backward-compatible helper: monthly rows only (see ``analyze_power``)."""
    return analyze_power(parameter, event_year, reference_start, reference_end, fill_value=fill_value)['monthly']
