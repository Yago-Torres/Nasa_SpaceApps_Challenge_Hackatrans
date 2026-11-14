"""HTTP routes for the rotation comparison engine (ABB-17) and scenario/sensitivity analysis (ABB-18)."""
from fastapi import APIRouter

from .services.rotations import RotationCompareRequest, RotationComparison, compare_rotations
from .services.scenarios import (
    ScenarioAnalysis,
    ScenarioAnalysisRequest,
    SensitivityAnalysis,
    SensitivityRequest,
    analyse_scenarios,
    analyse_sensitivity,
)

router = APIRouter(prefix='/api/v1/rotations', tags=['rotations (ABB-17)'])


@router.post('/compare', response_model=RotationComparison)
def compare(request: RotationCompareRequest) -> RotationComparison:
    """Stateless comparison of the current rotation (from crop history) with rule-generated alternatives
    under the farmer's declared calendar, exclusions, markets and water regime. Nothing is stored.
    Descriptive only: no yield, water, income or benefit figure and no score; ``verified_impact`` is null."""
    return compare_rotations(request)


@router.post('/scenarios', response_model=ScenarioAnalysis, tags=['rotation scenarios (ABB-18)'])
def scenarios(request: ScenarioAnalysisRequest) -> ScenarioAnalysis:
    """What-if analysis: the ABB-17 comparison under modified priorities and/or water availability, calendar
    exposure of each strategy to labelled climate scenarios (observed historical episodes or hypothetical
    month flags, never forecasts), a lexicographic ordering by the farmer's ranks with every step explained,
    and explicit trade-offs. Stateless and deterministic; ``verified_impact`` is null."""
    return analyse_scenarios(request)


@router.post('/sensitivity', response_model=SensitivityAnalysis, tags=['rotation scenarios (ABB-18)'])
def sensitivity(request: SensitivityRequest) -> SensitivityAnalysis:
    """Runs a base scenario request and a changed one (priority swap, new priorities, water or climate
    scenarios) and reports which criteria, values, strategies and ordering positions changed and why."""
    return analyse_sensitivity(request)
