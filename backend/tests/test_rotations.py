"""ABB-17 rotation comparison tests. All inputs are SYNTHETIC fixtures, not real farm records."""
import copy
import json
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from agroblackbox.app import app
from agroblackbox.farm_profile import CalendarWindow
from agroblackbox.services.rotations import (
    RotationCompareRequest,
    _Crop,
    check_transition,
    compare_rotations,
    to_shared_rotation,
)


def season(label, year, sow, harvest, water='RAINFED', role='MAIN_CROP'):
    return {'crop_label': label, 'season_year': year, 'sowing_date': sow, 'harvest_date': harvest,
            'water_regime': water, 'role': role}


def window(label, sow, harvest=None):
    out = {'crop_label': label, 'sowing_start_month': sow[0], 'sowing_end_month': sow[1]}
    if harvest:
        out |= {'harvest_start_month': harvest[0], 'harvest_end_month': harvest[1]}
    return out


def market(label, status):
    return {'crop_label': label, 'status': status}


def cereal_history(first=2022):
    """Wheat / barley alternation, rainfed (synthetic)."""
    crops = ['Common wheat', 'Barley', 'Common wheat', 'Barley']
    return [season(c, first + i, f'{first + i - 1}-11-05', f'{first + i}-06-25') for i, c in enumerate(crops)]


def profile():
    return {
        'crop_history': cereal_history(),
        'local_calendar': [
            window('Common wheat', (10, 12), (6, 7)), window('Barley', (10, 12), (6, 7)),
            window('Chickpea', (2, 3), (6, 7)), window('Sunflower', (3, 4), (8, 9)),
            window('Rapeseed', (9, 10), (6, 7)),
        ],
        'constraints': {
            'water_regime': 'RAINFED', 'available_equipment': ['seed drill', 'combine'],
            'market_access': [market('Common wheat', 'SELLABLE'), market('Barley', 'CONTRACTED'),
                              market('Chickpea', 'SELLABLE'), market('Sunflower', 'SELLABLE')],
        },
        'priorities': [{'criterion': 'SOIL_COVER', 'rank': 1}, {'criterion': 'CROP_DIVERSITY', 'rank': 2},
                       {'criterion': 'WATER_USE', 'rank': 3}],
    }


def compare(payload, **kwargs):
    return compare_rotations(RotationCompareRequest(profile=payload, **kwargs))


def screening(result):
    return {s.crop.crop_label: s for s in result.candidate_screening}


def pairs(strategy):
    labels = [slot[0].crop_label for slot in strategy.cycle]
    return {(labels[i], labels[(i + 1) % len(labels)]) for i in range(len(labels))}


def crop(label, sow, harvest, family='Poaceae'):
    return _Crop(key=label, code=None, label=label, family=family, is_legume=False,
                 window=CalendarWindow.model_validate(window(label, sow, harvest)))


# ---------------------------------------------------------------- calendar rule

def test_transition_compatible_tight_and_incompatible():
    wheat = crop('wheat', (10, 12), (6, 7))
    sunflower = crop('sunflower', (3, 4), (8, 9), 'Asteraceae')
    maize = crop('maize', (4, 5), (10, 11))
    early_rape = crop('rapeseed', (8, 9), (6, 7), 'Brassicaceae')

    ok = check_transition(wheat, sunflower)
    assert ok.status == 'COMPATIBLE'
    assert (ok.fallow_gap.min, ok.fallow_gap.max) == (7, 9)  # Aug..Feb at least, Jul..Mar at most

    tight = check_transition(maize, wheat)  # maize harvest Oct-Nov vs wheat sowing Oct-Dec
    assert tight.status == 'TIGHT' and tight.fallow_gap.min == 0

    impossible = check_transition(maize, early_rape)  # rapeseed must be sown by Sep, maize harvested from Oct
    assert impossible.status == 'INCOMPATIBLE' and impossible.fallow_gap is None


def test_windows_wrapping_year_end_are_handled():
    winter = crop('winter crop', (11, 1), (6, 7))  # sowing Nov-Jan wraps the year end
    spring = crop('spring crop', (3, 4), (9, 10), 'Asteraceae')
    assert check_transition(winter, spring).status == 'COMPATIBLE'
    assert check_transition(spring, winter).status == 'COMPATIBLE'  # harvest ends Oct, sowing starts Nov
    late_harvest = crop('late', (3, 4), (11, 12), 'Asteraceae')
    assert check_transition(late_harvest, winter).status == 'TIGHT'  # Nov-Dec harvest vs Nov-Jan sowing
    very_late = crop('very late', (5, 6), (12, 1), 'Asteraceae')  # harvest Dec-Jan wraps the year end
    after = check_transition(very_late, crop('spring cereal', (3, 4), (7, 8)))
    assert after.status == 'COMPATIBLE' and (after.fallow_gap.min, after.fallow_gap.max) == (1, 3)
    assert check_transition(very_late, crop('early sown', (9, 10), (6, 7))).status == 'INCOMPATIBLE'


