"""ABB-19 Uncertainty Hunter rules (no database). Every case, hypothesis, claim and farm is SYNTHETIC."""
from __future__ import annotations

import copy
from datetime import date
from uuid import UUID, uuid4

import pytest

from agroblackbox.api import uncertainty_dto
from agroblackbox.comparability import ClaimFacts, StudyContext
from agroblackbox.farm_profile import FarmProfile
from agroblackbox.services.forensics import HYPOTHESIS_TEMPLATES, template
from agroblackbox.uncertainty import (
    CATALOGUE,
    MISSING_EVIDENCE_QUESTIONS,
    NO_BASIS_STATEMENT,
    SPECS,
    VERIFICATION_QUESTIONS,
    CaseInput,
    ClaimInput,
    HypothesisInput,
    QuestionState,
    TimelineGapInput,
    build_report,
    dynamic_question_id,
)
from comparability_fixtures import numeric_score_keys
from test_rotations import profile as rotation_profile

CASE = CaseInput(case_id=UUID("00000000-0000-4000-8000-000000000019"), incident_start=date(2022, 5, 1),
                 incident_end=date(2022, 8, 31), crop_history=("wheat",))
NO_LOCAL = TimelineGapInput(id=UUID("00000000-0000-4000-8000-0000000000a1"), event_type="NO_LOCAL_MEASUREMENTS",
                            title="No field-scale measurements recorded", description="SYNTHETIC")


def hyp(code: str, status: str = "OPEN", **extra) -> HypothesisInput:
    t = template(code)
    return HypothesisInput(
        id=extra.pop("id", uuid4()), title=t["title"], statement=t["statement"], status=status, template_code=code,
        missing_evidence=tuple(t["missing_evidence"]),
        verification_questions=tuple((q["question"], q["why_it_matters"]) for q in t["verification_questions"]),
        **extra)


def questions(report):
    return {q.id: q for q in report.questions}


def test_every_template_text_maps_to_a_catalogue_question():
    for t in HYPOTHESIS_TEMPLATES:
        report = build_report(CASE, hypotheses=[hyp(t["code"])])
        assert all(q.origin == "CATALOGUE" for q in report.questions), t["code"]
    assert set(MISSING_EVIDENCE_QUESTIONS.values()) | set(VERIFICATION_QUESTIONS.values()) <= SPECS.keys()


def test_every_question_explains_the_uncertainty_and_what_to_record():
    report = build_report(CASE, hypotheses=[hyp(t["code"]) for t in HYPOTHESIS_TEMPLATES], timeline_gaps=[NO_LOCAL])
    assert report.questions
    for q in report.questions:
        assert q.addresses and q.addresses_gap_ids, q.id
        assert "It addresses:" in q.why_it_matters
        assert q.measurement and q.would_change_statement
    for spec in CATALOGUE:
        assert spec.question and spec.why_it_matters and spec.measurement


def test_not_evaluable_hypothesis_is_named_in_would_change():
    h = hyp("WATER_DEFICIT", "NOT_EVALUABLE")
    q = questions(build_report(CASE, hypotheses=[h]))["IRRIGATION_RECORDS"]
    [target] = q.would_change
    assert (target.target_type, target.target_id, target.current_state) == ("HYPOTHESIS", str(h.id), "NOT_EVALUABLE")
    assert "a person then decides" in target.how
    assert q.open_hypotheses_linked == 1


def test_user_written_missing_evidence_becomes_a_deterministic_question():
    a = HypothesisInput(id=uuid4(), title="SYNTHETIC frost", statement="Frost may have contributed.", status="OPEN",
                        missing_evidence=("Night temperature at canopy height",),
                        verification_questions=(("Was there hoar frost on the leaves?", "Frost leaves visible traces."),))
    b = HypothesisInput(id=uuid4(), title="SYNTHETIC other", statement="Another.", status="NOT_EVALUABLE",
                        missing_evidence=("night temperature  at CANOPY height",))
    report = build_report(CASE, hypotheses=[a, b])
    qid = dynamic_question_id("missing", "Night temperature at canopy height")
    q = questions(report)[qid]
    assert qid.startswith("H-") and q.origin == "HYPOTHESIS_TEXT" and q.category == "HYPOTHESIS_EVIDENCE"
    assert {t.target_id for t in q.would_change} == {str(a.id), str(b.id)}
    verification = questions(report)[dynamic_question_id("verification", "Was there hoar frost on the leaves?")]
    assert verification.question == "Was there hoar frost on the leaves?"
    assert verification.why_it_matters.startswith("Frost leaves visible traces.")


