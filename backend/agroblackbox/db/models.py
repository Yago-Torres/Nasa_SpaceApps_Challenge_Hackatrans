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
EFFECT_DIRECTIONS = ("INCREASE", "DECREASE", "NO_CLEAR_EFFECT", "MIXED", "NOT_STATED")
DISAGREEMENT_DECISIONS = ("CONFIRMED_CONTRADICTION", "NOT_COMPARABLE", "INCONCLUSIVE")


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
    # ABB-15 comparability fields, entered by people and matched exactly (never parsed from text).
    intervention: Mapped[str | None] = mapped_column(String(300), nullable=True)
    comparator: Mapped[str | None] = mapped_column(String(300), nullable=True)
    outcome_variable: Mapped[str | None] = mapped_column(String(300), nullable=True)
    effect_direction: Mapped[str] = mapped_column(
        String(24), default="NOT_STATED", server_default=text("'NOT_STATED'")
    )
    __table_args__ = (
        UniqueConstraint("case_id", "origin_ref", name="uq_claim_case_origin_ref"),
        CheckConstraint(_in("effect_direction", EFFECT_DIRECTIONS), name="ck_claim_effect_direction"),
        CheckConstraint(
            "effect_direction = 'NOT_STATED' OR evidence_basis != 'METADATA_ONLY'",
            name="ck_claim_direction_needs_source_text",
        ),
        CheckConstraint(
            "effect_direction = 'NOT_STATED' OR (intervention IS NOT NULL AND outcome_variable IS NOT NULL)",
            name="ck_claim_direction_needs_terms",
        ),
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


class ClaimDisagreementReview(IdMixin, Base):
    """Append-only human decisions on a candidate disagreement between two claims (ABB-15).

    Candidates are computed from the claims, never stored. A decision applies only while both
    claims keep the versions recorded here; the latest applicable row is the current decision.
    ``pair_id`` is the stable id of the pair (``comparability.pair_id``) and claim A is the lower UUID.
    """
    __tablename__ = "claim_disagreement_reviews"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    pair_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    claim_a_id: Mapped[UUID] = mapped_column(ForeignKey("evidence_claims.id", ondelete="CASCADE"), index=True)
    claim_b_id: Mapped[UUID] = mapped_column(ForeignKey("evidence_claims.id", ondelete="CASCADE"), index=True)
    claim_a_version: Mapped[int] = mapped_column(Integer)
    claim_b_version: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    __table_args__ = (
        CheckConstraint("claim_a_id < claim_b_id", name="ck_disagreement_pair_order"),
        CheckConstraint("claim_a_version >= 1 AND claim_b_version >= 1", name="ck_disagreement_versions"),
        CheckConstraint(_in("decision", DISAGREEMENT_DECISIONS), name="ck_disagreement_decision"),
        CheckConstraint("char_length(note) > 0", name="ck_disagreement_note"),
    )


UNCERTAINTY_ANSWER_ORIGINS = ("FARMER_REPORTED", "LOCAL_MEASUREMENT", "FIELD_RECORD", "ADVISOR_REPORT")
UNCERTAINTY_ANSWER_STATUSES = ("ANSWERED", "REVIEWED", "REJECTED", "SUPERSEDED")
UNCERTAINTY_EVENT_ACTIONS = ("ANSWERED", "REVIEWED", "REJECTED", "DISMISSED", "REOPENED")
UNCERTAINTY_QUESTION_STATUSES = ("OPEN", "ANSWERED", "REVIEWED", "DISMISSED")


class UncertaintyAnswer(IdMixin, Base):
    """Local answer to an Uncertainty Hunter question (ABB-19). Always FARMER_REPORTED evidence.

    Content is immutable: a correction is a new answer that supersedes the previous one, which is
    kept. Only the review fields and ``status`` change. Answers never overwrite scientific records.
    At most one ANSWERED/REVIEWED answer per question and case.
    """
    __tablename__ = "uncertainty_answers"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(40), index=True)
    question_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    observed_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    observed_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    origin: Mapped[str] = mapped_column(String(32))
    method: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ANSWERED")
    answered_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_by_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    __table_args__ = (
        CheckConstraint(_in("origin", UNCERTAINTY_ANSWER_ORIGINS), name="ck_uncertainty_answer_origin"),
        CheckConstraint(_in("status", UNCERTAINTY_ANSWER_STATUSES), name="ck_uncertainty_answer_status"),
        CheckConstraint("value_text IS NOT NULL OR value_number IS NOT NULL", name="ck_uncertainty_answer_value"),
        CheckConstraint("value_number IS NULL OR unit IS NOT NULL", name="ck_uncertainty_answer_unit"),
        CheckConstraint("observed_from IS NULL OR observed_to IS NULL OR observed_to >= observed_from",
                        name="ck_uncertainty_answer_period"),
        CheckConstraint("reviewed_by IS NULL OR reviewed_by != answered_by", name="ck_uncertainty_answer_no_self_review"),
        CheckConstraint(
            "status NOT IN ('REVIEWED','REJECTED') OR "
            "(reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL AND review_note IS NOT NULL)",
            name="ck_uncertainty_answer_review_complete"),
        CheckConstraint("status != 'SUPERSEDED' OR superseded_at IS NOT NULL", name="ck_uncertainty_answer_superseded"),
        CheckConstraint("version >= 1", name="ck_uncertainty_answer_version"),
        Index("uq_uncertainty_answer_current", "case_id", "question_id", unique=True,
              postgresql_where=text("status IN ('ANSWERED','REVIEWED')")),
    )


