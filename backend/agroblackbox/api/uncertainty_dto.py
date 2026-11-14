"""Request/response models for the Uncertainty Hunter (ABB-19).

No model carries a numeric score, weight, probability, confidence or value-of-information
estimate. Answers are FARMER_REPORTED evidence with an explicit origin, units and review state.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field as PydanticField, model_validator

from .. import schemas
from ..comparability import KoppenClass
from ..farm_profile import FarmProfile
from ..uncertainty import Gap, GapCause, Prioritisation, QuestionKind, QuestionResolution, QuestionView
from .dto import RequestModel, UserSummary
from .evidence_dto import CountryCode, Text40, Text1000, Text2000, Text5000

AnswerOrigin = Literal["FARMER_REPORTED", "LOCAL_MEASUREMENT", "FIELD_RECORD", "ADVISOR_REPORT"]
AnswerStatus = Literal["ANSWERED", "REVIEWED", "REJECTED", "SUPERSEDED"]
QuestionAction = Literal["ANSWERED", "REVIEWED", "REJECTED", "DISMISSED", "REOPENED"]

ANSWER_LIMITATIONS = [
    "FARMER_REPORTED: entered by a case member. A LOCAL_MEASUREMENT or FIELD_RECORD origin describes what the "
    "author says the value comes from; CropStory has not verified the instrument or document.",
    "REVIEWED means a case member other than the author checked the answer against the documentation available to "
    "them; it does not make it an independent measurement.",
    "Answers never change hypotheses, observations, claims, profiles or rotation results automatically.",
]


# ── requests ─────────────────────────────────────────────────────────────────

class UncertaintyRequest(RequestModel):
    """Optional request-only inputs; nothing here is stored."""
    farm_profile: FarmProfile | None = PydanticField(
        default=None, description="ABB-11 profile (FARMER_REPORTED); adds profile, rotation and ordering gaps")
    country_code: CountryCode | None = PydanticField(default=None, description="ISO 3166-1 alpha-2, stated by a person")
    koppen_climate: KoppenClass | None = None
    horizon_years: int | None = PydanticField(default=None, ge=2, le=10)


class AnswerCreate(RequestModel):
    """A local answer. Send ``replaces_answer_id`` = the current answer's id to correct it (409 if stale)."""
    value_text: Text5000 | None = PydanticField(default=None, description="What was found, as text")
    value_number: float | None = PydanticField(default=None, description="Numeric value; requires unit")
    unit: Text40 | None = None
    observed_from: date | None = PydanticField(default=None, description="Start of the period the answer describes")
    observed_to: date | None = None
    origin: AnswerOrigin
    method: Text2000 | None = PydanticField(default=None, description="How it was measured or recorded")
    source_reference: Text1000 | None = PydanticField(
        default=None, description="Where the record is kept (e.g. lab report number); no file is stored")
    note: Text5000 | None = None
    replaces_answer_id: UUID | None = None

    @model_validator(mode="after")
    def _consistent(self) -> AnswerCreate:
        if self.value_text is None and self.value_number is None:
            raise ValueError("an answer needs value_text or value_number")
        if self.value_number is not None and self.unit is None:
            raise ValueError("a numeric value needs a unit")
        if self.observed_from and self.observed_to and self.observed_to < self.observed_from:
            raise ValueError("observed_to must not be before observed_from")
        if self.origin == "LOCAL_MEASUREMENT" and self.method is None:
            raise ValueError("a LOCAL_MEASUREMENT needs the method (instrument, laboratory method or protocol)")
        return self


class AnswerReview(RequestModel):
    version: int = PydanticField(ge=1, description="Current answer version")
    decision: Literal["REVIEWED", "REJECTED"]
    note: Text5000 = PydanticField(description="What was checked, or why the answer is not accepted")


class ResolutionChange(RequestModel):
    note: Text5000 = PydanticField(description="Why the question is dismissed or reopened")


# ── responses ────────────────────────────────────────────────────────────────

class ReportInputs(schemas.ContractModel):
    farm_profile_supplied: bool
    country_code: str | None
    koppen_climate: str | None
    rotation_status: str | None = PydanticField(description="ABB-17 comparison status when a profile was supplied")


class ReportSummary(schemas.ContractModel):
    gaps: int
    gaps_by_cause: dict[GapCause, int]
    questions: int
    open_questions: int
    gaps_not_answerable_locally: int


class UncertaintyReport(schemas.ContractModel):
    case_id: UUID
    case_version: int
    generated_at: datetime
    method_version: str
    stored: Literal[False] = False
    inputs: ReportInputs
    summary: ReportSummary
    gaps: list[Gap]
    questions: list[QuestionView]
    prioritisation: Prioritisation
    limitations: list[str]


class AnswerView(schemas.ContractModel):
    id: UUID
    case_id: UUID
    question_id: str
    question: str
    kind: Literal["FARMER_REPORTED"] = "FARMER_REPORTED"
    source_kind: Literal[schemas.SourceKind.FARMER_REPORTED] = schemas.SourceKind.FARMER_REPORTED
    value_text: str | None
    value_number: float | None
    unit: str | None
    observed_from: date | None
    observed_to: date | None
    origin: AnswerOrigin
    method: str | None
    source_reference: str | None
    note: str | None
    status: AnswerStatus
    is_reviewed: bool
    answered_by: UserSummary | None
    answered_at: datetime
    reviewed_by: UserSummary | None
    reviewed_at: datetime | None
    review_note: str | None
    superseded_by_id: UUID | None
    superseded_at: datetime | None
    version: int
    can_review: bool
    limitations: list[str]


class AnswerList(schemas.ContractModel):
    items: list[AnswerView]
    limitations: list[str]


class QuestionEventView(schemas.ContractModel):
    id: UUID
    question_id: str
    action: QuestionAction
    answer_id: UUID | None
    actor: UserSummary | None
    created_at: datetime
    from_status: str
    to_status: str
    note: str | None
    changes: dict


class QuestionHistory(schemas.ContractModel):
    case_id: UUID
    question_id: str
    question: str | None
    resolution: QuestionResolution
    events: list[QuestionEventView]
    answers: list[AnswerView]


class CatalogueItem(schemas.ContractModel):
    id: str
    kind: QuestionKind
    category: str
    question: str
    why_it_matters: str
    measurement: str
    units: list[str]
    answer_route: str | None


class QuestionCatalogue(schemas.ContractModel):
    method_version: str
    items: list[CatalogueItem]
    limitations: list[str]
