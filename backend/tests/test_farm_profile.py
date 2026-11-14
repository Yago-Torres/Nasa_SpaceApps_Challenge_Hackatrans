"""ABB-11 farm profile tests. All inputs are SYNTHETIC fixtures, not real farm records."""
import json
from datetime import date

import httpx
import pytest
from pydantic import ValidationError

from agroblackbox.app import app
from agroblackbox.crop_catalog import ENTRIES, catalog, resolve_crop
from agroblackbox.farm_profile import FarmProfile, SoilObservation, assess_profile


def soil(prop, value, unit, origin='LOCAL_MEASUREMENT', top=0, bottom=30, **extra):
    base = {'property': prop, 'value': value, 'unit': unit, 'origin': origin,
            'depth_top_cm': top, 'depth_bottom_cm': bottom}
    if origin == 'LOCAL_MEASUREMENT':
        base |= {'method': 'synthetic lab method', 'sampled_on': '2024-02-10'}
    return base | extra


def season(label, year, sow, harvest, role='MAIN_CROP', water='RAINFED', **extra):
    return {'crop_label': label, 'season_year': year, 'sowing_date': sow, 'harvest_date': harvest,
            'role': role, 'water_regime': water} | extra


def complete_profile():
    return {
        'soil': [soil('CLAY', 30, '%'), soil('SILT', 40, '%'), soil('SAND', 30, '%'), soil('PH', 8.1, 'pH')],
        'crop_history': [
            season('Common wheat', 2023, '2022-11-05', '2023-06-25'),
            season('Cebada', 2024, '2023-11-10', '2024-06-20'),
        ],
        'local_calendar': [
            {'crop_label': 'Common wheat', 'sowing_start_month': 10, 'sowing_end_month': 12,
             'harvest_start_month': 6, 'harvest_end_month': 7},
        ],
        'constraints': {'water_regime': 'RAINFED', 'available_equipment': ['seed drill'],
                        'market_access': [{'crop_label': 'Barley', 'status': 'SELLABLE'}]},
        'priorities': [{'criterion': 'SOIL_COVER', 'rank': 1}, {'criterion': 'INCOME_STABILITY', 'rank': 2}],
    }


def assess(payload):
    return assess_profile(FarmProfile.model_validate(payload))


def codes(result, severity=None):
    return {i.code for i in result.issues if severity is None or i.severity == severity}


# ---------------------------------------------------------------- catalogue

def test_catalogue_is_identity_only_and_pending_review():
    data = catalog()
    assert len(data.entries) >= 20
    assert all(e.review_status.value == 'PENDING' for e in data.entries)
    assert all(e.agronomic_parameters is None for e in data.entries)
    assert ENTRIES['chickpea'].is_legume and ENTRIES['alfalfa'].is_legume
    assert not ENTRIES['barley'].is_legume
    assert all(e.is_legume == (e.botanical_family == 'Fabaceae') for e in data.entries)


@pytest.mark.parametrize('name,code', [
    ('Garbanzo', 'chickpea'), ('MAÍZ', 'maize'), ('maiz', 'maize'), ('Zea mays', 'maize'),
    ('faba_bean', 'faba_bean'), ('  common   wheat ', 'wheat_soft'),
])
def test_resolve_crop_exact_names(name, code):
    assert resolve_crop(name).code == code


@pytest.mark.parametrize('name', ['wheat', 'whaet', 'cover crop', '', None])
def test_resolve_crop_does_not_guess(name):
    assert resolve_crop(name) is None  # "wheat" is ambiguous (soft vs durum): never guessed


# ---------------------------------------------------------------- completeness

def test_empty_profile_is_limited_not_simulated():
    result = assess({})
    assert result.rotation_input_status == 'LIMITED_BY_MISSING_DATA'
    assert set(result.sections.values()) == {'MISSING'}
    assert codes(result, 'ERROR') == set()
    assert {'SOIL_MISSING', 'CROP_HISTORY_MISSING', 'LOCAL_CALENDAR_MISSING',
            'CONSTRAINTS_MISSING', 'PRIORITIES_MISSING'} <= codes(result, 'MISSING_DATA')
    assert all(i.consequence for i in result.issues if i.severity == 'MISSING_DATA')
    assert result.profile.soil == []  # nothing filled in by default


def test_complete_profile_has_no_issues_and_no_outcome_fields():
    result = assess(complete_profile())
    assert result.issues == []
    assert result.rotation_input_status == 'INPUTS_COMPLETE'
    assert set(result.sections.values()) == {'PROVIDED'}
    # Limitations explicitly say "no yield / water saving is computed"; everything else must not mention outcomes.
    serialized = json.dumps(result.model_dump(mode='json', exclude={'limitations'})).lower()
    for forbidden in ('yield', 'score', 'probability', 'saving', 'confidence'):
        assert forbidden not in serialized
    assert any('not that any rotation is agronomically validated' in l for l in result.limitations)


