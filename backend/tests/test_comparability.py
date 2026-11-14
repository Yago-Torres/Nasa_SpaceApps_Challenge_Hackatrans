"""ABB-15 rule tests that need no database: comparability, disagreement candidates, applicability.

All claims, studies and farms are SYNTHETIC.
"""
from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from agroblackbox import comparability as cmp
from agroblackbox.api.comparability_dto import ApplicabilityReport, ApplicabilityRequest, DisagreementList
from agroblackbox.api.evidence_dto import ClaimContent, ClaimContext, ClaimPatch
from agroblackbox.app import app
from agroblackbox.farm_profile import FarmProfile
from comparability_fixtures import (
    GLOBAL_META_CONTEXT,
    LIMITED_TRANSFER_EXPECTED,
    MEDITERRANEAN_CLIMATE,
    MEDITERRANEAN_COUNTRY,
    MEDITERRANEAN_PROFILE,
    numeric_score_keys,
)

U = [UUID(int=i) for i in range(1, 10)]


def study(**kwargs) -> cmp.StudyContext:
    return cmp.StudyContext.from_json(kwargs)


def profile(**kwargs) -> FarmProfile:
    return FarmProfile.model_validate(kwargs)


def soil(prop, value, unit="%", origin="LOCAL_MEASUREMENT", top=0, bottom=30):
    return {"property": prop, "value": value, "unit": unit, "origin": origin,
            "depth_top_cm": top, "depth_bottom_cm": bottom}


def facts(i, intervention="Legume pre-crop", outcome="Main-crop yield", direction="INCREASE", **kwargs):
    return cmp.ClaimFacts(id=U[i], intervention=intervention, comparator=kwargs.pop("comparator", None),
                          outcome_variable=outcome, effect_direction=direction,
                          review_status=kwargs.pop("review_status", "ACCEPTED"), **kwargs)


# ── USDA texture ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("clay,silt,sand,expected", [
    (5, 5, 90, "SAND"),
    (5, 15, 80, "LOAMY_SAND"),
    (10, 25, 65, "SANDY_LOAM"),
    (20, 40, 40, "LOAM"),
    (10, 70, 20, "SILT_LOAM"),
    (5, 88, 7, "SILT"),
    (25, 15, 60, "SANDY_CLAY_LOAM"),
    (28, 32, 40, "CLAY_LOAM"),
    (33, 55, 12, "SILTY_CLAY_LOAM"),
    (40, 5, 55, "SANDY_CLAY"),
    (45, 45, 10, "SILTY_CLAY"),
    (55, 20, 25, "CLAY"),
    (14, 16, 20, "CLAY_LOAM"),  # sums to 50: normalised to 28/32/40
])
def test_usda_texture_class(clay, silt, sand, expected):
    assert cmp.usda_texture_class(clay, silt, sand) == expected


def test_texture_is_not_derived_from_inconsistent_or_duplicated_layers():
    conditions = cmp.case_conditions(profile(soil=[
        soil("CLAY", 30), soil("SILT", 30), soil("SAND", 30),  # sums to 90
        soil("CLAY", 20, top=30, bottom=60), soil("CLAY", 22, top=30, bottom=60), soil("SILT", 40, top=30, bottom=60),
        soil("SAND", 38, top=30, bottom=60),
    ]))
    assert conditions.textures == []
    assert len(conditions.texture_notes) == 2
    note = cmp.texture_note(study(soil_texture_classes=["LOAM"]), conditions)
    assert note.status == "UNKNOWN" and "sum to 90" in note.reason


# ── applicability dimensions ─────────────────────────────────────────────────

@pytest.mark.parametrize("study_crops,case_crops,expected", [
    (["Durum wheat"], ["wheat_durum"], "MATCH"),
    (["durum wheat", "barley"], ["Trigo duro"], "PARTIAL"),
    (["maize", "rice"], ["wheat_durum", "maize"], "PARTIAL"),
    (["maize", "rice"], ["wheat_durum", "chickpea"], "MISMATCH"),
    (["wheat"], ["wheat_durum"], "UNKNOWN"),  # ambiguous name: no mismatch claimed by name
    (["sweet potato"], ["maize"], "UNKNOWN"),
    ([], ["maize"], "UNKNOWN"),
    (["maize"], [], "UNKNOWN"),
])
def test_crop_rules(study_crops, case_crops, expected):
    note = cmp.crops_note(study(crops=study_crops), cmp.CaseConditions(crops=case_crops, crops_source="test"))
    assert note.status == expected, note.reason