def test_missing_window_is_not_evaluable_not_invented():
    wheat = crop('wheat', (10, 12), (6, 7))
    unknown = _Crop(key='pea', code='pea', label='Pea', family='Fabaceae', is_legume=True, window=None)
    result = check_transition(wheat, unknown)
    assert result.status == 'NOT_EVALUABLE' and result.fallow_gap is None


# ---------------------------------------------------------------- comparison

def test_current_first_and_at_least_two_alternatives():
    result = compare(profile())
    assert result.status == 'COMPARED'
    assert len(result.strategies) >= 3
    current, *alternatives = result.strategies
    assert current.is_current and current.strategy_kind == 'CURRENT'
    assert current.sequence_origin == 'FARMER_REPORTED'
    assert [slot[0].crop_label for slot in current.cycle] == ['Common wheat', 'Barley']
    assert current.years == [['Common wheat'], ['Barley'], ['Common wheat'], ['Barley']]
    assert current.start_season_year == 2026
    assert all(not s.is_current and s.sequence_origin == 'RULE_GENERATED' for s in alternatives)
    assert len({tuple(map(tuple, s.years)) for s in result.strategies}) == len(result.strategies)
    for s in result.strategies:
        assert s.source_kind == 'MODEL_SCENARIO'
        assert s.verified_impact is None
        assert s.risks or s.possible_benefits
        assert s.conditions_requiring_review and s.assumptions and s.limitations


def test_current_family_repetition_is_flagged_and_alternatives_break_it():
    result = compare(profile())
    current = result.strategies[0]
    assert current.comparison.consecutive_same_family == 2
    assert {c.constraint: c.status for c in current.constraint_checks}['FAMILY_REPETITION'] == 'REVIEW_REQUIRED'
    for alt in result.strategies[1:]:
        assert alt.comparison.consecutive_same_family == 0
        assert all(not t.same_family for t in alt.transitions)


def test_alternatives_state_benefits_risks_and_review_without_numbers_of_effect():
    result = compare(profile())
    diversified = next(s for s in result.strategies if s.strategy_kind == 'FAMILY_DIVERSIFICATION')
    assert diversified.comparison.includes_legume
    assert any('legume' in b.lower() and 'requires' in b for b in diversified.possible_benefits)
    assert any('No farm experience' in r for r in diversified.risks)
    assert any('Agronomist' in c for c in diversified.conditions_requiring_review)
    assert {e.source_kind for e in diversified.evidence_refs} == {'LITERATURE_METADATA'}
    assert {e.review_status for e in diversified.evidence_refs} == {'HUMAN_REVIEW_REQUIRED'}
    texts = ' '.join(diversified.possible_benefits + diversified.risks)
    assert '%' not in texts


def test_priorities_are_addressed_by_rank_without_scores():
    result = compare(profile())
    current, alt = result.strategies[0], result.strategies[1]
    assert [p.relation_to_current for p in current.priorities_addressed] == ['REFERENCE'] * 3
    notes = {p.criterion.value: p for p in alt.priorities_addressed}
    assert [p.rank for p in alt.priorities_addressed] == [1, 2, 3]
    assert notes['CROP_DIVERSITY'].relation_to_current == 'MORE'
    assert notes['WATER_USE'].relation_to_current == 'NOT_EVALUABLE'
    assert notes['SOIL_COVER'].relation_to_current in {'MORE', 'LESS', 'SAME'}


def _keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from _keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _keys(inner)


def test_no_yield_water_income_or_score_fields():
    body = compare(profile()).model_dump(mode='json')
    keys = {k.lower() for k in _keys(body)}
    for forbidden in ('yield', 'saving', 'score', 'income', 'revenue', 'percent', 'probability', 'weight',
                      'confidence', 'benefit_value'):
        assert not [k for k in keys if forbidden in k], forbidden
    assert all(s['verified_impact'] is None for s in body['strategies'])


