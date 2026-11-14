"""Request/response models for collaboration: invitations, comments, activity and share links (ABB-25).

Free text from people (comments, invitation notes, share labels) is plain text: control and bidirectional
formatting characters are removed, line endings are normalised and nothing else is changed. The API never
renders or interprets markup; clients must display these strings as text (never as HTML).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, Field as PydanticField, JsonValue, model_validator

from .. import schemas
from ..db.models import COMMENT_MAX_LENGTH
from .dto import EmailField, GrantableRole, RequestModel, Role, UserSummary

# C0/C1 controls except TAB and LF, zero-width space/marks and bidi overrides/isolates (Trojan-source
# style reordering), and the BOM. ZWJ/ZWNJ (U+200C/U+200D) are kept: scripts and emoji need them.
_UNSAFE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f​‎‏‪-‮⁦-⁩﻿]")

INVITATION_DEFAULT_DAYS = 14
INVITATION_MAX_DAYS = 30
SHARE_DEFAULT_DAYS = 14
SHARE_MAX_DAYS = 30
BODY_FORMAT = "text/plain"


def clean_text(value: str) -> str:
    """NFC, ``\\n`` line endings, unsafe invisible characters removed, outer whitespace stripped."""
    value = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    return _UNSAFE.sub("", value).strip()


def _bounded(max_length: int):
    def check(value: str) -> str:
        value = clean_text(value)
        if not value:
            raise ValueError("must contain visible text")
        if len(value) > max_length:
            raise ValueError(f"must be at most {max_length} characters")
        return value
    return check


# Raw input is capped generously (control characters may be removed); the cleaned text is checked again.
CommentBody = Annotated[str, PydanticField(min_length=1, max_length=COMMENT_MAX_LENGTH * 2),
                        AfterValidator(_bounded(COMMENT_MAX_LENGTH))]
InvitationNote = Annotated[str, PydanticField(min_length=1, max_length=1000), AfterValidator(_bounded(500))]
ShareLabel = Annotated[str, PydanticField(min_length=1, max_length=240), AfterValidator(_bounded(120))]

CommentTargetKind = Literal[
    "CASE", "FIELD", "OBSERVATION", "ANOMALY", "HYPOTHESIS", "CLAIM", "CONCLUSION", "GRAPH_EDGE", "TIMELINE_EVENT",
]
InvitationStatus = Literal["PENDING", "ACCEPTED", "DECLINED", "REVOKED", "EXPIRED"]
ShareStatus = Literal["ACTIVE", "EXPIRED", "REVOKED"]
LocationDetail = Literal["NONE", "REGION", "APPROXIMATE"]
SharedPrecision = Literal["APPROXIMATE", "REGION_ONLY", "NONE"]
ActivitySource = Literal["CASE_HISTORY", "CLAIM_EVENT", "DISAGREEMENT_REVIEW", "COMMENT"]
ActivityCategory = Literal["CASE", "WORKFLOW", "PERMISSION", "INVITATION", "SHARING", "EVIDENCE", "REVIEW", "COMMENT"]


# ── invitations ──────────────────────────────────────────────────────────────

class InvitationCreate(EmailField):
    role: GrantableRole
    note: InvitationNote | None = None
    expires_in_days: int = PydanticField(default=INVITATION_DEFAULT_DAYS, ge=1, le=INVITATION_MAX_DAYS)


class InvitationView(schemas.ContractModel):
    """As seen by the case owner (the only role that lists invitations)."""
    id: UUID
    case_id: UUID
    email: str
    role: GrantableRole
    note: str | None
    status: InvitationStatus = PydanticField(description="EXPIRED is derived from expires_at")
    invited_by: UserSummary | None
    created_at: datetime
    expires_at: datetime
    responded_at: datetime | None
    revoked_at: datetime | None


class InvitationList(schemas.ContractModel):
    items: list[InvitationView]


class InvitedCase(schemas.ContractModel):
    id: UUID
    title: str


class ReceivedInvitationView(schemas.ContractModel):
    """A pending invitation addressed to the signed-in account's e-mail."""
    id: UUID
    case: InvitedCase
    role: GrantableRole
    note: str | None
    invited_by: UserSummary | None
    created_at: datetime
    expires_at: datetime


class ReceivedInvitationList(schemas.ContractModel):
    items: list[ReceivedInvitationView]


class InvitationDecision(schemas.ContractModel):
    invitation_id: UUID
    case_id: UUID
    status: Literal["ACCEPTED", "DECLINED"]
    role: Role | None = PydanticField(description="Your role on the case after accepting; null when declined")


# ── comments ─────────────────────────────────────────────────────────────────

class CommentTarget(schemas.ContractModel):
    kind: CommentTargetKind
    id: UUID | None = PydanticField(default=None, description="null when kind is CASE")


class CommentCreate(RequestModel):
    """Top-level comment on the case or a record of it, or a reply (``parent_id``) that inherits the
    parent's target. Replies are one level deep."""
    body: CommentBody
    target_kind: CommentTargetKind = "CASE"
    target_id: UUID | None = None
    parent_id: UUID | None = None

    @model_validator(mode="after")
    def _target(self) -> CommentCreate:
        if self.parent_id is not None:
            if {"target_kind", "target_id"} & self.model_fields_set:
                raise ValueError("a reply inherits its parent's target; omit target_kind and target_id")
        elif (self.target_kind == "CASE") != (self.target_id is None):
            raise ValueError("target_id is required for record targets and must be omitted for CASE")
        return self


