"""Request/response models for registered papers and case evidence claims (ABB-14).

Responses extend the shared ABB-02 contracts (``schemas.Paper`` / ``schemas.EvidenceClaim``)
additively. Outcome values, units and uncertainty are stored as text *as stated in the source*:
nothing here parses, converts or computes an effect size.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field as PydanticField, HttpUrl, JsonValue, StringConstraints, model_validator

from .. import schemas
from .dto import Limitation, RequestModel, UserSummary

StudyDesign = Literal[
    "META_ANALYSIS", "SYSTEMATIC_REVIEW", "FIELD_EXPERIMENT", "CONTROLLED_EXPERIMENT",
    "OBSERVATIONAL_STUDY", "MODELLING_STUDY", "NARRATIVE_REVIEW", "OTHER", "UNKNOWN",
]
EvidenceBasis = Literal["METADATA_ONLY", "ABSTRACT", "FULL_TEXT"]
AccessBasis = Literal[
    "NONE", "PUBLIC_ABSTRACT", "OPEN_ACCESS_LICENSE", "PUBLISHER_FREE_TO_READ",
    "INSTITUTIONAL_SUBSCRIPTION", "AUTHOR_PROVIDED_COPY",
]
ReviewDecisionKind = Literal["ACCEPTED", "REJECTED", "CHANGES_REQUESTED"]
ClaimOrigin = Literal["MANUAL", "PILOT_SEED_UNVERIFIED"]
DoiStatus = Literal[
    "VERIFIED_CROSSREF", "METADATA_MISMATCH", "NOT_FOUND_IN_CROSSREF",
    "VERIFICATION_UNAVAILABLE", "MALFORMED_DOI", "NO_DOI",
]

#: Access that legitimately allows reading/processing the full text.
FULL_TEXT_ACCESS: frozenset[str] = frozenset({
    "OPEN_ACCESS_LICENSE", "PUBLISHER_FREE_TO_READ", "INSTITUTIONAL_SUBSCRIPTION", "AUTHOR_PROVIDED_COPY",
})
ABSTRACT_ACCESS: frozenset[str] = FULL_TEXT_ACCESS | {"PUBLIC_ABSTRACT"}
MAX_QUOTE = 500


def _text(max_length: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)]


Text40 = _text(40)
Text80 = _text(80)
Text120 = _text(120)
Text200 = _text(200)
Text300 = _text(300)
Text500 = _text(500)
Text1000 = _text(1_000)
Text2000 = _text(2_000)
Text5000 = _text(5_000)
Term = Text120


def check_access(basis: str, access: str, license_: str | None, *, what: str) -> None:
    """Shared rule for claims and review evidence: full text needs legitimate access and a licence."""
    if basis == "FULL_TEXT":
        if access not in FULL_TEXT_ACCESS:
            raise ValueError(f"{what}: FULL_TEXT requires legitimate full-text access "
                             f"({', '.join(sorted(FULL_TEXT_ACCESS))})")
        if not license_:
            raise ValueError(f"{what}: FULL_TEXT requires the licence or access terms of the text consulted")
    elif basis == "ABSTRACT" and access not in ABSTRACT_ACCESS:
        raise ValueError(f"{what}: ABSTRACT requires PUBLIC_ABSTRACT or a full-text access basis")


def license_key(value: str) -> str:
    return value.strip().casefold().removeprefix("https://").removeprefix("http://").rstrip("/")


# ── papers ───────────────────────────────────────────────────────────────────

class PaperRegistration(RequestModel):
    """Identify a work; the server fetches and verifies its metadata. No metadata is accepted."""
    doi: Text300 | None = PydanticField(default=None, description="DOI, doi: or https://doi.org/ form")
    openalex_id: Text120 | None = PydanticField(default=None, description="W123… or https://openalex.org/W123…")

    @model_validator(mode="after")
    def _exactly_one(self) -> PaperRegistration:
        if (self.doi is None) == (self.openalex_id is None):
            raise ValueError("provide exactly one of doi or openalex_id")
        return self


class PaperView(schemas.Paper):
    """Shared ``Paper`` plus the ABB-13 caveat and source label (bibliographic metadata only)."""
    source: str
    caveat: str


class PaperSummary(schemas.ContractModel):
    id: UUID
    title: str
    year: int | None = None
    doi: str | None = None
    doi_id: str | None = None
    doi_status: DoiStatus
    openalex_id: str | None = None
    is_open_access: bool | None = None
    licenses: list[str] = PydanticField(default_factory=list)
    caveat: str


# ── claims ───────────────────────────────────────────────────────────────────

class ClaimContext(RequestModel):
    """Conditions of the study as reported by the paper (not of the farm)."""
    population: Text500 | None = None
    crops: list[Term] = PydanticField(default_factory=list, max_length=30)
    soils: list[Term] = PydanticField(default_factory=list, max_length=20)
    region: Text300 | None = None
    climate: Text500 | None = None
    management: Text1000 | None = PydanticField(default=None, description="Practices / intervention studied")


class ReportedOutcome(RequestModel):
    """Outcome exactly as stated in the source; values are text, never parsed or recomputed."""
    outcome: Text1000 | None = PydanticField(default=None, description="What was measured")
    comparison: Text500 | None = PydanticField(default=None, description="Compared with what")
    effect_as_stated: Text300 | None = None
    units_as_stated: Text80 | None = None
    uncertainty_as_stated: Text300 | None = None
    sample_as_stated: Text300 | None = None

    def has_quantities(self) -> bool:
        return any((self.effect_as_stated, self.units_as_stated, self.uncertainty_as_stated, self.sample_as_stated))


class SourceLocator(RequestModel):
    page: Text40 | None = None
    section: Text200 | None = None
    figure_or_table: Text120 | None = None


class ClaimContent(RequestModel):
    claim_text: Text2000
    study_context: Text5000 = PydanticField(description="Free-text summary of the study context")
    study_design: StudyDesign = "UNKNOWN"
    context: ClaimContext = PydanticField(default_factory=ClaimContext)
    reported_outcome: ReportedOutcome = PydanticField(default_factory=ReportedOutcome)
    source_locator: SourceLocator = PydanticField(default_factory=SourceLocator)
    quoted_fragment: Text500 | None = PydanticField(
        default=None, description=f"Short attributed quotation (≤{MAX_QUOTE} characters)")
    evidence_basis: EvidenceBasis = PydanticField(description="What the claim author actually read")
    access_basis: AccessBasis = "NONE"
    content_license: Text500 | None = PydanticField(
        default=None, description="Licence/terms under which the text was read (required for FULL_TEXT)")
    limitations: list[Limitation] = PydanticField(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _evidence_rules(self) -> ClaimContent:
        check_access(self.evidence_basis, self.access_basis, self.content_license, what="claim")
        if self.quoted_fragment is not None:
            if self.evidence_basis == "METADATA_ONLY":
                raise ValueError("a quoted fragment requires that the abstract or full text was read")
            if not (self.source_locator.page or self.source_locator.section or self.source_locator.figure_or_table):
                raise ValueError("a quoted fragment must be attributed with a page, section or figure/table")
        if self.evidence_basis == "METADATA_ONLY" and self.reported_outcome.has_quantities():
            raise ValueError("effects, units, uncertainty or sample size cannot come from metadata alone")
        return self


class ClaimCreate(ClaimContent):
    paper_id: UUID


class ClaimPatch(RequestModel):
    """Partial update; the merged claim is re-validated. Any change returns the claim to PENDING."""
    version: int = PydanticField(ge=1)
    claim_text: Text2000 | None = None
    study_context: Text5000 | None = None
    study_design: StudyDesign | None = None
    context: ClaimContext | None = None
    reported_outcome: ReportedOutcome | None = None
    source_locator: SourceLocator | None = None
    quoted_fragment: Text500 | None = None
    evidence_basis: EvidenceBasis | None = None
    access_basis: AccessBasis | None = None
    content_license: Text500 | None = None
    limitations: list[Limitation] | None = PydanticField(default=None, min_length=1, max_length=20)

    @model_validator(mode="after")
    def _not_null(self) -> ClaimPatch:
        nullable = {"quoted_fragment", "content_license"}
        for name in self.model_fields_set - nullable - {"version"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class SourceConsulted(RequestModel):
    """What the reviewer actually checked. Stored with the decision."""
    basis: EvidenceBasis
    access_basis: AccessBasis
    license: Text500 | None = PydanticField(default=None, description="Licence/terms of the text consulted")
    locator: Text300 | None = PydanticField(default=None, description="Pages/sections/tables checked")
    consulted_url: HttpUrl | None = None

    @model_validator(mode="after")
    def _access(self) -> SourceConsulted:
        check_access(self.basis, self.access_basis, self.license, what="source_consulted")
        return self


class ReviewDecision(RequestModel):
    version: int = PydanticField(ge=1)
    decision: ReviewDecisionKind
    note: Text5000
    source_consulted: SourceConsulted

    @model_validator(mode="after")
    def _accept_needs_full_text(self) -> ReviewDecision:
        if self.decision == "ACCEPTED" and self.source_consulted.basis != "FULL_TEXT":
            raise ValueError("ACCEPTED requires that the reviewer checked the full text; an abstract is not enough")
        return self


class ClaimContextView(schemas.ContractModel):
    population: str | None = None
    crops: list[str] = PydanticField(default_factory=list)
    soils: list[str] = PydanticField(default_factory=list)
    region: str | None = None
    climate: str | None = None
    management: str | None = None


class ReportedOutcomeView(schemas.ContractModel):
    outcome: str | None = None
    comparison: str | None = None
    effect_as_stated: str | None = None
    units_as_stated: str | None = None
    uncertainty_as_stated: str | None = None
    sample_as_stated: str | None = None


class SourceLocatorView(schemas.ContractModel):
    page: str | None = None
    section: str | None = None
    figure_or_table: str | None = None


class ClaimView(schemas.EvidenceClaim):
    """Shared ``EvidenceClaim`` plus structure, workflow and display flags.

    ``source_kind`` is LITERATURE_REVIEWED and ``is_reviewed`` true only for ACCEPTED claims.
    """
    case_id: UUID
    version: int = PydanticField(ge=1)
    is_reviewed: bool
    reviewer: UserSummary | None = None
    created_by: UserSummary | None = None
    created_at: datetime
    updated_at: datetime
    paper: PaperSummary
    study_design: StudyDesign
    context: ClaimContextView
    reported_outcome: ReportedOutcomeView
    source_locator: SourceLocatorView
    quoted_fragment: str | None = None
    evidence_basis: EvidenceBasis
    access_basis: AccessBasis
    content_license: str | None = None
    origin: ClaimOrigin
    origin_ref: str | None = None
    warnings: list[str] = PydanticField(default_factory=list)
    can_edit: bool
    can_review: bool

    @model_validator(mode="after")
    def _reviewed_flag_matches_kind(self) -> ClaimView:
        reviewed = self.source_kind == schemas.SourceKind.LITERATURE_REVIEWED
        if reviewed != self.is_reviewed or reviewed != (self.review_status == schemas.ReviewStatus.ACCEPTED):
            raise ValueError("only ACCEPTED claims are reviewed literature")
        return self


class ClaimList(schemas.ContractModel):
    items: list[ClaimView]
    reviewed_count: int
    unreviewed_count: int
    limitations: list[str]


class SourceConsultedView(schemas.ContractModel):
    basis: EvidenceBasis
    access_basis: AccessBasis
    license: str | None = None
    locator: str | None = None
    consulted_url: str | None = None


class ClaimEventView(schemas.ContractModel):
    id: UUID
    claim_id: UUID
    claim_version: int
    action: Literal["CREATED", "UPDATED", "REVIEWED"]
    actor: UserSummary | None
    created_at: datetime
    from_status: schemas.ReviewStatus | None = None
    to_status: schemas.ReviewStatus
    note: str | None = None
    source_consulted: SourceConsultedView | None = None
    paper_snapshot: dict[str, str | int | bool | None]
    changes: dict[str, JsonValue] = PydanticField(default_factory=dict)


class PilotImportItem(schemas.ContractModel):
    seed_id: str
    doi: str
    reason: str


class PilotImportResult(schemas.ContractModel):
    created: list[ClaimView]
    skipped: list[PilotImportItem]
    failed: list[PilotImportItem]
    limitations: list[str]
