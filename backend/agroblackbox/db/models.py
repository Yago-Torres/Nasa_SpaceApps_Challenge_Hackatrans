from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, ForeignKeyConstraint,
    Integer, String, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class IdMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)


class User(IdMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # ABB-05: scrypt hash (see agroblackbox.security); NULL means the account cannot log in.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("failed_login_count >= 0", name="ck_user_failed_logins"),)


class AuthSession(IdMixin, Base):
    """Opaque bearer session. Only the SHA-256 digest of the token is stored (ABB-05)."""
    __tablename__ = "sessions"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("expires_at > created_at", name="ck_session_expiry"),)


CASE_STATUSES = ("DRAFT", "INVESTIGATING", "REVIEWED", "PUBLISHED")


class Case(IdMixin, Base):
    __tablename__ = "cases"
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    incident_start: Mapped[date] = mapped_column(Date)
    incident_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    crop_history: Mapped[list[str]] = mapped_column(JSONB, default=list)
    incident_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(String(32), default="PRIVATE")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    # ABB-06 workflow; transitions and roles are enforced in agroblackbox.api.cases.
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", server_default=text("'DRAFT'"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("incident_end IS NULL OR incident_end >= incident_start", name="ck_case_dates"),
        CheckConstraint("visibility IN ('PRIVATE','SHARED','PUBLIC_ROUNDED')", name="ck_case_visibility"),
        CheckConstraint("version >= 1", name="ck_case_version"),
        CheckConstraint(
            "status IN ('DRAFT','INVESTIGATING','REVIEWED','PUBLISHED')", name="ck_case_status"
        ),
    )


class CaseHistory(IdMixin, Base):
    """Append-only audit of every case change: author, time, resulting version, before/after."""
    __tablename__ = "case_history"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (CheckConstraint("version >= 1", name="ck_case_history_version"),)


class CasePermission(IdMixin, Base):
    __tablename__ = "case_permissions"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(24))
    __table_args__ = (
        UniqueConstraint("case_id", "user_id"),
        CheckConstraint("role IN ('OWNER','EDITOR','REVIEWER','VIEWER')", name="ck_permission_role"),
    )


class Field(IdMixin, Base):
    __tablename__ = "fields"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(160))
    privacy_tier: Mapped[str] = mapped_column(String(24))
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    region_label: Mapped[str] = mapped_column(String(160))
    area_hectares: Mapped[float | None] = mapped_column(Float, nullable=True)
    precise_location_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    limitations: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # ABB-06: grid step (degrees) used to approximate the location for collaborators.
    rounding_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (
        CheckConstraint("rounding_deg IS NULL OR rounding_deg IN (0.1, 0.5, 1.0)", name="ck_field_rounding"),
        CheckConstraint(
            "privacy_tier != 'APPROXIMATE' OR rounding_deg IS NOT NULL", name="ck_field_approximate_rounding"
        ),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="ck_field_coordinate_pair"),
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="ck_field_latitude"),
        CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="ck_field_longitude"),
        CheckConstraint("privacy_tier != 'WITHHELD' OR latitude IS NULL", name="ck_field_withheld"),
        CheckConstraint("privacy_tier != 'EXACT' OR (latitude IS NOT NULL AND precise_location_consent)", name="ck_field_exact_consent"),
    )


class SourceManifest(IdMixin, Base):
    __tablename__ = "source_manifests"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(120))
    dataset: Mapped[str] = mapped_column(String(200))
    source_uri: Mapped[str] = mapped_column(Text)
    query_parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    dataset_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    processing_version: Mapped[str] = mapped_column(String(120))
    license: Mapped[str | None] = mapped_column(String(200), nullable=True)
    spatial_resolution: Mapped[dict[str, Any]] = mapped_column(JSONB)
    temporal_resolution: Mapped[dict[str, Any]] = mapped_column(JSONB)
    limitations: Mapped[list[str]] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("id", "case_id", name="uq_manifest_case"),)


class Observation(IdMixin, Base):
    __tablename__ = "observations"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    source_manifest_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), default="OBSERVED")
    variable: Mapped[str] = mapped_column(String(120))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    units: Mapped[str] = mapped_column(String(40))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    spatial_resolution: Mapped[dict[str, Any]] = mapped_column(JSONB)
    temporal_resolution: Mapped[dict[str, Any]] = mapped_column(JSONB)
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSONB)
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_manifest_id", "case_id"],
            ["source_manifests.id", "source_manifests.case_id"],
            ondelete="RESTRICT",
            name="fk_observation_manifest_same_case",
        ),
    )


class Hypothesis(IdMixin, Base):
    __tablename__ = "hypotheses"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    statement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    supporting_evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    contradicting_evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    missing_evidence: Mapped[list[str]] = mapped_column(JSONB, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSONB)


class Paper(IdMixin, Base):
    __tablename__ = "papers"
    title: Mapped[str] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    doi_id: Mapped[str | None] = mapped_column(String(300), nullable=True, unique=True)
    doi_status: Mapped[str] = mapped_column(String(40))
    openalex_id: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    bibliographic_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB)
    limitations: Mapped[list[str]] = mapped_column(JSONB)


