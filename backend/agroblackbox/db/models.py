from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, ForeignKeyConstraint,
    Integer, String, Text, UniqueConstraint, Uuid,
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
    __table_args__ = (
        CheckConstraint("incident_end IS NULL OR incident_end >= incident_start", name="ck_case_dates"),
        CheckConstraint("visibility IN ('PRIVATE','SHARED','PUBLIC_ROUNDED')", name="ck_case_visibility"),
        CheckConstraint("version >= 1", name="ck_case_version"),
    )


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
    __table_args__ = (
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