def test_same_input_same_output_and_input_order_does_not_matter():
    first = compare(profile()).model_dump_json()
    assert compare(profile()).model_dump_json() == first
    shuffled = profile()
    shuffled['local_calendar'].reverse()
    shuffled['constraints']['market_access'].reverse()
    a = [s.years for s in compare(profile()).strategies]
    b = [s.years for s in compare(shuffled).strategies]
    assert a == b


# ---------------------------------------------------------------- calendar-incompatible sequences are rejected

def maize_profile():
    payload = profile()
    payload['local_calendar'] = [
        window('Common wheat', (10, 12), (6, 7)), window('Barley', (10, 12), (6, 7)),
        window('Maize', (4, 5), (10, 11)), window('Rapeseed', (8, 9), (6, 7)),
        window('Chickpea', (2, 3), (6, 7)),
    ]
    payload['constraints']['water_regime'] = 'IRRIGATED'
    payload['constraints']['irrigation_allowance'] = {'value': 3000, 'unit': 'm3/ha/year', 'origin': 'FARMER_ESTIMATE'}
    payload['constraints']['market_access'] += [market('Maize', 'SELLABLE'), market('Rapeseed', 'SELLABLE')]
    return payload


def test_incompatible_calendar_pairs_never_appear_in_alternatives():
    result = compare(maize_profile())
    incompatible = {(t.from_crop, t.to_crop) for t in result.incompatible_transitions}
    assert ('Maize', 'Rapeseed') in incompatible
    assert result.status == 'COMPARED'
    for alt in result.strategies[1:]:
        assert not pairs(alt) & incompatible
        assert all(t.status != 'INCOMPATIBLE' for t in alt.transitions)
        assert alt.entry_transition is None or alt.entry_transition.status != 'INCOMPATIBLE'


def test_recorded_rotation_contradicting_declared_windows_is_flagged():
    payload = maize_profile()
    payload['crop_history'] = [
        season('Maize', 2022, '2022-04-20', '2022-10-20', water='IRRIGATED'),
        season('Rapeseed', 2023, '2022-11-01', '2023-06-20', water='IRRIGATED'),
        season('Maize', 2024, '2024-04-20', '2024-10-20', water='IRRIGATED'),
        season('Rapeseed', 2025, '2024-11-01', '2025-06-20', water='IRRIGATED'),
    ]
    result = compare(payload)
    current = result.strategies[0]
    assert any(t.status == 'INCOMPATIBLE' for t in current.transitions)
    assert {c.constraint: c.status for c in current.constraint_checks}['LOCAL_CALENDAR'] == 'VIOLATED'
    assert current.screening_result == 'CONFLICTS_WITH_DECLARED_CONSTRAINTS'
    assert current.comparison.longest_fallow_gap is None


def test_no_feasible_alternative_is_explained():
    # Two late-harvested cereals and one legume that must be sown before they can be harvested:
    # every family-alternating sequence contains an impossible cereal -> legume step.
    payload = profile()
    payload['crop_history'] = [
        season(crop_name, year, f'{year}-04-25', f'{year}-10-25', water='IRRIGATED')
        for crop_name, year in (('Maize', 2022), ('Sorghum', 2023), ('Maize', 2024), ('Sorghum', 2025))]
    payload['local_calendar'] = [window('Maize', (4, 5), (10, 11)), window('Sorghum', (4, 5), (10, 11)),
                                 window('Faba bean', (8, 9), (6, 7))]
    payload['constraints'] = {
        'water_regime': 'IRRIGATED', 'available_equipment': ['seed drill'],
        'irrigation_allowance': {'value': 3000, 'unit': 'm3/ha/year', 'origin': 'FARMER_ESTIMATE'},
        'market_access': [market('Maize', 'SELLABLE'), market('Sorghum', 'SELLABLE'), market('Faba bean', 'SELLABLE')]}
    result = compare(payload)
    incompatible = {(t.from_crop, t.to_crop) for t in result.incompatible_transitions}
    assert {('Maize', 'Faba bean'), ('Sorghum', 'Faba bean')} <= incompatible
    assert result.status == 'FEWER_ALTERNATIVES'
    assert result.generation.feasible_sequences == 0
    assert len(result.strategies) == 1 and result.strategies[0].is_current
    assert any('impossible calendar transitions' in e for e in result.explanation)


# ---------------------------------------------------------------- screening

