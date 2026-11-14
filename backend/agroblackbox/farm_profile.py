"""Farm profile: soil, crop history, local calendar, constraints and priorities (ABB-11).

The profile records what the farmer or a measurement says; it never fills gaps with
defaults. ``assess_profile`` checks consistency and lists missing data together with the
analysis it limits. It produces no agronomic outcome (yield, water, benefit) and no score.

Structural problems (wrong types, impossible months, negative depths) are rejected by the
models (HTTP 422). Agronomic consistency problems are returned as ``ERROR`` issues so a
wizard can show them next to the input without discarding data.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import Field as PydanticField, model_validator

from .crop_catalog import CATALOG_VERSION, ENTRIES, resolve_crop
from .schemas import ContractModel, Resolution, VersionedContract

PROCESSING_VERSION = 'abb11-farm-profile-0.1.0'
TEXTURE_SUM_TOLERANCE = 2.0  # percentage points allowed for rounding in reported texture fractions


class DataOrigin(str, Enum):
    LOCAL_MEASUREMENT = 'LOCAL_MEASUREMENT'  # lab or field measurement on this field
    FARMER_ESTIMATE = 'FARMER_ESTIMATE'      # farmer knowledge without a measurement
    REGIONAL_ESTIMATE = 'REGIONAL_ESTIMATE'  # soil map, gridded or regional product
    UNKNOWN = 'UNKNOWN'


class SoilProperty(str, Enum):
    PH = 'PH'
    ORGANIC_MATTER = 'ORGANIC_MATTER'
    ORGANIC_CARBON = 'ORGANIC_CARBON'
    CLAY = 'CLAY'
    SILT = 'SILT'
    SAND = 'SAND'
    CALCIUM_CARBONATE = 'CALCIUM_CARBONATE'
    ELECTRICAL_CONDUCTIVITY = 'ELECTRICAL_CONDUCTIVITY'
    BULK_DENSITY = 'BULK_DENSITY'
    AVAILABLE_WATER_CAPACITY = 'AVAILABLE_WATER_CAPACITY'
    STONE_CONTENT = 'STONE_CONTENT'
    ROOTING_DEPTH = 'ROOTING_DEPTH'


# Allowed units per property. Bounds below are definitional (pH scale, fractions), not agronomic thresholds.
SOIL_UNITS: dict[SoilProperty, set[str]] = {
    SoilProperty.PH: {'pH'},
    SoilProperty.ORGANIC_MATTER: {'%', 'g/kg'},
    SoilProperty.ORGANIC_CARBON: {'%', 'g/kg'},
    SoilProperty.CLAY: {'%'},
    SoilProperty.SILT: {'%'},
    SoilProperty.SAND: {'%'},
    SoilProperty.CALCIUM_CARBONATE: {'%', 'g/kg'},
    SoilProperty.ELECTRICAL_CONDUCTIVITY: {'dS/m'},
    SoilProperty.BULK_DENSITY: {'g/cm3'},
    SoilProperty.AVAILABLE_WATER_CAPACITY: {'mm', 'mm/m'},
    SoilProperty.STONE_CONTENT: {'%'},
    SoilProperty.ROOTING_DEPTH: {'cm'},
}
UNIT_BOUNDS: dict[str, tuple[float, float | None]] = {
    'pH': (0.0, 14.0), '%': (0.0, 100.0), 'g/kg': (0.0, 1000.0),
}
LAYER_INDEPENDENT = {SoilProperty.ROOTING_DEPTH}
TEXTURE = (SoilProperty.CLAY, SoilProperty.SILT, SoilProperty.SAND)


class WaterRegime(str, Enum):
    RAINFED = 'RAINFED'
    IRRIGATED = 'IRRIGATED'
    SUPPLEMENTAL_IRRIGATION = 'SUPPLEMENTAL_IRRIGATION'
    UNKNOWN = 'UNKNOWN'


class SeasonRole(str, Enum):
    MAIN_CROP = 'MAIN_CROP'
    INTERCROP = 'INTERCROP'
    COVER_CROP = 'COVER_CROP'
    FALLOW = 'FALLOW'


class SoilObservation(ContractModel):
    property: SoilProperty
    value: float
    unit: str = PydanticField(min_length=1, max_length=20)
    depth_top_cm: float | None = PydanticField(default=None, ge=0, le=1000)
    depth_bottom_cm: float | None = PydanticField(default=None, gt=0, le=1000)
    origin: DataOrigin
    method: str | None = PydanticField(default=None, max_length=300)
    sampled_on: date | None = None
    source_reference: str | None = PydanticField(default=None, max_length=300)
    spatial_resolution: Resolution | None = None
    notes: str | None = PydanticField(default=None, max_length=1000)

    @model_validator(mode='after')
    def depth_interval_is_ordered(self) -> SoilObservation:
        if (self.depth_top_cm is None) != (self.depth_bottom_cm is None):
            raise ValueError('depth_top_cm and depth_bottom_cm must be supplied together')
        if self.depth_top_cm is not None and self.depth_bottom_cm <= self.depth_top_cm:
            raise ValueError('depth_bottom_cm must be greater than depth_top_cm')
        return self


class CropSeason(ContractModel):
    crop_code: str | None = PydanticField(default=None, max_length=40)
    crop_label: str = PydanticField(min_length=1, max_length=120)
    role: SeasonRole = SeasonRole.MAIN_CROP
    season_year: int = PydanticField(ge=1950, le=2100)
    sowing_date: date | None = None
    harvest_date: date | None = PydanticField(default=None, description='Harvest or termination date.')
    water_regime: WaterRegime = WaterRegime.UNKNOWN
    origin: DataOrigin = DataOrigin.FARMER_ESTIMATE
    notes: str | None = PydanticField(default=None, max_length=1000)


class CalendarWindow(ContractModel):
    """Farmer-declared typical window for a crop at this farm (months 1-12; may wrap the year end)."""
    crop_code: str | None = PydanticField(default=None, max_length=40)
    crop_label: str = PydanticField(min_length=1, max_length=120)
    sowing_start_month: int = PydanticField(ge=1, le=12)
    sowing_end_month: int = PydanticField(ge=1, le=12)
    harvest_start_month: int | None = PydanticField(default=None, ge=1, le=12)
    harvest_end_month: int | None = PydanticField(default=None, ge=1, le=12)
    origin: DataOrigin = DataOrigin.FARMER_ESTIMATE
    notes: str | None = PydanticField(default=None, max_length=1000)

    @model_validator(mode='after')
    def harvest_window_is_complete(self) -> CalendarWindow:
        if (self.harvest_start_month is None) != (self.harvest_end_month is None):
            raise ValueError('harvest_start_month and harvest_end_month must be supplied together')
        return self


class IrrigationAllowance(ContractModel):
    value: float = PydanticField(ge=0)
    unit: Literal['mm/season', 'mm/year', 'm3/ha/season', 'm3/ha/year']
    origin: DataOrigin
    notes: str | None = PydanticField(default=None, max_length=500)


class MarketAccess(ContractModel):
    crop_code: str | None = PydanticField(default=None, max_length=40)
    crop_label: str = PydanticField(min_length=1, max_length=120)
    status: Literal['CONTRACTED', 'SELLABLE', 'NO_MARKET', 'UNKNOWN']
    notes: str | None = PydanticField(default=None, max_length=500)


class FarmerConstraints(ContractModel):
    water_regime: WaterRegime = WaterRegime.UNKNOWN
    irrigation_allowance: IrrigationAllowance | None = None
    excluded_crops: list[str] = PydanticField(default_factory=list, max_length=50)
    available_equipment: list[str] = PydanticField(default_factory=list, max_length=50)
    equipment_limitations: str | None = PydanticField(default=None, max_length=1000)
    market_access: list[MarketAccess] = PydanticField(default_factory=list, max_length=50)
    labour_notes: str | None = PydanticField(default=None, max_length=1000)
    planning_horizon_years: int | None = PydanticField(default=None, ge=1, le=10)
    other_notes: str | None = PydanticField(default=None, max_length=2000)


class PriorityCriterion(str, Enum):
    SOIL_COVER = 'SOIL_COVER'
    WATER_USE = 'WATER_USE'
    INCOME_STABILITY = 'INCOME_STABILITY'
    WORKLOAD = 'WORKLOAD'
    CROP_DIVERSITY = 'CROP_DIVERSITY'
    INPUT_COSTS = 'INPUT_COSTS'
    RISK_REDUCTION = 'RISK_REDUCTION'
    OTHER = 'OTHER'


class FarmerPriority(ContractModel):
    """Ordinal rank (1 = most important). Deliberately not a numeric weight."""
    criterion: PriorityCriterion
    rank: int = PydanticField(ge=1, le=20)
    note: str | None = PydanticField(default=None, max_length=500)


class FarmProfile(VersionedContract):
    case_id: UUID | None = None
    field_id: UUID | None = None
    soil: list[SoilObservation] = PydanticField(default_factory=list, max_length=200)
    crop_history: list[CropSeason] = PydanticField(default_factory=list, max_length=100)
    local_calendar: list[CalendarWindow] = PydanticField(default_factory=list, max_length=100)
    constraints: FarmerConstraints | None = None
    priorities: list[FarmerPriority] = PydanticField(default_factory=list, max_length=20)


class ProfileIssue(ContractModel):
    severity: Literal['ERROR', 'WARNING', 'MISSING_DATA']
    code: str
    path: str
    message: str
    consequence: str | None = None


SectionStatus = Literal['PROVIDED', 'PARTIAL', 'MISSING']


class FarmProfileAssessment(VersionedContract):
    source_kind: Literal['FARMER_REPORTED'] = 'FARMER_REPORTED'
    profile: FarmProfile
    sections: dict[str, SectionStatus]
    soil_origins: list[DataOrigin]
    issues: list[ProfileIssue]
    rotation_input_status: Literal['BLOCKED_BY_ERRORS', 'LIMITED_BY_MISSING_DATA', 'INPUTS_COMPLETE']
    catalog_version: str = CATALOG_VERSION
    processing_version: str = PROCESSING_VERSION
    limitations: list[str]


ASSESSMENT_LIMITATIONS = [
    'Consistency and completeness checks only; no yield, water saving, soil benefit or suitability is computed.',
    'INPUTS_COMPLETE means the required inputs are present, not that any rotation is agronomically validated.',
    'Farmer estimates and regional soil products are not field measurements.',
    'Crop identity comes from a catalogue pending human review; crop parameters are not included.',
]


# ---------------------------------------------------------------- checks

class _Collector:
    def __init__(self):
        self.issues: list[ProfileIssue] = []

    def add(self, severity, code, path, message, consequence=None):
        self.issues.append(ProfileIssue(severity=severity, code=code, path=path,
                                        message=message, consequence=consequence))


def _resolve(code: str | None, label: str, path: str, out: _Collector) -> str | None:
    """Return the catalogue code for an item, or None. Never guesses beyond exact name matches."""
    if code:
        if code not in ENTRIES:
            out.add('ERROR', 'UNKNOWN_CROP_CODE', f'{path}.crop_code',
                    f'"{code}" is not a code in the crop catalogue.')
            return None
        return code
    entry = resolve_crop(label)
    if entry is None:
        out.add('WARNING', 'CROP_NOT_IN_CATALOGUE', f'{path}.crop_label',
                f'"{label}" is not in the crop catalogue.',
                'Rules that depend on crop family (e.g. legume status) cannot be applied to this crop.')
        return None
    return entry.code


def _check_soil(profile: FarmProfile, out: _Collector) -> None:
    if not profile.soil:
        out.add('MISSING_DATA', 'SOIL_MISSING', 'soil', 'No soil information recorded.',
                'Soil-dependent constraints (texture, salinity, pH, water holding) cannot be checked.')
        return
    for i, obs in enumerate(profile.soil):
        path = f'soil[{i}]'
        allowed = SOIL_UNITS[obs.property]
        if obs.unit not in allowed:
            out.add('ERROR', 'SOIL_UNIT_NOT_ALLOWED', f'{path}.unit',
                    f'Unit "{obs.unit}" is not accepted for {obs.property.value}; use one of {sorted(allowed)}.')
        else:
            low, high = UNIT_BOUNDS.get(obs.unit, (0.0, None))
            if obs.value < low or (high is not None and obs.value > high):
                out.add('ERROR', 'SOIL_VALUE_OUT_OF_RANGE', f'{path}.value',
                        f'{obs.value} {obs.unit} is outside the possible range for {obs.property.value}.')
            elif obs.property in {SoilProperty.BULK_DENSITY, SoilProperty.ROOTING_DEPTH} and obs.value == 0:
                out.add('ERROR', 'SOIL_VALUE_OUT_OF_RANGE', f'{path}.value',
                        f'{obs.property.value} must be greater than zero.')
        if obs.property not in LAYER_INDEPENDENT and obs.depth_top_cm is None:
            out.add('WARNING', 'SOIL_DEPTH_MISSING', path,
                    f'{obs.property.value} has no sampling depth.',
                    'Values cannot be compared between layers or with sources sampled at other depths.')
        if obs.origin == DataOrigin.REGIONAL_ESTIMATE:
            if not obs.source_reference:
                out.add('ERROR', 'REGIONAL_SOURCE_MISSING', f'{path}.source_reference',
                        'A regional estimate must name its product or map.')
            if obs.spatial_resolution is None:
                out.add('WARNING', 'REGIONAL_RESOLUTION_MISSING', f'{path}.spatial_resolution',
                        'Regional estimate without spatial resolution.',
                        'Its representativeness for this field cannot be judged.')
        if obs.origin == DataOrigin.LOCAL_MEASUREMENT and (obs.method is None or obs.sampled_on is None):
            out.add('WARNING', 'MEASUREMENT_METADATA_MISSING', path,
                    'Local measurement without method and/or sampling date.',
                    'Comparability with other measurements and reference values is limited.')
        if obs.origin == DataOrigin.UNKNOWN:
            out.add('WARNING', 'SOIL_ORIGIN_UNKNOWN', f'{path}.origin',
                    'Origin of this soil value is unknown.', 'It cannot be treated as a field measurement.')

    origins = {o.origin for o in profile.soil}
    if DataOrigin.LOCAL_MEASUREMENT not in origins:
        out.add('WARNING', 'NO_LOCAL_SOIL_MEASUREMENT', 'soil',
                'No soil value is a local measurement.',
                'Soil information describes the region or the farmer\'s estimate, not a measured field.')
    present = {o.property for o in profile.soil}
    if not present.intersection(TEXTURE):
        out.add('MISSING_DATA', 'SOIL_TEXTURE_MISSING', 'soil', 'No clay, silt or sand fraction recorded.',
                'Texture-dependent checks (workability, drainage, water holding) cannot be made.')
    _check_texture_sums(profile, out)


def _check_texture_sums(profile: FarmProfile, out: _Collector) -> None:
    groups: dict[tuple, dict[SoilProperty, float]] = {}
    for obs in profile.soil:
        if obs.property in TEXTURE and obs.unit == '%':
            key = (obs.depth_top_cm, obs.depth_bottom_cm, obs.origin, obs.source_reference)
            groups.setdefault(key, {})[obs.property] = obs.value
    for (top, bottom, origin, _), values in groups.items():
        if len(values) == 3 and abs(sum(values.values()) - 100.0) > TEXTURE_SUM_TOLERANCE:
            out.add('ERROR', 'TEXTURE_SUM_INCONSISTENT', 'soil',
                    f'Clay + silt + sand = {sum(values.values()):g}% for depth {top}-{bottom} cm '
                    f'({origin.value}); fractions should add up to about 100%.')


def _overlaps(a: CropSeason, b: CropSeason) -> bool:
    return a.sowing_date <= b.harvest_date and b.sowing_date <= a.harvest_date


def _check_history(profile: FarmProfile, out: _Collector) -> None:
    seasons = profile.crop_history
    if not seasons:
        out.add('MISSING_DATA', 'CROP_HISTORY_MISSING', 'crop_history', 'No crop history recorded.',
                'The current rotation cannot be characterised or compared with alternatives.')
        return
    for i, season in enumerate(seasons):
        path = f'crop_history[{i}]'
        if season.role != SeasonRole.FALLOW:
            _resolve(season.crop_code, season.crop_label, path, out)
        if season.sowing_date and season.harvest_date:
            if season.harvest_date <= season.sowing_date:
                out.add('ERROR', 'HARVEST_BEFORE_SOWING', f'{path}.harvest_date',
                        'Harvest/termination date must be after the sowing date.')
            elif season.season_year not in {season.sowing_date.year, season.harvest_date.year}:
                out.add('WARNING', 'SEASON_YEAR_MISMATCH', f'{path}.season_year',
                        f'season_year {season.season_year} matches neither the sowing nor the harvest year.')
        elif season.role != SeasonRole.FALLOW:
            out.add('MISSING_DATA', 'SEASON_DATES_MISSING', path,
                    f'{season.crop_label} ({season.season_year}) has no sowing and/or harvest date.',
                    'Calendar compatibility between consecutive crops cannot be checked for this season.')
        if season.role != SeasonRole.FALLOW and season.water_regime == WaterRegime.UNKNOWN:
            out.add('MISSING_DATA', 'SEASON_WATER_REGIME_MISSING', f'{path}.water_regime',
                    f'Water regime of {season.crop_label} ({season.season_year}) is unknown.',
                    'Rainfed and irrigated seasons cannot be distinguished when comparing exposure.')

    dated = [(i, s) for i, s in enumerate(seasons)
             if s.sowing_date and s.harvest_date and s.harvest_date > s.sowing_date]
    for x, (i, a) in enumerate(dated):
        for j, b in dated[x + 1:]:
            if not _overlaps(a, b):
                continue
            roles = {a.role, b.role}
            if SeasonRole.FALLOW in roles:
                out.add('ERROR', 'FALLOW_OVERLAPS_CROP', f'crop_history[{j}]',
                        f'Seasons {i} and {j} overlap but one of them is fallow.')
            elif roles == {SeasonRole.MAIN_CROP}:
                out.add('ERROR', 'MAIN_CROPS_OVERLAP', f'crop_history[{j}]',
                        f'Main crops in seasons {i} and {j} overlap in time on the same field. '
                        'If they were grown together, record one of them as INTERCROP.')
            else:
                out.add('WARNING', 'SEASONS_OVERLAP', f'crop_history[{j}]',
                        f'Seasons {i} and {j} overlap (relay, undersown or intercrop).')

    main_years = {s.season_year for s in seasons if s.role == SeasonRole.MAIN_CROP}
    if len(main_years) < 2:
        out.add('MISSING_DATA', 'CROP_HISTORY_SHORT', 'crop_history',
                'Fewer than two seasons with a main crop recorded.',
                'A rotation sequence cannot be identified from a single season.')


def _months_in_window(start: int, end: int) -> set[int]:
    return set(range(start, end + 1)) if start <= end else set(range(start, 13)) | set(range(1, end + 1))


def _check_calendar(profile: FarmProfile, out: _Collector) -> None:
    if not profile.local_calendar:
        out.add('MISSING_DATA', 'LOCAL_CALENDAR_MISSING', 'local_calendar',
                'No typical sowing/harvest windows declared for this farm.',
                'Candidate rotations cannot be checked against local sowing windows; '
                'the catalogue deliberately contains no calendar defaults.')
        return
    seen: dict[str, int] = {}
    for i, window in enumerate(profile.local_calendar):
        path = f'local_calendar[{i}]'
        code = _resolve(window.crop_code, window.crop_label, path, out)
        key = code or window.crop_label.casefold()
        if key in seen:
            out.add('WARNING', 'DUPLICATE_CALENDAR_WINDOW', path,
                    f'{window.crop_label} already has a window at local_calendar[{seen[key]}].')
        seen.setdefault(key, i)
        if window.harvest_start_month is not None:
            sowing = _months_in_window(window.sowing_start_month, window.sowing_end_month)
            harvest = _months_in_window(window.harvest_start_month, window.harvest_end_month)
            if sowing & harvest and len(sowing | harvest) < 12:
                out.add('WARNING', 'SOWING_HARVEST_WINDOWS_OVERLAP', path,
                        f'Sowing and harvest windows of {window.crop_label} share months; check they are correct.')
        else:
            out.add('MISSING_DATA', 'HARVEST_WINDOW_MISSING', path,
                    f'No harvest window for {window.crop_label}.',
                    'The gap before the next crop cannot be checked.')


def _check_constraints(profile: FarmProfile, out: _Collector) -> None:
    c = profile.constraints
    if c is None:
        out.add('MISSING_DATA', 'CONSTRAINTS_MISSING', 'constraints', 'No farmer constraints recorded.',
                'Water, equipment and market feasibility of alternatives cannot be checked.')
        return
    if c.water_regime == WaterRegime.UNKNOWN:
        out.add('MISSING_DATA', 'WATER_REGIME_MISSING', 'constraints.water_regime',
                'Farm water availability (rainfed or irrigated) is unknown.',
                'Water-dependent alternatives cannot be screened.')
    if c.irrigation_allowance is not None:
        if c.water_regime == WaterRegime.RAINFED and c.irrigation_allowance.value > 0:
            out.add('ERROR', 'RAINFED_WITH_IRRIGATION', 'constraints.irrigation_allowance',
                    'An irrigation allowance above zero contradicts a rainfed water regime.')
    elif c.water_regime in {WaterRegime.IRRIGATED, WaterRegime.SUPPLEMENTAL_IRRIGATION}:
        out.add('MISSING_DATA', 'IRRIGATION_ALLOWANCE_MISSING', 'constraints.irrigation_allowance',
                'Irrigated farm without a declared water allowance.',
                'Alternatives cannot be checked against available irrigation water.')
    excluded = set()
    for i, name in enumerate(c.excluded_crops):
        code = _resolve(None, name, f'constraints.excluded_crops[{i}]', out)
        excluded.add(code or name.casefold())
    for i, market in enumerate(c.market_access):
        code = _resolve(market.crop_code, market.crop_label, f'constraints.market_access[{i}]', out)
        if market.status in {'CONTRACTED', 'SELLABLE'} and (code or market.crop_label.casefold()) in excluded:
            out.add('WARNING', 'EXCLUDED_CROP_HAS_MARKET', f'constraints.market_access[{i}]',
                    f'{market.crop_label} is excluded but has market status {market.status}.')
    if not c.available_equipment and not c.equipment_limitations:
        out.add('MISSING_DATA', 'EQUIPMENT_MISSING', 'constraints.available_equipment',
                'No equipment information recorded.', 'Machinery feasibility of alternatives cannot be checked.')
    if not c.market_access:
        out.add('MISSING_DATA', 'MARKET_ACCESS_MISSING', 'constraints.market_access',
                'No market information recorded.', 'Alternatives cannot be screened for sellable crops.')
    history_regimes = {s.water_regime for s in profile.crop_history
                       if s.water_regime in {WaterRegime.IRRIGATED, WaterRegime.SUPPLEMENTAL_IRRIGATION}}
    if c.water_regime == WaterRegime.RAINFED and history_regimes:
        out.add('WARNING', 'HISTORY_IRRIGATED_BUT_FARM_RAINFED', 'constraints.water_regime',
                'Crop history includes irrigated seasons but the farm is declared rainfed; '
                'confirm whether water access changed.')


def _check_priorities(profile: FarmProfile, out: _Collector) -> None:
    if not profile.priorities:
        out.add('MISSING_DATA', 'PRIORITIES_MISSING', 'priorities', 'No farmer priorities recorded.',
                'Alternatives cannot be ordered by what matters to the farmer; trade-offs are shown unranked.')
        return
    ranks = [p.rank for p in profile.priorities]
    if len(ranks) != len(set(ranks)):
        out.add('ERROR', 'DUPLICATE_PRIORITY_RANK', 'priorities', 'Two priorities share the same rank.')
    criteria = [p.criterion for p in profile.priorities if p.criterion != PriorityCriterion.OTHER]
    if len(criteria) != len(set(criteria)):
        out.add('ERROR', 'DUPLICATE_PRIORITY_CRITERION', 'priorities', 'A priority criterion is listed twice.')


def _section_status(profile: FarmProfile, issues: list[ProfileIssue]) -> dict[str, SectionStatus]:
    def status(present: bool, prefix: str) -> SectionStatus:
        if not present:
            return 'MISSING'
        flagged = any(i.path.startswith(prefix) and i.severity in {'MISSING_DATA', 'ERROR'} for i in issues)
        return 'PARTIAL' if flagged else 'PROVIDED'
    return {
        'soil': status(bool(profile.soil), 'soil'),
        'crop_history': status(bool(profile.crop_history), 'crop_history'),
        'local_calendar': status(bool(profile.local_calendar), 'local_calendar'),
        'constraints': status(profile.constraints is not None, 'constraints'),
        'priorities': status(bool(profile.priorities), 'priorities'),
    }


def assess_profile(profile: FarmProfile) -> FarmProfileAssessment:
    out = _Collector()
    _check_soil(profile, out)
    _check_history(profile, out)
    _check_calendar(profile, out)
    _check_constraints(profile, out)
    _check_priorities(profile, out)
    severities = {i.severity for i in out.issues}
    if 'ERROR' in severities:
        readiness = 'BLOCKED_BY_ERRORS'
    elif 'MISSING_DATA' in severities:
        readiness = 'LIMITED_BY_MISSING_DATA'
    else:
        readiness = 'INPUTS_COMPLETE'
    return FarmProfileAssessment(
        profile=profile,
        sections=_section_status(profile, out.issues),
        soil_origins=sorted({o.origin for o in profile.soil}, key=lambda o: o.value),
        issues=out.issues,
        rotation_input_status=readiness,
        limitations=list(ASSESSMENT_LIMITATIONS),
    )
