"""Comparability of evidence claims and applicability of a study context to a case (ABB-15).

Rules (``docs/science/CONTRADICTIONS_APPLICABILITY.md``):

- Only **structured fields entered by people** are compared: a claim's ``intervention``,
  ``comparator``, ``outcome_variable`` and ``effect_direction`` and the structured parts of its
  study ``context`` (crops, water regime, USDA texture classes, reported pH range, geographic
  scope/countries, Koppen-Geiger classes). Free text (``claim_text``, ``study_context``,
  ``context.region``/``climate``/``soils``/``management``, ``reported_outcome``) is shown to people
  but never parsed.
- Terms are matched exactly after case/accent/whitespace normalisation; there are no synonyms.
- Two claims with the same intervention and outcome variable but opposed stated directions form a
  **candidate disagreement**. A candidate is never presented as a contradiction; only a person
  can confirm it (or mark it not comparable / inconclusive).
- Applicability compares the study context with the case per dimension and returns MATCH /
  PARTIAL / MISMATCH / UNKNOWN with a reason. Missing data on either side is UNKNOWN. There is no
  numeric score, weight or overall percentage.

This module is pure (no database, no network) so the rules can be unit tested.
"""
from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import Field as PydanticField

from .crop_catalog import resolve_crop
from .farm_profile import FarmProfile, SeasonRole, SoilProperty, WaterRegime
from .schemas import ContractModel

METHOD_VERSION = "abb15-comparability-0.1.0"

EffectDirection = Literal["INCREASE", "DECREASE", "NO_CLEAR_EFFECT", "MIXED", "NOT_STATED"]
StudyWaterRegime = Literal["RAINFED", "IRRIGATED", "SUPPLEMENTAL_IRRIGATION", "MIXED", "NOT_REPORTED"]
GeographicScope = Literal["GLOBAL", "MULTI_COUNTRY", "NATIONAL", "SUBNATIONAL", "SITE", "NOT_REPORTED"]
# USDA soil texture classes (Soil Survey Manual), USDA particle-size limits.
TextureClass = Literal[
    "SAND", "LOAMY_SAND", "SANDY_LOAM", "LOAM", "SILT_LOAM", "SILT", "SANDY_CLAY_LOAM", "CLAY_LOAM",
    "SILTY_CLAY_LOAM", "SANDY_CLAY", "SILTY_CLAY", "CLAY",
]
# Koppen-Geiger climate classes.
KoppenClass = Literal[
    "Af", "Am", "Aw", "As", "BWh", "BWk", "BSh", "BSk", "Csa", "Csb", "Csc", "Cwa", "Cwb", "Cwc",
    "Cfa", "Cfb", "Cfc", "Dsa", "Dsb", "Dsc", "Dsd", "Dwa", "Dwb", "Dwc", "Dwd", "Dfa", "Dfb", "Dfc",
    "Dfd", "ET", "EF",
]
MatchStatus = Literal["MATCH", "PARTIAL", "MISMATCH", "UNKNOWN"]
Dimension = Literal[
    "CROPS", "WATER_REGIME", "SOIL_TEXTURE", "SOIL_PH", "REGION", "CLIMATE", "COMPARATOR", "STUDY_DESIGN",
]
TransferStatus = Literal["DIFFERENCES_FOUND", "INSUFFICIENT_DATA", "NO_DIFFERENCES_FOUND_IN_COMPARED_DIMENSIONS"]
DisagreementKind = Literal["OPPOSITE_DIRECTION", "EFFECT_VS_NO_CLEAR_EFFECT"]

#: Stated directions that can take part in disagreement detection.
COMPARABLE_DIRECTIONS = frozenset({"INCREASE", "DECREASE", "NO_CLEAR_EFFECT"})
_OPPOSED: dict[frozenset[str], DisagreementKind] = {
    frozenset({"INCREASE", "DECREASE"}): "OPPOSITE_DIRECTION",
    frozenset({"INCREASE", "NO_CLEAR_EFFECT"}): "EFFECT_VS_NO_CLEAR_EFFECT",
    frozenset({"DECREASE", "NO_CLEAR_EFFECT"}): "EFFECT_VS_NO_CLEAR_EFFECT",
}
#: Fixed namespace so a pair of claims always has the same disagreement id.
DISAGREEMENT_NAMESPACE = UUID("6d1f3c8e-1a4b-5c7d-9e2f-0a15abb15000")
TEXTURE_SUM_TOLERANCE = 2.0  # same rounding allowance as ABB-11 (percentage points)