class UncertaintyQuestionEvent(IdMixin, Base):
    """Append-only history of an Uncertainty Hunter question in a case (ABB-19).

    ``to_status`` is the question's resolution after the event; the latest event gives the current
    resolution (no event = OPEN). The question text is kept in ``question_snapshot`` because questions
    are computed and may change or disappear later.
    """
    __tablename__ = "uncertainty_question_events"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(40), index=True)
    action: Mapped[str] = mapped_column(String(16))
    answer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("uncertainty_answers.id", ondelete="CASCADE"), nullable=True, index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    from_status: Mapped[str] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    __table_args__ = (
        CheckConstraint(_in("action", UNCERTAINTY_EVENT_ACTIONS), name="ck_uncertainty_event_action"),
        CheckConstraint(_in("from_status", UNCERTAINTY_QUESTION_STATUSES), name="ck_uncertainty_event_from_status"),
        CheckConstraint(_in("to_status", UNCERTAINTY_QUESTION_STATUSES), name="ck_uncertainty_event_to_status"),
        CheckConstraint("action = 'ANSWERED' OR note IS NOT NULL", name="ck_uncertainty_event_note"),
        CheckConstraint("action NOT IN ('ANSWERED','REVIEWED','REJECTED') OR answer_id IS NOT NULL",
                        name="ck_uncertainty_event_answer"),
    )


GRAPH_REVIEW_STATUSES = CLAIM_REVIEW_STATUSES
GRAPH_EDGE_RELATIONS = ("SUPPORTS", "CONTRADICTS", "LIMITS", "ADDRESSES")
# Node ids a stored edge may reference (ABB-16): persisted case records and stable case facts only.
GRAPH_STORABLE_NODE = (
    r"^(observation|anomaly|claim|hypothesis|conclusion|field):"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    r"|^farmer:(incident|crop-history)$|^missing:no-local-measurements$"
)


