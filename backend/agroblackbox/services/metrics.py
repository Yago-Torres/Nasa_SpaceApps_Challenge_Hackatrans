"""Conservative descriptive statistics for daily regional meteorology."""
from collections import defaultdict
from datetime import datetime
from statistics import mean


def _clean(v):
    if v is None or not isinstance(v, (int, float)) or v <= -900:
        return None
    return float(v)


def summarize_power(parameter: dict, event_year: int, reference_start: int, reference_end: int):
    """Compare observed event year to explicit, short reference period; no causal inference."""
    if reference_start <= event_year <= reference_end:
        raise ValueError("Event year cannot be included in reference years")
    if reference_end - reference_start + 1 < 3:
        raise ValueError("Use at least 3 reference years")
    rain_by_ym = defaultdict(list)
    temp_by_ym = defaultdict(list)
    for key, val in parameter.get('PRECTOTCORR', {}).items():
        try: dt=datetime.strptime(key, '%Y%m%d')
        except ValueError: continue
        v=_clean(val)
        if v is not None: rain_by_ym[(dt.year,dt.month)].append(v)
    for key, val in parameter.get('T2M_MAX', {}).items():
        try: dt=datetime.strptime(key, '%Y%m%d')
        except ValueError: continue
        v=_clean(val)
        if v is not None: temp_by_ym[(dt.year,dt.month)].append(v)
    rows=[]
    for m in range(1,13):
        er=rain_by_ym.get((event_year,m))
        et=temp_by_ym.get((event_year,m))
        reference_r=[sum(rain_by_ym[(y,m)]) for y in range(reference_start,reference_end+1) if rain_by_ym.get((y,m))]
        reference_t=[mean(temp_by_ym[(y,m)]) for y in range(reference_start,reference_end+1) if temp_by_ym.get((y,m))]
        observed_r=sum(er) if er else None
        observed_t=mean(et) if et else None
        base_r=mean(reference_r) if len(reference_r)>=3 else None
        base_t=mean(reference_t) if len(reference_t)>=3 else None
        rows.append({
            'month':m,
            'precipitation_mm':round(observed_r,2) if observed_r is not None else None,
            'reference_precipitation_mm':round(base_r,2) if base_r is not None else None,
            'precipitation_anomaly_mm':round(observed_r-base_r,2) if observed_r is not None and base_r is not None else None,
            'max_temperature_c':round(observed_t,2) if observed_t is not None else None,
            'reference_max_temperature_c':round(base_t,2) if base_t is not None else None,
            'max_temperature_anomaly_c':round(observed_t-base_t,2) if observed_t is not None and base_t is not None else None,
        })
    if not any(r['precipitation_mm'] is not None for r in rows):
        raise ValueError('No usable precipitation observations for event year')
    return rows