DESIGN_NOTES: dict[str, str] = {
    "META_ANALYSIS": "Pooled estimate across many sites and conditions; the response at one farm can differ in "
                     "size and even direction.",
    "SYSTEMATIC_REVIEW": "Synthesis across studies; check which included studies resemble the case.",
    "MODELLING_STUDY": "Model output: it depends on the model's calibration region, inputs and assumptions.",
    "NARRATIVE_REVIEW": "Narrative review: studies were not pooled systematically.",
    "OBSERVATIONAL_STUDY": "Observational study: associations, possibly confounded by site and management.",
    "UNKNOWN": "Study design not recorded; the strength and scope of the result cannot be judged.",
}
NOT_ASSESSED_NOTE = (
    "Not compared automatically: intervention details and management practices, cultivars, sowing dates and "
    "the weather of the study years. Read the paper for these."
)
APPLICABILITY_LIMITATIONS = [
    "Descriptive comparison of recorded conditions; it is not a prediction that the result will or will not "
    "occur on this farm.",
    "No applicability score is computed: dimensions are not weighted or combined into a number.",
    "Only structured fields are compared; free-text descriptions are shown for people to read and never parsed.",
    "Names are matched exactly (case- and accent-insensitive); synonyms and broader categories are not inferred.",
    "MATCH means the case falls within the study's recorded conditions on that dimension only.",
]
DISAGREEMENT_LIMITATIONS = [
    "Candidates come from structured fields entered by people: same intervention and outcome variable, different "
    "stated direction. They are not contradictions until a reviewer confirms one.",
    "Comparability notes list recorded differences in comparator, design and study conditions; legitimate "
    "differences in conditions can explain opposed results.",
    "A confirmed contradiction says that two reviewed claims disagree as recorded; it does not say which study is "
    "right.",
    "Rejected claims and claims without an intervention, outcome variable or comparable stated direction are not "
    "compared.",
]


# ── models returned by the API ───────────────────────────────────────────────

class TransferNote(ContractModel):
    """One dimension of a claim-to-case comparison. Values are display text, never a score."""
    dimension: Dimension
    status: MatchStatus
    study_value: str | None = None
    case_value: str | None = None
    case_value_source: str | None = PydanticField(default=None, description="Where the case value came from")
    reason: str


class ComparabilityNote(ContractModel):
    """One dimension of a claim-to-claim comparison."""
    dimension: Dimension
    status: MatchStatus
    claim_a_value: str | None = None
    claim_b_value: str | None = None
    reason: str


# ── normalisation ────────────────────────────────────────────────────────────

def term_key(text: str | None) -> str | None:
    """Case/accent/whitespace-insensitive key for exact matching of human-entered terms."""
    if text is None:
        return None
    folded = unicodedata.normalize("NFKD", text).casefold()
    key = " ".join("".join(c for c in folded if not unicodedata.combining(c)).replace("_", " ").split())
    return key or None


def pair_id(a: UUID, b: UUID) -> UUID:
    """Stable, order-independent id of a claim pair."""
    low, high = sorted((a, b))
    return uuid5(DISAGREEMENT_NAMESPACE, f"{low}:{high}")


def _join(values: Iterable[str]) -> str:
    return ", ".join(values)


# ── study context ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StudyContext:
    """Structured study conditions of a claim (``EvidenceClaim.context``)."""
    crops: tuple[str, ...] = ()
    water_regime: str = "NOT_REPORTED"
    soil_texture_classes: tuple[str, ...] = ()
    soil_ph_min: float | None = None
    soil_ph_max: float | None = None
    geographic_scope: str = "NOT_REPORTED"
    countries: tuple[str, ...] = ()
    climate_classes: tuple[str, ...] = ()
    soils_text: tuple[str, ...] = ()
    region_text: str | None = None
    climate_text: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> StudyContext:
        data = data or {}
        return cls(
            crops=tuple(data.get("crops") or ()),
            water_regime=data.get("water_regime") or "NOT_REPORTED",
            soil_texture_classes=tuple(data.get("soil_texture_classes") or ()),
            soil_ph_min=data.get("soil_ph_min"), soil_ph_max=data.get("soil_ph_max"),
            geographic_scope=data.get("geographic_scope") or "NOT_REPORTED",
            countries=tuple(data.get("countries") or ()),
            climate_classes=tuple(data.get("climate_classes") or ()),
            soils_text=tuple(data.get("soils") or ()),
            region_text=data.get("region"), climate_text=data.get("climate"),
        )


