"""ABB-18 scenario, priority and sensitivity tests. All inputs are SYNTHETIC fixtures, not real farm records."""
import calendar
import copy
import json

import httpx
import pytest
from pydantic import ValidationError

from agroblackbox.app import app
from agroblackbox.services.metrics import analyze_power
from agroblackbox.services.rotations import RotationCompareRequest, compare_rotations
from agroblackbox.services.scenarios import (
    ScenarioAnalysisRequest,
    SensitivityRequest,
    analyse_scenarios,
    analyse_sensitivity,
)

from test_rotations import market, profile, season, window

DRY_SPRING = {'scenario_type': 'HYPOTHETICAL', 'id': 'dry-spring', 'label': 'Dry spring (hypothetical)',
              'flags': [{'condition': 'DRIER', 'months': [3, 4, 5]}]}


def analyse(payload=None, **kwargs):
    return analyse_scenarios(ScenarioAnalysisRequest(profile=payload or profile(), **kwargs))


def sensitivity(base, change):
    return analyse_sensitivity(SensitivityRequest(base=base, change=change))


def positions(result):
    return [(p.strategy_kind, p.position) for p in result.ordering.positions]


def episode(drop_june_days=0):
    """ABB-08 monthly anomalies from a synthetic daily series: spring 2022 drier, July hotter (known values).

    Reference 2019-2021: 2 mm/day and 25 °C every day. Event 2022: March-May 0.5 mm/day (March anomaly
    -46.5 mm), July 29 °C (+4 °C). Dropping June days makes the event June partial, so its anomaly is null."""
    def rain(y, m, d):
        return 0.5 if y == 2022 and m in (3, 4, 5) else 2.0

    def tmax(y, m, d):
        return 29.0 if y == 2022 and m == 7 else 25.0

    daily = {'PRECTOTCORR': {}, 'T2M_MAX': {}}
    for y in (2019, 2020, 2021, 2022):
        for m in range(1, 13):
            for d in range(1, calendar.monthrange(y, m)[1] + 1):
                key = f'{y:04d}{m:02d}{d:02d}'
                daily['PRECTOTCORR'][key] = rain(y, m, d)
                daily['T2M_MAX'][key] = tmax(y, m, d)
    for d in range(1, drop_june_days + 1):
        del daily['PRECTOTCORR'][f'202206{d:02d}']
    analysis = analyze_power(daily, 2022, 2019, 2021)
    return {
        'source_kind': 'OBSERVED', 'dataset': 'NASA POWER Daily Point (SYNTHETIC TEST SERIES)', 'data_sha256': 'a' * 64,
        'retrieved_at': '2026-11-14T12:00:00Z', 'event_year': 2022, 'reference_start': 2019, 'reference_end': 2021,
        'spatial_resolution': {'value': None, 'unit': 'degree', 'description': 'synthetic test grid cell'},
        'monthly': json.loads(json.dumps(analysis['monthly'])),
    }


def historical(drop_june_days=0):
    return {'scenario_type': 'HISTORICAL_EPISODE', 'id': 'replay-2022', 'label': '2022 replay (synthetic)',
            'episode': episode(drop_june_days),
            'flag_rules': [{'condition': 'DRIER', 'threshold': 30, 'unit': 'mm'},
                           {'condition': 'HOTTER', 'threshold': 2, 'unit': '°C'}]}


# ---------------------------------------------------------------- reproducibility and labelling

def test_same_input_same_output_and_stable_hash():
    kwargs = dict(climate_scenarios=[DRY_SPRING, historical()])
    first = analyse(**kwargs)
    assert analyse(**kwargs).model_dump_json() == first.model_dump_json()
    assert len(first.input_sha256) == 64 and all(c in '0123456789abcdef' for c in first.input_sha256)
    changed = analyse(climate_scenarios=[DRY_SPRING, historical()],
                      priorities_override=[{'criterion': 'CROP_DIVERSITY', 'rank': 1}])
    assert changed.input_sha256 != first.input_sha256
    # Defaults are part of the canonical form: an explicit default hashes the same as an omitted one.
    explicit = analyse(climate_scenarios=[DRY_SPRING, historical()], horizon_years=None)
    assert explicit.input_sha256 == first.input_sha256