def test_case_crops_come_from_profile_then_stored_case_history():
    with_profile = cmp.case_conditions(profile(crop_history=[
        {"crop_code": "barley", "crop_label": "Barley", "season_year": 2021},
        {"crop_label": "Fallow", "role": "FALLOW", "season_year": 2022},
    ]), case_crops=["maize"])
    assert with_profile.crops == ["barley"] and "farm profile" in with_profile.crops_source
    stored = cmp.case_conditions(None, case_crops=["maize", "maize"])
    assert stored.crops == ["maize"] and "case record" in stored.crops_source
    assert cmp.case_conditions(None).crops == []


@pytest.mark.parametrize("study_regime,constraints,history,expected", [
    ("RAINFED", "RAINFED", [], "MATCH"),
    ("IRRIGATED", "RAINFED", [], "MISMATCH"),
    ("MIXED", "RAINFED", [], "PARTIAL"),
    ("NOT_REPORTED", "RAINFED", [], "UNKNOWN"),
    ("RAINFED", None, ["RAINFED", "RAINFED"], "MATCH"),
    ("RAINFED", None, ["RAINFED", "IRRIGATED"], "UNKNOWN"),
    ("RAINFED", None, [], "UNKNOWN"),
])
def test_water_regime_rules(study_regime, constraints, history, expected):
    data = {"crop_history": [{"crop_label": "Barley", "season_year": 2020 + i, "water_regime": r}
                             for i, r in enumerate(history)]}
    if constraints:
        data["constraints"] = {"water_regime": constraints}
    note = cmp.water_note(study(water_regime=study_regime), cmp.case_conditions(profile(**data)))
    assert note.status == expected, note.reason
    if history == ["RAINFED", "IRRIGATED"]:
        assert "different water regimes" in note.reason


@pytest.mark.parametrize("values,expected", [
    ([6.5], "MATCH"), ([6.5, 8.0], "PARTIAL"), ([8.2], "MISMATCH"), ([], "UNKNOWN"),
])
def test_ph_rules(values, expected):
    conditions = cmp.case_conditions(profile(soil=[soil("PH", v, unit="pH", origin="FARMER_ESTIMATE",
                                                        top=i * 10, bottom=i * 10 + 10)
                                                   for i, v in enumerate(values)]))
    note = cmp.ph_note(study(soil_ph_min=5.5, soil_ph_max=7.5), conditions)
    assert note.status == expected
    if values:
        assert "FARMER_ESTIMATE" in note.case_value_source
    assert cmp.ph_note(study(), conditions).status == "UNKNOWN"


@pytest.mark.parametrize("scope,countries,case,expected", [
    ("GLOBAL", [], "ES", "PARTIAL"),
    ("NATIONAL", ["ES"], "ES", "MATCH"),
    ("MULTI_COUNTRY", ["ES", "PT"], "ES", "PARTIAL"),
    ("NATIONAL", ["US"], "ES", "MISMATCH"),
    ("SITE", [], "ES", "UNKNOWN"),
    ("NATIONAL", ["ES"], None, "UNKNOWN"),
])
def test_region_rules(scope, countries, case, expected):
    note = cmp.region_note(study(geographic_scope=scope, countries=countries, region="as written"),
                           cmp.CaseConditions(country=case, region_labels=["Synthetic valley"]))
    assert note.status == expected
    assert "not compared" in note.case_value  # free-text region labels are shown, never matched


@pytest.mark.parametrize("classes,case,expected", [
    (["Csa"], "Csa", "MATCH"),
    (["Csa", "Cfa"], "Csa", "PARTIAL"),
    (["Csb"], "Csa", "PARTIAL"),
    (["Cfa"], "Csa", "MISMATCH"),
    (["BSk"], "Csa", "MISMATCH"),
    ([], "Csa", "UNKNOWN"),
    (["Csa"], None, "UNKNOWN"),
])
def test_climate_rules(classes, case, expected):
    assert cmp.climate_note(study(climate_classes=classes), cmp.CaseConditions(climate=case)).status == expected