# ── case conditions ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Fact:
    value: Any
    source: str


@dataclass
class CaseConditions:
    """Case-side values with their origin. Empty means not provided (never defaulted)."""
    crops: list[str] = field(default_factory=list)
    crops_source: str | None = None
    water_regime: Fact | None = None
    water_note: str | None = None
    textures: list[Fact] = field(default_factory=list)
    texture_notes: list[str] = field(default_factory=list)
    ph_values: list[Fact] = field(default_factory=list)
    country: str | None = None
    climate: str | None = None
    region_labels: list[str] = field(default_factory=list)


def usda_texture_class(clay: float, silt: float, sand: float) -> str | None:
    """USDA texture class from fractions (%), normalised to sum 100. USDA particle-size limits assumed."""
    total = clay + silt + sand
    if total <= 0:
        return None
    clay, silt, sand = (100 * v / total for v in (clay, silt, sand))
    if silt + 1.5 * clay < 15:
        return "SAND"
    if silt + 2 * clay < 30:
        return "LOAMY_SAND"
    if (7 <= clay < 20 and sand > 52) or (clay < 7 and silt < 50):
        return "SANDY_LOAM"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "LOAM"
    if (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12):
        return "SILT_LOAM"
    if silt >= 80 and clay < 12:
        return "SILT"
    if 20 <= clay < 35 and silt < 28 and sand > 45:
        return "SANDY_CLAY_LOAM"
    if 27 <= clay < 40 and 20 < sand <= 45:
        return "CLAY_LOAM"
    if 27 <= clay < 40 and sand <= 20:
        return "SILTY_CLAY_LOAM"
    if clay >= 35 and sand > 45:
        return "SANDY_CLAY"
    if clay >= 40 and silt >= 40:
        return "SILTY_CLAY"
    if clay >= 40 and sand <= 45 and silt < 40:
        return "CLAY"
    return None  # pragma: no cover - the classes above partition the triangle


def _depth(top: float | None, bottom: float | None) -> str:
    return "depth not stated" if top is None else f"{top:g}-{bottom:g} cm"


def case_conditions(
    profile: FarmProfile | None, *, case_crops: Sequence[str] = (), country: str | None = None,
    climate: str | None = None, region_labels: Sequence[str] = (),
) -> CaseConditions:
    """Collect case-side values from a farm profile and stored case data. Nothing is defaulted."""
    out = CaseConditions(country=country, climate=climate, region_labels=list(region_labels))
    seasons = [s for s in (profile.crop_history if profile else []) if s.role != SeasonRole.FALLOW]
    if seasons:
        out.crops = list(dict.fromkeys(s.crop_code or s.crop_label for s in seasons))
        out.crops_source = "farm profile crop history (FARMER_REPORTED)"
    elif case_crops:
        out.crops = list(dict.fromkeys(case_crops))
        out.crops_source = "case record crop history (FARMER_REPORTED)"
    if profile is not None:
        regime = profile.constraints.water_regime if profile.constraints else WaterRegime.UNKNOWN
        if regime != WaterRegime.UNKNOWN:
            out.water_regime = Fact(regime.value, "farm profile constraints (FARMER_REPORTED)")
        else:
            regimes = {s.water_regime.value for s in seasons if s.water_regime != WaterRegime.UNKNOWN}
            if len(regimes) == 1:
                out.water_regime = Fact(regimes.pop(), "farm profile crop history (FARMER_REPORTED)")
            elif regimes:
                out.water_note = f"The crop history lists different water regimes ({_join(sorted(regimes))})."
        _soil_facts(profile, out)
    return out


