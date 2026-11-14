"""Uncertainty Hunter: data gaps, useful local questions and what they could change (ABB-19).

Pure functions only (no database, no network) so the rules are deterministic and unit tested.
See docs/science/UNCERTAINTY_HUNTER.md.

Scientific guard rails:

- Gaps come only from structured records: case data, timeline MISSING_DATA markers, hypothesis
  status / missing evidence / verification questions, evidence-claim review status and ABB-15
  applicability dimensions, and (when a farm profile is supplied) ABB-11 issues and ABB-17/18
  checks, screenings and ordering steps. Free text is never parsed; the only text rule is an exact
  match (case/accent/space-insensitive) against the static ABB-10 template wording.
- ``would_change`` lists items whose recorded state is linked to a gap (e.g. a hypothesis that is
  NOT_EVALUABLE pending this evidence, a rotation check that is NOT_EVALUABLE without this input).
  It never estimates how much, or in which direction, a conclusion would change: there is no
  value-of-information model, no score, weight, probability or confidence.
- Gaps that no local measurement can close (CropStory has no reviewed method for them) are labelled
  ``NO_METHOD`` and get no question.
- Questions may be ordered only by a documented count of linked items (``ORDER_RULE``). When the
  counts give no difference, the response says explicitly that there is no basis to prioritise.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID, uuid5

from .comparability import (
    ClaimFacts,
    applicability_notes,
    case_conditions,
    find_candidates,
    not_compared_reasons,
    term_key,
)
from .crop_catalog import resolve_crop
from .farm_profile import FarmProfile, WaterRegime, assess_profile
from .schemas import ContractModel
from .services.forensics import HYPOTHESIS_TEMPLATES
from .services.scenarios import ScenarioAnalysis, ScenarioAnalysisRequest, analyse_scenarios

METHOD_VERSION = "abb19-uncertainty-0.1.0"
ORDER_RULE_ID = "abb19-question-order-0.1.0"
NAMESPACE = UUID("8a3e1f52-6c0d-5b19-a7e4-19abb19c0de5")

QuestionKind = Literal["LOCAL_INFORMATION", "ANALYSIS_TASK"]
Category = Literal[
    "SOIL", "IRRIGATION", "LOCAL_MEASUREMENTS", "LOCAL_WEATHER", "PHENOLOGY", "FIELD_OBSERVATION", "MANAGEMENT",
    "CLIMATE_DATA_QUALITY", "LITERATURE", "CROP_CALENDAR", "CROP_HISTORY", "CROP_IDENTITY", "FARM_CONSTRAINTS",
    "PRIORITIES", "CASE_CONTEXT", "PROFILE_CONSISTENCY", "DECISION_CRITERIA", "METHOD_LIMITATION",
    "HYPOTHESIS_EVIDENCE",
]
GapCause = Literal[
    "MISSING_CASE_DATA",        # the case has no record of it
    "ESTIMATED_NOT_MEASURED",   # a value exists but is an estimate or of unknown origin
    "INCOMPLETE_SOURCE_DATA",   # a retrieved series is incomplete (ABB-08 QC) for a month
    "INCONSISTENT_INPUT",       # the farm profile has a consistency error
    "NOT_REVIEWED",             # literature claim not reviewed against the full text
    "MISSING_STUDY_DATA",       # the claim record lacks the study's structured conditions
    "MISSING_ANALYSIS_INPUT",   # an analysis input (e.g. a climate scenario) was not supplied
    "NO_METHOD",                # CropStory has no reviewed method/parameters: local data would not close it
]
TargetType = Literal[
    "HYPOTHESIS", "ROTATION_COMPARISON", "CANDIDATE_SCREENING", "ROTATION_CHECK", "ORDERING_STEP",
    "ORDERING_CRITERION", "APPLICABILITY_DIMENSION", "DISAGREEMENT_DETECTION", "PROFILE_ANALYSIS",
]
SourceEntity = Literal[
    "CASE", "TIMELINE_EVENT", "HYPOTHESIS", "EVIDENCE_CLAIM", "FARM_PROFILE", "ROTATION_COMPARISON",
    "SCENARIO_ORDERING",
]
QuestionStatus = Literal["OPEN", "ANSWERED", "REVIEWED", "DISMISSED"]
PrioritisationStatus = Literal["ORDERED_BY_LINK_COUNTS", "NO_BASIS_TO_PRIORITISE", "NO_OPEN_QUESTIONS"]
UNRESOLVED_HYPOTHESIS = frozenset({"OPEN", "NOT_EVALUABLE"})


# ── question catalogue ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class QuestionSpec:
    code: str
    kind: QuestionKind
    category: Category
    question: str
    why_it_matters: str
    measurement: str
    units: tuple[str, ...] = ()
    answer_route: str | None = None  # None: answered with POST …/uncertainty/questions/{id}/answers
    origin: Literal["CATALOGUE", "HYPOTHESIS_TEXT"] = "CATALOGUE"

    def snapshot(self) -> dict[str, Any]:
        return {"id": self.code, "kind": self.kind, "category": self.category, "question": self.question,
                "why_it_matters": self.why_it_matters, "measurement": self.measurement, "units": list(self.units),
                "answer_route": self.answer_route, "origin": self.origin}


def _local(code: str, category: Category, question: str, why: str, measurement: str,
           units: tuple[str, ...] = ()) -> QuestionSpec:
    return QuestionSpec(code, "LOCAL_INFORMATION", category, question, why, measurement, units)


def _task(code: str, category: Category, question: str, why: str, measurement: str, route: str) -> QuestionSpec:
    return QuestionSpec(code, "ANALYSIS_TASK", category, question, why, measurement, (), route)


CATALOGUE: tuple[QuestionSpec, ...] = (
    _local("SOIL_ANALYSIS", "SOIL",
           "Is there a soil analysis of this field, ideally of affected and unaffected zones?",
           "Without a measured soil analysis, soil limitations, soil comparisons with studies and soil-dependent "
           "checks rest on estimates or nothing.",
           "Laboratory results per sampled zone and depth: clay, silt and sand (%), pH (pH units, with method, e.g. "
           "1:2.5 water), organic matter (%), electrical conductivity (dS/m); sampling date, depth (cm) and "
           "laboratory method.", ("%", "pH", "dS/m", "cm")),
    _local("IRRIGATION_RECORDS", "IRRIGATION",
           "Was the field irrigated this season, and are irrigation dates, volumes and any equipment failures "
           "recorded?",
           "Regional precipitation does not describe water applied by irrigation; records separate a water "
           "shortage from a supply or equipment failure.",
           "Date and applied depth or volume of each irrigation (mm or m3/ha), system type, and dates of any "
           "breakdown or reduced supply.", ("mm", "m3/ha")),
    _local("LOCAL_RAIN_OR_SOIL_MOISTURE", "LOCAL_WEATHER",
           "Are there local rain-gauge or soil-moisture readings for the incident period?",
           "NASA POWER values describe a grid cell of about ½° × ⅝°, not the field; local readings show what the "
           "field itself received.",
           "Daily rain-gauge totals (mm) with where the gauge stands relative to the field, or soil-moisture "
           "readings (% volumetric or kPa) with depth (cm) and sensor type, covering the incident period.",
           ("mm", "%", "kPa", "cm")),
    _local("LOCAL_TEMPERATURE", "LOCAL_WEATHER",
           "Are there on-farm or nearby station temperature records for the incident period?",
           "Regional maximum temperature is a grid-cell value; local records show whether the field saw the same "
           "hot or cool spells.",
           "Daily maximum and minimum air temperature (°C), station name and approximate distance to the field (km).",
           ("°C", "km")),
    _local("CROP_STAGE_AT_EVENT", "PHENOLOGY",
           "What growth stage was the crop at when symptoms first appeared and during the anomalous months?",
           "Crops respond differently by stage (e.g. flowering, grain filling); without the stage, the timing of "
           "weather and damage cannot be compared.",
           "Date (YYYY-MM-DD) and growth stage on a named scale (e.g. BBCH or Zadoks), with sowing date and variety.",
           ("BBCH", "date")),
    _local("SYMPTOM_ONSET", "FIELD_OBSERVATION",
           "When were symptoms first noticed, and how did they progress?",
           "The order of events matters: damage that starts before a weather anomaly cannot be explained by it.",
           "Date first seen, dates of later checks and a short description of the symptoms at each date; dated "
           "photographs if available.", ("date",)),
    _local("FIELD_PHOTOS_SYMPTOMS", "FIELD_OBSERVATION",
           "Are there dated photographs or inspection notes of the symptoms (leaves, roots, insects, lesions, weeds)?",
           "Biotic and abiotic damage leave different signs that regional data cannot show.",
           "Dated photographs labelled with parcel and plant part, and inspection notes describing what was seen.",
           ("date",)),
    _local("PEST_DIAGNOSIS", "FIELD_OBSERVATION",
           "Did an agronomist, advisor or laboratory examine affected plants or samples?",
           "A diagnosis is the most direct way to confirm or rule out a pest or disease.",
           "Diagnosis report: examiner, date, sample type, organism identified (or none found) and method."),
    _local("REGIONAL_PEST_ALERTS", "FIELD_OBSERVATION",
           "Did the regional plant-protection service issue pest or disease alerts for this season?",
           "Regional alerts show whether pest or disease pressure was high in the area that season.",
           "Issuing body, date, organism and area of each alert (a reference or copy of the bulletin)."),
    _local("DAMAGE_MAP", "FIELD_OBSERVATION",
           "Where in the field is the damage: patches, low areas, soil zones, edges or the whole field?",
           "The spatial pattern separates field-specific causes (soil, drainage, irrigation layout) from "
           "field-wide ones such as weather.",
           "Sketch or map of damaged areas with the approximate share of the field (%) or area (ha) and their "
           "relation to slope, soil zones and irrigation layout (no coordinates needed).", ("%", "ha")),
    _local("STANDING_WATER", "FIELD_OBSERVATION",
           "Was standing water or saturated soil seen in affected areas, and when?",
           "Waterlogging leaves visible traces that regional data cannot show.",
           "Dates and location in the field of standing water or saturated soil, duration (days), dated photos.",
           ("date", "days")),
    _local("DRAINAGE_CONDITION", "SOIL",
           "What is the drainage condition of the field (drains, compaction, slope, known wet spots)?",
           "Poor drainage makes waterlogging possible even after rainfall within the usual range.",
           "Presence and state of drains, known wet areas, slope position, and any compaction observation "
           "(e.g. penetrometer reading in kPa or a spade test).", ("kPa",)),
    _local("MANAGEMENT_LOG", "MANAGEMENT",
           "Is there a log of field operations this season (sowing date, variety, fertilisation, crop protection), "
           "and did anything differ from previous seasons?",
           "Management changes can produce damage similar to weather stress.",
           "Date, operation, product or variety and rate (kg/ha or L/ha) of each operation, and any change from "
           "earlier seasons.", ("kg/ha", "L/ha", "date")),
    _local("NEIGHBOUR_FIELDS", "FIELD_OBSERVATION",
           "Do nearby fields with other soils, crops or management show the same pattern?",
           "A pattern shared across fields points to a regional factor; a field-specific pattern points to local "
           "causes.",
           "For each compared field (no coordinates): approximate distance (km), crop, water regime, whether damage "
           "was seen (yes/no/partly) and the observation date.", ("km", "date")),
    _local("CROP_HISTORY_RECORDS", "CROP_HISTORY",
           "Which crops were grown on this field in recent seasons, with sowing and harvest dates?",
           "The current rotation can only be characterised and compared from at least two recorded main-crop "
           "seasons.",
           "For each season: crop (exact species), role (main crop, cover crop, fallow), sowing and harvest dates, "
           "and water regime (rainfed or irrigated).", ("date",)),
    _local("LOCAL_CROP_CALENDAR", "CROP_CALENDAR",
           "In which months is each crop usually sown and harvested on this farm?",
           "CropStory has no calendar defaults; without farm windows, crops cannot be calendar-checked or used "
           "in alternatives.",
           "For each crop: sowing window and harvest window as months (1–12) as practised on this farm.", ("month",)),
    _local("CROP_IDENTITY", "CROP_IDENTITY",
           "Which exact crop (species, and variety if known) is meant by each name that could not be identified?",
           "Unidentified crop names have no botanical family, so family and legume rules and study comparisons "
           "cannot use them.",
           "Common and scientific name (e.g. durum wheat, Triticum durum) and variety if known."),
    _local("WATER_AVAILABILITY", "IRRIGATION",
           "Is the farm rainfed or irrigated, and how much irrigation water is available per season?",
           "Water-dependent screening of crops and comparison with studies need the water regime.",
           "Water regime (rainfed, irrigated, supplemental irrigation) and the seasonal allowance (mm/season or "
           "m3/ha/season) with its source (quota, concession, well).", ("mm/season", "m3/ha/season")),
    _local("FARM_CONSTRAINTS", "FARM_CONSTRAINTS",
           "Which crops are excluded, and which water, equipment and market limits apply on this farm?",
           "Alternatives cannot be screened against constraints that were never declared.",
           "Excluded crops with the reason, water regime, available machinery and market situation per crop."),
    _local("EQUIPMENT_INVENTORY", "FARM_CONSTRAINTS",
           "Which machinery is available for sowing, crop care and harvest (own, shared or contracted)?",
           "Crops new to the farm cannot be checked for machinery needs without an equipment list.",
           "List of machines and services available, and known limitations (e.g. no row-crop planter)."),
    _local("MARKET_ACCESS", "FARM_CONSTRAINTS",
           "For which crops is there a contract, a known buyer, or no market?",
           "Alternatives cannot be screened for sellable crops without declared market access.",
           "Per crop: CONTRACTED, SELLABLE, NO_MARKET or UNKNOWN, with a note on the buyer or contract."),
    _local("FARMER_PRIORITIES", "PRIORITIES",
           "Which goals matter most when comparing rotations, in order (e.g. soil cover, crop diversity, risk)?",
           "Without ranked priorities, strategies are separated only by declared constraints.",
           "Ordinal ranks (1 = most important) of the criteria; no weights.", ("rank",)),
    _local("CASE_COUNTRY_CLIMATE", "CASE_CONTEXT",
           "In which country is the field, and which Köppen–Geiger climate class applies?",
           "Study applicability by region and climate cannot be compared without them; CropStory does not derive "
           "them from the field location.",
           "ISO 3166-1 alpha-2 country code and Köppen–Geiger class (e.g. Csa) with the map used. The location "
           "itself is not needed."),
    _task("NASA_POWER_RETRIEVAL", "CLIMATE_DATA_QUALITY",
          "Retrieve NASA POWER observations for the years of the incident period that have none.",
          "Without observations, the weather hypotheses cannot be compared with regional data for those years.",
          "Case-bound NASA POWER retrieval (OWNER/EDITOR).",
          "POST /api/v1/cases/{case_id}/observations/nasa-power"),
    _task("CLAIM_REVIEW", "LITERATURE",
          "Have a second case member review the claim against the full text.",
          "Unreviewed claims are LITERATURE_METADATA: their content has not been checked against the paper.",
          "Review decision with the source consulted (ABB-14 protocol).",
          "POST /api/v1/cases/{case_id}/claims/{claim_id}/review"),
    _task("STUDY_RECORD", "LITERATURE",
          "Record the study's structured conditions and comparability fields from the paper.",
          "Applicability and disagreement checks only compare structured fields; missing ones stay UNKNOWN or are "
          "not compared.",
          "Crops, water regime, USDA texture classes, pH range, countries/scope, Köppen–Geiger classes, "
          "intervention, comparator, outcome variable and stated direction, as reported in the paper.",
          "PATCH /api/v1/cases/{case_id}/claims/{claim_id}"),
    _task("PROFILE_CORRECTION", "PROFILE_CONSISTENCY",
          "Correct the inconsistent farm-profile entries.",
          "Profile errors block the rotation comparison.",
          "The corrected value at the reported path, re-checked with the profile assessment.",
          "POST /api/v1/farm-profiles/assess"),
    _task("CLIMATE_SCENARIO", "DECISION_CRITERIA",
          "Supply a labelled climate scenario (an observed episode or hypothetical months) for the rotation "
          "analysis.",
          "The RISK_REDUCTION priority can only be applied as calendar exposure to a stated scenario.",
          "A HISTORICAL_EPISODE from /api/climate with explicit flag thresholds, or HYPOTHETICAL month flags.",
          "POST /api/v1/rotations/scenarios"),
)
SPECS: dict[str, QuestionSpec] = {spec.code: spec for spec in CATALOGUE}
CATALOGUE_INDEX: dict[str, int] = {spec.code: i for i, spec in enumerate(CATALOGUE)}

# ABB-10 template wording → catalogue question, by position in the template lists.
_TEMPLATE_MISSING: dict[str, tuple[str, ...]] = {
    "WATER_DEFICIT": ("IRRIGATION_RECORDS", "LOCAL_RAIN_OR_SOIL_MOISTURE", "CROP_STAGE_AT_EVENT"),
    "EXCESS_WATER": ("STANDING_WATER", "DRAINAGE_CONDITION"),
    "HEAT_STRESS": ("CROP_STAGE_AT_EVENT", "LOCAL_TEMPERATURE"),
    "PEST_DISEASE": ("FIELD_PHOTOS_SYMPTOMS", "PEST_DIAGNOSIS"),
    "MANAGEMENT": ("MANAGEMENT_LOG", "IRRIGATION_RECORDS"),
    "SOIL_LIMITATION": ("SOIL_ANALYSIS", "DAMAGE_MAP"),
}
_TEMPLATE_VERIFICATION: dict[str, tuple[str, ...]] = {
    "WATER_DEFICIT": ("IRRIGATION_RECORDS", "CROP_STAGE_AT_EVENT", "NEIGHBOUR_FIELDS"),
    "EXCESS_WATER": ("STANDING_WATER", "DAMAGE_MAP"),
    "HEAT_STRESS": ("CROP_STAGE_AT_EVENT", "SYMPTOM_ONSET"),
    "PEST_DISEASE": ("FIELD_PHOTOS_SYMPTOMS", "PEST_DIAGNOSIS", "REGIONAL_PEST_ALERTS"),
    "MANAGEMENT": ("MANAGEMENT_LOG", "IRRIGATION_RECORDS"),
    "SOIL_LIMITATION": ("DAMAGE_MAP", "SOIL_ANALYSIS"),
}


def _template_text_map() -> tuple[dict[str, str], dict[str, str]]:
    missing: dict[str, str] = {}
    verification: dict[str, str] = {}
    for template in HYPOTHESIS_TEMPLATES:
        codes_m, codes_v = _TEMPLATE_MISSING[template["code"]], _TEMPLATE_VERIFICATION[template["code"]]
        texts_v = [q["question"] for q in template["verification_questions"]]
        if len(codes_m) != len(template["missing_evidence"]) or len(codes_v) != len(texts_v):
            raise RuntimeError(f"ABB-19 mapping out of date for template {template['code']}")
        missing.update({term_key(t): c for t, c in zip(template["missing_evidence"], codes_m)})
        verification.update({term_key(t): c for t, c in zip(texts_v, codes_v)})
    return missing, verification


MISSING_EVIDENCE_QUESTIONS, VERIFICATION_QUESTIONS = _template_text_map()
TEMPLATE_VARIABLES: dict[str, frozenset[str]] = {
    t["code"]: frozenset(t["related_variables"]) for t in HYPOTHESIS_TEMPLATES}

# ABB-11 issue code → (question, category, cause). ERROR issues all go to PROFILE_CORRECTION.
PROFILE_ISSUES: dict[str, tuple[str, Category, GapCause]] = {
    "SOIL_MISSING": ("SOIL_ANALYSIS", "SOIL", "MISSING_CASE_DATA"),
    "SOIL_TEXTURE_MISSING": ("SOIL_ANALYSIS", "SOIL", "MISSING_CASE_DATA"),
    "NO_LOCAL_SOIL_MEASUREMENT": ("SOIL_ANALYSIS", "SOIL", "ESTIMATED_NOT_MEASURED"),
    "SOIL_ORIGIN_UNKNOWN": ("SOIL_ANALYSIS", "SOIL", "ESTIMATED_NOT_MEASURED"),
    "REGIONAL_RESOLUTION_MISSING": ("SOIL_ANALYSIS", "SOIL", "ESTIMATED_NOT_MEASURED"),
    "MEASUREMENT_METADATA_MISSING": ("SOIL_ANALYSIS", "SOIL", "MISSING_CASE_DATA"),
    "SOIL_DEPTH_MISSING": ("SOIL_ANALYSIS", "SOIL", "MISSING_CASE_DATA"),
    "CROP_HISTORY_MISSING": ("CROP_HISTORY_RECORDS", "CROP_HISTORY", "MISSING_CASE_DATA"),
    "CROP_HISTORY_SHORT": ("CROP_HISTORY_RECORDS", "CROP_HISTORY", "MISSING_CASE_DATA"),
    "SEASON_DATES_MISSING": ("CROP_HISTORY_RECORDS", "CROP_HISTORY", "MISSING_CASE_DATA"),
    "SEASON_WATER_REGIME_MISSING": ("WATER_AVAILABILITY", "IRRIGATION", "MISSING_CASE_DATA"),
    "WATER_REGIME_MISSING": ("WATER_AVAILABILITY", "IRRIGATION", "MISSING_CASE_DATA"),
    "IRRIGATION_ALLOWANCE_MISSING": ("WATER_AVAILABILITY", "IRRIGATION", "MISSING_CASE_DATA"),
    "LOCAL_CALENDAR_MISSING": ("LOCAL_CROP_CALENDAR", "CROP_CALENDAR", "MISSING_CASE_DATA"),
    "HARVEST_WINDOW_MISSING": ("LOCAL_CROP_CALENDAR", "CROP_CALENDAR", "MISSING_CASE_DATA"),
    "CONSTRAINTS_MISSING": ("FARM_CONSTRAINTS", "FARM_CONSTRAINTS", "MISSING_CASE_DATA"),
    "EQUIPMENT_MISSING": ("EQUIPMENT_INVENTORY", "FARM_CONSTRAINTS", "MISSING_CASE_DATA"),
    "MARKET_ACCESS_MISSING": ("MARKET_ACCESS", "FARM_CONSTRAINTS", "MISSING_CASE_DATA"),
    "PRIORITIES_MISSING": ("FARMER_PRIORITIES", "PRIORITIES", "MISSING_CASE_DATA"),
    "CROP_NOT_IN_CATALOGUE": ("CROP_IDENTITY", "CROP_IDENTITY", "MISSING_CASE_DATA"),
}
# ABB-15 applicability dimension → case-side question and category.
CASE_DIMENSIONS: dict[str, tuple[str, Category]] = {
    "CROPS": ("CROP_HISTORY_RECORDS", "CROP_HISTORY"),
    "WATER_REGIME": ("WATER_AVAILABILITY", "IRRIGATION"),
    "SOIL_TEXTURE": ("SOIL_ANALYSIS", "SOIL"),
    "SOIL_PH": ("SOIL_ANALYSIS", "SOIL"),
    "REGION": ("CASE_COUNTRY_CLIMATE", "CASE_CONTEXT"),
    "CLIMATE": ("CASE_COUNTRY_CLIMATE", "CASE_CONTEXT"),
}
CALENDAR_REASONS = frozenset({"CALENDAR_NOT_DECLARED", "HARVEST_WINDOW_NOT_DECLARED"})

LIMITATIONS = [
    "Gaps come only from structured case records and, when supplied, the request's farm profile; free text is not "
    "interpreted (template hypothesis wording is matched exactly).",
    "would_change lists recorded items linked to a gap. It is not a value-of-information estimate: it does not say "
    "how much, or in which direction, any conclusion would change, and an answer may change nothing.",
    "Answers are FARMER_REPORTED evidence. They never change hypotheses, observations, claims, profiles or rotation "
    "results automatically; people decide how to use them (e.g. link them to a hypothesis or add them to the farm "
    "profile).",
    "NO_METHOD gaps cannot be closed by local data: CropStory has no reviewed parameters or model for them.",
    f"Questions are ordered only by counts of linked items (rule {ORDER_RULE_ID}); ties are frequent and stated.",
]
ORDER_RULE_STEPS = [
    "Only questions whose resolution is OPEN get a position; answered, reviewed and dismissed questions follow "
    "without one.",
    "Step 1: more distinct unresolved hypotheses (status OPEN or NOT_EVALUABLE) in would_change come first.",
    "Step 2: more distinct other linked items in would_change (rotation checks, candidate screenings, ordering steps "
    "and criteria, applicability dimensions, disagreement detection, profile analyses, the rotation comparison) "
    "come first.",
    "Questions still tied share a position and are listed in catalogue order (questions written in hypotheses after "
    "catalogue questions), which is not a preference.",
]
NO_BASIS_STATEMENT = (
    "There is no basis to prioritise these questions: every open question is linked to the same number of "
    "unresolved hypotheses and other items. They are listed in catalogue order, which is not a preference."
)
ORDERED_STATEMENT = (
    "Open questions are ordered by how many unresolved hypotheses, then how many other recorded items, are linked "
    "to them. A count of links is not a measure of how informative an answer would be."
)
NO_OPEN_STATEMENT = "No question is open: every listed question is answered, reviewed or dismissed."


# ── output models ────────────────────────────────────────────────────────────

class SourceRef(ContractModel):
    entity_type: SourceEntity
    entity_id: str | None = None
    field: str | None = None
    label: str
    stored: bool = True  # False: the value came from the request body (e.g. a farm profile), not the case record


class ChangeTarget(ContractModel):
    """A recorded item whose state is linked to a gap. Says what could change, never how much."""
    target_type: TargetType
    target_id: str
    label: str
    current_state: str
    how: str


class Gap(ContractModel):
    id: UUID
    key: str
    kind: Literal["MISSING_DATA"] = "MISSING_DATA"
    category: Category
    cause: GapCause
    answerable_locally: bool
    title: str
    description: str
    sources: list[SourceRef]
    question_ids: list[str]
    would_change: list[ChangeTarget]
    limitations: list[str] = []


class QuestionResolution(ContractModel):
    status: QuestionStatus
    current_answer_id: UUID | None = None
    updated_at: datetime | None = None
    note: str | None = None


class QuestionView(ContractModel):
    id: str
    origin: Literal["CATALOGUE", "HYPOTHESIS_TEXT"]
    kind: QuestionKind
    category: Category
    question: str
    why_it_matters: str
    addresses: list[str]
    addresses_gap_ids: list[UUID]
    measurement: str
    units: list[str]
    answer_route: str | None
    answerable_here: bool
    would_change: list[ChangeTarget]
    would_change_statement: str
    open_hypotheses_linked: int
    other_items_linked: int
    priority_basis: str
    position: int | None
    tied_with: list[str]
    resolution: QuestionResolution
    currently_generated: bool


class Prioritisation(ContractModel):
    rule_id: str = ORDER_RULE_ID
    status: PrioritisationStatus
    statement: str
    steps: list[str]
    is_value_of_information: Literal[False] = False


# ── inputs ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CaseInput:
    case_id: UUID
    incident_start: date
    incident_end: date | None
    crop_history: tuple[str, ...] = ()
    region_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class HypothesisInput:
    id: UUID
    title: str | None
    statement: str
    status: str
    template_code: str | None = None
    missing_evidence: tuple[str, ...] = ()
    verification_questions: tuple[tuple[str, str], ...] = ()  # (question, why_it_matters)
    evidence_ids: frozenset[str] = frozenset()

    @property
    def label(self) -> str:
        return self.title or self.statement[:120]


@dataclass(frozen=True)
class TimelineGapInput:
    """A MISSING_DATA timeline event (ABB-10)."""
    id: UUID
    event_type: Literal["DATA_GAP", "NO_OBSERVATIONS", "NO_LOCAL_MEASUREMENTS"]
    title: str
    description: str
    variable: str | None = None
    overlaps_incident: bool | None = None


@dataclass(frozen=True)
class ClaimInput:
    facts: ClaimFacts
    label: str


@dataclass(frozen=True)
class QuestionState:
    status: QuestionStatus
    current_answer_id: UUID | None = None
    updated_at: datetime | None = None
    note: str | None = None
    snapshot: dict[str, Any] | None = None


@dataclass
class Report:
    gaps: list[Gap]
    questions: list[QuestionView]
    prioritisation: Prioritisation
    profile_supplied: bool
    rotation_status: str | None = None
    limitations: list[str] = field(default_factory=lambda: list(LIMITATIONS))


# ── helpers ──────────────────────────────────────────────────────────────────

def _digest(text: str) -> str:
    return hashlib.sha256((term_key(text) or "").encode()).hexdigest()[:16]


def dynamic_question_id(kind: Literal["missing", "verification"], text: str) -> str:
    """Stable id of a question written by people in a hypothesis (same text → same question)."""
    return "H-" + uuid5(NAMESPACE, f"{kind}:{term_key(text)}").hex


def gap_id(case_id: UUID, key: str) -> UUID:
    return uuid5(NAMESPACE, f"{case_id}:{key}")


def _hypothesis_target(h: HypothesisInput) -> ChangeTarget:
    if h.status == "NOT_EVALUABLE":
        how = ("Marked NOT_EVALUABLE because evidence is missing. This information could make it evaluable; a person "
               "then decides whether it is COMPATIBLE or CONTRADICTED.")
    elif h.status == "OPEN":
        how = ("Not evaluated yet. This information gives the evaluator evidence to set COMPATIBLE, CONTRADICTED or "
               "NOT_EVALUABLE; the decision stays human.")
    else:
        how = f"Evaluated as {h.status}. New evidence could lead a reviewer to revisit that evaluation."
    return ChangeTarget(target_type="HYPOTHESIS", target_id=str(h.id), label=h.label,
                        current_state=h.status, how=how)


class _Builder:
    def __init__(self, case_id: UUID):
        self.case_id = case_id
        self.gaps: dict[str, dict[str, Any]] = {}
        self.dynamic: dict[str, QuestionSpec] = {}

    def add(self, key: str, *, category: Category, cause: GapCause, title: str, description: str,
            sources: Iterable[SourceRef], questions: Sequence[str] = (), would_change: Iterable[ChangeTarget] = (),
            limitations: Iterable[str] = ()) -> None:
        gap = self.gaps.get(key)
        if gap is None:
            gap = self.gaps[key] = dict(
                id=gap_id(self.case_id, key), key=key, category=category, cause=cause,
                answerable_locally=cause != "NO_METHOD" and any(
                    (SPECS.get(q) or self.dynamic[q]).kind == "LOCAL_INFORMATION" for q in questions),
                title=title, description=description, sources=[], question_ids=list(dict.fromkeys(questions)),
                would_change=[], limitations=list(limitations))
        for source in sources:
            if source not in gap["sources"]:
                gap["sources"].append(source)
        seen = {(t.target_type, t.target_id) for t in gap["would_change"]}
        for target in would_change:
            if (target.target_type, target.target_id) not in seen:
                gap["would_change"].append(target)
                seen.add((target.target_type, target.target_id))

    def result(self) -> list[Gap]:
        return [Gap(**g) for g in self.gaps.values()]


# ── gap sources ──────────────────────────────────────────────────────────────

def _hypothesis_gaps(b: _Builder, hypotheses: Sequence[HypothesisInput]) -> None:
    for h in hypotheses:
        target = _hypothesis_target(h)
        for i, text in enumerate(h.missing_evidence):
            code = MISSING_EVIDENCE_QUESTIONS.get(term_key(text) or "")
            if code is None:
                code = dynamic_question_id("missing", text)
                b.dynamic.setdefault(code, QuestionSpec(
                    code, "LOCAL_INFORMATION", "HYPOTHESIS_EVIDENCE", f"Can the case team obtain this evidence: “{text}”?",
                    f"Listed as missing evidence for the hypothesis “{h.label}” by the case team.",
                    "Not specified by the hypothesis: record what was found, its date(s), units and origin.",
                    origin="HYPOTHESIS_TEXT"))
            spec = SPECS.get(code) or b.dynamic[code]
            b.add(f"hypothesis:{h.id}:missing_evidence:{_digest(text)}", category=spec.category,
                  cause="MISSING_CASE_DATA", title=f"Missing evidence for “{h.label}”: {text}",
                  description=(f"The hypothesis (status {h.status}) lists this as missing evidence. It is a candidate "
                               "explanation, not a demonstrated cause."),
                  sources=[SourceRef(entity_type="HYPOTHESIS", entity_id=str(h.id), field=f"missing_evidence[{i}]",
                                     label=h.label)],
                  questions=[code], would_change=[target])
        for i, (text, why) in enumerate(h.verification_questions):
            code = VERIFICATION_QUESTIONS.get(term_key(text) or "")
            if code is None:
                code = dynamic_question_id("verification", text)
                b.dynamic.setdefault(code, QuestionSpec(
                    code, "LOCAL_INFORMATION", "HYPOTHESIS_EVIDENCE", text,
                    why or f"Verification question of the hypothesis “{h.label}”.",
                    "Not specified by the hypothesis: record what was found, its date(s), units and origin.",
                    origin="HYPOTHESIS_TEXT"))
            spec = SPECS.get(code) or b.dynamic[code]
            b.add(f"hypothesis:{h.id}:verification:{_digest(text)}", category=spec.category,
                  cause="MISSING_CASE_DATA", title=f"Unanswered verification question of “{h.label}”: {text}",
                  description=f"Verification question recorded on the hypothesis (status {h.status}).",
                  sources=[SourceRef(entity_type="HYPOTHESIS", entity_id=str(h.id),
                                     field=f"verification_questions[{i}]", label=h.label)],
                  questions=[code], would_change=[target])


def _weather_hypotheses(hypotheses: Sequence[HypothesisInput], variable: str | None = None) -> list[ChangeTarget]:
    """Template hypotheses whose template names a weather variable (structured ABB-10 metadata)."""
    out = []
    for h in hypotheses:
        variables = TEMPLATE_VARIABLES.get(h.template_code or "", frozenset())
        if variables and (variable is None or variable in variables):
            out.append(_hypothesis_target(h))
    return out


def _timeline_gaps(b: _Builder, case: CaseInput, events: Sequence[TimelineGapInput],
                   hypotheses: Sequence[HypothesisInput]) -> None:
    for e in events:
        source = SourceRef(entity_type="TIMELINE_EVENT", entity_id=str(e.id), field=e.event_type, label=e.title)
        if e.event_type == "NO_LOCAL_MEASUREMENTS":
            b.add("timeline:no-local-measurements", category="LOCAL_MEASUREMENTS", cause="MISSING_CASE_DATA",
                  title="No field-scale measurements recorded for the incident period",
                  description=e.description, sources=[source],
                  questions=["LOCAL_RAIN_OR_SOIL_MOISTURE", "IRRIGATION_RECORDS", "CROP_STAGE_AT_EVENT"],
                  limitations=["Regional NASA POWER values cannot replace field-scale records."])
        elif e.event_type == "NO_OBSERVATIONS":
            targets = [t.model_copy(update={"how": "No observed regional values exist for part of the incident period; "
                                                   "with a retrieval the hypothesis can be compared with them there."})
                       for t in _weather_hypotheses(hypotheses)]
            b.add(f"timeline:no-observations:{e.id}", category="CLIMATE_DATA_QUALITY", cause="MISSING_CASE_DATA",
                  title=e.title, description=e.description, sources=[source], questions=["NASA_POWER_RETRIEVAL"],
                  would_change=targets,
                  limitations=["Absence of stored observations is not evidence of normal conditions."])
        else:  # DATA_GAP
            question = {"precipitation": "LOCAL_RAIN_OR_SOIL_MOISTURE",
                        "max_temperature": "LOCAL_TEMPERATURE"}.get(e.variable or "")
            targets = []
            if e.overlaps_incident:
                targets = [t.model_copy(update={"how": "This month has no anomaly (incomplete data or reference); a "
                                                       "local record for the month gives the evaluator information the "
                                                       "regional series lacks. It does not fill the NASA value."})
                           for t in _weather_hypotheses(hypotheses, e.variable)]
            b.add(f"timeline:data-gap:{e.id}", category="CLIMATE_DATA_QUALITY", cause="INCOMPLETE_SOURCE_DATA",
                  title=e.title, description=e.description, sources=[source],
                  questions=[question] if question else [], would_change=targets,
                  limitations=["No value is substituted for an incomplete month."])


def _unresolved(labels: Iterable[str]) -> list[str]:
    return [label for label in labels if resolve_crop(label) is None]


def _claim_gaps(b: _Builder, case: CaseInput, claims: Sequence[ClaimInput], hypotheses: Sequence[HypothesisInput],
                profile: FarmProfile | None, country: str | None, climate: str | None) -> None:
    active = [c for c in claims if c.facts.review_status != "REJECTED"]
    if not active:
        return
    conditions = case_conditions(profile, case_crops=list(case.crop_history), country=country, climate=climate,
                                 region_labels=list(case.region_labels))
    candidates = find_candidates([c.facts for c in active])
    stored = profile is None
    for claim in active:
        cid = str(claim.facts.id)
        claim_source = SourceRef(entity_type="EVIDENCE_CLAIM", entity_id=cid, label=claim.label)
        if claim.facts.review_status != "ACCEPTED":
            targets = [ChangeTarget(
                target_type="HYPOTHESIS", target_id=str(h.id), label=h.label, current_state=h.status,
                how="Cites this claim, which is LITERATURE_METADATA until reviewed; a review would make it "
                    "LITERATURE_REVIEWED or reject it.") for h in hypotheses if cid in h.evidence_ids]
            targets += [ChangeTarget(
                target_type="DISAGREEMENT_DETECTION", target_id=str(c.id), label="Candidate disagreement",
                current_state="CANDIDATE",
                how="Cannot be confirmed as a contradiction until both claims are ACCEPTED.")
                for c in candidates if claim.facts.id in (c.claim_a.id, c.claim_b.id)]
            b.add(f"claim:{cid}:not-reviewed", category="LITERATURE", cause="NOT_REVIEWED",
                  title=f"Claim not reviewed ({claim.facts.review_status}): {claim.label}",
                  description="The claim has not been checked against the full text by a second case member.",
                  sources=[claim_source.model_copy(update={"field": "review_status"})], questions=["CLAIM_REVIEW"],
                  would_change=targets)
        notes = applicability_notes(claim.facts.context, conditions)
        study = claim.facts.context
        study_missing: list[str] = []
        for note in notes:
            if note.status != "UNKNOWN":
                continue
            dim = note.dimension
            study_side = {
                "CROPS": not study.crops or bool(_unresolved(study.crops) and not _unresolved(conditions.crops)
                                                 and conditions.crops),
                "WATER_REGIME": study.water_regime == "NOT_REPORTED",
                "SOIL_TEXTURE": not study.soil_texture_classes,
                "SOIL_PH": study.soil_ph_min is None or study.soil_ph_max is None,
                "REGION": study.geographic_scope != "GLOBAL" and not study.countries,
                "CLIMATE": not study.climate_classes,
            }[dim]
            case_side = {
                "CROPS": not conditions.crops,
                "WATER_REGIME": conditions.water_regime is None,
                "SOIL_TEXTURE": not conditions.textures,
                "SOIL_PH": not conditions.ph_values,
                "REGION": conditions.country is None,
                "CLIMATE": conditions.climate is None,
            }[dim]
            target = ChangeTarget(
                target_type="APPLICABILITY_DIMENSION", target_id=f"{cid}:{dim}", label=f"{dim} for claim: {claim.label}",
                current_state="UNKNOWN",
                how="Could become MATCH, PARTIAL or MISMATCH, which can change the claim's transfer_status; it does "
                    "not predict the result on this farm.")
            if study_side:
                study_missing.append(dim)
                b.add(f"claim:{cid}:study-record", category="LITERATURE", cause="MISSING_STUDY_DATA",
                      title=f"Study conditions not recorded for claim: {claim.label}",
                      description="Structured study conditions are missing on the claim record.",
                      sources=[claim_source.model_copy(update={"field": "context"})], questions=["STUDY_RECORD"],
                      would_change=[target])
            ambiguous_case = dim == "CROPS" and conditions.crops and _unresolved(conditions.crops)
            if case_side or ambiguous_case:
                question, category = ("CROP_IDENTITY", "CROP_IDENTITY") if ambiguous_case and not case_side \
                    else CASE_DIMENSIONS[dim]
                key = f"case:{dim}" + (":ambiguous" if ambiguous_case and not case_side else "")
                b.add(key, category=category, cause="MISSING_CASE_DATA",
                      title=(f"Case crop names not identified: {', '.join(_unresolved(conditions.crops))}"
                             if ambiguous_case and not case_side else f"Case value missing for {dim}"),
                      description=note.reason,
                      sources=[SourceRef(entity_type="FARM_PROFILE" if profile is not None else "CASE",
                                         entity_id=str(case.case_id), field=dim.lower(),
                                         label="Farm profile (request)" if profile is not None else "Case record",
                                         stored=stored)],
                      questions=[question], would_change=[target])
        reasons = not_compared_reasons(claim.facts)
        if reasons:
            b.add(f"claim:{cid}:study-record", category="LITERATURE", cause="MISSING_STUDY_DATA",
                  title=f"Study conditions not recorded for claim: {claim.label}",
                  description="Structured study conditions are missing on the claim record.",
                  sources=[claim_source.model_copy(update={"field": "intervention/outcome_variable/effect_direction"})],
                  questions=["STUDY_RECORD"],
                  would_change=[ChangeTarget(
                      target_type="DISAGREEMENT_DETECTION", target_id=f"{cid}:not-compared",
                      label=f"Disagreement detection for claim: {claim.label}", current_state="NOT_COMPARED",
                      how="Not compared with other claims (" + "; ".join(reasons) + "); with the fields recorded it "
                          "would take part in candidate detection.")])


def _profile_gaps(b: _Builder, case: CaseInput, profile: FarmProfile) -> None:
    for issue in assess_profile(profile).issues:
        if issue.severity == "ERROR":
            mapped: tuple[str, Category, GapCause] | None = ("PROFILE_CORRECTION", "PROFILE_CONSISTENCY",
                                                              "INCONSISTENT_INPUT")
        else:
            mapped = PROFILE_ISSUES.get(issue.code)
        if mapped is None:  # other warnings are consistency notes shown by the assessment itself
            continue
        question, category, cause = mapped
        how = issue.consequence or ("Blocks the rotation comparison (BLOCKED_BY_ERRORS) until corrected."
                                    if issue.severity == "ERROR" else issue.message)
        b.add(f"profile:{issue.code}:{issue.path}", category=category, cause=cause, title=issue.message,
              description=f"Farm profile assessment ({issue.severity}, {issue.code}) at {issue.path}.",
              sources=[SourceRef(entity_type="FARM_PROFILE", entity_id=str(case.case_id), field=issue.path,
                                 label="Farm profile (request)", stored=False)],
              questions=[question],
              would_change=[ChangeTarget(target_type="PROFILE_ANALYSIS", target_id=f"{issue.code}:{issue.path}",
                                         label=f"Profile check {issue.code}", current_state=issue.severity, how=how)])


def _rotation_gaps(b: _Builder, case: CaseInput, profile: FarmProfile, analysis: ScenarioAnalysis) -> None:
    comparison = analysis.comparison
    source = SourceRef(entity_type="ROTATION_COMPARISON", label="Rotation comparison (ABB-17) of the request profile",
                       stored=False)
    whole = ChangeTarget(target_type="ROTATION_COMPARISON", target_id="comparison", label="Rotation comparison",
                         current_state=comparison.status, how="")
    if comparison.status == "INSUFFICIENT_INPUT":
        b.add("rotation:insufficient-input", category="CROP_HISTORY", cause="MISSING_CASE_DATA",
              title="Rotation comparison not possible: fewer than two main-crop seasons", description=" ".join(
                  comparison.explanation), sources=[source], questions=["CROP_HISTORY_RECORDS"],
              would_change=[whole.model_copy(update={"how": "With at least two main-crop seasons the current rotation "
                                                            "and alternatives can be compared."})])
    elif comparison.status == "BLOCKED_BY_PROFILE_ERRORS":
        b.add("rotation:blocked", category="PROFILE_CONSISTENCY", cause="INCONSISTENT_INPUT",
              title="Rotation comparison blocked by farm-profile errors", description=" ".join(comparison.explanation),
              sources=[source], questions=["PROFILE_CORRECTION"],
              would_change=[whole.model_copy(update={"how": "Once the errors are corrected the comparison can run."})])

    calendar_gaps: set[str] = set()
    for screening in comparison.candidate_screening:
        if screening.status != "NOT_EVALUABLE":
            continue
        crop = screening.crop
        crop_id = crop.crop_code or crop.crop_label
        target = ChangeTarget(
            target_type="CANDIDATE_SCREENING", target_id=crop_id, label=f"Candidate crop {crop.crop_label}",
            current_state="NOT_EVALUABLE",
            how="Left out of alternative generation; with this information it would be screened again (ELIGIBLE or "
                "EXCLUDED).")
        codes = {r.code for r in screening.reasons}
        if codes & CALENDAR_REASONS:
            calendar_gaps.add(crop.crop_label)
            b.add(f"rotation:screening:{crop_id}:calendar", category="CROP_CALENDAR", cause="MISSING_CASE_DATA",
                  title=f"No complete sowing/harvest window declared for {crop.crop_label}",
                  description=" ".join(r.message for r in screening.reasons if r.code in CALENDAR_REASONS),
                  sources=[source.model_copy(update={"field": "candidate_screening"})],
                  questions=["LOCAL_CROP_CALENDAR"], would_change=[target])
        if "CROP_NOT_IN_CATALOGUE" in codes:
            b.add(f"rotation:screening:{crop_id}:identity", category="CROP_IDENTITY", cause="MISSING_CASE_DATA",
                  title=f"Crop not identified in the catalogue: {crop.crop_label}",
                  description=" ".join(r.message for r in screening.reasons if r.code == "CROP_NOT_IN_CATALOGUE"),
                  sources=[source.model_copy(update={"field": "candidate_screening"})],
                  questions=["CROP_IDENTITY"], would_change=[target])

    regime = profile.constraints.water_regime if profile.constraints else WaterRegime.UNKNOWN
    for strategy in comparison.strategies:
        labels = {ref.crop_label for slot in strategy.cycle for ref in slot}
        for check in strategy.constraint_checks:
            if check.status != "NOT_EVALUABLE":
                continue
            data_question = {
                "EXCLUDED_CROPS": "FARM_CONSTRAINTS", "MARKET_ACCESS": "MARKET_ACCESS",
                "LOCAL_CALENDAR": "LOCAL_CROP_CALENDAR" if labels & calendar_gaps else None,
                "WATER_REGIME": "WATER_AVAILABILITY" if regime == WaterRegime.UNKNOWN else None,
                "FAMILY_REPETITION": "CROP_IDENTITY", "EQUIPMENT": "EQUIPMENT_INVENTORY",
            }.get(check.constraint)
            check_source = source.model_copy(update={"entity_id": strategy.id,
                                                     "field": f"constraint_checks.{check.constraint}"})
            if data_question is None:
                b.add(f"rotation:check:{check.constraint}:no-method", category="METHOD_LIMITATION", cause="NO_METHOD",
                      title=f"{check.constraint} check not evaluable for any input in this rule set",
                      description=f"{check.detail} No local measurement makes this check evaluable in "
                                  f"{comparison.rule_set_version}.",
                      sources=[check_source])
                continue
            targets = [ChangeTarget(
                target_type="ROTATION_CHECK", target_id=f"{strategy.id}:{check.constraint}",
                label=f"{strategy.strategy_kind}: {check.constraint}", current_state="NOT_EVALUABLE",
                how="Could become SATISFIED, VIOLATED or REVIEW_REQUIRED once the input is declared in the farm "
                    "profile.")]
            if check.constraint == "LOCAL_CALENDAR" and strategy.screening_result == "NOT_FULLY_EVALUABLE":
                targets.append(ChangeTarget(
                    target_type="ORDERING_STEP", target_id=f"DECLARED_CONSTRAINTS:{strategy.id}",
                    label=f"Ordering step 0 for {strategy.strategy_kind}", current_state="NOT_FULLY_EVALUABLE",
                    how="Strategies that are not fully evaluable are placed after those passing the declared "
                        "constraints; a declared window could change its screening result."))
            b.add(f"rotation:check:{check.constraint}", category=SPECS[data_question].category,
                  cause="MISSING_CASE_DATA", title=f"{check.constraint} check not evaluable: {check.detail}",
                  description=f"Rotation constraint check NOT_EVALUABLE ({comparison.rule_set_version}).",
                  sources=[check_source], questions=[data_question], would_change=targets)

    ordering = analysis.ordering
    if ordering is None:
        return
    order_source = SourceRef(entity_type="SCENARIO_ORDERING", label="Ordering by farmer rank (ABB-18)", stored=False)
    for item in ordering.criteria_not_used:
        crit = item.criterion.value
        target = ChangeTarget(target_type="ORDERING_CRITERION", target_id=crit,
                              label=f"Priority {crit} (rank {item.rank})", current_state="NOT_USED", how="")
        if crit == "RISK_REDUCTION":
            b.add("ordering:criterion:RISK_REDUCTION", category="DECISION_CRITERIA", cause="MISSING_ANALYSIS_INPUT",
                  title="RISK_REDUCTION priority not used: no climate scenario supplied", description=item.reason,
                  sources=[order_source.model_copy(update={"field": "criteria_not_used"})],
                  questions=["CLIMATE_SCENARIO"],
                  would_change=[target.model_copy(update={
                      "how": "With a scenario it becomes an ordering step (calendar exposure, a labelled proxy, "
                             "not a risk estimate)."})])
        else:
            b.add(f"ordering:criterion:{crit}:no-method", category="METHOD_LIMITATION", cause="NO_METHOD",
                  title=f"Priority {crit} cannot be used to order strategies", description=item.reason,
                  sources=[order_source.model_copy(update={"field": "criteria_not_used"})])
    kinds = {s.id: s.strategy_kind for s in comparison.strategies}
    for step in ordering.steps:
        if step.step == 0:
            continue
        question = {"SOIL_COVER_MONTHS": "LOCAL_CROP_CALENDAR", "BOTANICAL_FAMILIES": "CROP_IDENTITY"}.get(
            step.criterion_id)
        missing = [v.strategy_id for v in step.values if v.value is None]
        if not question or not missing:
            continue
        b.add(f"ordering:step:{step.criterion_id}", category=SPECS[question].category, cause="MISSING_CASE_DATA",
              title=f"Ordering criterion {step.criterion_id} not evaluable for {len(missing)} strategy(ies)",
              description=step.explanation,
              sources=[order_source.model_copy(update={"field": f"steps[{step.step}]"})], questions=[question],
              would_change=[ChangeTarget(
                  target_type="ORDERING_STEP", target_id=f"{step.criterion_id}:{sid}",
                  label=f"Step {step.step} ({step.criterion_id}, rank {step.rank}) for {kinds.get(sid, sid)}",
                  current_state="NOT_EVALUABLE",
                  how="Strategies without a value are placed after those with one at this step; a value could move "
                      "this strategy.") for sid in missing])


# ── questions and ordering ───────────────────────────────────────────────────

def _spec(code: str, dynamic: dict[str, QuestionSpec], state: QuestionState | None) -> QuestionSpec | None:
    if code in SPECS:
        return SPECS[code]
    if code in dynamic:
        return dynamic[code]
    snap = state.snapshot if state else None
    if not snap:
        return None
    return QuestionSpec(code, snap["kind"], snap["category"], snap["question"], snap["why_it_matters"],
                        snap["measurement"], tuple(snap.get("units") or ()), snap.get("answer_route"),
                        snap.get("origin", "HYPOTHESIS_TEXT"))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _questions(gaps: list[Gap], dynamic: dict[str, QuestionSpec], states: dict[str, QuestionState],
               hypothesis_status: dict[str, str]) -> list[QuestionView]:
    by_code: dict[str, list[Gap]] = {}
    for gap in gaps:
        for code in gap.question_ids:
            by_code.setdefault(code, []).append(gap)
    codes = list(by_code) + [c for c in states if c not in by_code]
    views = []
    for code in codes:
        state = states.get(code)
        spec = _spec(code, dynamic, state)
        if spec is None:  # pragma: no cover - stored states always carry a snapshot
            continue
        linked = by_code.get(code, [])
        targets: list[ChangeTarget] = []
        seen: set[tuple[str, str]] = set()
        for gap in linked:
            for t in gap.would_change:
                if (t.target_type, t.target_id) not in seen:
                    seen.add((t.target_type, t.target_id))
                    targets.append(t)
        open_h = sorted({t.label for t in targets if t.target_type == "HYPOTHESIS"
                         and hypothesis_status.get(t.target_id) in UNRESOLVED_HYPOTHESIS})
        open_count = len({t.target_id for t in targets if t.target_type == "HYPOTHESIS"
                          and hypothesis_status.get(t.target_id) in UNRESOLVED_HYPOTHESIS})
        other = sum(1 for t in targets if t.target_type != "HYPOTHESIS")
        addresses = list(dict.fromkeys(g.title for g in linked))
        why = spec.why_it_matters
        if addresses:
            why += " It addresses: " + "; ".join(addresses[:5]) + (
                f"; and {len(addresses) - 5} more gap(s)." if len(addresses) > 5 else ".")
        statement = ("No hypothesis, rotation check, ordering step or applicability dimension is currently linked to "
                     "this question; an answer adds local context only." if not targets else
                     f"{_plural(len(targets), 'linked item')} could change (listed in would_change). This lists what "
                     "could change, not by how much or in which direction.")
        basis = (f"Linked to {_plural(open_count, 'unresolved hypothesis')}"
                 + (f" ({'; '.join(open_h)})" if open_h else "") + f" and {_plural(other, 'other item')}.")
        basis = basis.replace("hypothesiss", "hypotheses")
        views.append(QuestionView(
            id=code, origin=spec.origin, kind=spec.kind, category=spec.category, question=spec.question,
            why_it_matters=why, addresses=addresses, addresses_gap_ids=[g.id for g in linked],
            measurement=spec.measurement, units=list(spec.units), answer_route=spec.answer_route,
            answerable_here=spec.answer_route is None, would_change=targets, would_change_statement=statement,
            open_hypotheses_linked=open_count, other_items_linked=other, priority_basis=basis, position=None,
            tied_with=[],
            resolution=QuestionResolution(status=state.status, current_answer_id=state.current_answer_id,
                                          updated_at=state.updated_at, note=state.note) if state else
            QuestionResolution(status="OPEN"),
            currently_generated=bool(linked),
        ))
    return views


def _catalogue_rank(q: QuestionView) -> tuple[int, str]:
    return (CATALOGUE_INDEX.get(q.id, len(CATALOGUE_INDEX)), q.id)


def prioritise(questions: list[QuestionView]) -> tuple[list[QuestionView], Prioritisation]:
    """Apply ``ORDER_RULE_ID``. Returns questions in display order and the prioritisation statement."""
    open_q = [q for q in questions if q.resolution.status == "OPEN"]
    closed = sorted((q for q in questions if q.resolution.status != "OPEN"), key=_catalogue_rank)
    if not open_q:
        return closed, Prioritisation(status="NO_OPEN_QUESTIONS", statement=NO_OPEN_STATEMENT,
                                      steps=list(ORDER_RULE_STEPS))

    def key(q: QuestionView) -> tuple[int, int]:
        return (-q.open_hypotheses_linked, -q.other_items_linked)

    ordered = sorted(open_q, key=lambda q: (key(q), _catalogue_rank(q)))
    keys = [key(q) for q in ordered]
    distinct = sorted(set(keys))
    positions = {k: i for i, k in enumerate(distinct, start=1)}
    result = []
    for q in ordered:
        k = key(q)
        result.append(q.model_copy(update={
            "position": positions[k], "tied_with": [o.id for o in ordered if o.id != q.id and key(o) == k]}))
    if len(distinct) == 1:
        prio = Prioritisation(status="NO_BASIS_TO_PRIORITISE", statement=NO_BASIS_STATEMENT,
                              steps=list(ORDER_RULE_STEPS))
    else:
        prio = Prioritisation(status="ORDERED_BY_LINK_COUNTS", statement=ORDERED_STATEMENT,
                              steps=list(ORDER_RULE_STEPS))
    return result + closed, prio


# ── entry point ──────────────────────────────────────────────────────────────

def build_report(case: CaseInput, *, hypotheses: Sequence[HypothesisInput] = (),
                 timeline_gaps: Sequence[TimelineGapInput] = (), claims: Sequence[ClaimInput] = (),
                 profile: FarmProfile | None = None, country: str | None = None, climate: str | None = None,
                 horizon_years: int | None = None, states: dict[str, QuestionState] | None = None) -> Report:
    """Deterministic gap inventory, questions and prioritisation for one case."""
    b = _Builder(case.case_id)
    _hypothesis_gaps(b, hypotheses)
    _timeline_gaps(b, case, timeline_gaps, hypotheses)
    _claim_gaps(b, case, claims, hypotheses, profile, country, climate)
    rotation_status = None
    if profile is not None:
        _profile_gaps(b, case, profile)
        analysis = analyse_scenarios(ScenarioAnalysisRequest(profile=profile, horizon_years=horizon_years))
        rotation_status = analysis.comparison.status
        _rotation_gaps(b, case, profile, analysis)
    gaps = b.result()
    questions = _questions(gaps, b.dynamic, states or {}, {str(h.id): h.status for h in hypotheses})
    ordered, prio = prioritise(questions)
    return Report(gaps=gaps, questions=ordered, prioritisation=prio, profile_supplied=profile is not None,
                  rotation_status=rotation_status)


def question_spec(code: str, *, hypotheses: Sequence[HypothesisInput] = ()) -> QuestionSpec | None:
    """Catalogue question, or a question currently written in one of the case's hypotheses."""
    if code in SPECS:
        return SPECS[code]
    b = _Builder(UUID(int=0))
    _hypothesis_gaps(b, hypotheses)
    return b.dynamic.get(code)
