"""Scenario, priority and sensitivity analysis over the ABB-17 rotation comparison (ABB-18).

Method (docs/science/SCENARIOS_SENSITIVITY.md):
- What-if inputs replace the farmer's ordinal priorities and/or water availability in the
  farm profile, then the unchanged ABB-17 engine is run on the modified profile.
- Labelled climate scenarios are month-of-year flags. A ``HISTORICAL_EPISODE`` flags the
  months of an observed ABB-08 anomaly series (``GET /api/climate``) that pass a threshold
  chosen by the user. A ``HYPOTHETICAL`` scenario lists months the user assumes to be
  drier/wetter/hotter/cooler. Neither is a forecast.
- Exposure is the calendar overlap between flagged months and the months each crop is in
  the field by the farmer-declared windows. It is a count of months, not an impact.
- Strategies are ordered by a lexicographic rule over descriptive criteria, in the order of
  the farmer's priority ranks. There are no weights and no score; every step is listed.
- Sensitivity runs a base request and a changed request and reports which criteria,
  values, strategies and positions changed and which criterion decides each pair.

Everything is deterministic: the same request gives the same response, and each response
carries a SHA-256 of the canonical request.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import Field as PydanticField, model_validator

from ..climate import ClimateMonth
from ..farm_profile import (
    FarmerConstraints,
    FarmerPriority,
    FarmProfile,
    IrrigationAllowance,
    PriorityCriterion,
    WaterRegime,
)
from ..schemas import ContractModel, Resolution, SourceKind, VersionedContract
from .metrics import MIN_REFERENCE_YEARS
from .rotations import (
    MonthRange,
    RotationCompareRequest,
    RotationComparison,
    RotationStrategy,
    _Crop,
    _norm,
    _Registry,
    _slot_months,
    compare_rotations,
)

RULE_SET_VERSION = 'abb18-scenarios-0.1.0'
MAX_SCENARIOS = 6

Condition = Literal['DRIER', 'WETTER', 'HOTTER', 'COOLER']
Direction = Literal['MORE_FIRST', 'FEWER_FIRST', 'PASSES_FIRST']
ScenarioId = Annotated[str, PydanticField(pattern=r'^[a-z0-9][a-z0-9_-]{0,39}$')]

_CONDITION_TEXT = {'DRIER': 'drier', 'WETTER': 'wetter', 'HOTTER': 'hotter', 'COOLER': 'cooler'}
_OPPOSITE = {'DRIER': 'WETTER', 'WETTER': 'DRIER', 'HOTTER': 'COOLER', 'COOLER': 'HOTTER'}
# condition -> (ClimateMonth quality key, ClimateMonth anomaly field, unit, sign of a flagged anomaly)
_CONDITION_FIELD = {
    'DRIER': ('precipitation', 'precipitation_anomaly_mm', 'mm', -1),
    'WETTER': ('precipitation', 'precipitation_anomaly_mm', 'mm', 1),
    'HOTTER': ('max_temperature', 'max_temperature_anomaly_c', '°C', 1),
    'COOLER': ('max_temperature', 'max_temperature_anomaly_c', '°C', -1),
}


# ---------------------------------------------------------------- input contract

def _check_priorities(priorities: list[FarmerPriority]) -> None:
    ranks = [p.rank for p in priorities]
    if len(ranks) != len(set(ranks)):
        raise ValueError('two priorities share the same rank')
    criteria = [p.criterion for p in priorities if p.criterion != PriorityCriterion.OTHER]
    if len(criteria) != len(set(criteria)):
        raise ValueError('a priority criterion is listed twice')


class WaterAvailability(ContractModel):
    """What-if water availability. Replaces ``constraints.water_regime`` and ``irrigation_allowance``."""
    water_regime: WaterRegime
    irrigation_allowance: IrrigationAllowance | None = None

    @model_validator(mode='after')
    def allowance_matches_regime(self) -> WaterAvailability:
        if (self.water_regime == WaterRegime.RAINFED and self.irrigation_allowance is not None
                and self.irrigation_allowance.value > 0):
            raise ValueError('an irrigation allowance above zero contradicts a RAINFED water regime')
        return self


class AnomalyFlagRule(ContractModel):
    """Flags a month of an observed episode. The threshold is the user's choice, not an agronomic limit."""
    condition: Condition
    threshold: float = PydanticField(gt=0, le=2000, description='Absolute anomaly magnitude in `unit`.')
    unit: Literal['mm', '°C']

    @model_validator(mode='after')
    def unit_matches_condition(self) -> AnomalyFlagRule:
        expected = _CONDITION_FIELD[self.condition][2]
        if self.unit != expected:
            raise ValueError(f'{self.condition} thresholds are monthly anomalies in {expected}')
        return self