def _soil_facts(profile: FarmProfile, out: CaseConditions) -> None:
    layers: dict[tuple[float | None, float | None], dict[SoilProperty, list]] = {}
    for obs in profile.soil:
        if not math.isfinite(obs.value):
            continue
        if obs.property == SoilProperty.PH and obs.unit == "pH" and 0 <= obs.value <= 14:
            out.ph_values.append(Fact(obs.value, f"{_depth(obs.depth_top_cm, obs.depth_bottom_cm)}, "
                                                 f"{obs.origin.value}"))
        if obs.property in (SoilProperty.CLAY, SoilProperty.SILT, SoilProperty.SAND) and obs.unit == "%":
            layers.setdefault((obs.depth_top_cm, obs.depth_bottom_cm), {}).setdefault(obs.property, []).append(obs)
    for (top, bottom), props in layers.items():
        where = _depth(top, bottom)
        if any(len(props.get(p, [])) != 1 for p in (SoilProperty.CLAY, SoilProperty.SILT, SoilProperty.SAND)):
            out.texture_notes.append(f"Layer {where}: clay, silt and sand are not each given exactly once; "
                                     "texture class not derived.")
            continue
        clay, silt, sand = (props[p][0] for p in (SoilProperty.CLAY, SoilProperty.SILT, SoilProperty.SAND))
        total = clay.value + silt.value + sand.value
        if abs(total - 100) > TEXTURE_SUM_TOLERANCE:
            out.texture_notes.append(f"Layer {where}: fractions sum to {total:g} %; texture class not derived.")
            continue
        texture = usda_texture_class(clay.value, silt.value, sand.value)
        if texture is not None:
            origins = _join(sorted({o.origin.value for o in (clay, silt, sand)}))
            out.textures.append(Fact(texture, f"derived from clay/silt/sand %, {where}, {origins}"))


# ── per-dimension rules: study vs case ───────────────────────────────────────

def _crop_ids(labels: Iterable[str]) -> tuple[dict[str, str], set[str]]:
    """Map identifier -> display label; identifiers are catalogue codes or normalised text."""
    ids: dict[str, str] = {}
    unresolved: set[str] = set()
    for label in labels:
        entry = resolve_crop(label)
        if entry is not None:
            ids.setdefault(f"code:{entry.code}", label)
        elif (key := term_key(label)) is not None:
            ids.setdefault(f"text:{key}", label)
            unresolved.add(label)
    return ids, unresolved


def _set_status(case: set[str], study: set[str]) -> MatchStatus:
    """Case values vs study values: MATCH only if they are the same conditions (no pooling with others)."""
    overlap = case & study
    if not overlap:
        return "MISMATCH"
    return "MATCH" if case == study else "PARTIAL"


def crops_note(study: StudyContext, case: CaseConditions) -> TransferNote:
    s_ids, s_unres = _crop_ids(study.crops)
    c_ids, c_unres = _crop_ids(case.crops)
    base = dict(dimension="CROPS", study_value=_join(study.crops) or None, case_value=_join(case.crops) or None,
                case_value_source=case.crops_source)
    if not s_ids or not c_ids:
        side = "study" if not s_ids else "case"
        return TransferNote(**base, status="UNKNOWN", reason=f"No crops recorded for the {side}.")
    status = _set_status(set(c_ids), set(s_ids))
    shared = [c_ids[i] for i in c_ids if i in s_ids]
    if status == "MISMATCH" and (s_unres or c_unres):
        return TransferNote(**base, status="UNKNOWN", reason=(
            "No crop name matches exactly, but " + _join(sorted(s_unres | c_unres))
            + " is not in the crop catalogue, so a difference cannot be established by name."))
    reason = {
        "MATCH": "The study crops are the case crops.",
        "PARTIAL": f"Shared crops: {_join(shared)}. The study also covers other crops or the case has crops "
                   "the study does not cover; results may be pooled across crops.",
        "MISMATCH": "None of the case crops was studied.",
    }[status]
    return TransferNote(**base, status=status, reason=reason)


def water_note(study: StudyContext, case: CaseConditions) -> TransferNote:
    case_value = case.water_regime.value if case.water_regime else None
    base = dict(dimension="WATER_REGIME", study_value=study.water_regime, case_value=case_value,
                case_value_source=case.water_regime.source if case.water_regime else None)
    if study.water_regime == "NOT_REPORTED":
        return TransferNote(**base, status="UNKNOWN", reason="The study water regime is not recorded.")
    if case_value is None:
        return TransferNote(**base, status="UNKNOWN",
                            reason=case.water_note or "The case water regime is not provided.")
    if study.water_regime == case_value:
        return TransferNote(**base, status="MATCH", reason="Same water regime.")
    if study.water_regime == "MIXED":
        return TransferNote(**base, status="PARTIAL", reason=(
            "The study covers several water regimes; unless the paper reports results for the case regime "
            "separately, its result is not specific to it."))
    return TransferNote(**base, status="MISMATCH",
                        reason=f"Different water regime ({study.water_regime} vs {case_value}).")