def test_missing_data_on_either_side_is_unknown_and_no_score():
    notes = cmp.applicability_notes(cmp.StudyContext(), cmp.case_conditions(None))
    assert {n.status for n in notes} == {"UNKNOWN"}
    assert cmp.transfer_status(notes) == "INSUFFICIENT_DATA"
    assert all(n.reason for n in notes)
    assert not numeric_score_keys([n.model_dump() for n in notes])


def test_limited_transfer_example_documents_each_difference():
    conditions = cmp.case_conditions(FarmProfile.model_validate(MEDITERRANEAN_PROFILE),
                                     country=MEDITERRANEAN_COUNTRY, climate=MEDITERRANEAN_CLIMATE)
    notes = cmp.applicability_notes(cmp.StudyContext.from_json(GLOBAL_META_CONTEXT), conditions)
    assert {n.dimension: n.status for n in notes} == LIMITED_TRANSFER_EXPECTED
    assert cmp.transfer_status(notes) == "DIFFERENCES_FOUND"
    by_dim = {n.dimension: n for n in notes}
    assert by_dim["SOIL_TEXTURE"].case_value == "CLAY_LOAM"  # derived, but the study reports no classes
    assert "LOCAL_MEASUREMENT" in by_dim["SOIL_PH"].case_value_source
    assert by_dim["CROPS"].case_value == "wheat_durum, chickpea"


def test_transfer_status_categories():
    def note(status):
        return cmp.TransferNote(dimension="CROPS", status=status, reason="x")
    assert cmp.transfer_status([note("MATCH"), note("MATCH")]) == "NO_DIFFERENCES_FOUND_IN_COMPARED_DIMENSIONS"
    assert cmp.transfer_status([note("MATCH"), note("UNKNOWN")]) == "INSUFFICIENT_DATA"
    assert cmp.transfer_status([note("PARTIAL"), note("UNKNOWN")]) == "DIFFERENCES_FOUND"


# ── disagreement candidates ──────────────────────────────────────────────────

def test_opposed_directions_on_same_terms_are_candidates_only():
    found = cmp.find_candidates([
        facts(2, direction="DECREASE", intervention="  legume   PRE-CROP "),
        facts(1, direction="INCREASE"),
        facts(3, direction="NO_CLEAR_EFFECT"),
        facts(4, direction="INCREASE", outcome="soil nitrate"),  # other outcome
        facts(5, direction="DECREASE", intervention="cover crop"),  # other intervention
    ])
    kinds = {(c.claim_a.id, c.claim_b.id): c.kind for c in found}
    assert kinds == {
        (U[1], U[2]): "OPPOSITE_DIRECTION",
        (U[1], U[3]): "EFFECT_VS_NO_CLEAR_EFFECT",
        (U[2], U[3]): "EFFECT_VS_NO_CLEAR_EFFECT",
    }
    assert all(c.claim_a.id < c.claim_b.id and c.id == cmp.pair_id(c.claim_b.id, c.claim_a.id) for c in found)


@pytest.mark.parametrize("other", [
    {"direction": "INCREASE"},
    {"direction": "MIXED"},
    {"direction": "NOT_STATED"},
    {"direction": "DECREASE", "review_status": "REJECTED"},
    {"direction": "DECREASE", "intervention": None},
    {"direction": "DECREASE", "outcome": "  "},
])
def test_no_candidate_without_comparable_structured_fields(other):
    assert cmp.find_candidates([facts(1), facts(2, **other)]) == []


def test_not_compared_reasons_are_explicit():
    reasons = cmp.not_compared_reasons(facts(1, intervention=None, outcome=None, direction="NOT_STATED",
                                             review_status="REJECTED"))
    assert reasons == ["rejected by a reviewer", "no intervention recorded", "no outcome variable recorded",
                       "stated direction NOT_STATED is not compared"]