def test_simulation_observation_and_validated_result_are_separated():
    result = analyse(climate_scenarios=[DRY_SPRING, historical()])
    assert result.source_kind == 'MODEL_SCENARIO' and result.verified_impact is None
    assert all(s.source_kind == 'MODEL_SCENARIO' and s.verified_impact is None for s in result.comparison.strategies)
    hypo, hist = result.scenarios
    assert (hypo.scenario_label, hypo.source_kind, hypo.is_forecast, hypo.provenance) == (
        'HYPOTHETICAL_SCENARIO', 'MODEL_SCENARIO', False, None)
    assert 'not a forecast' in hypo.statement
    assert (hist.scenario_label, hist.source_kind, hist.is_forecast) == ('HISTORICAL_EPISODE_OBSERVED', 'OBSERVED', False)
    assert hist.provenance.data_sha256 == 'a' * 64 and hist.provenance.event_year == 2022
    assert 'not a forecast' in hist.statement
    kinds = {n.kind: n for n in result.separation}
    assert kinds['VALIDATED_FIELD_RESULT'].present is False
    assert kinds['OBSERVED'].present and kinds['HYPOTHETICAL_SCENARIO'].present
    assert all(e.basis == 'CALENDAR_OVERLAP_NOT_IMPACT' for e in result.exposure)


def test_comparison_is_the_unchanged_abb17_output():
    result = analyse()
    direct = compare_rotations(RotationCompareRequest(profile=profile()))
    assert result.comparison.model_dump() == direct.model_dump()


# ---------------------------------------------------------------- climate scenarios and exposure

def test_historical_episode_flags_from_abb08_anomalies():
    hist = analyse(climate_scenarios=[historical()]).scenarios[0]
    flagged = {f.month: f.conditions for f in hist.flagged_months}
    assert flagged == {3: ['DRIER'], 4: ['DRIER'], 5: ['DRIER'], 7: ['HOTTER']}
    march = next(f for f in hist.flagged_months if f.month == 3)
    assert march.basis == ['Precipitation anomaly -46.5 mm ≤ -30 mm (DRIER rule).']
    assert hist.not_evaluable_months == []


def test_months_without_anomaly_are_not_evaluable_and_never_unflagged():
    result = analyse(climate_scenarios=[historical(drop_june_days=3)])
    hist = result.scenarios[0]
    assert [m.month for m in hist.not_evaluable_months] == [6]
    assert 'precipitation anomaly not available' in hist.not_evaluable_months[0].reason
    current = next(e for e in result.exposure if e.strategy_kind == 'CURRENT')
    assert current.status == 'PARTIAL' and current.flagged_months_in_field_per_year is None
    assert all(6 in row.not_evaluable_months_in_field for row in current.by_cycle_year)


def test_exposure_counts_follow_the_declared_windows():
    scenario = {'scenario_type': 'HYPOTHETICAL', 'id': 'mixed', 'label': 'Dry spring, hot October',
                'flags': [{'condition': 'DRIER', 'months': [3, 4, 5]}, {'condition': 'HOTTER', 'months': [10]}]}
    result = analyse(climate_scenarios=[scenario])
    current = next(e for e in result.exposure if e.strategy_kind == 'CURRENT')
    # Wheat and barley: sown Oct-Dec, harvested Jun-Jul. Certainly in the field Dec-Jun, possibly Oct-Jul.
    row = current.by_cycle_year[0]
    assert row.months_in_field_certain == [1, 2, 3, 4, 5, 6, 12]
    assert row.months_in_field_possible == [1, 2, 3, 4, 5, 6, 7, 10, 11, 12]
    assert [(f.month, f.in_field) for f in row.flagged_months_in_field] == [
        (3, 'CERTAIN'), (4, 'CERTAIN'), (5, 'CERTAIN'), (10, 'POSSIBLE')]
    assert current.status == 'EVALUATED'
    assert (current.flagged_months_in_field_per_year.min, current.flagged_months_in_field_per_year.max) == (3, 4)
    assert (current.cycle_years_with_flagged_months.min, current.cycle_years_with_flagged_months.max) == (2, 2)
    assert 'not evaluated' in current.explanation


def test_missing_calendar_makes_exposure_not_evaluable():
    payload = profile()
    payload['local_calendar'] = [w for w in payload['local_calendar'] if w['crop_label'] != 'Barley']
    current = next(e for e in analyse(payload, climate_scenarios=[DRY_SPRING]).exposure if e.strategy_kind == 'CURRENT')
    assert current.status == 'PARTIAL' and current.flagged_months_in_field_per_year is None
    barley = next(r for r in current.by_cycle_year if r.crop_label == 'Barley')
    assert barley.status == 'NOT_EVALUABLE' and 'not invented' in barley.reason

    payload['local_calendar'] = [w for w in payload['local_calendar'] if w['crop_label'] != 'Common wheat']
    current = next(e for e in analyse(payload, climate_scenarios=[DRY_SPRING]).exposure if e.strategy_kind == 'CURRENT')
    assert current.status == 'NOT_EVALUABLE'