def texture_note(study: StudyContext, case: CaseConditions) -> TransferNote:
    case_classes = sorted({f.value for f in case.textures})
    base = dict(dimension="SOIL_TEXTURE", study_value=_join(study.soil_texture_classes) or None,
                case_value=_join(case_classes) or None,
                case_value_source="; ".join(f.source for f in case.textures) or None)
    if not study.soil_texture_classes:
        free = f" Free-text soils recorded: {_join(study.soils_text)} (not compared)." if study.soils_text else ""
        return TransferNote(**base, status="UNKNOWN",
                            reason="The study soil texture is not recorded as USDA classes." + free)
    if not case_classes:
        notes = " " + " ".join(case.texture_notes) if case.texture_notes else ""
        return TransferNote(**base, status="UNKNOWN",
                            reason="No case soil texture (clay, silt and sand % of one layer) is provided." + notes)
    status = _set_status(set(case_classes), set(study.soil_texture_classes))
    reason = {
        "MATCH": "The case texture class is the study's.",
        "PARTIAL": "The case texture class is among the study's, which also include other classes (or the case "
                   "has layers in other classes).",
        "MISMATCH": "The case texture class is not among the study's.",
    }[status]
    return TransferNote(**base, status=status, reason=reason)


def ph_note(study: StudyContext, case: CaseConditions) -> TransferNote:
    has_range = study.soil_ph_min is not None and study.soil_ph_max is not None
    values = [f.value for f in case.ph_values]
    base = dict(dimension="SOIL_PH",
                study_value=f"{study.soil_ph_min:g}-{study.soil_ph_max:g}" if has_range else None,
                case_value=_join(f"{v:g}" for v in values) or None,
                case_value_source="; ".join(f.source for f in case.ph_values) or None)
    if not has_range:
        return TransferNote(**base, status="UNKNOWN", reason="The study pH range is not recorded.")
    if not values:
        return TransferNote(**base, status="UNKNOWN", reason="No case soil pH is provided.")
    inside = [v for v in values if study.soil_ph_min <= v <= study.soil_ph_max]
    if len(inside) == len(values):
        return TransferNote(**base, status="MATCH", reason="Case pH within the range recorded for the study "
                                                            "(compared exactly, no tolerance).")
    if inside:
        return TransferNote(**base, status="PARTIAL", reason="Some case pH values fall outside the study range.")
    return TransferNote(**base, status="MISMATCH", reason="Case pH outside the range recorded for the study.")


def region_note(study: StudyContext, case: CaseConditions) -> TransferNote:
    scope = study.geographic_scope
    study_value = scope + (f"; countries: {_join(study.countries)}" if study.countries else "")
    if study.region_text:
        study_value += f"; as written: {study.region_text}"
    case_value = case.country
    if case.region_labels:
        labels = f"region labels: {_join(case.region_labels)} (not compared)"
        case_value = f"{case.country}; {labels}" if case.country else labels
    base = dict(dimension="REGION", study_value=study_value, case_value=case_value,
                case_value_source="request (country code)" if case.country else None)
    if case.country is None:
        return TransferNote(**base, status="UNKNOWN", reason="No case country code is provided.")
    if scope == "GLOBAL":
        included = " Sites in this country are listed." if case.country in study.countries else ""
        return TransferNote(**base, status="PARTIAL", reason=(
            "Global pooling: the case region may or may not be represented; check the paper's site list." + included))
    if not study.countries:
        return TransferNote(**base, status="UNKNOWN", reason="The study countries are not recorded.")
    status = _set_status({case.country}, set(study.countries))
    reason = {
        "MATCH": "Same country; climate, soils and practice can still differ within a country.",
        "PARTIAL": "The study includes this country together with others.",
        "MISMATCH": "The study was not conducted in the case country.",
    }[status]
    return TransferNote(**base, status=status, reason=reason)


def _climate_status(case: set[str], study: set[str]) -> MatchStatus:
    if case & study:
        return _set_status(case, study)
    if {c[:2] for c in case} & {s[:2] for s in study}:
        return "PARTIAL"
    return "MISMATCH"