def test_comparability_notes_show_recorded_differences():
    a = facts(1, comparator="Cereal pre-crop", study_design="META_ANALYSIS",
              context=study(crops=["maize"], water_regime="MIXED", geographic_scope="GLOBAL",
                            soil_ph_min=5.5, soil_ph_max=7.5, climate_classes=["Cfa"]))
    b = facts(2, direction="DECREASE", comparator="fallow", study_design="FIELD_EXPERIMENT",
              context=study(crops=["wheat_durum"], water_regime="RAINFED", geographic_scope="NATIONAL",
                            countries=["ES"], soil_ph_min=7.8, soil_ph_max=8.4, climate_classes=["Csa"]))
    notes = {n.dimension: n.status for n in cmp.comparability_notes(a, b)}
    assert notes == {"COMPARATOR": "MISMATCH", "STUDY_DESIGN": "MISMATCH", "CROPS": "MISMATCH",
                     "WATER_REGIME": "PARTIAL", "SOIL_TEXTURE": "UNKNOWN", "SOIL_PH": "MISMATCH",
                     "REGION": "PARTIAL", "CLIMATE": "MISMATCH"}
    same = {n.dimension: n.status for n in cmp.comparability_notes(a, a)}
    assert same["COMPARATOR"] == same["CROPS"] == same["CLIMATE"] == "MATCH"


# ── request validation ───────────────────────────────────────────────────────

def content(**overrides) -> dict:
    return {"claim_text": "SYNTHETIC", "study_context": "SYNTHETIC", "evidence_basis": "ABSTRACT",
            "access_basis": "PUBLIC_ABSTRACT", "limitations": ["Synthetic"], "intervention": "legume pre-crop",
            "outcome_variable": "yield", "effect_direction": "INCREASE", **overrides}


@pytest.mark.parametrize("overrides,message", [
    ({"evidence_basis": "METADATA_ONLY", "access_basis": "NONE"}, "metadata alone"),
    ({"intervention": None}, "needs the intervention"),
    ({"outcome_variable": None}, "needs the intervention"),
    ({"effect_direction": "BIGGER"}, "Input should be"),
    ({"context": {"soil_ph_min": 7}}, "together"),
    ({"context": {"soil_ph_min": 8, "soil_ph_max": 7}}, "must not exceed"),
    ({"context": {"soil_ph_min": 3, "soil_ph_max": 15}}, "less than or equal"),
    ({"context": {"climate_classes": ["Mediterranean"]}}, "Input should be"),
    ({"context": {"countries": ["ESP"]}}, "pattern"),
    ({"context": {"soil_texture_classes": ["LOAM", "LOAM"]}}, "duplicates"),
    ({"context": {"water_regime": "DRY"}}, "Input should be"),
])
def test_claim_comparability_fields_are_validated(overrides, message):
    with pytest.raises(ValidationError, match=message):
        ClaimContent.model_validate(content(**overrides))


def test_valid_structured_claim_and_patch_nulls():
    claim = ClaimContent.model_validate(content(context={"countries": ["es"], "climate_classes": ["Csa"]}))
    assert claim.context.countries == ["ES"]
    assert ClaimContent.model_validate(content(effect_direction="NOT_STATED", evidence_basis="METADATA_ONLY",
                                               access_basis="NONE")).effect_direction == "NOT_STATED"
    assert ClaimPatch.model_validate({"version": 1, "comparator": None}).comparator is None
    with pytest.raises(ValidationError, match="cannot be null"):
        ClaimPatch.model_validate({"version": 1, "effect_direction": None})
    assert ClaimContext().water_regime == "NOT_REPORTED"


@pytest.mark.parametrize("body", [
    {"country_code": "Spain"}, {"koppen_climate": "Mediterranean"}, {"score": 1}, {"farm_profile": {"x": 1}},
])
def test_applicability_request_is_strict(body):
    with pytest.raises(ValidationError):
        ApplicabilityRequest.model_validate(body)


def test_openapi_exposes_routes_and_no_score_fields():
    schema = app.openapi()
    paths = schema["paths"]
    assert "get" in paths["/api/v1/cases/{case_id}/claims/disagreements"]
    assert "post" in paths["/api/v1/cases/{case_id}/claims/disagreements/{disagreement_id}/review"]
    assert "post" in paths["/api/v1/cases/{case_id}/claims/{claim_id}/applicability"]
    for model in (ApplicabilityReport, DisagreementList):
        assert not numeric_score_keys(model.model_json_schema()), model.__name__
    names = list(schema["components"]["schemas"])
    assert "ApplicabilityReport" in names and "DisagreementView" in names
    # Route order ("/claims/disagreements" before "/claims/{claim_id}") is exercised by the
    # PostgreSQL tests in test_api_comparability.py, which GET the disagreements list.
