"""Request/response models for claim disagreements and study applicability (ABB-15).

No model here carries a numeric score, weight, probability or confidence: comparisons are
per-dimension categories with a written reason, and disagreements need a human decision.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field as PydanticField

from .. import schemas
from ..comparability import (
    ComparabilityNote,
    Dimension,
    DisagreementKind,
    EffectDirection,
    KoppenClass,
    TransferNote,
    TransferStatus,
)
from ..farm_profile import FarmProfile
from .dto import RequestModel, UserSummary
from .evidence_dto import CountryCode, PaperSummary, StudyDesign, Text5000

DisagreementDecision = Literal["CONFIRMED_CONTRADICTION", "NOT_COMPARABLE", "INCONCLUSIVE"]
DisagreementStatus = Literal["CANDIDATE", "CONFIRMED_CONTRADICTION", "NOT_COMPARABLE", "INCONCLUSIVE"]


# ── disagreements ────────────────────────────────────────────────────────────

class DisagreementReviewRequest(RequestModel):
    """Send the claim versions you compared; 409 if either claim changed since."""
    decision: DisagreementDecision
    note: Text5000 = PydanticField(description="Why: what was compared and what explains the decision")
    claim_a_version: int = PydanticField(ge=1)
    claim_b_version: int = PydanticField(ge=1)


class DisagreementClaimRef(schemas.ContractModel):
    """One side of a disagreement, with its bibliographic reference."""
    claim_id: UUID
    claim_version: int
    claim_text: str
    intervention: str | None
    comparator: str | None
    outcome_variable: str | None
    effect_direction: EffectDirection
    study_design: StudyDesign
    review_status: schemas.ReviewStatus
    is_reviewed: bool
    source_kind: schemas.SourceKind
    paper: PaperSummary


class DisagreementReviewView(schemas.ContractModel):
    id: UUID
    decision: DisagreementDecision
    note: str
    reviewer: UserSummary | None
    reviewed_at: datetime
    claim_a_version: int
    claim_b_version: int
    applies_to_current_versions: bool


class DisagreementView(schemas.VersionedContract):
    id: UUID = PydanticField(description="Stable id of the claim pair")
    case_id: UUID
    kind: DisagreementKind
    status: DisagreementStatus
    matched_on: dict[Literal["intervention", "outcome_variable"], str]
    claim_a: DisagreementClaimRef
    claim_b: DisagreementClaimRef
    both_claims_reviewed: bool
    comparability_notes: list[ComparabilityNote]
    current_review: DisagreementReviewView | None = None
    reviews: list[DisagreementReviewView] = PydanticField(default_factory=list, description="Oldest first")
    warnings: list[str]
    can_review: bool


class ClaimNotCompared(schemas.ContractModel):
    claim_id: UUID
    reasons: list[str]


class DisagreementList(schemas.VersionedContract):
    case_id: UUID
    items: list[DisagreementView]
    claims_not_compared: list[ClaimNotCompared]
    method_version: str
    limitations: list[str]


# ── applicability ────────────────────────────────────────────────────────────

class ApplicabilityRequest(RequestModel):
    """Case conditions to compare with the claim's study. Everything is optional; missing → UNKNOWN.

    Nothing is stored. Stored case crop history is used when the farm profile has no crop history;
    coordinates are never used.
    """
    farm_profile: FarmProfile | None = PydanticField(default=None, description="ABB-11 farm profile (stateless)")
    country_code: CountryCode | None = PydanticField(default=None, description="ISO 3166-1 alpha-2 of the case")
    koppen_climate: KoppenClass | None = PydanticField(default=None, description="Koppen-Geiger class of the case")


class ApplicabilityReport(schemas.VersionedContract):
    """Transferability notes for one claim and one case. Deliberately no score."""
    case_id: UUID
    claim_id: UUID
    claim_version: int
    claim_review_status: schemas.ReviewStatus
    is_reviewed: bool
    study_design: StudyDesign
    paper: PaperSummary
    dimensions: list[TransferNote]
    transfer_status: TransferStatus
    differing_dimensions: list[Dimension]
    unknown_dimensions: list[Dimension]
    notes: list[str]
    stored: Literal[False] = False
    method_version: str
    limitations: list[str]