def climate_note(study: StudyContext, case: CaseConditions) -> TransferNote:
    study_value = _join(study.climate_classes) or None
    if study.climate_text:
        study_value = (study_value + "; " if study_value else "") + f"as written: {study.climate_text}"
    base = dict(dimension="CLIMATE", study_value=study_value, case_value=case.climate,
                case_value_source="request (Koppen-Geiger class)" if case.climate else None)
    if not study.climate_classes:
        return TransferNote(**base, status="UNKNOWN",
                            reason="The study climate is not recorded as Koppen-Geiger classes.")
    if case.climate is None:
        return TransferNote(**base, status="UNKNOWN", reason="No case Koppen-Geiger class is provided.")
    status = _climate_status({case.climate}, set(study.climate_classes))
    reason = {
        "MATCH": "Same Koppen-Geiger class.",
        "PARTIAL": "Same main group and precipitation pattern, or the study pools this class with others.",
        "MISMATCH": "Different climate type (main group or precipitation pattern differs).",
    }[status]
    return TransferNote(**base, status=status, reason=reason)


def applicability_notes(study: StudyContext, case: CaseConditions) -> list[TransferNote]:
    return [rule(study, case) for rule in (crops_note, water_note, texture_note, ph_note, region_note, climate_note)]


def transfer_status(notes: Sequence[TransferNote | ComparabilityNote]) -> TransferStatus:
    statuses = {n.status for n in notes}
    if statuses & {"MISMATCH", "PARTIAL"}:
        return "DIFFERENCES_FOUND"
    if "UNKNOWN" in statuses:
        return "INSUFFICIENT_DATA"
    return "NO_DIFFERENCES_FOUND_IN_COMPARED_DIMENSIONS"


# ── claim-to-claim comparability ─────────────────────────────────────────────

@dataclass(frozen=True)
class ClaimFacts:
    id: UUID
    intervention: str | None
    comparator: str | None
    outcome_variable: str | None
    effect_direction: str
    review_status: str
    study_design: str = "UNKNOWN"
    context: StudyContext = field(default_factory=StudyContext)


@dataclass(frozen=True)
class Candidate:
    id: UUID
    claim_a: ClaimFacts  # lower UUID
    claim_b: ClaimFacts
    kind: DisagreementKind


def not_compared_reasons(claim: ClaimFacts) -> list[str]:
    reasons = []
    if claim.review_status == "REJECTED":
        reasons.append("rejected by a reviewer")
    if term_key(claim.intervention) is None:
        reasons.append("no intervention recorded")
    if term_key(claim.outcome_variable) is None:
        reasons.append("no outcome variable recorded")
    if claim.effect_direction not in COMPARABLE_DIRECTIONS:
        reasons.append(f"stated direction {claim.effect_direction} is not compared")
    return reasons


def find_candidates(claims: Sequence[ClaimFacts]) -> list[Candidate]:
    eligible = sorted((c for c in claims if not not_compared_reasons(c)), key=lambda c: c.id)
    found = []
    for i, a in enumerate(eligible):
        for b in eligible[i + 1:]:
            if term_key(a.intervention) != term_key(b.intervention):
                continue
            if term_key(a.outcome_variable) != term_key(b.outcome_variable):
                continue
            kind = _OPPOSED.get(frozenset({a.effect_direction, b.effect_direction}))
            if kind is not None:
                found.append(Candidate(id=pair_id(a.id, b.id), claim_a=a, claim_b=b, kind=kind))
    return found


def _pair_sets(dimension: Dimension, a: set[str], b: set[str], show_a: str | None, show_b: str | None,
               *, prefix_partial: bool = False, unresolved: set[str] = frozenset()) -> ComparabilityNote:
    base = dict(dimension=dimension, claim_a_value=show_a, claim_b_value=show_b)
    if not a or not b:
        return ComparabilityNote(**base, status="UNKNOWN", reason="Not recorded for both claims.")
    if a == b:
        return ComparabilityNote(**base, status="MATCH", reason="Same recorded values.")
    if a & b or (prefix_partial and {x[:2] for x in a} & {y[:2] for y in b}):
        return ComparabilityNote(**base, status="PARTIAL", reason="Recorded values overlap only in part.")
    if unresolved:
        return ComparabilityNote(**base, status="UNKNOWN", reason=(
            "No exact match, but " + _join(sorted(unresolved)) + " is not in the crop catalogue."))
    return ComparabilityNote(**base, status="MISMATCH", reason="Recorded values do not overlap.")