def test_no_basis_to_prioritise_is_said_explicitly():
    report = build_report(CASE, timeline_gaps=[NO_LOCAL])
    assert report.prioritisation.status == "NO_BASIS_TO_PRIORITISE"
    assert report.prioritisation.statement == NO_BASIS_STATEMENT
    assert "no basis to prioritise" in report.prioritisation.statement
    assert {q.position for q in report.questions} == {1}
    assert all(len(q.tied_with) == len(report.questions) - 1 for q in report.questions)
    for q in report.questions:
        assert not q.would_change
        assert "adds local context only" in q.would_change_statement


def test_questions_are_ordered_by_linked_unresolved_hypotheses_then_other_items():
    report = build_report(CASE, hypotheses=[hyp("WATER_DEFICIT"), hyp("HEAT_STRESS", "NOT_EVALUABLE"),
                                            hyp("SOIL_LIMITATION", "COMPATIBLE")], timeline_gaps=[NO_LOCAL])
    assert report.prioritisation.status == "ORDERED_BY_LINK_COUNTS"
    assert report.prioritisation.is_value_of_information is False
    by = questions(report)
    assert report.questions[0].id == "CROP_STAGE_AT_EVENT"  # the only question linked to both open hypotheses
    assert by["CROP_STAGE_AT_EVENT"].position == 1 and by["CROP_STAGE_AT_EVENT"].open_hypotheses_linked == 2
    assert by["IRRIGATION_RECORDS"].position == 2
    # COMPATIBLE hypotheses are listed in would_change but not counted as unresolved
    assert by["SOIL_ANALYSIS"].open_hypotheses_linked == 0 and by["SOIL_ANALYSIS"].would_change
    assert by["SOIL_ANALYSIS"].position > by["IRRIGATION_RECORDS"].position
    positions = [q.position for q in report.questions]
    assert positions == sorted(positions)


def test_report_is_deterministic():
    kwargs = dict(hypotheses=[hyp("WATER_DEFICIT", id=UUID(int=1)), hyp("PEST_DISEASE", id=UUID(int=2))],
                  timeline_gaps=[NO_LOCAL], profile=FarmProfile.model_validate(rotation_profile()))
    first, second = build_report(CASE, **kwargs), build_report(CASE, **kwargs)
    assert [g.model_dump() for g in first.gaps] == [g.model_dump() for g in second.gaps]
    assert [q.model_dump() for q in first.questions] == [q.model_dump() for q in second.questions]


def test_data_gap_links_only_weather_hypotheses_of_that_variable_in_the_incident():
    rain_gap = TimelineGapInput(id=uuid4(), event_type="DATA_GAP", title="Precipitation, June 2022: no anomaly",
                                description="SYNTHETIC", variable="precipitation", overlaps_incident=True)
    old_heat_gap = TimelineGapInput(id=uuid4(), event_type="DATA_GAP", title="Maximum temperature, Jan 2022",
                                    description="SYNTHETIC", variable="max_temperature", overlaps_incident=False)
    water, heat = hyp("WATER_DEFICIT"), hyp("HEAT_STRESS")
    report = build_report(CASE, hypotheses=[water, heat], timeline_gaps=[rain_gap, old_heat_gap])
    gaps = {g.title: g for g in report.gaps}
    assert {t.target_id for t in gaps[rain_gap.title].would_change} == {str(water.id)}
    assert gaps[rain_gap.title].cause == "INCOMPLETE_SOURCE_DATA"
    assert gaps[old_heat_gap.title].would_change == []
    assert gaps[old_heat_gap.title].question_ids == ["LOCAL_TEMPERATURE"]


def test_no_observations_gap_is_an_analysis_task():
    gap = TimelineGapInput(id=uuid4(), event_type="NO_OBSERVATIONS", title="No NASA POWER observations for 2022",
                           description="SYNTHETIC")
    q = questions(build_report(CASE, timeline_gaps=[gap], hypotheses=[hyp("EXCESS_WATER")]))["NASA_POWER_RETRIEVAL"]
    assert q.kind == "ANALYSIS_TASK" and not q.answerable_here and q.answer_route.endswith("/nasa-power")
    assert q.open_hypotheses_linked == 1