class EvidenceConclusion(IdMixin, Base):
    """Human-authored conclusion of a case evidence graph (ABB-16).

    Never generated by the system. Its citations are ``evidence_graph_edges`` rows with
    ``conclusion_id`` set; at least one SUPPORTS citation is required by the API. A review
    decision is recorded by a member who did not contribute (``contributor_ids``).
    """
    __tablename__ = "evidence_conclusions"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    statement: Mapped[str] = mapped_column(Text)
    limitations: Mapped[list[str]] = mapped_column(JSONB)
    review_status: Mapped[str] = mapped_column(String(24), default="PENDING", server_default=text("'PENDING'"))
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contributor_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=text("now()"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    __table_args__ = (
        UniqueConstraint("id", "case_id", name="uq_conclusion_case"),
        CheckConstraint("version >= 1", name="ck_conclusion_version"),
        CheckConstraint(_in("review_status", GRAPH_REVIEW_STATUSES), name="ck_conclusion_review_status"),
        CheckConstraint("jsonb_array_length(limitations) >= 1", name="ck_conclusion_limitations"),
        CheckConstraint(
            "review_status != 'PENDING' OR (reviewed_by IS NULL AND reviewed_at IS NULL)",
            name="ck_conclusion_pending_unreviewed",
        ),
        CheckConstraint(
            "review_status = 'PENDING' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL "
            "AND review_note IS NOT NULL)",
            name="ck_conclusion_decision_complete",
        ),
        CheckConstraint(
            "reviewed_by IS NULL OR NOT (contributor_ids @> jsonb_build_array(reviewed_by::text))",
            name="ck_conclusion_no_self_review",
        ),
    )


class EvidenceGraphEdge(IdMixin, Base):
    """Human-added edge of a case evidence graph (ABB-16).

    Edges derived from existing records (anomaly → observation → manifest, claim → paper,
    hypothesis evidence links) are generated on read and never stored here. ``conclusion_id``
    is set when one endpoint is a conclusion; the composite FK keeps it in the same case and
    removes the citations together with their conclusion.
    """
    __tablename__ = "evidence_graph_edges"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    source_node: Mapped[str] = mapped_column(String(160))
    target_node: Mapped[str] = mapped_column(String(160))
    relation: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text)
    conclusion_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    review_status: Mapped[str] = mapped_column(String(24), default="PENDING", server_default=text("'PENDING'"))
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contributor_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=text("now()"))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    __table_args__ = (
        ForeignKeyConstraint(
            ["conclusion_id", "case_id"],
            ["evidence_conclusions.id", "evidence_conclusions.case_id"],
            ondelete="CASCADE",
            name="fk_graph_edge_conclusion_same_case",
        ),
        UniqueConstraint("case_id", "source_node", "target_node", "relation", name="uq_graph_edge"),
        CheckConstraint("version >= 1", name="ck_graph_edge_version"),
        CheckConstraint("source_node != target_node", name="ck_graph_edge_not_self"),
        CheckConstraint(_in("relation", GRAPH_EDGE_RELATIONS), name="ck_graph_edge_relation"),
        CheckConstraint(_in("review_status", GRAPH_REVIEW_STATUSES), name="ck_graph_edge_review_status"),
        CheckConstraint(f"source_node ~ '{GRAPH_STORABLE_NODE}'", name="ck_graph_edge_source_node"),
        CheckConstraint(f"target_node ~ '{GRAPH_STORABLE_NODE}'", name="ck_graph_edge_target_node"),
        CheckConstraint(
            "(conclusion_id IS NULL) = (source_node NOT LIKE 'conclusion:%' AND target_node NOT LIKE 'conclusion:%')",
            name="ck_graph_edge_conclusion_flag",
        ),
        CheckConstraint(
            "conclusion_id IS NULL OR source_node = 'conclusion:' || conclusion_id::text "
            "OR target_node = 'conclusion:' || conclusion_id::text",
            name="ck_graph_edge_conclusion_endpoint",
        ),
        CheckConstraint(
            "review_status != 'PENDING' OR (reviewed_by IS NULL AND reviewed_at IS NULL)",
            name="ck_graph_edge_pending_unreviewed",
        ),
        CheckConstraint(
            "review_status = 'PENDING' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_graph_edge_decision_complete",
        ),
        CheckConstraint(
            "reviewed_by IS NULL OR NOT (contributor_ids @> jsonb_build_array(reviewed_by::text))",
            name="ck_graph_edge_no_self_review",
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