# ---------------------------------------------------------------- soil

def test_local_measurement_is_distinguished_from_regional_estimate():
    payload = complete_profile()
    payload['soil'] = [soil('CLAY', 25, '%', origin='REGIONAL_ESTIMATE')]
    result = assess(payload)
    assert result.soil_origins == ['REGIONAL_ESTIMATE']
    assert 'NO_LOCAL_SOIL_MEASUREMENT' in codes(result, 'WARNING')
    assert 'REGIONAL_SOURCE_MISSING' in codes(result, 'ERROR')  # must name the map/product
    assert 'REGIONAL_RESOLUTION_MISSING' in codes(result, 'WARNING')


def test_regional_estimate_with_source_and_resolution_is_accepted():
    payload = complete_profile()
    payload['soil'].append(soil('ORGANIC_CARBON', 9, 'g/kg', origin='REGIONAL_ESTIMATE',
                                source_reference='Synthetic soil map fixture',
                                spatial_resolution={'value': 250, 'unit': 'm', 'description': 'grid cell'}))
    result = assess(payload)
    assert codes(result, 'ERROR') == set()
    assert result.soil_origins == ['LOCAL_MEASUREMENT', 'REGIONAL_ESTIMATE']


@pytest.mark.parametrize('obs,code', [
    (soil('PH', 15, 'pH'), 'SOIL_VALUE_OUT_OF_RANGE'),
    (soil('CLAY', 120, '%'), 'SOIL_VALUE_OUT_OF_RANGE'),
    (soil('ORGANIC_CARBON', -1, 'g/kg'), 'SOIL_VALUE_OUT_OF_RANGE'),
    (soil('BULK_DENSITY', 0, 'g/cm3'), 'SOIL_VALUE_OUT_OF_RANGE'),
    (soil('PH', 7, '%'), 'SOIL_UNIT_NOT_ALLOWED'),
    (soil('ELECTRICAL_CONDUCTIVITY', 1.2, 'mS/cm'), 'SOIL_UNIT_NOT_ALLOWED'),
])
def test_soil_value_and_unit_validation(obs, code):
    payload = complete_profile()
    payload['soil'].append(obs)
    result = assess(payload)
    assert code in codes(result, 'ERROR')
    assert result.rotation_input_status == 'BLOCKED_BY_ERRORS'


def test_texture_fractions_must_add_up():
    payload = complete_profile()
    payload['soil'][0]['value'] = 60  # 60 + 40 + 30 = 130 %
    assert 'TEXTURE_SUM_INCONSISTENT' in codes(assess(payload), 'ERROR')


def test_soil_depth_interval_is_structurally_validated():
    with pytest.raises(ValidationError, match='greater than depth_top_cm'):
        SoilObservation.model_validate(soil('CLAY', 20, '%', top=30, bottom=10))
    with pytest.raises(ValidationError, match='supplied together'):
        SoilObservation.model_validate(soil('CLAY', 20, '%', bottom=None))


def test_measurement_without_metadata_and_depth_is_flagged():
    payload = complete_profile()
    payload['soil'].append({'property': 'PH', 'value': 7.5, 'unit': 'pH', 'origin': 'LOCAL_MEASUREMENT'})
    result = assess(payload)
    assert {'MEASUREMENT_METADATA_MISSING', 'SOIL_DEPTH_MISSING'} <= codes(result, 'WARNING')


# ---------------------------------------------------------------- crop history and calendar

def test_harvest_before_sowing_is_rejected():
    payload = complete_profile()
    payload['crop_history'][0]['harvest_date'] = '2022-10-01'
    assert 'HARVEST_BEFORE_SOWING' in codes(assess(payload), 'ERROR')


def test_overlapping_main_crops_are_rejected_but_intercrops_warn():
    payload = complete_profile()
    payload['crop_history'].append(season('Garbanzo', 2023, '2023-03-01', '2023-07-15'))
    result = assess(payload)
    assert 'MAIN_CROPS_OVERLAP' in codes(result, 'ERROR')

    payload['crop_history'][-1]['role'] = 'INTERCROP'
    result = assess(payload)
    assert 'MAIN_CROPS_OVERLAP' not in codes(result)
    assert 'SEASONS_OVERLAP' in codes(result, 'WARNING')


def test_fallow_cannot_overlap_a_crop():
    payload = complete_profile()
    payload['crop_history'].append(season('fallow', 2023, '2023-01-01', '2023-05-01', role='FALLOW'))
    assert 'FALLOW_OVERLAPS_CROP' in codes(assess(payload), 'ERROR')