class CommentEdit(RequestModel):
    version: int = PydanticField(ge=1, description="Current comment version")
    body: CommentBody


class CommentView(schemas.ContractModel):
    id: UUID
    case_id: UUID
    target: CommentTarget
    parent_id: UUID | None
    author: UserSummary | None
    body: str | None = PydanticField(description="Plain text; null once deleted. Render as text, never as HTML.")
    body_format: Literal["text/plain"] = BODY_FORMAT
    created_at: datetime
    edited_at: datetime | None
    version: int
    revision_count: int = PydanticField(ge=0, description="Number of earlier texts kept in the edit history")
    reply_count: int = PydanticField(ge=0)
    deleted: bool
    deleted_at: datetime | None
    deleted_by: UserSummary | None
    can_edit: bool
    can_delete: bool


class CommentList(schemas.ContractModel):
    items: list[CommentView]
    total: int
    limit: int
    offset: int


class CommentRevisionView(schemas.ContractModel):
    revision: int
    body: str
    body_format: Literal["text/plain"] = BODY_FORMAT
    replaced_at: datetime
    edited_by: UserSummary | None


# ── activity ─────────────────────────────────────────────────────────────────

class ActivityTarget(schemas.ContractModel):
    kind: str
    id: str | None = None


class ActivityEntry(schemas.ContractModel):
    id: str = PydanticField(description="'<source>:<record id>[:<event>]', stable across requests")
    source: ActivitySource
    kind: str
    category: ActivityCategory
    actor: UserSummary | None
    created_at: datetime
    target: ActivityTarget | None
    note: str | None = None
    evidence: dict[str, JsonValue] | None = PydanticField(
        default=None, description="Evidence the source recorded with the action (null when it recorded none)")
    changes: dict[str, JsonValue] | None = PydanticField(
        default=None, description="Before/after values from the case history; coordinates REDACTED for guests")


class ActivityPage(schemas.ContractModel):
    items: list[ActivityEntry]
    total: int
    limit: int
    offset: int
    order: Literal["asc", "desc"]
    sources: list[ActivitySource]


# ── share links ──────────────────────────────────────────────────────────────

class ShareSections(RequestModel):
    """What the owner agrees to show. Every key is required so consent is explicit; nothing is implied."""
    incident_notes: bool
    field_labels: bool
    location_detail: LocationDetail = PydanticField(
        description="NONE: no location; REGION: region labels only; APPROXIMATE: grid-cell centres for "
                    "APPROXIMATE fields, region labels otherwise. Exact points are never shared.")
    hypotheses: bool
    evidence_claims: bool
    conclusions: bool
    member_names: bool = PydanticField(description="false: comment authors appear as 'Member 1', 'Member 2'…")
    comments: bool


class ShareLinkCreate(RequestModel):
    consent: Literal[True] = PydanticField(
        description="Must be true: the owner agrees that anyone holding the link can read the selected sections")
    sections: ShareSections
    label: ShareLabel | None = None
    expires_in_days: int = PydanticField(default=SHARE_DEFAULT_DAYS, ge=1, le=SHARE_MAX_DAYS)


class ShareLinkView(schemas.ContractModel):
    id: UUID
    case_id: UUID
    label: str | None
    sections: ShareSections
    consent_statement: str
    status: ShareStatus
    created_by: UserSummary | None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


class ShareLinkCreated(ShareLinkView):
    token: str = PydanticField(description="Shown once; only its SHA-256 digest is stored")
    path: str = PydanticField(description="Relative API path of the public view")


class ShareLinkList(schemas.ContractModel):
    items: list[ShareLinkView]


class SharedField(schemas.ContractModel):
    label: str
    region_label: str | None
    location_precision: SharedPrecision
    latitude: float | None
    longitude: float | None
    rounding_deg: float | None


class SharedHypothesis(schemas.ContractModel):
    title: str | None
    statement: str
    status: str
    evaluation_note: str | None
    supporting_evidence_count: int
    contradicting_evidence_count: int
    missing_evidence: list[str]
    limitations: list[str]


class SharedPaper(schemas.ContractModel):
    title: str
    year: int | None
    doi: str | None


class SharedClaim(schemas.ContractModel):
    claim_text: str
    review_status: str
    source_kind: str
    study_design: str
    paper: SharedPaper
    limitations: list[str]


class SharedConclusion(schemas.ContractModel):
    title: str | None
    statement: str
    review_status: str
    limitations: list[str]


class SharedComment(schemas.ContractModel):
    ref: str = PydanticField(description="Position-based reference within this view, e.g. 'C3'")
    reply_to: str | None
    author: str
    target_kind: CommentTargetKind
    body: str
    body_format: Literal["text/plain"] = BODY_FORMAT
    created_at: datetime
    edited: bool


class SharedCaseSummary(schemas.ContractModel):
    title: str
    status: str
    incident_start: date
    incident_end: date | None
    crop_history: list[str]
    incident_notes: str | None
    case_version: int
    updated_at: datetime


class SharedCaseView(schemas.ContractModel):
    kind: Literal["CROPSTORY_SHARED_CASE"] = "CROPSTORY_SHARED_CASE"
    generated_at: datetime
    link_expires_at: datetime
    sections: ShareSections
    case: SharedCaseSummary
    fields: list[SharedField]
    hypotheses: list[SharedHypothesis] | None
    evidence_claims: list[SharedClaim] | None
    conclusions: list[SharedConclusion] | None
    comments: list[SharedComment] | None
    limitations: list[str]
