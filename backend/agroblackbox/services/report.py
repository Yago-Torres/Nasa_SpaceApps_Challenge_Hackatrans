"""Conservative, human-auditable case investigation in Markdown."""
from datetime import datetime, timezone


def _text(value, limit=600):
    """Flatten supplied text to one Markdown-safe line (payload comes from the client)."""
    return ' '.join(str(value).split()).replace('|', '/')[:limit]


def _cell(value):
    return 'no data' if value is None or value == '' else _text(value, 40)


def _quality_cell(row):
    quality = row.get('quality')
    if not isinstance(quality, dict):
        return 'not supplied'
    parts = []
    for key in ('precipitation', 'max_temperature'):
        q = quality.get(key) if isinstance(quality.get(key), dict) else {}
        ref = q.get('reference') if isinstance(q.get('reference'), dict) else {}
        parts.append(f"{_text(q.get('status', '?'), 20)}, n={_text(ref.get('sample_count', '?'), 6)} ref. years")
    return ' / '.join(parts)


def _climate_method_lines(climate):
    """ABB-08: state which period and method produced each indicator, when supplied."""
    lines = []
    method = climate.get('method') if isinstance(climate.get('method'), dict) else None
    provenance = climate.get('provenance') if isinstance(climate.get('provenance'), dict) else {}
    if climate.get('retrieved_at'):
        lines.append(f"Retrieved at (UTC): {_text(climate['retrieved_at'], 40)}")
    if provenance.get('dataset_version'):
        lines.append(f"Source version (as reported): {_text(provenance['dataset_version'], 120)}")
    spatial = climate.get('spatial_resolution')
    if isinstance(spatial, dict) and spatial.get('description'):
        lines.append(f"Spatial resolution: {_text(spatial['description'])}")
    if method:
        lines += [f"Anomaly method ({_text(method.get('id', 'unspecified'), 60)}): {_text(method.get('description', ''), 1200)}",
                  f"Reference window: {_text(method.get('reference_label', ''))}"]
        aggregations = method.get('aggregations')
        if isinstance(aggregations, dict):
            for key, text in aggregations.items():
                lines.append(f"- {_text(key, 40)}: {_text(text, 300)}")
    quality = climate.get('quality') if isinstance(climate.get('quality'), dict) else None
    if quality:
        lines.append(f"Data quality status: {_text(quality.get('status', 'unknown'), 20)}")
        for warning in quality.get('warnings') or []:
            lines.append(f"- Warning: {_text(warning)}")
    return lines

def build_report(case: dict):
    label=case.get('location_label','Unspecified region')
    climate=case.get('climate') or {}
    literature=case.get('literature') or []
    rotations=case.get('rotations') or []
    rows=climate.get('monthly',[])
    lines=[f'# CropStory — Preliminary Case Investigation',
           '',f'Generated at (UTC): {datetime.now(timezone.utc).isoformat()}',
           f'Case location: {label}',
           '', '## Methods and provenance',
           'NASA POWER daily point meteorology was analyzed against an explicit short reference period.',
           'This is regional gridded exposure, not a field measurement or causal diagnosis.',
           f"Data SHA-256: `{climate.get('data_sha256','not supplied')}`",
           f"Reference period: {climate.get('reference_start','?')}–{climate.get('reference_end','?')}"]
    lines+=_climate_method_lines(climate)
    lines+=['', '## Monthly meteorological anomalies',
           '| Month | Rain anomaly (mm) | Max temp anomaly (°C) | Data quality (rain / temp) |',
           '|---|---:|---:|---|']
    for r in rows:
        lines.append(f"| {r.get('month','')} | {_cell(r.get('precipitation_anomaly_mm'))} | "
                     f"{_cell(r.get('max_temperature_anomaly_c'))} | {_quality_cell(r)} |")
    lines+=['','## Hypotheses, not proven causes',
            'Meteorological anomalies may contribute to agricultural stress; pests, management, soil and irrigation are unmeasured competing explanations.',
            '', '## Crop rotation scenarios',
            'The scenarios below are planning alternatives, not calibrated yield models.']
    for r in rotations:
        lines.append(f"- **{r.get('name','Unnamed')}** — {r.get('interpretation','Needs local validation')}")
    lines+=['','## Supporting literature (bibliographic matches, not validated findings)']
    for w in literature:
        lines.append(f"- {w.get('title','Untitled')} ({w.get('year','n.d.')}). {w.get('doi') or w.get('openalex_id') or 'DOI unavailable'}. Verify applicability and original study.")
    lines+=['','## Limitations and data required',
            '- No crop yield, farm loss, field water use, soil-carbon change or causal attribution has been measured.',
            '- Soil characteristics, crop calendar, management records and expert assessment are needed.',
            '- Published global effect sizes must not be interpreted as local predicted benefits.',
            '- The reference interval is a short illustrative comparison, not a standard 30-year climatology.',
            '', '## Reproduction',
            'See repository source, data query parameters and SHA-256 fingerprint for the retrieved NASA record.',
            '', '## Report status',
            '**Preliminary autogenerated technical case investigation; local review required.**']
    return '\n'.join(lines)+'\n'