def test_unknown_crop_code_errors_and_unknown_label_warns():
    payload = complete_profile()
    payload['crop_history'][0]['crop_code'] = 'teff'
    payload['crop_history'][1]['crop_label'] = 'Tritordeum'
    result = assess(payload)
    assert 'UNKNOWN_CROP_CODE' in codes(result, 'ERROR')
    assert 'CROP_NOT_IN_CATALOGUE' in codes(result, 'WARNING')


def test_missing_dates_and_water_regime_limit_analysis():
    payload = complete_profile()
    payload['crop_history'] = [{'crop_label': 'Barley', 'season_year': 2024}]
    result = assess(payload)
    assert {'SEASON_DATES_MISSING', 'SEASON_WATER_REGIME_MISSING', 'CROP_HISTORY_SHORT'} <= codes(result, 'MISSING_DATA')
    assert result.sections['crop_history'] == 'PARTIAL'


def test_calendar_windows_wrap_year_end():
    payload = complete_profile()
    assert 'SOWING_HARVEST_WINDOWS_OVERLAP' not in codes(assess(payload))  # Oct-Dec sowing, Jun-Jul harvest
    payload['local_calendar'][0] |= {'sowing_start_month': 11, 'sowing_end_month': 2,
                                     'harvest_start_month': 1, 'harvest_end_month': 3}
    assert 'SOWING_HARVEST_WINDOWS_OVERLAP' in codes(assess(payload), 'WARNING')


def test_calendar_months_are_validated():
    payload = complete_profile()
    payload['local_calendar'][0]['sowing_start_month'] = 13
    with pytest.raises(ValidationError):
        FarmProfile.model_validate(payload)


# ---------------------------------------------------------------- constraints and priorities

def test_rainfed_farm_with_irrigation_allowance_is_inconsistent():
    payload = complete_profile()
    payload['constraints']['irrigation_allowance'] = {'value': 200, 'unit': 'mm/season', 'origin': 'FARMER_ESTIMATE'}
    assert 'RAINFED_WITH_IRRIGATION' in codes(assess(payload), 'ERROR')


def test_irrigated_farm_without_allowance_is_missing_data():
    payload = complete_profile()
    payload['constraints']['water_regime'] = 'IRRIGATED'
    assert 'IRRIGATION_ALLOWANCE_MISSING' in codes(assess(payload), 'MISSING_DATA')


def test_excluded_crop_with_market_warns():
    payload = complete_profile()
    payload['constraints']['excluded_crops'] = ['Cebada']
    assert 'EXCLUDED_CROP_HAS_MARKET' in codes(assess(payload), 'WARNING')


def test_priorities_are_ordinal_and_unique():
    payload = complete_profile()
    payload['priorities'][1]['rank'] = 1
    assert 'DUPLICATE_PRIORITY_RANK' in codes(assess(payload), 'ERROR')
    payload['priorities'][1] = {'criterion': 'SOIL_COVER', 'rank': 2}
    assert 'DUPLICATE_PRIORITY_CRITERION' in codes(assess(payload), 'ERROR')


def test_unknown_fields_such_as_expected_yield_are_rejected():
    payload = complete_profile() | {'expected_yield_t_ha': 5.0}
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        FarmProfile.model_validate(payload)


# ---------------------------------------------------------------- HTTP

async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


@pytest.mark.asyncio
async def test_assess_endpoint_returns_issues_without_storing():
    async with await _client() as client:
        response = await client.post('/api/v1/farm-profiles/assess', json=complete_profile())
        assert response.status_code == 200
        body = response.json()
        assert body['source_kind'] == 'FARMER_REPORTED'
        assert body['rotation_input_status'] == 'INPUTS_COMPLETE'
        assert body['schema_version'] == '1.0'

        bad = await client.post('/api/v1/farm-profiles/assess', json={'soil': [soil('CLAY', 20, '%', top=30, bottom=10)]})
        assert bad.status_code == 422


@pytest.mark.asyncio
async def test_catalogue_endpoint_and_openapi_registration():
    async with await _client() as client:
        response = await client.get('/api/v1/crop-catalog')
        assert response.status_code == 200
        body = response.json()
        assert {e['code'] for e in body['entries']} == set(ENTRIES)
        assert all(e['agronomic_parameters'] is None for e in body['entries'])

    schema = app.openapi()
    assert '/api/v1/farm-profiles/assess' in schema['paths']
    assert '/api/v1/crop-catalog' in schema['paths']
    assert {'CropCatalogEntry', 'FarmProfileAssessment'} <= schema['components']['schemas'].keys()
    assert 'Case' in schema['components']['schemas']  # ABB-02 contracts still registered


def test_dates_in_fixture_are_parsed():
    profile = FarmProfile.model_validate(complete_profile())
    assert profile.crop_history[0].sowing_date == date(2022, 11, 5)
