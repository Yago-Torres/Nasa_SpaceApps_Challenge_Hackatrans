"""Forensic timeline rules and rival-hypothesis templates (ABB-10).

Pure functions only (no database, no network) so the rules are deterministic and unit
tested. See docs/science/TIMELINE_HYPOTHESES.md.

Scientific guard rails:

- The departure label describes how far an event-year monthly value lies from the mean of
  its reference months, in units of the reference sample standard deviation. It is not a
  probability, percentile, significance test or a statement about crop damage.
- Hypothesis templates are candidate explanations with verification questions. They are
  never derived from case evidence, never scored and never marked as a demonstrated cause.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Literal

SEVERITY_RULE_ID = 'abb10-departure-vs-reference-sd-1'
MODERATE_THRESHOLD_SD = 1.0
LARGE_THRESHOLD_SD = 2.0

Severity = Literal['WITHIN_REFERENCE_SPREAD', 'MODERATE_DEPARTURE', 'LARGE_DEPARTURE', 'NOT_CLASSIFIED']
Direction = Literal['ABOVE_REFERENCE', 'BELOW_REFERENCE', 'EQUAL_TO_REFERENCE']

SEVERITY_RULE: dict[str, Any] = {
    'id': SEVERITY_RULE_ID,
    'description': (
        'Departure of an event-year monthly value from the mean of the same calendar month over the '
        'reference years, divided by the sample standard deviation (n-1) of those reference monthly values. '
        f'|departure| < {MODERATE_THRESHOLD_SD:g} SD: WITHIN_REFERENCE_SPREAD; '
        f'{MODERATE_THRESHOLD_SD:g} SD <= |departure| < {LARGE_THRESHOLD_SD:g} SD: MODERATE_DEPARTURE; '
        f'|departure| >= {LARGE_THRESHOLD_SD:g} SD: LARGE_DEPARTURE. NOT_CLASSIFIED when the anomaly, the '
        'standard deviation or at least 3 reference years are unavailable, or the spread is zero. '
        'outside_reference_range is true when the observed value lies below the smallest or above the '
        'largest reference monthly value.'),
    'thresholds_sd': {'moderate': MODERATE_THRESHOLD_SD, 'large': LARGE_THRESHOLD_SD},
    'inputs': 'Values rounded to 0.01 in the variable units (as stored by the ABB-08 anomaly engine).',
    'interpretation': (
        'A descriptive distance from a short reference sample. Not a probability, percentile, return period, '
        'significance test or evidence that the weather caused crop damage.'),
    'review_status': 'PENDING_SCIENTIFIC_REVIEW',
}

SEVERITY_LIMITATIONS: tuple[str, ...] = (
    'Severity thresholds (1 and 2 reference standard deviations) are conventions, not calibrated agronomic '
    'damage thresholds; pending scientific review.',
    'Monthly precipitation is skewed and bounded at zero, and the reference sample is small (3 or more years), '
    'so the standard-deviation scale is a coarse descriptive label.',
)


@dataclass(frozen=True)
class Departure:
    severity: Severity
    direction: Direction | None
    departure_in_reference_sd: float | None
    outside_reference_range: bool | None
    reason: str | None


def classify_departure(*, anomaly: float | None, observed: float | None, reference_sd: float | None,
                       reference_min: float | None, reference_max: float | None,
                       reference_sample_count: int) -> Departure:
    """Apply ``SEVERITY_RULE``. Never raises for missing inputs: returns NOT_CLASSIFIED with a reason."""
    if anomaly is None or observed is None or not math.isfinite(anomaly):
        return Departure('NOT_CLASSIFIED', None, None, None, 'No anomaly is available for this month.')
    direction: Direction = ('ABOVE_REFERENCE' if anomaly > 0 else
                            'BELOW_REFERENCE' if anomaly < 0 else 'EQUAL_TO_REFERENCE')
    outside = None
    if reference_min is not None and reference_max is not None:
        outside = observed < reference_min or observed > reference_max
    if reference_sample_count < 3 or reference_sd is None:
        return Departure('NOT_CLASSIFIED', direction, None, outside,
                         'Reference spread unavailable (fewer than 3 complete reference years).')
    if reference_sd <= 0:
        return Departure('NOT_CLASSIFIED', direction, None, outside,
                         'Reference values have zero spread; the departure cannot be scaled.')
    ratio = anomaly / reference_sd
    magnitude = abs(ratio)
    severity: Severity = ('LARGE_DEPARTURE' if magnitude >= LARGE_THRESHOLD_SD else
                          'MODERATE_DEPARTURE' if magnitude >= MODERATE_THRESHOLD_SD else
                          'WITHIN_REFERENCE_SPREAD')
    return Departure(severity, direction, round(ratio, 2), outside, None)


def content_sha256(parameter: dict[str, dict[str, Any]], names: tuple[str, ...]) -> str:
    """SHA-256 of the returned daily values only (canonical JSON, sorted keys).

    Contains no request parameters or coordinates, so exposing it cannot be brute-forced back
    to a precise location. Identical data from two retrievals gives the same digest.
    """
    canonical = json.dumps({name: parameter.get(name) or {} for name in names}, sort_keys=True,
                           separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def ingestion_key(*, provider: str, field_id: str, event_year: int, reference_start: int,
                  reference_end: int) -> str:
    canonical = json.dumps({'provider': provider, 'field_id': field_id, 'event_year': event_year,
                            'reference_start': reference_start, 'reference_end': reference_end}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def default_reference_window(event_year: int, *, years: int = 12, earliest: int = 1981) -> tuple[int, int]:
    """The ``years`` calendar years before the event year, clipped at POWER's first year."""
    end = event_year - 1
    return max(earliest, end - years + 1), end


