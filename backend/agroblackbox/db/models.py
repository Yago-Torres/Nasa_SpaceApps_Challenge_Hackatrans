from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, ForeignKeyConstraint,
    Index, Integer, String, Text, UniqueConstraint, Uuid, text,
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
    # ABB-10 case-bound ingestion. ``query_parameters`` may hold the field's precise
    # coordinates and is only served to OWNER/EDITOR (see agroblackbox.api.observations).
    field_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=text("now()")
    )
    # SHA-256 of {provider, field, event year, reference window}; one active manifest per key.
    ingestion_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SHA-256 of the canonical returned values (no coordinates), used to detect re-ingestion
    # of unchanged data even though the raw-byte checksum changes between retrievals.
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    event_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    __table_args__ = (
        UniqueConstraint("id", "case_id", name="uq_manifest_case"),
        CheckConstraint("revision >= 1", name="ck_manifest_revision"),
        Index("ix_source_manifests_case_ingestion_key", "case_id", "ingestion_key"),
    )


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
    # ABB-10: aggregation period of the value and its daily coverage (status, day counts, reason).
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_manifest_id", "case_id"],
            ["source_manifests.id", "source_manifests.case_id"],
            ondelete="RESTRICT",
            name="fk_observation_manifest_same_case",
        ),
        CheckConstraint(
            "period_start IS NULL OR period_end IS NULL OR period_end >= period_start",
            name="ck_observation_period",
        ),
        UniqueConstraint("id", "case_id", name="uq_observation_case"),
    )


class Anomaly(IdMixin, Base):
    """Descriptive monthly anomaly of one observation against its reference years (ABB-08/10)."""
    __tablename__ = "anomalies"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    observation_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    units: Mapped[str] = mapped_column(String(40))
    method: Mapped[str] = mapped_column(String(300))
    reference_start: Mapped[date] = mapped_column(Date)
    reference_end: Mapped[date] = mapped_column(Date)
    reference_sample_count: Mapped[int] = mapped_column(Integer)
    reference_status: Mapped[str] = mapped_column(String(16))
    reference_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_standard_deviation: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_minimum: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_maximum: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_years_excluded: Mapped[list[int]] = mapped_column(JSONB, default=list)
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        ForeignKeyConstraint(
            ["observation_id", "case_id"],
            ["observations.id", "observations.case_id"],
            ondelete="CASCADE",
            name="fk_anomaly_observation_same_case",
        ),
        CheckConstraint("reference_end >= reference_start", name="ck_anomaly_reference_dates"),
        CheckConstraint("reference_sample_count >= 0", name="ck_anomaly_sample_count"),
        CheckConstraint(
            "reference_status IN ('complete','reduced','insufficient')", name="ck_anomaly_reference_status"
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
    # ABB-10: rival-hypothesis workflow. No numeric probability or causal score is stored.
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    origin: Mapped[str] = mapped_column(String(16), default="USER", server_default=text("'USER'"))
    template_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verification_questions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    evaluation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluated_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=text("now()"))
    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN','SUPPORTED','CHALLENGED','REJECTED','COMPATIBLE','CONTRADICTED','NOT_EVALUABLE')",
            name="ck_hypothesis_status",
        ),
        CheckConstraint("origin IN ('USER','TEMPLATE')", name="ck_hypothesis_origin"),
        CheckConstraint("version >= 1", name="ck_hypothesis_version"),
        UniqueConstraint("case_id", "template_code", name="uq_hypothesis_case_template"),
    )


class Paper(IdMixin, Base):
    __tablename__ = "papers"
    title: Mapped[str] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    doi_id: Mapped[str | None] = mapped_column(String(300), nullable=True, unique=True)
    doi_status: Mapped[str] = mapped_column(String(40))
    openalex_id: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    bibliographic_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB)
    limitations: Mapped[list[str]] = mapped_column(JSONB)


class EvidenceClaim(IdMixin, Base):
    __tablename__ = "evidence_claims"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    paper_id: Mapped[UUID] = mapped_column(ForeignKey("papers.id", ondelete="RESTRICT"), index=True)
    claim_text: Mapped[str] = mapped_column(Text)
    study_context: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    limitations: Mapped[list[str]] = mapped_column(JSONB)


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