def claim(review_status="PENDING", **context) -> ClaimInput:
    facts = ClaimFacts(id=uuid4(), intervention=None, comparator=None, outcome_variable=None,
                       effect_direction="NOT_STATED", review_status=review_status, study_design="META_ANALYSIS",
                       context=StudyContext(**context))
    return ClaimInput(facts=facts, label="SYNTHETIC claim")


def test_claim_gaps_review_study_record_and_case_side_applicability():
    c = claim(crops=("wheat",), water_regime="RAINFED", soil_ph_min=5.5, soil_ph_max=7.5, geographic_scope="GLOBAL")
    citing = HypothesisInput(
        id=uuid4(), title="SYNTHETIC cites claim", statement="S.", status="OPEN",
        evidence_ids=frozenset({str(c.facts.id)}))
    report = build_report(CASE, claims=[c, claim("REJECTED")], hypotheses=[citing])
    gaps = {g.key: g for g in report.gaps}
    review = gaps[f"claim:{c.facts.id}:not-reviewed"]
    assert review.cause == "NOT_REVIEWED" and review.question_ids == ["CLAIM_REVIEW"]
    assert [t.target_id for t in review.would_change] == [str(citing.id)]
    ph = gaps["case:SOIL_PH"]
    assert ph.question_ids == ["SOIL_ANALYSIS"]
    assert ph.would_change[0].target_type == "APPLICABILITY_DIMENSION"
    assert ph.would_change[0].target_id == f"{c.facts.id}:SOIL_PH"
    study = gaps[f"claim:{c.facts.id}:study-record"]
    targets = {t.target_id for t in study.would_change}
    assert f"{c.facts.id}:SOIL_TEXTURE" in targets and f"{c.facts.id}:CLIMATE" in targets
    assert f"{c.facts.id}:not-compared" in targets  # no intervention/outcome/direction recorded
    assert "case:REGION" in gaps and "case:CLIMATE" in gaps
    assert not any("REJECTED" in g.title for g in report.gaps)

    profile = FarmProfile.model_validate({"soil": [{"property": "PH", "value": 8.2, "unit": "pH", "depth_top_cm": 0,
                                                    "depth_bottom_cm": 30, "origin": "LOCAL_MEASUREMENT",
                                                    "method": "SYNTHETIC", "sampled_on": "2022-03-01"}]})
    with_profile = {g.key for g in build_report(CASE, claims=[c], profile=profile, country="ES", climate="Csa").gaps}
    assert "case:SOIL_PH" not in with_profile and "case:REGION" not in with_profile
    assert "case:CLIMATE" not in with_profile


def test_profile_rotation_and_ordering_gaps():
    payload = rotation_profile()
    payload["local_calendar"] = [w for w in payload["local_calendar"] if w["crop_label"] != "Sunflower"]
    payload["priorities"] += [{"criterion": "RISK_REDUCTION", "rank": 4}]
    report = build_report(CASE, profile=FarmProfile.model_validate(payload))
    gaps = {g.key: g for g in report.gaps}
    assert report.rotation_status in {"COMPARED", "FEWER_ALTERNATIVES"}
    assert gaps["profile:SOIL_MISSING:soil"].question_ids == ["SOIL_ANALYSIS"]
    for key in ("rotation:check:SOIL:no-method", "rotation:check:CLIMATE:no-method",
                "ordering:criterion:WATER_USE:no-method"):
        assert gaps[key].cause == "NO_METHOD" and gaps[key].question_ids == []
        assert gaps[key].answerable_locally is False and gaps[key].would_change == []
    risk = gaps["ordering:criterion:RISK_REDUCTION"]
    assert risk.question_ids == ["CLIMATE_SCENARIO"] and risk.would_change[0].target_type == "ORDERING_CRITERION"
    sunflower = gaps["rotation:screening:sunflower:calendar"]
    assert sunflower.question_ids == ["LOCAL_CROP_CALENDAR"]
    assert sunflower.would_change[0].target_type == "CANDIDATE_SCREENING"
    assert all(s.stored is False for g in report.gaps for s in g.sources if s.entity_type == "FARM_PROFILE")