# ── rival hypothesis templates ──────────────────────────────────────────────

TEMPLATE_LIMITATION = ('Template generated by CropStory as a starting point for comparison; it is not derived '
                       'from this case\'s evidence and is not a diagnosis.')
HYPOTHESIS_LIMITATION = ('A hypothesis is a candidate explanation to be checked against evidence. It is not a '
                         'demonstrated cause and carries no probability.')


def _q(question: str, why: str) -> dict[str, str]:
    return {'question': question, 'why_it_matters': why}


HYPOTHESIS_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        'code': 'WATER_DEFICIT',
        'title': 'Water deficit during the season',
        'statement': ('Insufficient water available to the crop during a sensitive period may have contributed '
                      'to the reported damage.'),
        'related_variables': ['precipitation'],
        'missing_evidence': [
            'Irrigation dates and volumes for the season',
            'Soil moisture or local rain-gauge records',
            'Crop growth stage when symptoms appeared',
        ],
        'verification_questions': [
            _q('Was the field irrigated, and are irrigation dates and volumes recorded?',
               'Regional precipitation does not describe water applied by irrigation.'),
            _q('At which growth stage were symptoms first noticed?',
               'Water shortage matters most in sensitive stages such as flowering or grain filling.'),
            _q('Do nearby rainfed fields with other soils or crops show the same pattern?',
               'A shared pattern across fields points to a regional factor rather than a field-specific one.'),
        ],
    },
    {
        'code': 'EXCESS_WATER',
        'title': 'Excess water or waterlogging',
        'statement': ('Waterlogging after heavy rain, flooding or poor drainage may have contributed to the '
                      'reported damage.'),
        'related_variables': ['precipitation'],
        'missing_evidence': ['Observations of standing water or saturated soil', 'Drainage condition of the field'],
        'verification_questions': [
            _q('Was standing water or saturated soil seen in the affected areas?',
               'Waterlogging leaves visible traces that regional data cannot show.'),
            _q('Are the damaged areas in low parts of the field?',
               'Damage concentrated in depressions suggests drainage problems.'),
        ],
    },
    {
        'code': 'HEAT_STRESS',
        'title': 'Heat stress',
        'statement': ('High temperatures during a sensitive crop stage may have contributed to the reported '
                      'damage.'),
        'related_variables': ['max_temperature'],
        'missing_evidence': ['Crop stage during hot periods', 'Local temperature records'],
        'verification_questions': [
            _q('What was the crop stage during the hottest weeks?',
               'Heat around flowering or grain filling affects crops more than at other stages.'),
            _q('Did symptoms appear shortly after a hot spell?',
               'Timing consistent with a hot spell is necessary, though not sufficient, for this hypothesis.'),
        ],
    },
    {
        'code': 'PEST_DISEASE',
        'title': 'Pest or disease',
        'statement': 'A pest, disease or weed pressure may have contributed to the reported damage.',
        'related_variables': [],
        'missing_evidence': ['Field inspection notes or photographs of symptoms', 'Laboratory or advisor diagnosis'],
        'verification_questions': [
            _q('Were insects, lesions, discoloration patterns or weeds observed on affected plants?',
               'Biotic damage usually leaves specific signs that weather data cannot reveal.'),
            _q('Did an agronomist, advisor or laboratory examine samples?',
               'A diagnosis is the most direct way to confirm or rule out a pest or disease.'),
            _q('Were regional pest or disease alerts issued for that season?',
               'Regional alerts show whether pressure was high in the area.'),
        ],
    },
    {
        'code': 'MANAGEMENT',
        'title': 'Management or irrigation-system failure',
        'statement': ('A management factor (sowing date, variety, fertilisation, crop protection, or an irrigation '
                      'equipment failure) may have contributed to the reported damage.'),
        'related_variables': [],
        'missing_evidence': ['Field operations log for the season', 'Irrigation equipment maintenance records'],
        'verification_questions': [
            _q('Were sowing date, variety or inputs different from previous seasons?',
               'Management changes can produce damage similar to weather stress.'),
            _q('Did the irrigation system fail or run below plan at any point?',
               'Equipment failures can mimic a water deficit even in normal rainfall years.'),
        ],
    },
    {
        'code': 'SOIL_LIMITATION',
        'title': 'Soil limitation',
        'statement': ('A soil limitation (low water-holding capacity, compaction, salinity or nutrient deficiency) '
                      'may have contributed to the reported damage.'),
        'related_variables': [],
        'missing_evidence': ['Soil analysis of affected and unaffected zones', 'Map of damaged areas within the field'],
        'verification_questions': [
            _q('Does the damage follow soil zones within the field?',
               'Damage tracking soil differences points to a soil factor.'),
            _q('Is a recent soil analysis available for affected and unaffected zones?',
               'Comparing zones separates soil limitations from weather effects.'),
        ],
    },
)

TEMPLATE_CODES: tuple[str, ...] = tuple(t['code'] for t in HYPOTHESIS_TEMPLATES)


def template(code: str) -> dict[str, Any]:
    for item in HYPOTHESIS_TEMPLATES:
        if item['code'] == code:
            return item
    raise KeyError(code)
