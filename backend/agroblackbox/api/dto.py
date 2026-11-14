"""Versioned request/response models for the authenticated ``/api/v1`` routes (ABB-05/06).

Response models extend the shared ABB-02 contracts (``schemas.Case`` / ``schemas.Field``)
additively; request models reject unknown fields, NaN and infinities.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field as PydanticField,
    JsonValue,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from .. import schemas
from ..privacy import ROUNDING_STEPS

Role = Literal["OWNER", "EDITOR", "REVIEWER", "VIEWER"]
GrantableRole = Literal["EDITOR", "REVIEWER", "VIEWER"]
CaseStatus = Literal["DRAFT", "INVESTIGATING", "REVIEWED", "PUBLISHED"]
LocationPrecision = Literal["EXACT", "APPROXIMATE", "REGION_ONLY", "NONE"]

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")
_ROUNDING_SCHEMA = {"enum": list(ROUNDING_STEPS)}
EARLIEST_INCIDENT = date(1900, 1, 1)
MAX_FIELDS = 20

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
CropEntry = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Limitation = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def normalize_email(value: str) -> str:
    return value.strip().lower()


class EmailField(RequestModel):
    email: str = PydanticField(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def _normalized(cls, value: str) -> str:
        value = normalize_email(value)
        if not _EMAIL.match(value):
            raise ValueError("enter a valid email address")
        return value


# ── Authentication ────────────────────────────────────────────────────────────

class RegisterRequest(EmailField):
    # Length is checked in the handler so validation errors never echo the password.
    password: SecretStr
    display_name: ShortText


class LoginRequest(RequestModel):
    email: str = PydanticField(min_length=1, max_length=320)
    password: SecretStr


class UserOut(schemas.ContractModel):
    id: UUID
    email: str
    display_name: str
    created_at: datetime


class UserSummary(schemas.ContractModel):
    id: UUID
    display_name: str


class SessionOut(schemas.ContractModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserOut


# ── Fields (parcels) ─────────────────────────────────────────────────────────

def check_location(
    *, privacy_tier: schemas.PrivacyTier | str, latitude: float | None, longitude: float | None,
    precise_location_consent: bool, rounding_deg: float | None,
) -> None:
    """Same rules as the shared ``Field`` contract and the database constraints."""
    tier = schemas.PrivacyTier(privacy_tier)
    if (latitude is None) != (longitude is None):
        raise ValueError("latitude and longitude must be supplied together")
    if tier == schemas.PrivacyTier.EXACT and (latitude is None or not precise_location_consent):
        raise ValueError("EXACT fields require coordinates and explicit precise_location_consent")
    if tier == schemas.PrivacyTier.WITHHELD and latitude is not None:
        raise ValueError("WITHHELD fields cannot store coordinates")
    if rounding_deg is not None and rounding_deg not in ROUNDING_STEPS:
        raise ValueError("rounding_deg must be one of 0.1, 0.5 or 1.0")
    if tier == schemas.PrivacyTier.APPROXIMATE and rounding_deg is None:
        raise ValueError("APPROXIMATE fields require rounding_deg")


class FieldInput(RequestModel):
    label: ShortText
    privacy_tier: schemas.PrivacyTier
    latitude: float | None = PydanticField(default=None, ge=-90, le=90)
    longitude: float | None = PydanticField(default=None, ge=-180, le=180)
    region_label: ShortText
    area_hectares: float | None = PydanticField(default=None, gt=0, le=1_000_000)
    precise_location_consent: bool = False
    rounding_deg: float | None = PydanticField(default=None, json_schema_extra=_ROUNDING_SCHEMA)
    limitations: list[Limitation] = PydanticField(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _location_rules(self) -> FieldInput:
        if self.privacy_tier == schemas.PrivacyTier.APPROXIMATE and self.rounding_deg is None:
            self.rounding_deg = 0.1
        check_location(
            privacy_tier=self.privacy_tier, latitude=self.latitude, longitude=self.longitude,
            precise_location_consent=self.precise_location_consent, rounding_deg=self.rounding_deg,
        )
        return self


class FieldCreate(RequestModel):
    version: int = PydanticField(ge=1, description="Current case version")
    field: FieldInput


class FieldPatch(RequestModel):
    """Partial update. Omitted keys are unchanged; the merged field is re-validated."""
    version: int = PydanticField(ge=1)
    label: ShortText | None = None
    privacy_tier: schemas.PrivacyTier | None = None
    latitude: float | None = PydanticField(default=None, ge=-90, le=90)
    longitude: float | None = PydanticField(default=None, ge=-180, le=180)
    region_label: ShortText | None = None
    area_hectares: float | None = PydanticField(default=None, gt=0, le=1_000_000)
    precise_location_consent: bool | None = None
    rounding_deg: float | None = PydanticField(default=None, json_schema_extra=_ROUNDING_SCHEMA)
    limitations: list[Limitation] | None = PydanticField(default=None, max_length=20)

    @model_validator(mode="after")
    def _not_null(self) -> FieldPatch:
        for name in ("label", "privacy_tier", "region_label", "precise_location_consent", "limitations"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


# ── Cases ────────────────────────────────────────────────────────────────────

def check_incident_dates(start: date, end: date | None) -> None:
    today = date.today()
    if start < EARLIEST_INCIDENT or start > today:
        raise ValueError("incident_start must be between 1900-01-01 and today")
    if end is not None and (end < start or end > today):
        raise ValueError("incident_end must be between incident_start and today")


class CaseCreate(RequestModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    incident_start: date
    incident_end: date | None = None
    crop_history: list[CropEntry] = PydanticField(default_factory=list, max_length=50)
    incident_notes: str | None = PydanticField(default=None, max_length=10_000)
    fields: list[FieldInput] = PydanticField(min_length=1, max_length=MAX_FIELDS)

    @model_validator(mode="after")
    def _dates(self) -> CaseCreate:
        check_incident_dates(self.incident_start, self.incident_end)
        return self


class CaseUpdate(RequestModel):
    version: int = PydanticField(ge=1)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    incident_start: date | None = None
    incident_end: date | None = None
    crop_history: list[CropEntry] | None = PydanticField(default=None, max_length=50)
    incident_notes: str | None = PydanticField(default=None, max_length=10_000)

    @model_validator(mode="after")
    def _not_null(self) -> CaseUpdate:
        for name in ("title", "incident_start", "crop_history"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class StatusChange(RequestModel):
    version: int = PydanticField(ge=1)
    status: CaseStatus
    note: str | None = PydanticField(default=None, max_length=2_000)


class ArchiveRequest(RequestModel):
    version: int = PydanticField(ge=1)
    archived: bool


class PermissionGrant(EmailField):
    role: GrantableRole


# ── Responses ────────────────────────────────────────────────────────────────

class CaseFieldView(schemas.Field):
    """Shared ``Field`` as seen by the caller: coordinates are already redacted per role."""
    location_precision: LocationPrecision
    rounding_deg: float | None = None
    precise_location_consent: bool


class CaseView(schemas.Case):
    """Shared ``Case`` plus workflow, optimistic version and the caller's role."""
    model_config = ConfigDict(extra="forbid", json_schema_extra=None)
    fields: list[CaseFieldView] = PydanticField(min_length=1)
    version: int = PydanticField(ge=1)
    status: CaseStatus
    archived_at: datetime | None = None
    owner: UserSummary
    my_role: Role


class CaseList(schemas.ContractModel):
    items: list[CaseView]


class HistoryEntry(schemas.ContractModel):
    id: UUID
    version: int
    action: str
    actor: UserSummary | None
    created_at: datetime
    changes: dict[str, JsonValue]
    note: str | None = None


class PermissionView(schemas.ContractModel):
    user_id: UUID
    display_name: str
    email: str | None = PydanticField(default=None, description="Shown to the case owner only")
    role: Role
