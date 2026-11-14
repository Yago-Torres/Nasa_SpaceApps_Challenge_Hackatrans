"""Server-side location privacy for case collaborators (ABB-05/ABB-06, ADR-0004).

Owners and editors see stored coordinates. Reviewers and viewers receive coordinates only
as permitted by the field's privacy tier, unless the owner gave explicit consent to share the
precise location. Redaction happens before serialisation, so a guest payload never contains
the stored point.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Any, Literal

ROUNDING_STEPS: tuple[float, ...] = (0.1, 0.5, 1.0)
PRECISE_ROLES = frozenset({"OWNER", "EDITOR"})
REDACTED = "REDACTED"
_COORDINATE_KEYS = frozenset({"latitude", "longitude"})

LocationPrecision = Literal["EXACT", "APPROXIMATE", "REGION_ONLY", "NONE"]


@dataclass(frozen=True)
class VisibleLocation:
    latitude: float | None
    longitude: float | None
    precision: LocationPrecision


def snap_to_cell_centre(value: float, step: float, limit: float) -> float:
    """Centre of the ``step``-degree grid cell containing ``value``.

    Decimal arithmetic avoids binary floor errors (0.3 / 0.1 = 2.999...). The result stays
    inside [-limit, limit], so a pole or antimeridian point maps to the last valid cell.
    Matches ``roundToCell`` in ``frontend/src/cases/model.ts`` for interior values.
    """
    if step not in ROUNDING_STEPS:
        raise ValueError("unsupported rounding step")
    d_value, d_step, d_limit = Decimal(str(value)), Decimal(str(step)), Decimal(str(limit))
    index = (d_value / d_step).to_integral_value(rounding=ROUND_FLOOR)
    max_index = (d_limit / d_step).to_integral_value(rounding=ROUND_FLOOR) - 1
    index = max(min(index, max_index), -max_index - 1)
    centre = index * d_step + d_step / 2
    return float(centre.quantize(Decimal("0.001")))


def visible_location(
    *, role: str, privacy_tier: str, latitude: float | None, longitude: float | None,
    rounding_deg: float | None, precise_location_consent: bool,
) -> VisibleLocation:
    if latitude is None or longitude is None:
        return VisibleLocation(None, None, "NONE")
    if role in PRECISE_ROLES or precise_location_consent or privacy_tier == "EXACT":
        # EXACT is only storable with consent (database constraint ck_field_exact_consent).
        return VisibleLocation(latitude, longitude, "EXACT")
    if privacy_tier == "APPROXIMATE" and rounding_deg in ROUNDING_STEPS:
        return VisibleLocation(
            snap_to_cell_centre(latitude, rounding_deg, 90.0),
            snap_to_cell_centre(longitude, rounding_deg, 180.0),
            "APPROXIMATE",
        )
    if privacy_tier == "REGION_ONLY":
        return VisibleLocation(None, None, "REGION_ONLY")
    return VisibleLocation(None, None, "NONE")


def redact_coordinates(value: Any) -> Any:
    """Replace every ``latitude``/``longitude`` value in nested history data."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if key in _COORDINATE_KEYS and item is not None else redact_coordinates(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_coordinates(item) for item in value]
    return value