# ---------------------------------------------------------------- transparent ordering and trade-offs

def test_lexicographic_ordering_by_rank_with_every_step_explained():
    result = analyse()  # priorities: SOIL_COVER 1, CROP_DIVERSITY 2, WATER_USE 3
    o = result.ordering
    assert o.rule == 'LEXICOGRAPHIC_BY_FARMER_RANK' and o.is_recommendation is False
    assert [c.criterion_id for c in o.criteria] == ['DECLARED_CONSTRAINTS', 'SOIL_COVER_MONTHS', 'BOTANICAL_FAMILIES']
    assert [(n.criterion.value, n.rank) for n in o.criteria_not_used] == [('WATER_USE', 3)]
    # months_with_crop.min: CALENDAR_COVER 8.0, CURRENT 7.0, FAMILY_DIVERSIFICATION 6.2, MINIMAL_CHANGE 5.5
    assert positions(result) == [('CALENDAR_COVER', 1), ('CURRENT', 2), ('FAMILY_DIVERSIFICATION', 3),
                                 ('MINIMAL_CHANGE', 4)]
    assert [s.step for s in o.steps] == [0, 1, 2]
    assert all(d.decided_by == 'SOIL_COVER_MONTHS' for d in o.adjacent_decisions)
    assert 'CALENDAR_COVER has 8 and CURRENT 7 months per year' in o.adjacent_decisions[0].explanation
    assert o.steps[2].explanation == 'Step 2 (BOTANICAL_FAMILIES): no tie left to split.'


def test_ties_are_shown_not_hidden():
    result = analyse(priorities_override=[{'criterion': 'CROP_DIVERSITY', 'rank': 1}])
    # Families: FAMILY_DIVERSIFICATION 4, MINIMAL_CHANGE 2, CALENDAR_COVER 2, CURRENT 1.
    assert positions(result) == [('FAMILY_DIVERSIFICATION', 1), ('MINIMAL_CHANGE', 2), ('CALENDAR_COVER', 2),
                                 ('CURRENT', 3)]
    tied = {p.strategy_kind: p.tied_with for p in result.ordering.positions}
    assert tied['MINIMAL_CHANGE'] == ['alt-3-calendar-cover']
    tie = result.ordering.adjacent_decisions[1]
    assert tie.decided_by is None and 'not a preference' in tie.explanation


def test_declared_constraints_come_before_priorities():
    payload = profile()
    payload['constraints']['excluded_crops'] = ['Barley']  # the current rotation grows barley
    result = analyse(payload)
    assert positions(result)[-1][0] == 'CURRENT'
    last = result.ordering.adjacent_decisions[-1]
    assert last.decided_by == 'DECLARED_CONSTRAINTS' and 'CONFLICTS_WITH_DECLARED_CONSTRAINTS' in last.explanation


def test_no_priorities_leaves_strategies_tied():
    result = analyse(priorities_override=[])
    assert {p.position for p in result.ordering.positions} == {1}
    assert any('declared constraints only' in e for e in result.explanation)


def test_risk_reduction_uses_scenario_exposure_as_labelled_proxy():
    without = analyse(priorities_override=[{'criterion': 'RISK_REDUCTION', 'rank': 1}])
    assert without.ordering.criteria_not_used[0].criterion.value == 'RISK_REDUCTION'
    assert 'no risk model' in without.ordering.criteria_not_used[0].reason
    result = analyse(priorities_override=[{'criterion': 'RISK_REDUCTION', 'rank': 1}], climate_scenarios=[DRY_SPRING])
    crit = result.ordering.criteria[1]
    assert crit.criterion_id == 'SCENARIO_EXPOSURE:dry-spring' and crit.direction == 'FEWER_FIRST'
    assert 'not a risk estimate' in crit.description
    # Chickpea is sown Feb-Mar, so March is only possibly in the field: 2.8 vs 3 months per year.
    assert positions(result)[0] == ('FAMILY_DIVERSIFICATION', 1)