def test_excluded_and_no_market_crops_are_excluded_with_reasons():
    payload = profile()
    payload['constraints']['excluded_crops'] = ['Girasol']
    payload['constraints']['market_access'].append(market('Rapeseed', 'NO_MARKET'))
    result = compare(payload)
    screen = screening(result)
    assert screen['Sunflower'].status == 'EXCLUDED'
    assert [r.code for r in screen['Sunflower'].reasons] == ['EXCLUDED_BY_FARMER']
    assert screen['Rapeseed'].status == 'EXCLUDED'
    assert [r.code for r in screen['Rapeseed'].reasons] == ['NO_MARKET']
    used = {c.crop_label for s in result.strategies[1:] for slot in s.cycle for c in slot}
    assert not used & {'Sunflower', 'Rapeseed'}


def test_currently_grown_excluded_crop_makes_current_conflict():
    payload = profile()
    payload['constraints']['excluded_crops'] = ['Barley']
    result = compare(payload)
    current = result.strategies[0]
    assert {c.constraint: c.status for c in current.constraint_checks}['EXCLUDED_CROPS'] == 'VIOLATED'
    assert current.screening_result == 'CONFLICTS_WITH_DECLARED_CONSTRAINTS'
    assert all('Barley' not in sum(s.years, []) for s in result.strategies[1:])
    assert any('CONTRACTED' in r for s in result.strategies[1:] for r in s.risks)


def test_rainfed_farm_excludes_crops_only_grown_irrigated_and_flags_current():
    payload = profile()
    payload['crop_history'] = [
        season('Maize', 2022, '2022-04-20', '2022-10-15', water='IRRIGATED'),
        season('Common wheat', 2023, '2022-11-20', '2023-06-25'),
        season('Maize', 2024, '2024-04-20', '2024-10-15', water='IRRIGATED'),
        season('Common wheat', 2025, '2024-11-20', '2025-06-25'),
    ]
    payload['local_calendar'].append(window('Maize', (4, 5), (9, 10)))
    payload['constraints']['market_access'].append(market('Maize', 'SELLABLE'))
    result = compare(payload)
    maize = screening(result)['Maize']
    assert maize.status == 'EXCLUDED'
    assert [r.code for r in maize.reasons] == ['IRRIGATED_ONLY_ON_RAINFED_FARM']
    current = result.strategies[0]
    water = {c.constraint: c for c in current.constraint_checks}['WATER_REGIME']
    assert water.status == 'REVIEW_REQUIRED' and 'irrigation' in water.detail
    assert all('Maize' not in sum(s.years, []) for s in result.strategies[1:])


def test_rainfed_new_crops_require_water_review():
    result = compare(profile())
    for alt in result.strategies[1:]:
        water = {c.constraint: c for c in alt.constraint_checks}['WATER_REGIME']
        assert water.status == 'REVIEW_REQUIRED'
        assert 'not evaluated' in water.detail
    current_water = {c.constraint: c.status for c in result.strategies[0].constraint_checks}['WATER_REGIME']
    assert current_water == 'SATISFIED'


def test_crop_without_declared_window_is_not_evaluable():
    payload = profile()
    payload['constraints']['market_access'].append(market('Pea', 'CONTRACTED'))
    payload['local_calendar'].append(window('Lentil', (11, 12)))  # no harvest window
    result = compare(payload)
    screen = screening(result)
    assert screen['Pea'].status == 'NOT_EVALUABLE'
    assert [r.code for r in screen['Pea'].reasons] == ['CALENDAR_NOT_DECLARED']
    assert [r.code for r in screen['Lentil'].reasons] == ['HARVEST_WINDOW_NOT_DECLARED']
    used = {c.crop_label for s in result.strategies[1:] for slot in s.cycle for c in slot}
    assert not used & {'Pea', 'Lentil'}


def test_current_crop_without_window_makes_current_not_fully_evaluable():
    payload = profile()
    payload['local_calendar'] = [w for w in payload['local_calendar'] if w['crop_label'] != 'Barley']
    result = compare(payload)
    current = result.strategies[0]
    assert current.screening_result == 'NOT_FULLY_EVALUABLE'
    assert current.comparison.months_with_crop is None
    assert current.comparison.not_evaluable


def test_soil_and_climate_are_declared_not_evaluable():
    result = compare(profile())
    for s in result.strategies:
        checks = {c.constraint: c.status for c in s.constraint_checks}
        assert checks['SOIL'] == 'NOT_EVALUABLE' and checks['CLIMATE'] == 'NOT_EVALUABLE'


# ---------------------------------------------------------------- insufficient or inconsistent input

def test_single_season_history_is_insufficient_and_explained():
    payload = profile()
    payload['crop_history'] = payload['crop_history'][:1]
    result = compare(payload)
    assert result.status == 'INSUFFICIENT_INPUT'
    assert result.strategies == []
    assert any('two years with a main crop' in e for e in result.explanation)