CLAIM_REVIEW_STATUSES = ("PENDING", "ACCEPTED", "CHANGES_REQUESTED", "REJECTED")
STUDY_DESIGNS = (
    "META_ANALYSIS", "SYSTEMATIC_REVIEW", "FIELD_EXPERIMENT", "CONTROLLED_EXPERIMENT",
    "OBSERVATIONAL_STUDY", "MODELLING_STUDY", "NARRATIVE_REVIEW", "OTHER", "UNKNOWN",
)
EVIDENCE_BASES = ("METADATA_ONLY", "ABSTRACT", "FULL_TEXT")
ACCESS_BASES = (
    "NONE", "PUBLIC_ABSTRACT", "OPEN_ACCESS_LICENSE", "PUBLISHER_FREE_TO_READ",
    "INSTITUTIONAL_SUBSCRIPTION", "AUTHOR_PROVIDED_COPY",
)
CLAIM_ORIGINS = ("MANUAL", "PILOT_SEED_UNVERIFIED")
CLAIM_EVENT_ACTIONS = ("CREATED", "UPDATED", "REVIEWED")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{value}'" for value in values) + ")"


class EvidenceClaim(IdMixin, Base):
    """Case-scoped claim extracted from a registered paper (ABB-14).

    ``source_kind`` is derived, never stored: LITERATURE_REVIEWED only while ``review_status`` is
    ACCEPTED. ``reviewed_by``/``reviewed_at`` describe the latest review decision; the full trail is in
    ``evidence_claim_events``.
    """
    __tablename__ = "evidence_claims"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[UUID] = mapped_column(ForeignKey("papers.id", ondelete="RESTRICT"), index=True)
    claim_text: Mapped[str] = mapped_column(Text)
    study_context: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    limitations: Mapped[list[str]] = mapped_column(JSONB)
    # ABB-14 structured record, review workflow and provenance of the claim itself.
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=text("now()"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    study_design: Mapped[str] = mapped_column(String(32), default="UNKNOWN", server_default=text("'UNKNOWN'"))
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    reported_outcome: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    source_locator: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    quoted_fragment: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_basis: Mapped[str] = mapped_column(
        String(24), default="METADATA_ONLY", server_default=text("'METADATA_ONLY'")
    )
    access_basis: Mapped[str] = mapped_column(String(32), default="NONE", server_default=text("'NONE'"))
    content_license: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(String(32), default="MANUAL", server_default=text("'MANUAL'"))
    origin_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    __table_args__ = (
        UniqueConstraint("case_id", "origin_ref", name="uq_claim_case_origin_ref"),
        CheckConstraint("version >= 1", name="ck_claim_version"),
        CheckConstraint(_in("review_status", CLAIM_REVIEW_STATUSES), name="ck_claim_review_status"),
        CheckConstraint(_in("study_design", STUDY_DESIGNS), name="ck_claim_study_design"),
        CheckConstraint(_in("evidence_basis", EVIDENCE_BASES), name="ck_claim_evidence_basis"),
        CheckConstraint(_in("access_basis", ACCESS_BASES), name="ck_claim_access_basis"),
        CheckConstraint(_in("origin", CLAIM_ORIGINS), name="ck_claim_origin"),
        CheckConstraint(
            "review_status != 'PENDING' OR (reviewed_by IS NULL AND reviewed_at IS NULL)",
            name="ck_claim_pending_unreviewed",
        ),
        CheckConstraint(
            "review_status = 'PENDING' OR reviewed_at IS NOT NULL", name="ck_claim_decision_timestamp"
        ),
        CheckConstraint(
            "review_status != 'ACCEPTED' OR reviewed_by IS NOT NULL", name="ck_claim_accepted_reviewer"
        ),
        CheckConstraint(
            "created_by IS NULL OR reviewed_by IS NULL OR created_by != reviewed_by", name="ck_claim_no_self_review"
        ),
        CheckConstraint(
            "quoted_fragment IS NULL OR evidence_basis != 'METADATA_ONLY'", name="ck_claim_quote_needs_source_text"
        ),
        CheckConstraint(
            "evidence_basis != 'FULL_TEXT' OR (access_basis NOT IN ('NONE','PUBLIC_ABSTRACT') "
            "AND content_license IS NOT NULL)",
            name="ck_claim_full_text_access",
        ),
    )


class EvidenceClaimEvent(IdMixin, Base):
    """Append-only trail of a claim: creation, edits and every review decision (ABB-14).

    Review events keep the reviewer, time, note, the source the reviewer consulted and a snapshot
    of the paper identity at that moment. The actor FK is RESTRICT so the reviewer is never lost.
    """
    __tablename__ = "evidence_claim_events"
    claim_id: Mapped[UUID] = mapped_column(ForeignKey("evidence_claims.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    claim_version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(24))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_consulted: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    paper_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    __table_args__ = (
        CheckConstraint("claim_version >= 1", name="ck_claim_event_version"),
        CheckConstraint(_in("action", CLAIM_EVENT_ACTIONS), name="ck_claim_event_action"),
        CheckConstraint(_in("to_status", CLAIM_REVIEW_STATUSES), name="ck_claim_event_to_status"),
        CheckConstraint(
            "action != 'REVIEWED' OR (note IS NOT NULL AND source_consulted IS NOT NULL "
            "AND from_status IS NOT NULL AND to_status != 'PENDING')",
            name="ck_claim_event_review_complete",
        ),
    )


class Rotation(IdMixin, Base):
    __tablename__ = "rotations"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    source_kind: Mapped[str] = mapped_column(String(32))
    years: Mapped[list[list[str]]] = mapped_column(JSONB)
    assumptions: Mapped[list[str]] = mapped_column(JSONB)
    constraints: Mapped[list[str]] = mapped_column(JSONB, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSONB)


class Review(IdMixin, Base):
    __tablename__ = "reviews"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(32))
    comment: Mapped[str] = mapped_column(Text)
    target_kind: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Report(IdMixin, Base):
    __tablename__ = "reports"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(24), default="PRELIMINARY")
    format: Mapped[str] = mapped_column(String(16))
    content_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_manifest_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("case_id", "version"),)