def comparability_notes(a: ClaimFacts, b: ClaimFacts) -> list[ComparabilityNote]:
    """Recorded differences between two claims, for the person reviewing a candidate."""
    notes: list[ComparabilityNote] = []
    ka, kb = term_key(a.comparator), term_key(b.comparator)
    notes.append(ComparabilityNote(
        dimension="COMPARATOR", claim_a_value=a.comparator, claim_b_value=b.comparator,
        status="UNKNOWN" if ka is None or kb is None else "MATCH" if ka == kb else "MISMATCH",
        reason="Comparator not recorded for both claims." if ka is None or kb is None else
        "Same comparator." if ka == kb else "Different comparators: effects relative to different baselines can "
                                            "legitimately differ in direction."))
    unknown = "UNKNOWN" in (a.study_design, b.study_design)
    same = a.study_design == b.study_design
    notes.append(ComparabilityNote(
        dimension="STUDY_DESIGN", claim_a_value=a.study_design, claim_b_value=b.study_design,
        status="UNKNOWN" if unknown else "MATCH" if same else "MISMATCH",
        reason="Study design not recorded for both claims." if unknown else "Same study design." if same else
        "Different designs (e.g. pooled vs single-site results) can legitimately differ."))
    ca, cb = a.context, b.context
    a_ids, a_unres = _crop_ids(ca.crops)
    b_ids, b_unres = _crop_ids(cb.crops)
    notes.append(_pair_sets("CROPS", set(a_ids), set(b_ids), _join(ca.crops) or None, _join(cb.crops) or None,
                            unresolved=a_unres | b_unres))
    wa = set() if ca.water_regime == "NOT_REPORTED" else {ca.water_regime}
    wb = set() if cb.water_regime == "NOT_REPORTED" else {cb.water_regime}
    water = _pair_sets("WATER_REGIME", wa, wb, ca.water_regime, cb.water_regime)
    if water.status == "MISMATCH" and "MIXED" in wa | wb:
        water = water.model_copy(update={"status": "PARTIAL",
                                         "reason": "One study covers several water regimes."})
    notes.append(water)
    notes.append(_pair_sets("SOIL_TEXTURE", set(ca.soil_texture_classes), set(cb.soil_texture_classes),
                            _join(ca.soil_texture_classes) or None, _join(cb.soil_texture_classes) or None))
    notes.append(_ph_pair(ca, cb))
    notes.append(_region_pair(ca, cb))
    notes.append(_pair_sets("CLIMATE", set(ca.climate_classes), set(cb.climate_classes),
                            _join(ca.climate_classes) or None, _join(cb.climate_classes) or None,
                            prefix_partial=True))
    return notes


def _ph_pair(a: StudyContext, b: StudyContext) -> ComparabilityNote:
    def show(c: StudyContext) -> str | None:
        return None if c.soil_ph_min is None or c.soil_ph_max is None else f"{c.soil_ph_min:g}-{c.soil_ph_max:g}"
    base = dict(dimension="SOIL_PH", claim_a_value=show(a), claim_b_value=show(b))
    if base["claim_a_value"] is None or base["claim_b_value"] is None:
        return ComparabilityNote(**base, status="UNKNOWN", reason="pH range not recorded for both claims.")
    if (a.soil_ph_min, a.soil_ph_max) == (b.soil_ph_min, b.soil_ph_max):
        return ComparabilityNote(**base, status="MATCH", reason="Same recorded pH range.")
    if a.soil_ph_min <= b.soil_ph_max and b.soil_ph_min <= a.soil_ph_max:
        return ComparabilityNote(**base, status="PARTIAL", reason="pH ranges overlap in part.")
    return ComparabilityNote(**base, status="MISMATCH", reason="pH ranges do not overlap.")


def _region_pair(a: StudyContext, b: StudyContext) -> ComparabilityNote:
    def show(c: StudyContext) -> str:
        return c.geographic_scope + (f"; countries: {_join(c.countries)}" if c.countries else "")
    if "GLOBAL" in (a.geographic_scope, b.geographic_scope):
        return ComparabilityNote(dimension="REGION", claim_a_value=show(a), claim_b_value=show(b), status="PARTIAL",
                                 reason="At least one study pools sites globally; site sets are not compared.")
    return _pair_sets("REGION", set(a.countries), set(b.countries), show(a), show(b))