def test_trade_offs_state_what_each_strategy_gives_up():
    result = analyse(climate_scenarios=[DRY_SPRING])
    t = {x.strategy_kind: x for x in result.trade_offs}
    soil = {c.criterion_id: c for c in t['FAMILY_DIVERSIFICATION'].criteria}['SOIL_COVER_MONTHS']
    assert soil.relation_to_most_favourable == 'GIVES_UP' and soil.most_favourable_value == 8.0
    assert soil.most_favourable_strategy_ids == ['alt-3-calendar-cover']
    assert any(g.startswith('SOIL_COVER_MONTHS: 6.2 months per year where CALENDAR_COVER has 8') for g in
               t['FAMILY_DIVERSIFICATION'].gives_up)
    assert any(g.startswith('BOTANICAL_FAMILIES: 4 families instead of 1') for g in t['FAMILY_DIVERSIFICATION'].gains_vs_current)
    assert 'Drops: Common wheat.' in t['FAMILY_DIVERSIFICATION'].other_differences_vs_current
    assert {c.relation_to_current for c in t['CURRENT'].criteria} == {'REFERENCE'}


def _keys(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from _keys(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _keys(inner)


def test_no_yield_saving_probability_or_score_fields():
    base = ScenarioAnalysisRequest(profile=profile(), climate_scenarios=[DRY_SPRING, historical()])
    bodies = [analyse_scenarios(base).model_dump(mode='json'),
              sensitivity(base, {'change_type': 'PRIORITY_SWAP', 'criterion_a': 'SOIL_COVER',
                                 'criterion_b': 'CROP_DIVERSITY'}).model_dump(mode='json')]
    for body in bodies:
        keys = {k.lower() for k in _keys(body)}
        for forbidden in ('yield', 'saving', 'score', 'income', 'revenue', 'percent', 'probability', 'weight',
                          'confidence', 'benefit_value'):
            assert not [k for k in keys if forbidden in k], forbidden
        assert body['verified_impact'] is None


# ---------------------------------------------------------------- sensitivity

def test_priority_swap_shows_which_criterion_changes_and_why():
    base = ScenarioAnalysisRequest(profile=profile())
    result = sensitivity(base, {'change_type': 'PRIORITY_SWAP', 'criterion_a': 'SOIL_COVER',
                                'criterion_b': 'CROP_DIVERSITY'})
    assert result.status == 'COMPARED'
    assert [(c.criterion.value, c.rank_before, c.rank_after) for c in result.priority_changes] == [
        ('CROP_DIVERSITY', 2, 1), ('SOIL_COVER', 1, 2)]
    changes = {c.criterion_id: c for c in result.criteria_changes}
    assert (changes['BOTANICAL_FAMILIES'].change, changes['BOTANICAL_FAMILIES'].step_after) == ('MOVED_EARLIER', 1)
    assert changes['SOIL_COVER_MONTHS'].change == 'MOVED_LATER'
    moves = {p.strategy_kind: (p.position_before, p.position_after, p.movement) for p in result.position_changes}
    assert moves['FAMILY_DIVERSIFICATION'] == (3, 1, 'UP') and moves['CURRENT'] == (2, 4, 'DOWN')
    flip = next(p for p in result.pair_changes if {p.first_kind, p.second_kind} == {'CURRENT', 'FAMILY_DIVERSIFICATION'})
    assert flip.order_changed and flip.decided_by_before == 'SOIL_COVER_MONTHS'
    assert flip.decided_by_after == 'BOTANICAL_FAMILIES'
    assert 'FAMILY_DIVERSIFICATION has 4 and CURRENT 1 families' in flip.explanation
    assert result.explanation[0] == 'Swapped priority ranks: SOIL_COVER 1 → 2, CROP_DIVERSITY 2 → 1.'
    assert any('moves from position 3 to 1' in e for e in result.explanation)
    assert result.base_input_sha256 != result.variant_input_sha256
    again = sensitivity(base, {'change_type': 'PRIORITY_SWAP', 'criterion_a': 'SOIL_COVER',
                               'criterion_b': 'CROP_DIVERSITY'})
    assert again.model_dump_json() == result.model_dump_json()


def test_priority_change_without_reordering_says_so():
    base = ScenarioAnalysisRequest(profile=profile(), priorities_override=[{'criterion': 'SOIL_COVER', 'rank': 1}])
    result = sensitivity(base, {'change_type': 'PRIORITIES', 'priorities': [
        {'criterion': 'SOIL_COVER', 'rank': 1}, {'criterion': 'WORKLOAD', 'rank': 2}]})
    assert all(p.movement == 'SAME' for p in result.position_changes)
    assert result.pair_changes == []
    assert 'No ordering position changed.' in result.explanation
    assert [(c.criterion.value, c.rank_before, c.rank_after) for c in result.priority_changes] == [('WORKLOAD', None, 2)]


def test_water_change_shows_screening_and_constraint_changes():
    payload = profile()
    payload['crop_history'] = [season('Maize', 2022, '2022-04-20', '2022-09-30', water='IRRIGATED'),
                               season('Common wheat', 2023, '2022-11-05', '2023-06-25', water='IRRIGATED'),
                               season('Maize', 2024, '2024-04-20', '2024-09-30', water='IRRIGATED'),
                               season('Common wheat', 2025, '2024-11-05', '2025-06-25', water='IRRIGATED')]
    payload['local_calendar'].append(window('Maize', (4, 5), (9, 10)))
    payload['constraints']['water_regime'] = 'IRRIGATED'
    payload['constraints']['irrigation_allowance'] = {'value': 300, 'unit': 'mm/season', 'origin': 'FARMER_ESTIMATE'}
    payload['constraints']['market_access'].append(market('Maize', 'SELLABLE'))
    base = ScenarioAnalysisRequest(profile=payload)
    result = sensitivity(base, {'change_type': 'WATER', 'water': {'water_regime': 'RAINFED'}})
    assert result.status == 'COMPARED' and result.change_summary == ['Water regime: IRRIGATED → RAINFED.']
    maize = next(s for s in result.screening_changes if s.crop_label == 'Maize')
    assert (maize.status_before, maize.status_after) == ('ELIGIBLE', 'EXCLUDED')
    assert 'IRRIGATED_ONLY_ON_RAINFED_FARM' in maize.reasons_after
    current = next(s for s in result.strategy_changes if s.strategy_kind == 'CURRENT')
    assert any(c.startswith('WATER_REGIME: NOT_EVALUABLE → REVIEW_REQUIRED') for c in current.constraint_changes)


def test_scenario_change_adds_exposure_criterion():
    base = ScenarioAnalysisRequest(profile=profile(), priorities_override=[
        {'criterion': 'RISK_REDUCTION', 'rank': 1}, {'criterion': 'SOIL_COVER', 'rank': 2}])
    result = sensitivity(base, {'change_type': 'CLIMATE_SCENARIOS', 'climate_scenarios': [DRY_SPRING]})
    added = {c.criterion_id: c for c in result.criteria_changes}['SCENARIO_EXPOSURE:dry-spring']
    assert (added.change, added.step_after) == ('ADDED', 1)
    assert {e.scenario_id for e in result.exposure_changes} == {'dry-spring'}
    assert all(e.before is None and e.after is not None for e in result.exposure_changes)
    assert any(p.movement != 'SAME' for p in result.position_changes)


def test_blocked_profile_is_not_analysed_and_not_compared():
    payload = profile()
    payload['priorities'] = [{'criterion': 'SOIL_COVER', 'rank': 1}, {'criterion': 'CROP_DIVERSITY', 'rank': 1}]
    blocked = analyse(payload)
    assert blocked.status == 'NOT_ANALYSED' and blocked.ordering is None and blocked.exposure == []
    assert blocked.comparison.status == 'BLOCKED_BY_PROFILE_ERRORS'
    result = sensitivity(ScenarioAnalysisRequest(profile=payload), {
        'change_type': 'PRIORITIES', 'priorities': [{'criterion': 'SOIL_COVER', 'rank': 1}]})
    assert result.status == 'NOT_COMPARABLE' and result.variant_ordering is not None and result.base_ordering is None


# ---------------------------------------------------------------- validation (422)

def test_invalid_what_if_inputs_are_rejected():
    def bad(**kwargs):
        with pytest.raises(ValidationError):
            ScenarioAnalysisRequest.model_validate({'profile': profile(), **kwargs})

    bad(priorities_override=[{'criterion': 'SOIL_COVER', 'rank': 1}, {'criterion': 'WORKLOAD', 'rank': 1}])
    bad(priorities_override=[{'criterion': 'SOIL_COVER', 'rank': 1}, {'criterion': 'SOIL_COVER', 'rank': 2}])
    bad(priorities_override=[{'criterion': 'SOIL_COVER', 'rank': 1, 'weight': 0.7}])
    bad(water_override={'water_regime': 'RAINFED',
                        'irrigation_allowance': {'value': 50, 'unit': 'mm/season', 'origin': 'FARMER_ESTIMATE'}})
    bad(climate_scenarios=[DRY_SPRING, DRY_SPRING])
    bad(climate_scenarios=[{**DRY_SPRING, 'id': f's{i}'} for i in range(7)])
    bad(climate_scenarios=[{**DRY_SPRING, 'flags': [{'condition': 'DRIER', 'months': [13]}]}])
    bad(climate_scenarios=[{**DRY_SPRING, 'flags': [{'condition': 'DRIER', 'months': [4]},
                                                    {'condition': 'WETTER', 'months': [4]}]}])
    bad(climate_scenarios=[{**DRY_SPRING, 'probability': 0.3}])
    rule_unit = historical()
    rule_unit['flag_rules'] = [{'condition': 'DRIER', 'threshold': 30, 'unit': '°C'}]
    bad(climate_scenarios=[rule_unit])
    zero = historical()
    zero['flag_rules'] = [{'condition': 'DRIER', 'threshold': 0, 'unit': 'mm'}]
    bad(climate_scenarios=[zero])
    coords = historical()
    coords['episode']['request_params'] = {'latitude': 41.6, 'longitude': -0.9}
    bad(climate_scenarios=[coords])
    overlap = historical()
    overlap['episode']['reference_end'] = 2022
    bad(climate_scenarios=[overlap])
    forecast = historical()
    forecast['episode']['source_kind'] = 'MODEL_SCENARIO'
    bad(climate_scenarios=[forecast])

    base = {'profile': profile()}
    for change in ({'change_type': 'PRIORITY_SWAP', 'criterion_a': 'SOIL_COVER', 'criterion_b': 'SOIL_COVER'},
                   {'change_type': 'PRIORITY_SWAP', 'criterion_a': 'SOIL_COVER', 'criterion_b': 'WORKLOAD'},
                   {'change_type': 'WATER', 'water': {'water_regime': 'DESERT'}},
                   {'change_type': 'FORECAST'}):
        with pytest.raises(ValidationError):
            SensitivityRequest.model_validate({'base': base, 'change': change})


# ---------------------------------------------------------------- HTTP

async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


@pytest.mark.asyncio
async def test_scenario_and_sensitivity_endpoints():
    body = {'profile': profile(), 'climate_scenarios': [DRY_SPRING, historical()]}
    async with await _client() as client:
        response = await client.post('/api/v1/rotations/scenarios', json=body)
        assert response.status_code == 200
        data = response.json()
        assert data['schema_version'] == '1.0' and data['status'] == 'ANALYSED'
        assert data['verified_impact'] is None and data['ordering']['is_recommendation'] is False
        again = await client.post('/api/v1/rotations/scenarios', json=body)
        assert again.json() == data

        swap = {'base': body, 'change': {'change_type': 'PRIORITY_SWAP', 'criterion_a': 'SOIL_COVER',
                                         'criterion_b': 'CROP_DIVERSITY'}}
        response = await client.post('/api/v1/rotations/sensitivity', json=swap)
        assert response.status_code == 200 and response.json()['status'] == 'COMPARED'

        extra = copy.deepcopy(body) | {'expected_yield_t_ha': 5}
        assert (await client.post('/api/v1/rotations/scenarios', json=extra)).status_code == 422
        dup = copy.deepcopy(body) | {'priorities_override': [{'criterion': 'SOIL_COVER', 'rank': 1},
                                                             {'criterion': 'WORKLOAD', 'rank': 1}]}
        assert (await client.post('/api/v1/rotations/scenarios', json=dup)).status_code == 422
        bad_swap = copy.deepcopy(swap)
        bad_swap['change']['criterion_b'] = 'INPUT_COSTS'
        assert (await client.post('/api/v1/rotations/sensitivity', json=bad_swap)).status_code == 422

    schema = app.openapi()
    assert {'/api/v1/rotations/scenarios', '/api/v1/rotations/sensitivity',
            '/api/v1/rotations/compare'} <= schema['paths'].keys()
    assert {'ScenarioAnalysis', 'ScenarioAnalysisRequest', 'SensitivityAnalysis',
            'SensitivityRequest'} <= schema['components']['schemas'].keys()
    json.dumps(schema)
