"""Request/response models for the case evidence graph (ABB-16).

Nodes and edges follow the frontend request B3 (``{id, kind, label, provenance}`` and
``{from, to, relation, note}``) with additive fields. No model carries a weight, probability,
confidence or causal score, and provenance never contains coordinates.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field as PydanticField, JsonValue, StringConstraints, model_validator

from .. import schemas
from ..services.evidence_graph import EdgeOrigin, EdgeReviewStatus, NodeKind, NodeType, Relation
from .dto import Limitation, RequestModel, UserSummary

NodeId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=160,
                                          pattern=r"^[a-z-]+:[0-9a-z:-]{1,150}$")]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000)]
ManualRelation = Literal["SUPPORTS", "CONTRADICTS", "LIMITS", "ADDRESSES"]
GraphReviewDecision = Literal["ACCEPTED", "REJECTED", "CHANGES_REQUESTED"]
ConclusionStatus = Literal["PENDING", "ACCEPTED", "CHANGES_REQUESTED", "REJECTED"]
MAX_CITATIONS = 50


# ── graph payload ────────────────────────────────────────────────────────────

class GraphProvenance(schemas.ContractModel):
    """Where a node comes from. Never includes request parameters or coordinates; the full source
    manifest (coordinates for OWNER/EDITOR only) is served by ``GET /cases/{id}/observations``."""
    source_kind: str
    description: str
    case_id: UUID
    case_version: int | None = None
    source_manifest_id: UUID | None = None
    observation_id: UUID | None = None
    anomaly_id: UUID | None = None
    claim_id: UUID | None = None
    paper_id: UUID | None = None
    hypothesis_id: UUID | None = None
    conclusion_id: UUID | None = None
    field_id: UUID | None = None
    field_label: str | None = None
    region_label: str | None = None
    provider: str | None = None
    dataset: str | None = None
    dataset_version: str | None = None
    source_uri: str | None = None
    retrieved_at: datetime | None = None
    checksum_sha256: str | None = None
    content_sha256: str | None = None
    processing_version: str | None = None
    revision: int | None = None
    spatial_resolution: schemas.Resolution | None = None
    temporal_resolution: schemas.Resolution | None = None
    doi: str | None = PydanticField(default=None, description="https://doi.org/ URL as registered; never inferred")
    doi_id: str | None = None
    doi_status: str | None = None
    openalex_id: str | None = None
    origin: str | None = None
    created_by: UserSummary | None = None
    created_at: datetime | None = None
    reviewed_by: UserSummary | None = None
    reviewed_at: datetime | None = None
    evaluated_by: UserSummary | None = None
    evaluated_at: datetime | None = None


class GraphNodeView(schemas.ContractModel):
    id: str = PydanticField(description="Typed node id, e.g. anomaly:<uuid>, claim:<uuid>, farmer:incident")
    node_type: NodeType
    kind: NodeKind = PydanticField(description="Evidence classification shown by the UI")
    label: str
    entity_id: UUID | None = PydanticField(description="Id of the underlying record, when there is one")
    status: str | None = PydanticField(
        default=None, description="Claim/conclusion review status or hypothesis evaluation status")
    active: bool = PydanticField(description="False for values of a superseded retrieval")
    original_evidence: bool = PydanticField(
        description="True for records a trace ends at: source manifest, farmer-reported record, registered paper")
    linkable: bool = PydanticField(description="Whether stored edges and conclusions may reference this node")
    start: date | None = None
    end: date | None = None
    provenance: GraphProvenance
    limitations: list[str] = PydanticField(min_length=1)
    details: dict[str, JsonValue]


class GraphEdgeView(schemas.ContractModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str
    from_: str = PydanticField(alias="from", description="Source node id")
    to: str = PydanticField(description="Target node id")
    relation: Relation
    origin: EdgeOrigin = PydanticField(
        description="STRUCTURAL (generated from stored records), HYPOTHESIS_LINK (hypothesis evidence lists) or "
                    "MANUAL (stored, written by a case member)")
    note: str | None = None
    review_status: EdgeReviewStatus
    record_id: UUID | None = PydanticField(default=None, description="Stored edge id (MANUAL edges only)")
    conclusion_id: UUID | None = None
    version: int | None = None
    author: UserSummary | None = None
    created_at: datetime | None = None
    reviewed_by: UserSummary | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    can_edit: bool = False
    can_review: bool = False


class OrphanReferenceView(schemas.ContractModel):
    referenced_by: str
    missing_node: str
    relation: str
    origin: str


class RelationLegend(schemas.ContractModel):
    relation: Relation
    description: str
    stored: bool = PydanticField(description="True when people add it; False when generated from stored records")


class GraphCounts(schemas.ContractModel):
    total_nodes: int
    total_edges: int
    nodes_by_kind: dict[str, int]
    nodes_by_type: dict[str, int]
    edges_by_relation: dict[str, int]
    edges_by_origin: dict[str, int]


class EvidenceGraphView(schemas.ContractModel):
    case_id: UUID
    case_version: int
    generated_at: datetime
    include_superseded: bool
    nodes: list[GraphNodeView]
    edges: list[GraphEdgeView]
    counts: GraphCounts
    relations: list[RelationLegend]
    orphan_references: list[OrphanReferenceView] = PydanticField(
        description="Stored references whose endpoint no longer exists; always empty unless data was changed "
                    "outside the API. Such references are never drawn as edges.")
    limitations: list[str]


class TraceStepView(schemas.ContractModel):
    node_id: str
    edge_id: str | None = PydanticField(description="Edge that leads from the previous step to this node")
    relation: Relation | None


class TracePathView(schemas.ContractModel):
    steps: list[TraceStepView]
    ends_at_original_evidence: bool


class TraceSummary(schemas.ContractModel):
    reaches_observed_data: bool
    reaches_farmer_report: bool
    reaches_literature: bool
    reviewed_claim_ids: list[str]
    unreviewed_claim_ids: list[str]
    unevaluated_hypothesis_ids: list[str]
    superseded_node_ids: list[str]
    missing_data_node_ids: list[str]


class EvidenceTraceView(schemas.ContractModel):
    case_id: UUID
    generated_at: datetime
    root: GraphNodeView
    complete: bool = PydanticField(description="Every grounding branch from the root ends at original evidence")
    original_evidence: list[str]
    dead_ends: list[str]
    paths: list[TracePathView]
    truncated: bool
    nodes: list[GraphNodeView]
    edges: list[GraphEdgeView]
    limiting_edges: list[GraphEdgeView]
    summary: TraceSummary
    review_blockers: list[str] = PydanticField(
        description="What would prevent accepting a conclusion with this trace (empty when nothing)")
    limitations: list[str]


# ── conclusions ──────────────────────────────────────────────────────────────

class Citation(RequestModel):
    node_id: NodeId
    note: Note = PydanticField(description="Why this node supports, contradicts or limits the conclusion")


def _unique_nodes(*groups: list[Citation] | None) -> None:
    seen: set[str] = set()
    for group in groups:
        for item in group or []:
            if item.node_id in seen:
                raise ValueError(f"{item.node_id} is cited more than once")
            seen.add(item.node_id)


class ConclusionCreate(RequestModel):
    """A human-written conclusion. It must cite at least one supporting node and state its limitations."""
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    statement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)]
    limitations: list[Limitation] = PydanticField(min_length=1, max_length=20)
    supporting: list[Citation] = PydanticField(min_length=1, max_length=MAX_CITATIONS)
    contradicting: list[Citation] = PydanticField(default_factory=list, max_length=MAX_CITATIONS)
    limited_by: list[Citation] = PydanticField(default_factory=list, max_length=MAX_CITATIONS)
    addresses_hypothesis_ids: list[UUID] = PydanticField(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _distinct(self) -> ConclusionCreate:
        _unique_nodes(self.supporting, self.contradicting, self.limited_by)
        if len(set(self.addresses_hypothesis_ids)) != len(self.addresses_hypothesis_ids):
            raise ValueError("addresses_hypothesis_ids contains duplicates")
        return self


class ConclusionUpdate(RequestModel):
    """Partial update of the text. Citations are changed through the edge routes. Any change returns
    the conclusion to PENDING."""
    version: int = PydanticField(ge=1, description="Current conclusion version")
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    statement: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)] | None = None
    limitations: list[Limitation] | None = PydanticField(default=None, min_length=1, max_length=20)

    @model_validator(mode="after")
    def _not_null(self) -> ConclusionUpdate:
        for name in ("statement", "limitations"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class GraphReview(RequestModel):
    version: int = PydanticField(ge=1)
    decision: GraphReviewDecision
    note: Note


class ConclusionView(schemas.ContractModel):
    id: UUID
    case_id: UUID
    node_id: str
    source_kind: Literal["CONCLUSION"] = "CONCLUSION"
    title: str | None
    statement: str
    limitations: list[str] = PydanticField(min_length=1)
    review_status: ConclusionStatus
    review_note: str | None
    reviewer: UserSummary | None
    reviewed_at: datetime | None
    created_by: UserSummary | None
    created_at: datetime
    updated_at: datetime
    version: int
    citations: list[GraphEdgeView]
    trace_complete: bool = PydanticField(description="Every cited branch reaches original evidence")
    review_blockers: list[str]
    warnings: list[str]
    can_edit: bool
    can_review: bool


class ConclusionList(schemas.ContractModel):
    items: list[ConclusionView]
    limitations: list[str]


# ── manual edges ─────────────────────────────────────────────────────────────

class EdgeCreate(RequestModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, populate_by_name=True)
    from_: NodeId = PydanticField(alias="from")
    to: NodeId
    relation: ManualRelation
    note: Note


class EdgeUpdate(RequestModel):
    version: int = PydanticField(ge=1)
    note: Note


class EdgeList(schemas.ContractModel):
    items: list[GraphEdgeView]
    limitations: list[str]