def test_insufficient_crop_history_blocks_rotation_comparison():
    payload = copy.deepcopy(rotation_profile())
    payload["crop_history"] = payload["crop_history"][:1]
    gaps = {g.key: g for g in build_report(CASE, profile=FarmProfile.model_validate(payload)).gaps}
    target = gaps["rotation:insufficient-input"].would_change[0]
    assert (target.target_type, target.current_state) == ("ROTATION_COMPARISON", "INSUFFICIENT_INPUT")


def test_resolved_questions_get_no_position_and_all_resolved_says_so():
    states = {"IRRIGATION_RECORDS": QuestionState(status="ANSWERED", current_answer_id=uuid4())}
    report = build_report(CASE, timeline_gaps=[NO_LOCAL], states=states)
    by = questions(report)
    assert by["IRRIGATION_RECORDS"].position is None and by["IRRIGATION_RECORDS"].resolution.status == "ANSWERED"
    assert report.questions[-1].id == "IRRIGATION_RECORDS"
    all_done = {code: QuestionState(status="DISMISSED", note="SYNTHETIC")
                for code in ("LOCAL_RAIN_OR_SOIL_MOISTURE", "IRRIGATION_RECORDS", "CROP_STAGE_AT_EVENT")}
    assert build_report(CASE, timeline_gaps=[NO_LOCAL], states=all_done).prioritisation.status == "NO_OPEN_QUESTIONS"


def test_stored_question_no_longer_generated_is_still_listed():
    snapshot = {"id": "H-" + "0" * 32, "kind": "LOCAL_INFORMATION", "category": "HYPOTHESIS_EVIDENCE",
                "question": "SYNTHETIC old question?", "why_it_matters": "SYNTHETIC", "measurement": "SYNTHETIC",
                "units": [], "answer_route": None, "origin": "HYPOTHESIS_TEXT"}
    report = build_report(CASE, states={"H-" + "0" * 32: QuestionState(status="ANSWERED", snapshot=snapshot)})
    [q] = report.questions
    assert q.currently_generated is False and q.question == "SYNTHETIC old question?"


def test_no_score_probability_or_weight_anywhere():
    report = build_report(CASE, hypotheses=[hyp(t["code"]) for t in HYPOTHESIS_TEMPLATES], timeline_gaps=[NO_LOCAL],
                          claims=[claim()], profile=FarmProfile.model_validate(rotation_profile()))
    dumped = {"gaps": [g.model_dump(mode="json") for g in report.gaps],
              "questions": [q.model_dump(mode="json") for q in report.questions],
              "prioritisation": report.prioritisation.model_dump(mode="json")}
    assert not numeric_score_keys(dumped)
    for model in (uncertainty_dto.UncertaintyReport, uncertainty_dto.AnswerView, uncertainty_dto.AnswerCreate,
                  uncertainty_dto.QuestionHistory, uncertainty_dto.QuestionCatalogue):
        assert not numeric_score_keys(model.model_json_schema()), model.__name__


@pytest.mark.parametrize("body", [
    {"origin": "FARMER_REPORTED"},
    {"origin": "FARMER_REPORTED", "value_number": 12.0},
    {"origin": "LOCAL_MEASUREMENT", "value_number": 7.9, "unit": "pH"},
    {"origin": "FARMER_REPORTED", "value_text": "x", "observed_from": "2022-06-02", "observed_to": "2022-06-01"},
    {"origin": "GUESS", "value_text": "x"},
    {"origin": "FARMER_REPORTED", "value_text": "x", "score": 3},
])
def test_invalid_answers_are_rejected(body):
    with pytest.raises(ValueError):
        uncertainty_dto.AnswerCreate.model_validate(body)


def test_openapi_exposes_uncertainty_routes():
    from agroblackbox.app import app
    paths = app.openapi()["paths"]
    base = "/api/v1/cases/{case_id}/uncertainty"
    assert {"get", "post"} <= paths[base].keys()
    for suffix in ("/questions/{question_id}/answers", "/answers/{answer_id}/review",
                   "/questions/{question_id}/dismiss", "/questions/{question_id}/reopen"):
        assert "post" in paths[base + suffix]
    assert "get" in paths[base + "/questions/{question_id}/history"]
    assert "get" in paths["/api/v1/uncertainty/question-catalogue"]