def test_no_calendar_gives_current_only_with_explanation():
    payload = profile()
    payload['local_calendar'] = []
    result = compare(payload)
    assert result.status == 'FEWER_ALTERNATIVES'
    assert [s.is_current for s in result.strategies] == [True]
    assert any('No local_calendar declared' in e for e in result.explanation)
    assert all(s.status == 'NOT_EVALUABLE' for s in result.candidate_screening)


def test_single_family_candidates_are_explained():
    payload = profile()
    payload['local_calendar'] = payload['local_calendar'][:2]  # wheat and barley only
    result = compare(payload)
    assert result.status == 'FEWER_ALTERNATIVES'
    assert any('Poaceae' in e for e in result.explanation)


def test_profile_errors_block_comparison():
    payload = profile()
    payload['constraints']['irrigation_allowance'] = {'value': 100, 'unit': 'mm/season', 'origin': 'FARMER_ESTIMATE'}
    result = compare(payload)
    assert result.status == 'BLOCKED_BY_PROFILE_ERRORS'
    assert result.strategies == []
    assert any('irrigation' in e.lower() for e in result.explanation)


def test_monoculture_and_fallow_years_are_described():
    payload = profile()
    payload['crop_history'] = [
        season('Common wheat', 2021, '2020-11-05', '2021-06-25'),
        season('fallow', 2022, None, None, role='FALLOW'),
        season('Common wheat', 2023, '2022-11-05', '2023-06-25'),
        season('fallow', 2024, None, None, role='FALLOW'),
    ]
    payload['crop_history'] = [{k: v for k, v in s.items() if v is not None} for s in payload['crop_history']]
    result = compare(payload, horizon_years=2)
    current = result.strategies[0]
    assert current.years == [['Common wheat'], ['Fallow']]
    assert current.comparison.consecutive_same_family == 1  # wheat follows wheat across the fallow year
    assert current.transitions[0].fallow_gap.min >= 12


def test_horizon_defaults_and_short_horizon():
    payload = profile()
    payload['constraints']['planning_horizon_years'] = 6
    assert compare(payload).horizon_years == 6
    result = compare(profile(), horizon_years=2)
    assert all(len(s.years) == 2 for s in result.strategies)
    assert all(len(s.cycle) == 2 for s in result.strategies[1:])


def test_strategy_maps_onto_shared_rotation_contract():
    strategy = compare(profile()).strategies[1]
    shared = to_shared_rotation(strategy, rotation_id=UUID(int=1), case_id=UUID(int=2))
    assert shared.source_kind == 'MODEL_SCENARIO' and shared.verified_impact is None
    assert shared.years == strategy.years


def test_request_rejects_unknown_fields_and_bad_horizon():
    with pytest.raises(ValidationError):
        RotationCompareRequest.model_validate({'profile': profile(), 'expected_yield_t_ha': 5})
    with pytest.raises(ValidationError):
        RotationCompareRequest.model_validate({'profile': profile(), 'horizon_years': 1})


# ---------------------------------------------------------------- HTTP

async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


@pytest.mark.asyncio
async def test_compare_endpoint_and_validation_errors():
    async with await _client() as client:
        response = await client.post('/api/v1/rotations/compare', json={'profile': profile()})
        assert response.status_code == 200
        body = response.json()
        assert body['schema_version'] == '1.0' and body['source_kind'] == 'MODEL_SCENARIO'
        assert body['strategies'][0]['is_current'] is True
        assert len(body['strategies']) >= 3

        bad_horizon = await client.post('/api/v1/rotations/compare', json={'profile': profile(), 'horizon_years': 0})
        assert bad_horizon.status_code == 422
        extra = copy.deepcopy(profile()) | {'expected_yield_t_ha': 5}
        assert (await client.post('/api/v1/rotations/compare', json={'profile': extra})).status_code == 422
        bad_month = profile()
        bad_month['local_calendar'][0]['sowing_start_month'] = 13
        assert (await client.post('/api/v1/rotations/compare', json={'profile': bad_month})).status_code == 422

        demo = await client.get('/api/rotations/demo')
        assert demo.status_code == 200 and len(demo.json()['rotations']) == 3

    schema = app.openapi()
    assert '/api/v1/rotations/compare' in schema['paths']
    assert {'RotationComparison', 'RotationStrategy', 'RotationCompareRequest'} <= schema['components']['schemas'].keys()
    assert 'Rotation' in schema['components']['schemas']  # ABB-02 contracts still registered
    json.dumps(schema)