class ObservedClimateEpisode(ContractModel):
    """Keys copied unchanged from a ``GET /api/climate`` response (ABB-07/08).

    Coordinates and request parameters are deliberately not accepted, so they are never echoed."""
    source_kind: Literal[SourceKind.OBSERVED]
    dataset: str = PydanticField(min_length=1, max_length=200)
    data_sha256: str = PydanticField(pattern=r'^[0-9a-f]{64}$')
    retrieved_at: datetime
    event_year: int = PydanticField(ge=1981, le=2100)
    reference_start: int = PydanticField(ge=1981, le=2100)
    reference_end: int = PydanticField(ge=1981, le=2100)
    spatial_resolution: Resolution
    monthly: list[ClimateMonth] = PydanticField(min_length=1, max_length=12)
    limitations: list[str] = PydanticField(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def consistent_episode(self) -> ObservedClimateEpisode:
        months = [m.month for m in self.monthly]
        if len(months) != len(set(months)):
            raise ValueError('each month may appear only once in monthly')
        if self.reference_end < self.reference_start or self.reference_start <= self.event_year <= self.reference_end:
            raise ValueError('reference years must be ordered and exclude the event year')
        if self.reference_end - self.reference_start + 1 < MIN_REFERENCE_YEARS:
            raise ValueError(f'at least {MIN_REFERENCE_YEARS} reference years are required')
        return self


class HistoricalEpisodeScenario(ContractModel):
    scenario_type: Literal['HISTORICAL_EPISODE']
    id: ScenarioId
    label: str = PydanticField(min_length=1, max_length=120)
    episode: ObservedClimateEpisode
    flag_rules: list[AnomalyFlagRule] = PydanticField(min_length=1, max_length=4)

    @model_validator(mode='after')
    def unique_conditions(self) -> HistoricalEpisodeScenario:
        conditions = [r.condition for r in self.flag_rules]
        if len(conditions) != len(set(conditions)):
            raise ValueError('each condition may have only one flag rule')
        return self


class HypotheticalMonths(ContractModel):
    condition: Condition
    months: list[Annotated[int, PydanticField(ge=1, le=12)]] = PydanticField(min_length=1, max_length=12)

    @model_validator(mode='after')
    def unique_months(self) -> HypotheticalMonths:
        if len(self.months) != len(set(self.months)):
            raise ValueError('a month is listed twice')
        return self


class HypotheticalScenario(ContractModel):
    """User-defined assumption, e.g. "dry spring": months 3-5 drier than the reference. Not a forecast."""
    scenario_type: Literal['HYPOTHETICAL']
    id: ScenarioId
    label: str = PydanticField(min_length=1, max_length=120)
    description: str | None = PydanticField(default=None, max_length=1000)
    flags: list[HypotheticalMonths] = PydanticField(min_length=1, max_length=4)

    @model_validator(mode='after')
    def consistent_flags(self) -> HypotheticalScenario:
        by_condition = {f.condition: set(f.months) for f in self.flags}
        if len(by_condition) != len(self.flags):
            raise ValueError('each condition may be listed only once')
        for condition, months in by_condition.items():
            clash = months & by_condition.get(_OPPOSITE[condition], set())
            if clash:
                raise ValueError(f'month(s) {sorted(clash)} cannot be both {condition} and {_OPPOSITE[condition]}')
        return self


ClimateScenario = Annotated[Union[HistoricalEpisodeScenario, HypotheticalScenario],
                            PydanticField(discriminator='scenario_type')]


def _check_scenario_ids(scenarios: list) -> None:
    ids = [s.id for s in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError('scenario ids must be unique')


class ScenarioAnalysisRequest(VersionedContract):
    profile: FarmProfile
    horizon_years: int | None = PydanticField(default=None, ge=2, le=10)
    priorities_override: list[FarmerPriority] | None = PydanticField(
        default=None, max_length=20,
        description='What-if ordinal priorities (1 = most important). Replaces profile.priorities when given.')
    water_override: WaterAvailability | None = PydanticField(
        default=None, description='What-if water availability. Replaces the declared water regime and allowance.')
    climate_scenarios: list[ClimateScenario] = PydanticField(default_factory=list, max_length=MAX_SCENARIOS)

    @model_validator(mode='after')
    def consistent_what_if(self) -> ScenarioAnalysisRequest:
        if self.priorities_override is not None:
            _check_priorities(self.priorities_override)
        _check_scenario_ids(self.climate_scenarios)
        return self

    def effective_priorities(self) -> list[FarmerPriority]:
        chosen = self.priorities_override if self.priorities_override is not None else self.profile.priorities
        return sorted(chosen, key=lambda p: (p.rank, p.criterion.value))


class PrioritySwapChange(ContractModel):
    change_type: Literal['PRIORITY_SWAP']
    criterion_a: PriorityCriterion
    criterion_b: PriorityCriterion


class PrioritiesChange(ContractModel):
    change_type: Literal['PRIORITIES']
    priorities: list[FarmerPriority] = PydanticField(max_length=20)

    @model_validator(mode='after')
    def consistent(self) -> PrioritiesChange:
        _check_priorities(self.priorities)
        return self


class WaterChange(ContractModel):
    change_type: Literal['WATER']
    water: WaterAvailability


class ScenariosChange(ContractModel):
    change_type: Literal['CLIMATE_SCENARIOS']
    climate_scenarios: list[ClimateScenario] = PydanticField(max_length=MAX_SCENARIOS)

    @model_validator(mode='after')
    def unique_ids(self) -> ScenariosChange:
        _check_scenario_ids(self.climate_scenarios)
        return self


SensitivityChange = Annotated[Union[PrioritySwapChange, PrioritiesChange, WaterChange, ScenariosChange],
                              PydanticField(discriminator='change_type')]


class SensitivityRequest(VersionedContract):
    base: ScenarioAnalysisRequest
    change: SensitivityChange

    @model_validator(mode='after')
    def swap_is_possible(self) -> SensitivityRequest:
        if isinstance(self.change, PrioritySwapChange):
            a, b = self.change.criterion_a, self.change.criterion_b
            if a == b:
                raise ValueError('a priority swap needs two different criteria')
            if PriorityCriterion.OTHER in {a, b}:
                raise ValueError('OTHER cannot be swapped (it may appear more than once)')
            ranked = {p.criterion for p in self.base.effective_priorities()}
            missing = [c.value for c in (a, b) if c not in ranked]
            if missing:
                raise ValueError(f'not among the base priorities: {", ".join(missing)}')
        return self


# ---------------------------------------------------------------- output contract

class AppliedInputs(ContractModel):
    horizon_years: int | None
    priorities: list[FarmerPriority]
    priorities_from: Literal['PROFILE', 'OVERRIDE']
    water_regime: WaterRegime
    irrigation_allowance: IrrigationAllowance | None
    water_from: Literal['PROFILE', 'OVERRIDE']
    scenario_ids: list[str]


class EpisodeProvenance(ContractModel):
    dataset: str
    data_sha256: str
    retrieved_at: datetime
    event_year: int
    reference_start: int
    reference_end: int
    spatial_resolution: Resolution


class FlaggedMonth(ContractModel):
    month: int = PydanticField(ge=1, le=12)
    conditions: list[Condition]
    basis: list[str]
    quality_flags: list[str]


class NotEvaluableMonth(ContractModel):
    month: int = PydanticField(ge=1, le=12)
    reason: str


class ScenarioSummary(ContractModel):
    id: str
    label: str
    scenario_type: Literal['HISTORICAL_EPISODE', 'HYPOTHETICAL']
    scenario_label: Literal['HISTORICAL_EPISODE_OBSERVED', 'HYPOTHETICAL_SCENARIO']
    source_kind: Literal[SourceKind.OBSERVED, SourceKind.MODEL_SCENARIO]
    is_forecast: Literal[False] = False
    statement: str
    provenance: EpisodeProvenance | None
    flag_rules: list[AnomalyFlagRule]
    flagged_months: list[FlaggedMonth]
    not_evaluable_months: list[NotEvaluableMonth]
    limitations: list[str]


class FlaggedMonthInField(ContractModel):
    month: int = PydanticField(ge=1, le=12)
    conditions: list[Condition]
    in_field: Literal['CERTAIN', 'POSSIBLE'] = PydanticField(
        description='CERTAIN: inside latest sowing to earliest harvest; POSSIBLE: only inside the widest window.')


class CycleYearExposure(ContractModel):
    cycle_year: int = PydanticField(ge=1)
    crop_label: str | None
    status: Literal['EVALUATED', 'FALLOW', 'NOT_EVALUABLE']
    months_in_field_certain: list[int]
    months_in_field_possible: list[int]
    flagged_months_in_field: list[FlaggedMonthInField]
    not_evaluable_months_in_field: list[int]
    reason: str | None = None


class CountRange(ContractModel):
    min: int = PydanticField(ge=0)
    max: int = PydanticField(ge=0)
    of: int = PydanticField(ge=1)
    unit: Literal['cycle years'] = 'cycle years'


class StrategyExposure(ContractModel):
    strategy_id: str
    strategy_kind: str
    scenario_id: str
    basis: Literal['CALENDAR_OVERLAP_NOT_IMPACT'] = 'CALENDAR_OVERLAP_NOT_IMPACT'
    status: Literal['EVALUATED', 'PARTIAL', 'NOT_EVALUABLE']
    by_cycle_year: list[CycleYearExposure]
    flagged_months_in_field_per_year: MonthRange | None
    cycle_years_with_flagged_months: CountRange | None
    explanation: str


class OrderingCriterion(ContractModel):
    step: int = PydanticField(ge=0)
    criterion_id: str
    priority_criterion: PriorityCriterion | None
    rank: int | None
    direction: Direction
    scenario_id: str | None = None
    description: str
    unit: str | None


class CriterionValue(ContractModel):
    strategy_id: str
    value: float | str | None


class OrderingStep(ContractModel):
    step: int = PydanticField(ge=0)
    criterion_id: str
    rank: int | None
    values: list[CriterionValue]
    groups_before: list[list[str]]
    groups_after: list[list[str]]
    explanation: str


class CriterionNotUsed(ContractModel):
    criterion: PriorityCriterion
    rank: int
    reason: str


class OrderedPosition(ContractModel):
    strategy_id: str
    strategy_kind: str
    position: int = PydanticField(ge=1)
    tied_with: list[str]


class AdjacentDecision(ContractModel):
    first_strategy_id: str
    second_strategy_id: str
    decided_at_step: int | None
    decided_by: str | None
    explanation: str


class Ordering(ContractModel):
    rule: Literal['LEXICOGRAPHIC_BY_FARMER_RANK'] = 'LEXICOGRAPHIC_BY_FARMER_RANK'
    description: str
    is_recommendation: Literal[False] = False
    criteria: list[OrderingCriterion]
    criteria_not_used: list[CriterionNotUsed]
    steps: list[OrderingStep]
    positions: list[OrderedPosition]
    adjacent_decisions: list[AdjacentDecision]
    notes: list[str]


class CriterionComparison(ContractModel):
    criterion_id: str
    priority_criterion: PriorityCriterion
    rank: int | None
    direction: Direction
    unit: str
    value: float | None
    most_favourable_value: float | None
    most_favourable_strategy_ids: list[str]
    relation_to_most_favourable: Literal['MOST_FAVOURABLE', 'GIVES_UP', 'NOT_EVALUABLE']
    relation_to_current: Literal['REFERENCE', 'MORE', 'LESS', 'SAME', 'NOT_EVALUABLE']


class StrategyTradeOff(ContractModel):
    strategy_id: str
    strategy_kind: str
    criteria: list[CriterionComparison]
    gives_up: list[str]
    gains_vs_current: list[str]
    other_differences_vs_current: list[str]


class SeparationNote(ContractModel):
    part: str
    kind: Literal['OBSERVED', 'MODEL_SCENARIO', 'HYPOTHETICAL_SCENARIO', 'FARMER_REPORTED',
                  'VALIDATED_FIELD_RESULT']
    present: bool
    meaning: str


class ScenarioAnalysis(VersionedContract):
    status: Literal['ANALYSED', 'NOT_ANALYSED']
    source_kind: Literal[SourceKind.MODEL_SCENARIO] = SourceKind.MODEL_SCENARIO
    input_sha256: str
    applied_inputs: AppliedInputs
    scenarios: list[ScenarioSummary]
    comparison: RotationComparison
    exposure: list[StrategyExposure]
    ordering: Ordering | None
    trade_offs: list[StrategyTradeOff]
    separation: list[SeparationNote]
    explanation: list[str]
    rule_set_version: str = RULE_SET_VERSION
    limitations: list[str]
    verified_impact: None = None


class PriorityRankChange(ContractModel):
    criterion: PriorityCriterion
    rank_before: int | None
    rank_after: int | None


class ValueChange(ContractModel):
    strategy_kind: str
    before: float | str | None
    after: float | str | None


class CriterionChange(ContractModel):
    criterion_id: str
    step_before: int | None
    step_after: int | None
    change: Literal['ADDED', 'REMOVED', 'MOVED_EARLIER', 'MOVED_LATER', 'SAME_STEP']
    values_changed: list[ValueChange]
    explanation: str


class ScreeningChange(ContractModel):
    crop_label: str
    status_before: str | None
    status_after: str | None
    reasons_before: list[str]
    reasons_after: list[str]


class StrategyChange(ContractModel):
    strategy_kind: str
    change: Literal['SAME_SEQUENCE', 'DIFFERENT_SEQUENCE', 'ONLY_IN_BASE', 'ONLY_IN_VARIANT']
    years_before: list[list[str]] | None
    years_after: list[list[str]] | None
    constraint_changes: list[str]
    explanation: str


class PositionChange(ContractModel):
    strategy_kind: str
    position_before: int | None
    position_after: int | None
    movement: Literal['UP', 'DOWN', 'SAME', 'ADDED', 'REMOVED']
    explanation: str


PairRelation = Literal['FIRST_BEFORE_SECOND', 'TIED', 'SECOND_BEFORE_FIRST']


class PairChange(ContractModel):
    first_kind: str
    second_kind: str
    before: PairRelation
    after: PairRelation
    order_changed: bool
    decided_by_before: str | None
    decided_by_after: str | None
    explanation: str


class ExposureChange(ContractModel):
    strategy_kind: str
    scenario_id: str
    status_before: str | None
    status_after: str | None
    before: MonthRange | None
    after: MonthRange | None


class SensitivityAnalysis(VersionedContract):
    status: Literal['COMPARED', 'NOT_COMPARABLE']
    source_kind: Literal[SourceKind.MODEL_SCENARIO] = SourceKind.MODEL_SCENARIO
    request_sha256: str
    base_input_sha256: str
    variant_input_sha256: str
    change_type: Literal['PRIORITY_SWAP', 'PRIORITIES', 'WATER', 'CLIMATE_SCENARIOS']
    change_summary: list[str]
    priority_changes: list[PriorityRankChange]
    criteria_changes: list[CriterionChange]
    screening_changes: list[ScreeningChange]
    strategy_changes: list[StrategyChange]
    position_changes: list[PositionChange]
    pair_changes: list[PairChange]
    exposure_changes: list[ExposureChange]
    explanation: list[str]
    base_ordering: Ordering | None
    variant_ordering: Ordering | None
    rule_set_version: str = RULE_SET_VERSION
    limitations: list[str]
    verified_impact: None = None


LIMITATIONS = [
    'What-if analysis of declared inputs with the ABB-17 rules; not an agronomic model, a forecast or a '
    'recommendation. verified_impact is null.',
    'Climate scenarios are month-of-year flags. Exposure counts months a crop is in the field by the farmer-'
    'declared windows; it does not estimate damage, yield, water use or any probability.',
    'Historical episodes replay an observed year at a regional grid cell; they say nothing about how likely '
    'the episode is to recur.',
    'For crops in the field across the year end, the flagged months of an episode come from one calendar '
    'year and are overlaid by month of year, not as one continuous season.',
    'Flag thresholds are the user\'s choice; they are not agronomic or statistical thresholds.',
    'The ordering is lexicographic over descriptive criteria in the order of the farmer\'s ranks; it has no '
    'weights and no score, and it is not a judgement that one strategy is better.',
    'Crop sensitivity by growth stage, irrigation buffering, soil water and management are not evaluated.',
]

SEPARATION = {
    'comparison': ('MODEL_SCENARIO', 'Rule-based strategies from declared inputs (ABB-17); not observed outcomes.'),
    'historical': ('OBSERVED', 'Observed regional monthly anomalies passed in from /api/climate, with provenance.'),
    'hypothetical': ('HYPOTHETICAL_SCENARIO', 'User-defined assumption about months; not observed, not a forecast.'),
    'inputs': ('FARMER_REPORTED', 'Profile, calendar windows and priorities as declared by the farmer.'),
    'validated': ('VALIDATED_FIELD_RESULT', 'No validated field result exists for any strategy; '
                                            'verified_impact is null.'),
}


# ---------------------------------------------------------------- helpers

def canonical_sha256(model: ContractModel) -> str:
    """SHA-256 of the request as canonical JSON (defaults included, keys sorted)."""
    text = json.dumps(model.model_dump(mode='json'), sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _fmt(value: float | str | None) -> str:
    if value is None:
        return 'not evaluable'
    return value if isinstance(value, str) else f'{value:g}'


def _span(low: float, high: float) -> str:
    return f'{low:g}' if low == high else f'{low:g}–{high:g}'


def _effective_profile(request: ScenarioAnalysisRequest) -> FarmProfile:
    update: dict = {}
    if request.priorities_override is not None:
        update['priorities'] = list(request.priorities_override)
    if request.water_override is not None:
        constraints = request.profile.constraints or FarmerConstraints()
        update['constraints'] = constraints.model_copy(update={
            'water_regime': request.water_override.water_regime,
            'irrigation_allowance': request.water_override.irrigation_allowance})
    return request.profile.model_copy(update=update) if update else request.profile


def _applied_inputs(request: ScenarioAnalysisRequest, profile: FarmProfile) -> AppliedInputs:
    c = profile.constraints
    return AppliedInputs(
        horizon_years=request.horizon_years, priorities=request.effective_priorities(),
        priorities_from='OVERRIDE' if request.priorities_override is not None else 'PROFILE',
        water_regime=c.water_regime if c else WaterRegime.UNKNOWN,
        irrigation_allowance=c.irrigation_allowance if c else None,
        water_from='OVERRIDE' if request.water_override is not None else 'PROFILE',
        scenario_ids=[s.id for s in request.climate_scenarios])


# ---------------------------------------------------------------- scenarios

@dataclass
class _Flags:
    flagged: dict[int, list[str]]  # month -> conditions
    not_evaluable: set[int]


def _historical(s: HistoricalEpisodeScenario) -> tuple[ScenarioSummary, _Flags]:
    ep = s.episode
    rows = {m.month: m for m in ep.monthly}
    flagged: list[FlaggedMonth] = []
    not_evaluable: list[NotEvaluableMonth] = []
    for month in range(1, 13):
        row = rows.get(month)
        if row is None:
            not_evaluable.append(NotEvaluableMonth(month=month, reason='Month not supplied in the episode data.'))
            continue
        conditions, basis, quality, missing = [], [], set(), []
        for rule in sorted(s.flag_rules, key=lambda r: r.condition):
            q_key, field, unit, sign = _CONDITION_FIELD[rule.condition]
            value = getattr(row, field)
            q = getattr(row.quality, q_key)
            if value is None:
                missing.append(f'{q_key.replace("_", " ")} anomaly not available'
                               + (f' ({q.anomaly_reason})' if q.anomaly_reason else ''))
                continue
            if sign * value >= rule.threshold:
                conditions.append(rule.condition)
                op = '≤' if sign < 0 else '≥'
                basis.append(f'{q_key.replace("_", " ").capitalize()} anomaly {value:g} {unit} {op} '
                             f'{sign * rule.threshold:g} {unit} ({rule.condition} rule).')
                quality.update(q.flags)
        if conditions:
            flagged.append(FlaggedMonth(month=month, conditions=conditions, basis=basis, quality_flags=sorted(quality)))
        elif missing:
            not_evaluable.append(NotEvaluableMonth(month=month, reason='; '.join(missing) + '.'))
    summary = ScenarioSummary(
        id=s.id, label=s.label, scenario_type='HISTORICAL_EPISODE', scenario_label='HISTORICAL_EPISODE_OBSERVED',
        source_kind=SourceKind.OBSERVED,
        statement=(f'Replay of observed monthly anomalies for {ep.event_year} against reference years '
                   f'{ep.reference_start}–{ep.reference_end} ({ep.dataset}), flagged with the thresholds chosen by the '
                   'user. Historical scenario replay is not a forecast of future weather.'),
        provenance=EpisodeProvenance(dataset=ep.dataset, data_sha256=ep.data_sha256, retrieved_at=ep.retrieved_at,
                                     event_year=ep.event_year, reference_start=ep.reference_start,
                                     reference_end=ep.reference_end, spatial_resolution=ep.spatial_resolution),
        flag_rules=list(s.flag_rules), flagged_months=flagged, not_evaluable_months=not_evaluable,
        limitations=['Regional grid-cell observation, not a field measurement.',
                     'Flag thresholds are chosen by the user; they are not agronomic or statistical thresholds.',
                     'Months without an anomaly (incomplete data or insufficient reference years) are not '
                     'evaluable and are never treated as unflagged.',
                     *ep.limitations])
    return summary, _Flags({f.month: list(f.conditions) for f in flagged}, {n.month for n in not_evaluable})


def _hypothetical(s: HypotheticalScenario) -> tuple[ScenarioSummary, _Flags]:
    by_month: dict[int, list[str]] = {}
    for flag in sorted(s.flags, key=lambda f: f.condition):
        for month in flag.months:
            by_month.setdefault(month, []).append(flag.condition)
    flagged = [FlaggedMonth(month=m, conditions=c,
                            basis=[f'User assumption: {_CONDITION_TEXT[x]} than the reference.' for x in c],
                            quality_flags=[])
               for m, c in sorted(by_month.items())]
    parts = [f'months {", ".join(map(str, sorted(f.months)))} {_CONDITION_TEXT[f.condition]}'
             for f in sorted(s.flags, key=lambda f: f.condition)]
    summary = ScenarioSummary(
        id=s.id, label=s.label, scenario_type='HYPOTHETICAL', scenario_label='HYPOTHETICAL_SCENARIO',
        source_kind=SourceKind.MODEL_SCENARIO,
        statement=(f'User-defined hypothetical scenario: {"; ".join(parts)} than the reference. Not observed, not a '
                   'forecast and not a probability.' + (f' Description: {s.description}' if s.description else '')),
        provenance=None, flag_rules=[], flagged_months=flagged, not_evaluable_months=[],
        limitations=['Qualitative month flags without magnitude; no weather data is generated.'])
    return summary, _Flags(by_month, set())


# ---------------------------------------------------------------- calendar exposure

def _lookup(reg: _Registry, code: str | None, label: str) -> _Crop | None:
    return reg.crops.get(code) if code else reg.crops.get(f'label:{_norm(label)}')


def _months_in_field(crop: _Crop) -> tuple[list[int], list[int]]:
    s_start, s_end, h_start, h_end = _slot_months(crop.window, 0)
    certain = sorted({m % 12 + 1 for m in range(s_end, h_start + 1)})
    possible = sorted({m % 12 + 1 for m in range(s_start, h_end + 1)})
    return certain, possible


def _exposure(strategy: RotationStrategy, reg: _Registry, scenario: ScenarioSummary, flags: _Flags) -> StrategyExposure:
    rows: list[CycleYearExposure] = []
    certain_total = possible_total = years_min = years_max = 0
    evaluated = complete = 0
    touches_unknown = False
    for year, slot in enumerate(strategy.cycle, start=1):
        empty = dict(months_in_field_certain=[], months_in_field_possible=[], flagged_months_in_field=[],
                     not_evaluable_months_in_field=[])
        if not slot:
            rows.append(CycleYearExposure(cycle_year=year, crop_label=None, status='FALLOW', **empty))
            complete += 1
            continue
        label = ' + '.join(c.crop_label for c in slot)
        if len(slot) > 1:
            rows.append(CycleYearExposure(cycle_year=year, crop_label=label, status='NOT_EVALUABLE', **empty,
                                          reason='More than one main crop in a year (double cropping) is not modelled.'))
            continue
        crop = _lookup(reg, slot[0].crop_code, slot[0].crop_label)
        if crop is None or not crop.has_full_window:
            rows.append(CycleYearExposure(cycle_year=year, crop_label=label, status='NOT_EVALUABLE', **empty,
                                          reason='No complete farmer-declared sowing and harvest window; months in '
                                                 'the field are not invented.'))
            continue
        certain, possible = _months_in_field(crop)
        in_field = [FlaggedMonthInField(month=m, conditions=flags.flagged[m],
                                        in_field='CERTAIN' if m in certain else 'POSSIBLE')
                    for m in possible if m in flags.flagged]
        unknown = [m for m in possible if m in flags.not_evaluable]
        touches_unknown = touches_unknown or bool(unknown)
        n_certain = sum(1 for f in in_field if f.in_field == 'CERTAIN')
        certain_total += n_certain
        possible_total += len(in_field)
        years_min += n_certain > 0
        years_max += bool(in_field)
        evaluated += 1
        complete += 1
        rows.append(CycleYearExposure(cycle_year=year, crop_label=label, status='EVALUATED',
                                      months_in_field_certain=certain, months_in_field_possible=possible,
                                      flagged_months_in_field=in_field, not_evaluable_months_in_field=unknown))
    n = len(strategy.cycle)
    base = dict(strategy_id=strategy.id, strategy_kind=strategy.strategy_kind, scenario_id=scenario.id,
                by_cycle_year=rows)
    if evaluated == 0 or len(flags.not_evaluable) == 12:
        return StrategyExposure(status='NOT_EVALUABLE', flagged_months_in_field_per_year=None,
                                cycle_years_with_flagged_months=None, **base,
                                explanation=f'Exposure under "{scenario.label}" cannot be evaluated: no crop of the '
                                            'cycle has a complete declared window or no month of the scenario is '
                                            'evaluable.')
    if complete < n or touches_unknown:
        why = []
        if complete < n:
            why.append('a cycle year has no complete declared window or more than one main crop')
        if touches_unknown:
            why.append('some months in the field have no evaluable anomaly')
        return StrategyExposure(status='PARTIAL', flagged_months_in_field_per_year=None,
                                cycle_years_with_flagged_months=None, **base,
                                explanation=f'Exposure under "{scenario.label}" is only partly evaluable ('
                                            f'{"; ".join(why)}); per-year counts are not given because they would '
                                            'understate exposure. See by_cycle_year.')
    per_year = MonthRange(min=round(certain_total / n, 1), max=round(possible_total / n, 1), unit='months per year')
    return StrategyExposure(
        status='EVALUATED', flagged_months_in_field_per_year=per_year,
        cycle_years_with_flagged_months=CountRange(min=years_min, max=years_max, of=n), **base,
        explanation=(f'Under "{scenario.label}", {_span(per_year.min, per_year.max)} flagged months per year fall '
                     f'inside the declared crop windows; {_span(years_min, years_max)} of {n} cycle years have at least '
                     'one. '
                     'Calendar overlap only: crop sensitivity by stage, irrigation and soil are not evaluated.'))


# ---------------------------------------------------------------- criteria and ordering

@dataclass(frozen=True)
class _Criterion:
    id: str
    priority: PriorityCriterion
    direction: Direction
    description: str
    unit: str
    scenario_id: str | None = None


_SCREEN_TIER = {'PASSES_DECLARED_CONSTRAINTS': 0, 'NOT_FULLY_EVALUABLE': 1, 'CONFLICTS_WITH_DECLARED_CONSTRAINTS': 2}
_NOT_USED_REASON = {
    PriorityCriterion.WATER_USE: 'No crop water-demand data or water model; the water regime is shown as '
                                 'constraint checks (WATER_REGIME) instead.',
    PriorityCriterion.INCOME_STABILITY: 'No prices or yields; market status per crop is shown in the comparison.',
    PriorityCriterion.WORKLOAD: 'No labour data; crops new to the farm are shown in the comparison.',
    PriorityCriterion.INPUT_COSTS: 'No cost data.',
    PriorityCriterion.OTHER: 'Free-text priority; it has no descriptive criterion.',
}


def _all_criteria(scenarios: list[ScenarioSummary]) -> list[_Criterion]:
    out = [
        _Criterion('SOIL_COVER_MONTHS', PriorityCriterion.SOIL_COVER, 'MORE_FIRST',
                   'Months per year with a crop in the field by the declared windows (comparison.months_with_crop.min;'
                   ' calendar-based potential cover)', 'months per year'),
        _Criterion('BOTANICAL_FAMILIES', PriorityCriterion.CROP_DIVERSITY, 'MORE_FIRST',
                   'Botanical families per cycle (comparison.distinct_families)', 'families'),
    ]
    for s in scenarios:
        out.append(_Criterion(
            f'SCENARIO_EXPOSURE:{s.id}', PriorityCriterion.RISK_REDUCTION, 'FEWER_FIRST',
            f'Proxy for risk reduction: flagged months per year inside the declared crop windows under "{s.label}" '
            '(flagged_months_in_field_per_year.min; calendar exposure, not a risk estimate)', 'months per year',
            scenario_id=s.id))
    return out


def _value(c: _Criterion, s: RotationStrategy, exposure: dict[tuple[str, str], StrategyExposure]) -> float | None:
    if c.id == 'SOIL_COVER_MONTHS':
        return s.comparison.months_with_crop.min if s.comparison.months_with_crop else None
    if c.id == 'BOTANICAL_FAMILIES':
        if any(ref.botanical_family is None for slot in s.cycle for ref in slot):
            return None
        return float(s.comparison.distinct_families)
    e = exposure.get((s.id, c.scenario_id))
    return e.flagged_months_in_field_per_year.min if e and e.flagged_months_in_field_per_year else None


def _sort_part(value: float | None, direction: Direction) -> tuple:
    if value is None:
        return (1, 0.0)
    return (0, -value if direction == 'MORE_FIRST' else value)


@dataclass
class _Ordered:
    """Internal ordering state, also used to explain pairwise decisions in sensitivity analysis."""
    strategies: dict[str, RotationStrategy]
    criteria: list[_Criterion]           # ordering criteria (step 1..n)
    ranks: dict[str, int]                # criterion id -> farmer rank
    values: dict[str, dict[str, float | None]]  # criterion id -> strategy id -> value
    keys: dict[str, tuple]
    order: list[str]
    positions: dict[str, int]

    def step_label(self, step: int) -> str:
        return 'DECLARED_CONSTRAINTS' if step == 0 else self.criteria[step - 1].id

    def decided_at(self, a: str, b: str) -> int | None:
        for i, (x, y) in enumerate(zip(self.keys[a], self.keys[b])):
            if x != y:
                return i
        return None

    def relation(self, a: str, b: str) -> int:
        """-1 if a comes before b, 0 if tied, 1 if b comes before a."""
        ka, kb = self.keys[a], self.keys[b]
        return -1 if ka < kb else (1 if kb < ka else 0)

    def pair_sentence(self, a: str, b: str) -> str:
        sa, sb = self.strategies[a], self.strategies[b]
        step = self.decided_at(a, b)
        if step is None:
            return f'{sa.strategy_kind} and {sb.strategy_kind} are tied on every ordering step.'
        first, second = (sa, sb) if self.relation(a, b) < 0 else (sb, sa)
        if step == 0:
            return (f'{first.strategy_kind} comes first because its screening result is '
                    f'{first.screening_result} and {second.strategy_kind} is {second.screening_result} '
                    '(declared constraints are applied before priorities).')
        c = self.criteria[step - 1]
        v1, v2 = self.values[c.id][first.id], self.values[c.id][second.id]
        how = 'more' if c.direction == 'MORE_FIRST' else 'fewer'
        if v2 is None:
            why = f'{c.id} cannot be evaluated for {second.strategy_kind} ({_fmt(v1)} {c.unit} for {first.strategy_kind})'
        else:
            why = f'{first.strategy_kind} has {_fmt(v1)} and {second.strategy_kind} {_fmt(v2)} {c.unit}'
        return (f'{first.strategy_kind} comes before {second.strategy_kind} at step {step}, {c.id} '
                f'(priority {c.priority.value}, rank {self.ranks[c.id]}; {how} first): {why}.')


def _groups(ids: list[str], keys: dict[str, tuple], depth: int) -> list[list[str]]:
    out: list[list[str]] = []
    for sid in ids:
        if out and keys[out[-1][0]][:depth] == keys[sid][:depth]:
            out[-1].append(sid)
        else:
            out.append([sid])
    return out


def _order(strategies: list[RotationStrategy], priorities: list[FarmerPriority], scenarios: list[ScenarioSummary],
           exposure: dict[tuple[str, str], StrategyExposure]) -> tuple[Ordering, _Ordered]:
    available = _all_criteria(scenarios)
    used: list[_Criterion] = []
    ranks: dict[str, int] = {}
    not_used: list[CriterionNotUsed] = []
    for p in priorities:
        matches = [c for c in available if c.priority == p.criterion]
        if p.criterion == PriorityCriterion.RISK_REDUCTION and not matches:
            not_used.append(CriterionNotUsed(criterion=p.criterion, rank=p.rank,
                                             reason='No climate scenario supplied; there is no risk model, and the '
                                                    'only descriptive proxy is calendar exposure to a scenario.'))
        elif not matches:
            not_used.append(CriterionNotUsed(criterion=p.criterion, rank=p.rank,
                                             reason=_NOT_USED_REASON.get(p.criterion, 'No descriptive criterion.')))
        for c in matches:
            used.append(c)
            ranks[c.id] = p.rank
    values = {c.id: {s.id: _value(c, s, exposure) for s in strategies} for c in available}
    index = {s.id: i for i, s in enumerate(strategies)}
    keys = {s.id: (_SCREEN_TIER[s.screening_result],) + tuple(_sort_part(values[c.id][s.id], c.direction) for c in used)
            for s in strategies}
    order = sorted(keys, key=lambda sid: (keys[sid], index[sid]))
    final_groups = _groups(order, keys, len(used) + 1)
    positions = {sid: g for g, group in enumerate(final_groups, start=1) for sid in group}
    by_id = {s.id: s for s in strategies}
    state = _Ordered(strategies=by_id, criteria=used, ranks=ranks, values=values, keys=keys, order=order,
                     positions=positions)

    criteria_out = [OrderingCriterion(step=0, criterion_id='DECLARED_CONSTRAINTS', priority_criterion=None, rank=None,
                                      direction='PASSES_FIRST', unit=None,
                                      description='screening_result: PASSES_DECLARED_CONSTRAINTS, then '
                                                  'NOT_FULLY_EVALUABLE, then CONFLICTS_WITH_DECLARED_CONSTRAINTS.')]
    criteria_out += [OrderingCriterion(step=i, criterion_id=c.id, priority_criterion=c.priority, rank=ranks[c.id],
                                       direction=c.direction, scenario_id=c.scenario_id, description=c.description,
                                       unit=c.unit)
                     for i, c in enumerate(used, start=1)]
    steps = []
    for step in range(len(used) + 1):
        before = _groups(order, keys, step)
        after = _groups(order, keys, step + 1)
        if step == 0:
            vals = [CriterionValue(strategy_id=s.id, value=s.screening_result) for s in strategies]
            label, rank, unit = 'DECLARED_CONSTRAINTS', None, ''
        else:
            c = used[step - 1]
            vals = [CriterionValue(strategy_id=s.id, value=values[c.id][s.id]) for s in strategies]
            label, rank, unit = c.id, ranks[c.id], c.unit
        if before == after:
            text = (f'Step {step} ({label}): no tie left to split.' if all(len(g) == 1 for g in before)
                    else f'Step {step} ({label}): tied strategies have equal values; nothing is separated.')
        else:
            split = [f'[{", ".join(g)}] → ' + ' then '.join(f'[{", ".join(h)}]' for h in after if set(h) <= set(g))
                     for g in before if sum(1 for h in after if set(h) <= set(g)) > 1]
            text = f'Step {step} ({label}{"" if rank is None else f", rank {rank}"}) separates ' + '; '.join(split) + '.'
            if step > 0 and any(v.value is None for v in vals):
                text += f' Strategies where {label} is not evaluable are placed after those where it is.'
        steps.append(OrderingStep(step=step, criterion_id=label, rank=rank, values=vals, groups_before=before,
                                  groups_after=after, explanation=text))
    adjacent = []
    for a, b in zip(order, order[1:]):
        step = state.decided_at(a, b)
        adjacent.append(AdjacentDecision(first_strategy_id=a, second_strategy_id=b, decided_at_step=step,
                                         decided_by=None if step is None else state.step_label(step),
                                         explanation=(state.pair_sentence(a, b) if step is not None else
                                                      f'{by_id[a].strategy_kind} and {by_id[b].strategy_kind} are tied '
                                                      'on every ordering step; they are listed in input order, which '
                                                      'is not a preference.')))
    notes = ['Lexicographic rule: a later criterion only separates strategies that are tied on every earlier one. '
             'No weights, scores or sums across criteria are used.',
             'Declared constraints are applied first; then each ranked priority with a descriptive criterion, from '
             'rank 1 down. Ties that remain share a position.']
    if not used:
        notes.append('No ranked priority has a descriptive criterion; only declared constraints separate strategies.')
    ordering = Ordering(
        description=('Strategies ordered by declared constraints, then by the farmer\'s ranked priorities applied one '
                     'at a time to descriptive criteria. This shows what the stated priorities imply for the compared '
                     'strategies; it is not a recommendation or a prediction.'),
        criteria=criteria_out, criteria_not_used=not_used, steps=steps,
        positions=[OrderedPosition(strategy_id=sid, strategy_kind=by_id[sid].strategy_kind, position=positions[sid],
                                   tied_with=[o for o in order if o != sid and positions[o] == positions[sid]])
                   for sid in order],
        adjacent_decisions=adjacent, notes=notes)
    return ordering, state


# ---------------------------------------------------------------- trade-offs

def _favourable(c: _Criterion, a: float, b: float) -> bool:
    return a > b if c.direction == 'MORE_FIRST' else a < b


def _trade_offs(strategies: list[RotationStrategy], state: _Ordered, scenarios: list[ScenarioSummary]) -> list[StrategyTradeOff]:
    criteria = _all_criteria(scenarios)
    current = strategies[0] if strategies and strategies[0].is_current else None
    out = []
    for s in strategies:
        rows, gives_up, gains = [], [], []
        for c in criteria:
            vals = state.values[c.id]
            known = [v for v in vals.values() if v is not None]
            best = (max(known) if c.direction == 'MORE_FIRST' else min(known)) if known else None
            best_ids = [sid for sid, v in vals.items() if v is not None and v == best]
            value = vals[s.id]
            if value is None:
                to_best = 'NOT_EVALUABLE'
            elif value == best:
                to_best = 'MOST_FAVOURABLE'
            else:
                to_best = 'GIVES_UP'
                gives_up.append(f'{c.id}: {_fmt(value)} {c.unit} where {", ".join(state.strategies[i].strategy_kind for i in best_ids)} '
                                f'{"has" if len(best_ids) == 1 else "have"} {_fmt(best)} '
                                f'({"more" if c.direction == "MORE_FIRST" else "fewer"} is more favourable for '
                                f'{c.priority.value}).')
            ref = vals[current.id] if current is not None else None
            if current is None:
                to_current = 'NOT_EVALUABLE'
            elif s.id == current.id:
                to_current = 'REFERENCE'
            elif value is None or ref is None:
                to_current = 'NOT_EVALUABLE'
            else:
                to_current = 'MORE' if value > ref else ('LESS' if value < ref else 'SAME')
                if _favourable(c, value, ref):
                    gains.append(f'{c.id}: {_fmt(value)} {c.unit} instead of {_fmt(ref)} in the current rotation '
                                 f'({c.priority.value}).')
            rows.append(CriterionComparison(
                criterion_id=c.id, priority_criterion=c.priority, rank=state.ranks.get(c.id), direction=c.direction,
                unit=c.unit, value=value, most_favourable_value=best, most_favourable_strategy_ids=best_ids,
                relation_to_most_favourable=to_best, relation_to_current=to_current))
        out.append(StrategyTradeOff(strategy_id=s.id, strategy_kind=s.strategy_kind, criteria=rows, gives_up=gives_up,
                                    gains_vs_current=gains,
                                    other_differences_vs_current=_other_differences(s, current)))
    return out


def _other_differences(s: RotationStrategy, current: RotationStrategy | None) -> list[str]:
    """Neutral facts that differ from the current rotation (no direction is assumed)."""
    if current is None or s.id == current.id:
        return []
    a, b = s.comparison, current.comparison
    out = []
    if a.crops_new_to_farm:
        out.append(f'Crops new to the farm: {", ".join(a.crops_new_to_farm)}.')
    dropped = sorted({ref.crop_label for slot in current.cycle for ref in slot}
                     - {ref.crop_label for slot in s.cycle for ref in slot})
    if dropped:
        out.append(f'Drops: {", ".join(dropped)}.')
    if a.includes_legume != b.includes_legume:
        out.append('Includes a legume; the current rotation does not.' if a.includes_legume
                   else 'No legume; the current rotation has one.')
    tight_a = sum(t.status == 'TIGHT' for t in s.transitions)
    tight_b = sum(t.status == 'TIGHT' for t in current.transitions)
    if tight_a != tight_b:
        out.append(f'{tight_a} TIGHT changeover(s) per cycle (current: {tight_b}).')
    if a.longest_fallow_gap and b.longest_fallow_gap and a.longest_fallow_gap.max != b.longest_fallow_gap.max:
        out.append(f'Longest gap between harvest and next sowing up to {a.longest_fallow_gap.max:g} months '
                   f'(current: {b.longest_fallow_gap.max:g}).')
    current_checks = {c.constraint: c.status for c in current.constraint_checks}
    for check in s.constraint_checks:
        before = current_checks.get(check.constraint)
        if before is not None and before != check.status:
            out.append(f'{check.constraint}: {check.status} (current: {before}).')
    if s.screening_result != current.screening_result:
        out.append(f'Screening: {s.screening_result} (current: {current.screening_result}).')
    return out


# ---------------------------------------------------------------- scenario analysis entry point

@dataclass
class _Result:
    analysis: ScenarioAnalysis
    state: _Ordered | None


def _run(request: ScenarioAnalysisRequest) -> _Result:
    profile = _effective_profile(request)
    comparison = compare_rotations(RotationCompareRequest(profile=profile, horizon_years=request.horizon_years))
    summaries: list[ScenarioSummary] = []
    flags: dict[str, _Flags] = {}
    for s in request.climate_scenarios:
        summary, f = _historical(s) if isinstance(s, HistoricalEpisodeScenario) else _hypothetical(s)
        summaries.append(summary)
        flags[s.id] = f
    kinds = {s.scenario_type for s in request.climate_scenarios}
    separation = [
        SeparationNote(part='comparison', kind=SEPARATION['comparison'][0], present=True,
                       meaning=SEPARATION['comparison'][1]),
        SeparationNote(part='applied_inputs', kind=SEPARATION['inputs'][0], present=True, meaning=SEPARATION['inputs'][1]),
        SeparationNote(part='scenarios[HISTORICAL_EPISODE]', kind=SEPARATION['historical'][0],
                       present='HISTORICAL_EPISODE' in kinds, meaning=SEPARATION['historical'][1]),
        SeparationNote(part='scenarios[HYPOTHETICAL]', kind=SEPARATION['hypothetical'][0],
                       present='HYPOTHETICAL' in kinds, meaning=SEPARATION['hypothetical'][1]),
        SeparationNote(part='exposure, ordering, trade_offs', kind='MODEL_SCENARIO', present=True,
                       meaning='Calendar overlap and rule-based ordering computed here; not observed outcomes.'),
        SeparationNote(part='verified_impact', kind=SEPARATION['validated'][0], present=False,
                       meaning=SEPARATION['validated'][1]),
    ]
    base = dict(input_sha256=canonical_sha256(request), applied_inputs=_applied_inputs(request, profile),
                scenarios=summaries, comparison=comparison, separation=separation, limitations=list(LIMITATIONS))
    if not comparison.strategies:
        return _Result(ScenarioAnalysis(
            status='NOT_ANALYSED', exposure=[], ordering=None, trade_offs=[], **base,
            explanation=[f'The rotation comparison returned {comparison.status}; there are no strategies to analyse.',
                         *comparison.explanation]), None)
    reg = _Registry(profile)
    exposure = [_exposure(st, reg, sm, flags[sm.id]) for sm in summaries for st in comparison.strategies]
    by_key = {(e.strategy_id, e.scenario_id): e for e in exposure}
    priorities = request.effective_priorities()
    ordering, state = _order(comparison.strategies, priorities, summaries, by_key)
    explanation = [f'{len(comparison.strategies)} strategies from the ABB-17 comparison ({comparison.status}).']
    if request.priorities_override is not None:
        explanation.append('Priorities replaced for this what-if: '
                           + ', '.join(f'{p.rank}. {p.criterion.value}' for p in priorities) + '.')
    if request.water_override is not None:
        explanation.append(f'Water availability replaced for this what-if: {request.water_override.water_regime.value}.')
    if not priorities:
        explanation.append('No priorities declared: strategies are separated by declared constraints only.')
    if not summaries:
        explanation.append('No climate scenario supplied: no exposure is computed.')
    explanation.extend(a.explanation for a in ordering.adjacent_decisions)
    return _Result(ScenarioAnalysis(status='ANALYSED', exposure=exposure, ordering=ordering,
                                    trade_offs=_trade_offs(comparison.strategies, state, summaries),
                                    explanation=explanation, **base), state)


def analyse_scenarios(request: ScenarioAnalysisRequest) -> ScenarioAnalysis:
    return _run(request).analysis


# ---------------------------------------------------------------- sensitivity

def apply_change(base: ScenarioAnalysisRequest, change) -> ScenarioAnalysisRequest:
    data = base.model_dump(mode='json')
    if isinstance(change, PrioritySwapChange):
        swapped = []
        ranks = {p.criterion: p.rank for p in base.effective_priorities()}
        for p in base.effective_priorities():
            item = p.model_dump(mode='json')
            if p.criterion == change.criterion_a:
                item['rank'] = ranks[change.criterion_b]
            elif p.criterion == change.criterion_b:
                item['rank'] = ranks[change.criterion_a]
            swapped.append(item)
        data['priorities_override'] = swapped
    elif isinstance(change, PrioritiesChange):
        data['priorities_override'] = [p.model_dump(mode='json') for p in change.priorities]
    elif isinstance(change, WaterChange):
        data['water_override'] = change.water.model_dump(mode='json')
    else:
        data['climate_scenarios'] = [s.model_dump(mode='json') for s in change.climate_scenarios]
    return ScenarioAnalysisRequest.model_validate(data)


def _change_summary(base: ScenarioAnalysisRequest, variant: ScenarioAnalysisRequest, change) -> list[str]:
    if isinstance(change, PrioritySwapChange):
        r = {p.criterion: p.rank for p in base.effective_priorities()}
        a, b = change.criterion_a, change.criterion_b
        return [f'Swapped priority ranks: {a.value} {r[a]} → {r[b]}, {b.value} {r[b]} → {r[a]}.']
    if isinstance(change, PrioritiesChange):
        return ['Priorities replaced: ' + (', '.join(f'{p.rank}. {p.criterion.value}' for p in variant.effective_priorities())
                                          or 'none') + '.']
    if isinstance(change, WaterChange):
        c = base.profile.constraints
        before = base.water_override.water_regime if base.water_override else (c.water_regime if c else WaterRegime.UNKNOWN)
        return [f'Water regime: {before.value} → {change.water.water_regime.value}.']
    before = [s.id for s in base.climate_scenarios]
    after = [s.id for s in change.climate_scenarios]
    return [f'Climate scenarios: [{", ".join(before)}] → [{", ".join(after)}].']


def _kind_map(analysis: ScenarioAnalysis) -> dict[str, RotationStrategy]:
    return {s.strategy_kind: s for s in analysis.comparison.strategies}


def _relation_label(rel: int) -> PairRelation:
    return 'FIRST_BEFORE_SECOND' if rel < 0 else ('TIED' if rel == 0 else 'SECOND_BEFORE_FIRST')


def analyse_sensitivity(request: SensitivityRequest) -> SensitivityAnalysis:
    variant_request = apply_change(request.base, request.change)
    base, variant = _run(request.base), _run(variant_request)
    b, v = base.analysis, variant.analysis
    summary = _change_summary(request.base, variant_request, request.change)

    before_ranks = {p.criterion: p.rank for p in request.base.effective_priorities()}
    after_ranks = {p.criterion: p.rank for p in variant_request.effective_priorities()}
    priority_changes = [PriorityRankChange(criterion=c, rank_before=before_ranks.get(c), rank_after=after_ranks.get(c))
                        for c in sorted(before_ranks.keys() | after_ranks.keys(), key=lambda c: c.value)
                        if before_ranks.get(c) != after_ranks.get(c)]

    screening_before = {s.crop.crop_label: s for s in b.comparison.candidate_screening}
    screening_after = {s.crop.crop_label: s for s in v.comparison.candidate_screening}
    screening_changes = []
    for label in sorted(screening_before.keys() | screening_after.keys()):
        x, y = screening_before.get(label), screening_after.get(label)
        rx = [r.code for r in x.reasons] if x else []
        ry = [r.code for r in y.reasons] if y else []
        if (x.status if x else None) != (y.status if y else None) or rx != ry:
            screening_changes.append(ScreeningChange(crop_label=label, status_before=x.status if x else None,
                                                     status_after=y.status if y else None,
                                                     reasons_before=rx, reasons_after=ry))

    kb, kv = _kind_map(b), _kind_map(v)
    order_of_kinds = [k for k in ('CURRENT', 'MINIMAL_CHANGE', 'FAMILY_DIVERSIFICATION', 'CALENDAR_COVER')
                      if k in kb or k in kv]
    strategy_changes = []
    for kind in order_of_kinds:
        x, y = kb.get(kind), kv.get(kind)
        if x is None or y is None:
            change = 'ONLY_IN_VARIANT' if x is None else 'ONLY_IN_BASE'
            text = (f'{kind} is only generated {"after" if x is None else "before"} the change'
                    + ('; see screening_changes.' if screening_changes else '.'))
            strategy_changes.append(StrategyChange(strategy_kind=kind, change=change,
                                                   years_before=x.years if x else None,
                                                   years_after=y.years if y else None, constraint_changes=[],
                                                   explanation=text))
            continue
        checks_x = {c.constraint: c.status for c in x.constraint_checks}
        constraint_changes = [f'{c.constraint}: {checks_x.get(c.constraint)} → {c.status}' for c in y.constraint_checks
                              if checks_x.get(c.constraint) != c.status]
        same = x.years == y.years
        text = (f'{kind} keeps the same sequence.' if same else
                f'{kind} changes sequence: {" / ".join(c[0] for c in x.years[:len(x.cycle)])} → '
                f'{" / ".join(c[0] for c in y.years[:len(y.cycle)])}'
                + ('; see screening_changes.' if screening_changes else '.'))
        if constraint_changes:
            text += ' Constraint checks changed: ' + '; '.join(constraint_changes) + '.'
        strategy_changes.append(StrategyChange(strategy_kind=kind, change='SAME_SEQUENCE' if same else 'DIFFERENT_SEQUENCE',
                                               years_before=x.years, years_after=y.years,
                                               constraint_changes=constraint_changes, explanation=text))

    exposure_changes = []
    eb = {(e.strategy_kind, e.scenario_id): e for e in b.exposure}
    ev = {(e.strategy_kind, e.scenario_id): e for e in v.exposure}
    for key in sorted(eb.keys() | ev.keys(), key=lambda k: (order_of_kinds.index(k[0]) if k[0] in order_of_kinds else 9, k[1])):
        x, y = eb.get(key), ev.get(key)
        rx = x.flagged_months_in_field_per_year if x else None
        ry = y.flagged_months_in_field_per_year if y else None
        if (x.status if x else None) != (y.status if y else None) or rx != ry:
            exposure_changes.append(ExposureChange(strategy_kind=key[0], scenario_id=key[1],
                                                   status_before=x.status if x else None,
                                                   status_after=y.status if y else None, before=rx, after=ry))

    if base.state is None or variant.state is None:
        explanation = [*summary, 'No comparison: '
                       + ('the base' if base.state is None else 'the changed') + ' request has no strategies '
                       f'({(b if base.state is None else v).comparison.status}).']
        return SensitivityAnalysis(
            status='NOT_COMPARABLE', request_sha256=canonical_sha256(request), base_input_sha256=b.input_sha256,
            variant_input_sha256=v.input_sha256, change_type=request.change.change_type, change_summary=summary,
            priority_changes=priority_changes, criteria_changes=[], screening_changes=screening_changes,
            strategy_changes=strategy_changes, position_changes=[], pair_changes=[], exposure_changes=exposure_changes,
            explanation=explanation, base_ordering=b.ordering, variant_ordering=v.ordering, limitations=list(LIMITATIONS))

    sb, sv = base.state, variant.state
    criteria_changes = _criteria_changes(sb, sv)
    id_b = {s.strategy_kind: s.id for s in b.comparison.strategies}
    id_v = {s.strategy_kind: s.id for s in v.comparison.strategies}
    pair_changes = []
    for i, k1 in enumerate(order_of_kinds):
        for k2 in order_of_kinds[i + 1:]:
            if not all(k in id_b and k in id_v for k in (k1, k2)):
                continue
            rb = sb.relation(id_b[k1], id_b[k2])
            rv = sv.relation(id_v[k1], id_v[k2])
            first, second = (k1, k2) if rb <= 0 else (k2, k1)
            if rb > 0:
                rb, rv = -rb, -rv
            db = sb.decided_at(id_b[first], id_b[second])
            dv = sv.decided_at(id_v[first], id_v[second])
            label_b = None if db is None else sb.step_label(db)
            label_v = None if dv is None else sv.step_label(dv)
            if rb == rv and label_b == label_v:
                continue
            text = (f'Before: {sb.pair_sentence(id_b[first], id_b[second])} '
                    f'After: {sv.pair_sentence(id_v[first], id_v[second])}')
            if rb == rv:
                text = f'Order of {first} and {second} unchanged, but the deciding criterion changed. ' + text
            pair_changes.append(PairChange(first_kind=first, second_kind=second, before=_relation_label(rb),
                                           after=_relation_label(rv), order_changed=rb != rv,
                                           decided_by_before=label_b, decided_by_after=label_v, explanation=text))

    position_changes = []
    for kind in order_of_kinds:
        pb = sb.positions.get(id_b[kind]) if kind in id_b else None
        pv = sv.positions.get(id_v[kind]) if kind in id_v else None
        if pb is None or pv is None:
            movement = 'ADDED' if pb is None else 'REMOVED'
            text = f'{kind} is {"added" if pb is None else "removed"}: the strategy is only generated ' \
                   f'{"after" if pb is None else "before"} the change.'
        else:
            movement = 'SAME' if pb == pv else ('UP' if pv < pb else 'DOWN')
            if movement == 'SAME':
                text = f'{kind} stays at position {pb}.'
            else:
                reasons = [p.explanation for p in pair_changes if p.order_changed and kind in (p.first_kind, p.second_kind)]
                text = f'{kind} moves from position {pb} to {pv}. ' + (' '.join(reasons) if reasons else
                                                                         'Ties with other strategies changed.')
        position_changes.append(PositionChange(strategy_kind=kind, position_before=pb, position_after=pv,
                                               movement=movement, explanation=text))

    explanation = list(summary)
    explanation += [c.explanation for c in criteria_changes if c.change != 'SAME_STEP' or c.values_changed]
    explanation += [f'Screening of {s.crop_label}: {s.status_before} → {s.status_after} '
                    f'({", ".join(s.reasons_after) or "no reason codes"}).' for s in screening_changes]
    explanation += [s.explanation for s in strategy_changes if s.change != 'SAME_SEQUENCE' or s.constraint_changes]
    moved = [p for p in position_changes if p.movement != 'SAME']
    explanation += [p.explanation for p in moved]
    if not moved:
        explanation.append('No ordering position changed.')
        explanation += [p.explanation for p in pair_changes if not p.order_changed]
        if not pair_changes:
            explanation.append('Every pair of strategies is still decided at the same step by the same criterion.')
    return SensitivityAnalysis(
        status='COMPARED', request_sha256=canonical_sha256(request), base_input_sha256=b.input_sha256,
        variant_input_sha256=v.input_sha256, change_type=request.change.change_type, change_summary=summary,
        priority_changes=priority_changes, criteria_changes=criteria_changes, screening_changes=screening_changes,
        strategy_changes=strategy_changes, position_changes=position_changes, pair_changes=pair_changes,
        exposure_changes=exposure_changes, explanation=explanation, base_ordering=b.ordering,
        variant_ordering=v.ordering, limitations=list(LIMITATIONS))


def _criteria_changes(sb: _Ordered, sv: _Ordered) -> list[CriterionChange]:
    step_b = {c.id: i for i, c in enumerate(sb.criteria, start=1)}
    step_v = {c.id: i for i, c in enumerate(sv.criteria, start=1)}
    ids = list(dict.fromkeys([c.id for c in sb.criteria] + [c.id for c in sv.criteria]
                             + sorted(sb.values.keys() | sv.values.keys())))
    kind_b = {sid: s.strategy_kind for sid, s in sb.strategies.items()}
    kind_v = {sid: s.strategy_kind for sid, s in sv.strategies.items()}
    out = []
    for cid in ids:
        xb, xv = step_b.get(cid), step_v.get(cid)
        vb = {kind_b[sid]: val for sid, val in sb.values.get(cid, {}).items()}
        vv = {kind_v[sid]: val for sid, val in sv.values.get(cid, {}).items()}
        values_changed = [ValueChange(strategy_kind=k, before=vb.get(k), after=vv.get(k))
                          for k in sorted(vb.keys() | vv.keys()) if vb.get(k) != vv.get(k)]
        if xb is None and xv is None:
            if not values_changed:
                continue
            change, text = 'SAME_STEP', f'{cid} is not used for ordering, but its values changed (see values_changed).'
        elif xb is None:
            change = 'ADDED'
            text = f'{cid} is now used for ordering at step {xv} (rank {sv.ranks[cid]}).'
        elif xv is None:
            change = 'REMOVED'
            text = f'{cid} is no longer used for ordering (was step {xb}, rank {sb.ranks[cid]}).'
        elif xb == xv:
            change = 'SAME_STEP'
            text = f'{cid} stays at step {xb}' + (', but its values changed.' if values_changed else '.')
        else:
            change = 'MOVED_EARLIER' if xv < xb else 'MOVED_LATER'
            text = (f'{cid} moves from step {xb} to step {xv} (rank {sb.ranks[cid]} → {sv.ranks[cid]}), so it is '
                    f'applied {"earlier" if xv < xb else "later"}. Ordering steps are now: DECLARED_CONSTRAINTS → '
                    + ' → '.join(c.id for c in sv.criteria) + '.')
        if values_changed and xb is not None and xv is not None and xb != xv:
            text += ' Its values also changed.'
        out.append(CriterionChange(criterion_id=cid, step_before=xb, step_after=xv, change=change,
                                   values_changed=values_changed, explanation=text))
    return out
