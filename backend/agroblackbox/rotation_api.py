"""HTTP routes for the rotation comparison engine (ABB-17)."""
from fastapi import APIRouter

from .services.rotations import RotationCompareRequest, RotationComparison, compare_rotations

router = APIRouter(prefix='/api/v1/rotations', tags=['rotations (ABB-17)'])


@router.post('/compare', response_model=RotationComparison)
def compare(request: RotationCompareRequest) -> RotationComparison:
    """Stateless comparison of the current rotation (from crop history) with rule-generated alternatives
    under the farmer's declared calendar, exclusions, markets and water regime. Nothing is stored.
    Descriptive only: no yield, water, income or benefit figure and no score; ``verified_impact`` is null."""
    return compare_rotations(request)
