"""Case evidence graph, human-authored conclusions and manual edges (ABB-16).

Rules (docs/science/EVIDENCE_GRAPH.md):
- The graph is assembled on every read from the case records (``services.evidence_graph``).
  Derived edges (anomaly → observation → source manifest, claim → paper, hypothesis evidence
  links) are generated, never stored; only human-added edges and conclusions are stored.
- Every stored edge endpoint must exist in the same case (422 otherwise, same answer for unknown
  and foreign ids). Deleting a referenced hypothesis, claim or field is refused (409, see
  ``api.graph_guard``).
- A conclusion is written by a person, cites at least one supporting node, states at least one
  limitation, and every node it cites as support or contradiction must trace back to original
  evidence. The system never creates or scores conclusions.
- Roles (ADR-0004): every member reads; OWNER/EDITOR create, edit and delete conclusions and
  edges; OWNER/EDITOR/REVIEWER record review decisions, never on content they contributed.
  Writes need an editable case, carry the item ``version`` (409) and append ``case_history``
  rows without bumping the case version.
- Provenance never includes request parameters or coordinates, for any role.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db.models import (
    Case,
    CaseHistory,
    ClaimDisagreementReview,
    EvidenceClaim,
    EvidenceConclusion,
    EvidenceGraphEdge,
    Field,
    Hypothesis,
    Paper,
    User,
    utcnow,
)
from ..services.evidence_graph import (
    POLARITY,
    RELATION_DESCRIPTIONS,
    RELATIONS,
    SYSTEM_RELATIONS,
    Edge,
    Graph,
    GraphInputs,
    GraphRuleError,
    Node,
    build_graph,
    check_edge,
    conclusion_node,
    conclusion_uuid,
    counts,
    edges_of_conclusion,
    require_grounded,
    stored_edge,
    trace,
    trace_problems,
)
from .cases import EDITOR_ROLES, EDITABLE_STATUSES, _load, _record, _require_editable, _require_role, _summary
from .deps import CurrentPrincipal, DbSession
from .graph_dto import (
    ConclusionCreate,
    ConclusionList,
    ConclusionUpdate,
    ConclusionView,
    EdgeCreate,
    EdgeList,
    EdgeUpdate,
    EvidenceGraphView,
    EvidenceTraceView,
    GraphCounts,
    GraphEdgeView,
    GraphNodeView,
    GraphProvenance,
    GraphReview,
    OrphanReferenceView,
    RelationLegend,
    TracePathView,
    TraceStepView,
    TraceSummary,
)
from .observations import load_ingestions

router = APIRouter(prefix="/api/v1/cases", tags=["evidence graph (ABB-16)"])

REVIEW_ROLES = frozenset({"OWNER", "EDITOR", "REVIEWER"})
DECISIONS_FROM: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"ACCEPTED", "REJECTED", "CHANGES_REQUESTED"}),
    "ACCEPTED": frozenset({"REJECTED", "CHANGES_REQUESTED"}),  # withdrawal of an acceptance
}
MAX_CONCLUSIONS = 100
MAX_EDGES = 1_000
CONCLUSION_NOT_FOUND = "Conclusion not found."
EDGE_NOT_FOUND = "Edge not found."
NODE_ORDER = ("CONCLUSION", "HYPOTHESIS", "EVIDENCE_CLAIM", "PAPER", "ANOMALY", "OBSERVATION", "SOURCE_MANIFEST",
              "FARMER_REPORT", "FIELD", "MISSING_DATA")
ADDRESSES_NOTE = "The conclusion discusses this hypothesis."
GRAPH_LIMITATIONS = [
    "Edges record which record refers to which; they are not causal links and carry no weight, probability or "
    "score.",
    "STRUCTURAL edges are generated from stored records; HYPOTHESIS_LINK edges come from the hypothesis evidence "
    "lists; MANUAL edges and conclusions were written by case members and are reviewed by members who did not "
    "write them.",
    "Conclusions are human statements; the system never generates them and does not verify that the cited "
    "evidence establishes them.",
    "OBSERVED nodes are regional NASA POWER grid-cell values (about ½° × ⅝°), not field measurements.",
    "LITERATURE_METADATA nodes have not been checked against the paper by a reviewer; only LITERATURE_REVIEWED "
    "claims were.",
    "Provenance never includes request coordinates; full source manifests are served by GET /observations "
    "(coordinates for owners and editors only).",
]
CONCLUSION_LIMITATIONS = [
    "A conclusion is a human statement over the cited evidence. ACCEPTED means a member who did not write it "
    "checked that every cited branch reaches original evidence and that cited literature was reviewed; it is not "
    "a scientific validation of the case.",
    "No conclusion carries a probability, confidence percentage or causal score.",
]
EDGE_LIMITATIONS = [
    "Stored edges were written by case members. Derived edges are listed by GET /evidence-graph.",
    "An ACCEPTED edge means another member agreed the link is stated correctly; it is not proof of a cause.",
]


@dataclass(frozen=True)
class Access:
    role: str
    user_id: UUID
    editable: bool

    @property
    def can_write(self) -> bool:
        return self.role in EDITOR_ROLES and self.editable

    def can_review(self, contributors: tuple[str, ...] | list[str], review_status: str) -> bool:
        return (self.role in REVIEW_ROLES and self.editable and str(self.user_id) not in contributors
                and review_status in DECISIONS_FROM)


def _access(case: Case, role: str, user: User) -> Access:
    return Access(role=role, user_id=user.id, editable=case.archived_at is None and case.status in EDITABLE_STATUSES)


# ── loading ──────────────────────────────────────────────────────────────────

def load_graph(db: Session, case: Case, *, include_superseded: bool) -> Graph:
    manifests, observations, anomalies = load_ingestions(db, case.id, include_superseded=True)
    claims = list(db.scalars(select(EvidenceClaim).where(EvidenceClaim.case_id == case.id)))
    paper_ids = {c.paper_id for c in claims}
    return build_graph(GraphInputs(
        case=case,
        fields=list(db.scalars(select(Field).where(Field.case_id == case.id))),
        manifests=manifests,
        observations=[o for items in observations.values() for o in items],
        anomalies=list(anomalies.values()),
        papers={p.id: p for p in db.scalars(select(Paper).where(Paper.id.in_(paper_ids)))} if paper_ids else {},
        claims=claims,
        hypotheses=list(db.scalars(select(Hypothesis).where(Hypothesis.case_id == case.id))),
        conclusions=list(db.scalars(select(EvidenceConclusion).where(EvidenceConclusion.case_id == case.id))),
        edges=list(db.scalars(select(EvidenceGraphEdge).where(EvidenceGraphEdge.case_id == case.id))),
        disagreements=list(db.scalars(select(ClaimDisagreementReview).where(
            ClaimDisagreementReview.case_id == case.id))),
    ), include_superseded=include_superseded)


def _user_map(db: Session, ids: set[UUID | None]) -> dict[UUID, User]:
    wanted = {i for i in ids if i}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(wanted)))} if wanted else {}


def _graph_users(db: Session, nodes: list[Node], edges: list[Edge]) -> dict[UUID, User]:
    ids: set[UUID | None] = set()
    for node in nodes:
        ids.update(node.provenance.get(k) for k in ("created_by_id", "reviewed_by_id", "evaluated_by_id"))
    for edge in edges:
        ids.update((edge.author_id, edge.reviewed_by))
    return _user_map(db, ids)


# ── views ────────────────────────────────────────────────────────────────────

def _user(users: dict[UUID, User], user_id: UUID | None):
    return _summary(users.get(user_id)) if user_id else None


def node_view(node: Node, users: dict[UUID, User]) -> GraphNodeView:
    provenance = dict(node.provenance)
    for key in ("created_by", "reviewed_by", "evaluated_by"):
        provenance[key] = _user(users, provenance.pop(f"{key}_id", None))
    return GraphNodeView(
        id=node.id, node_type=node.node_type, kind=node.kind, label=node.label, entity_id=node.entity_id,
        status=node.status, active=node.active, original_evidence=node.original_evidence, linkable=node.linkable,
        start=node.start, end=node.end, provenance=GraphProvenance(**provenance), limitations=node.limitations,
        details=node.details,
    )


def edge_view(edge: Edge, users: dict[UUID, User], access: Access) -> GraphEdgeView:
    manual = edge.origin == "MANUAL"
    return GraphEdgeView(
        id=edge.id, from_=edge.source, to=edge.target, relation=edge.relation, origin=edge.origin, note=edge.note,
        review_status=edge.review_status, record_id=edge.record_id, conclusion_id=edge.conclusion_id,
        version=edge.version, author=_user(users, edge.author_id), created_at=edge.created_at,
        reviewed_by=_user(users, edge.reviewed_by), reviewed_at=edge.reviewed_at, review_note=edge.review_note,
        can_edit=manual and access.can_write,
        can_review=(manual and edge.conclusion_id is None
                    and access.can_review(edge.contributor_ids, edge.review_status)),
    )


def _node_key(node: Node) -> tuple[Any, ...]:
    return (NODE_ORDER.index(node.node_type), node.start is None, node.start or date.min, node.label, node.id)


def _conclusion_view(graph: Graph, conclusion: EvidenceConclusion, users: dict[UUID, User],
                     access: Access) -> ConclusionView:
    node_id = f"conclusion:{conclusion.id}"
    result = trace(graph, node_id)
    blockers = trace_problems(graph, result)
    citations = edges_of_conclusion(graph, node_id)
    warnings: list[str] = []
    if conclusion.review_status == "ACCEPTED":
        warnings.append("Reviewed: a member who did not write it checked the cited evidence trail. This is not a "
                        "scientific validation of the case.")
    else:
        warnings.append("Not reviewed: a working conclusion written by a case member.")
        if conclusion.review_status == "REJECTED":
            warnings.append("Rejected by a reviewer; do not report it as a conclusion of the case.")
        elif conclusion.review_status == "CHANGES_REQUESTED":
            warnings.append("A reviewer requested changes.")
    if not result.complete:
        warnings.append("Not every cited item traces back to original evidence.")
    superseded = [n for n in result.node_ids if not graph.nodes[n].active]
    if superseded:
        warnings.append("Cites values of a superseded retrieval: " + ", ".join(superseded))
    if result.contradiction_edge_ids:
        edges_by_id = {e.id: e for e in graph.edges}
        pairs = [f"{edges_by_id[i].source} / {edges_by_id[i].target}" for i in result.contradiction_edge_ids]
        warnings.append("Cited literature includes claims a reviewer confirmed as contradicting each other "
                        "(ABB-15): " + "; ".join(pairs))
    node = graph.nodes[node_id]
    return ConclusionView(
        id=conclusion.id, case_id=conclusion.case_id, node_id=node_id, title=conclusion.title,
        statement=conclusion.statement, limitations=node.limitations, review_status=conclusion.review_status,
        review_note=conclusion.review_note, reviewer=_user(users, conclusion.reviewed_by),
        reviewed_at=conclusion.reviewed_at, created_by=_user(users, conclusion.created_by_id),
        created_at=conclusion.created_at, updated_at=conclusion.updated_at, version=conclusion.version,
        citations=[edge_view(e, users, access) for e in citations], trace_complete=result.complete,
        review_blockers=blockers, warnings=warnings, can_edit=access.can_write,
        can_review=access.can_review(list(conclusion.contributor_ids or []), conclusion.review_status),
    )


def _conclusion_views(db: Session, case: Case, access: Access,
                      conclusions: list[EvidenceConclusion]) -> list[ConclusionView]:
    graph = load_graph(db, case, include_superseded=False)
    users = _graph_users(db, list(graph.nodes.values()), graph.edges)
    users.update(_user_map(db, {u for c in conclusions for u in (c.created_by_id, c.reviewed_by)}))
    return [_conclusion_view(graph, c, users, access) for c in conclusions]


# ── write helpers ────────────────────────────────────────────────────────────

def _rule(fn, *args) -> None:
    try:
        fn(*args)
    except GraphRuleError as exc:
        raise HTTPException(exc.status, detail=exc.message) from exc


def _check_new_edge(graph: Graph, source: str, target: str, relation: str) -> None:
    _rule(check_edge, graph, source, target, relation)
    if relation in POLARITY:
        _rule(require_grounded, graph, source)


def _with_contributor(contributors: list[str] | None, user: User) -> list[str]:
    items = list(contributors or [])
    return items if str(user.id) in items else [*items, str(user.id)]


def _conclusion_or_404(db: Session, case_id: UUID, conclusion_id: UUID, *, lock: bool = False) -> EvidenceConclusion:
    row = db.get(EvidenceConclusion, conclusion_id, with_for_update=lock, populate_existing=lock)
    if row is None or row.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=CONCLUSION_NOT_FOUND)
    return row


def _edge_or_404(db: Session, case_id: UUID, edge_id: UUID, *, lock: bool = False) -> EvidenceGraphEdge:
    row = db.get(EvidenceGraphEdge, edge_id, with_for_update=lock, populate_existing=lock)
    if row is None or row.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=EDGE_NOT_FOUND)
    return row


def _require_item_version(kind: str, current: int, sent: int) -> None:
    if current != sent:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"The {kind} changed since you loaded it (current version {current}). "
                                   "Reload and retry.")


def _conclusion_edges(db: Session, conclusion_id: UUID) -> list[EvidenceGraphEdge]:
    return list(db.scalars(select(EvidenceGraphEdge).where(EvidenceGraphEdge.conclusion_id == conclusion_id)
                           .order_by(EvidenceGraphEdge.created_at, EvidenceGraphEdge.id).with_for_update()))


def _edge_snapshot(row: EvidenceGraphEdge) -> dict[str, Any]:
    return {"id": str(row.id), "from": row.source_node, "to": row.target_node, "relation": row.relation,
            "note": row.note, "review_status": row.review_status,
            "conclusion_id": str(row.conclusion_id) if row.conclusion_id else None}


def _conclusion_snapshot(row: EvidenceConclusion, edges: list[EvidenceGraphEdge]) -> dict[str, Any]:
    return {"id": str(row.id), "title": row.title, "statement": row.statement, "limitations": list(row.limitations),
            "review_status": row.review_status, "citations": [_edge_snapshot(e) for e in edges]}


def _clear_review(row: EvidenceConclusion | EvidenceGraphEdge) -> None:
    row.review_status, row.reviewed_by, row.reviewed_at, row.review_note = "PENDING", None, None, None


def _touch_conclusion(db: Session, conclusion: EvidenceConclusion, user: User) -> dict[str, Any]:
    """The conclusion's content (text or citations) changed: new version, editor becomes a
    contributor, and an earlier review decision no longer applies (conclusion and its edges)."""
    changes: dict[str, Any] = {}
    if conclusion.review_status != "PENDING":
        changes["review_status"] = {"before": conclusion.review_status, "after": "PENDING"}
        _clear_review(conclusion)
        for edge in _conclusion_edges(db, conclusion.id):
            if edge.review_status != "PENDING":
                _clear_review(edge)
                edge.version += 1
    conclusion.contributor_ids = _with_contributor(conclusion.contributor_ids, user)
    conclusion.version += 1
    conclusion.updated_at = utcnow()
    return changes


def _ever_reviewed(db: Session, case_id: UUID, conclusion_id: UUID) -> bool:
    return db.scalar(select(CaseHistory.id).where(
        CaseHistory.case_id == case_id, CaseHistory.action == "CONCLUSION_REVIEWED",
        CaseHistory.changes["conclusion_id"].astext == str(conclusion_id)).limit(1)) is not None


def _count(db: Session, model: Any, case_id: UUID) -> int:
    return db.scalar(select(func.count()).select_from(model).where(model.case_id == case_id)) or 0


def _new_edge(case_id: UUID, source: str, target: str, relation: str, note: str, user: User,
              conclusion_id: UUID | None) -> EvidenceGraphEdge:
    now = utcnow()
    return EvidenceGraphEdge(
        id=uuid4(), case_id=case_id, source_node=source, target_node=target, relation=relation, note=note,
        conclusion_id=conclusion_id, review_status="PENDING", contributor_ids=[str(user.id)],
        created_by_id=user.id, created_at=now, updated_at=now, version=1,
    )


# ── graph and trace ──────────────────────────────────────────────────────────

@router.get("/{case_id}/evidence-graph", response_model=EvidenceGraphView)
def evidence_graph(
    case_id: UUID, principal: CurrentPrincipal, db: DbSession,
    include_superseded: bool = Query(default=False, description="Also include values of superseded retrievals "
                                                                "that no evidence refers to"),
) -> EvidenceGraphView:
    """Every member. Nodes (observed data, farmer reports, literature, hypotheses, conclusions,
    missing data) and typed edges with provenance, review state and authorship."""
    case, role = _load(db, case_id, principal.user.id)
    access = _access(case, role, principal.user)
    graph = load_graph(db, case, include_superseded=include_superseded)
    nodes = sorted(graph.nodes.values(), key=_node_key)
    users = _graph_users(db, nodes, graph.edges)
    tallies = counts(nodes, graph.edges)
    limitations = list(GRAPH_LIMITATIONS)
    if graph.orphan_references:
        limitations.append("Some stored references point to records that no longer exist; they are listed in "
                           "orphan_references and not drawn.")
    return EvidenceGraphView(
        case_id=case.id, case_version=case.version, generated_at=utcnow(), include_superseded=include_superseded,
        nodes=[node_view(n, users) for n in nodes], edges=[edge_view(e, users, access) for e in graph.edges],
        counts=GraphCounts(total_nodes=len(nodes), total_edges=len(graph.edges), **tallies),
        relations=[RelationLegend(relation=r, description=RELATION_DESCRIPTIONS[r], stored=r not in SYSTEM_RELATIONS)
                   for r in RELATIONS],
        orphan_references=[OrphanReferenceView(referenced_by=o.referenced_by, missing_node=o.missing_node,
                                               relation=o.relation, origin=o.origin)
                           for o in graph.orphan_references],
        limitations=limitations,
    )


@router.get("/{case_id}/evidence-graph/trace/{node_id}", response_model=EvidenceTraceView)
def trace_node(
    case_id: UUID, principal: CurrentPrincipal, db: DbSession,
    node_id: str = Path(min_length=3, max_length=160, description="Node id, e.g. conclusion:<uuid>"),
) -> EvidenceTraceView:
    """Every member. All paths from a node (typically a conclusion) back to original evidence: NASA
    POWER source manifests, farmer-reported records and registered papers, with the limitations
    that apply along the way."""
    case, role = _load(db, case_id, principal.user.id)
    access = _access(case, role, principal.user)
    graph = load_graph(db, case, include_superseded=True)
    if node_id not in graph.nodes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Node not found in this case's evidence graph.")
    result = trace(graph, node_id)
    edges_by_id = {e.id: e for e in graph.edges}
    involved = [graph.nodes[n] for n in (*result.node_ids, *result.limiting_node_ids,
                                         *result.contradiction_node_ids)]
    traced_edges = [edges_by_id[e] for e in (*result.edge_ids, *result.limiting_edge_ids,
                                             *result.contradiction_edge_ids)]
    users = _graph_users(db, involved, traced_edges)
    traced = [graph.nodes[n] for n in result.node_ids]
    summary = TraceSummary(
        reaches_observed_data=any(n.node_type == "SOURCE_MANIFEST" for n in traced),
        reaches_farmer_report=any(n.node_type in ("FARMER_REPORT", "FIELD") and n.original_evidence for n in traced),
        reaches_literature=any(n.node_type == "PAPER" for n in traced),
        reviewed_claim_ids=[n.id for n in traced if n.node_type == "EVIDENCE_CLAIM" and n.status == "ACCEPTED"],
        unreviewed_claim_ids=[n.id for n in traced if n.node_type == "EVIDENCE_CLAIM" and n.status != "ACCEPTED"],
        unevaluated_hypothesis_ids=[n.id for n in traced if n.node_type == "HYPOTHESIS" and n.status == "OPEN"],
        superseded_node_ids=[n.id for n in traced if not n.active],
        missing_data_node_ids=[n.id for n in involved if n.kind == "MISSING_DATA"],
    )
    limitations = [
        "A trace lists the recorded references from this node back to original evidence; it does not show that "
        "the evidence establishes the statement.",
        "LIMITS edges qualify the traced evidence and are listed separately; they are not part of a path.",
        "Contradictions between claims confirmed by a reviewer (ABB-15) are listed in contradiction_edges; they "
        "are not part of a path.",
    ]
    if result.truncated:
        limitations.append(f"Only the first {len(result.paths)} paths are listed; nodes and edges are complete.")
    return EvidenceTraceView(
        case_id=case.id, generated_at=utcnow(), root=node_view(graph.nodes[node_id], users), complete=result.complete,
        original_evidence=result.original_evidence, dead_ends=result.dead_ends,
        paths=[TracePathView(steps=[TraceStepView(node_id=s.node_id, edge_id=s.edge_id, relation=s.relation)
                                    for s in p.steps], ends_at_original_evidence=p.ends_at_original_evidence)
               for p in result.paths],
        truncated=result.truncated, nodes=[node_view(n, users) for n in involved],
        edges=[edge_view(edges_by_id[e], users, access) for e in result.edge_ids],
        limiting_edges=[edge_view(edges_by_id[e], users, access) for e in result.limiting_edge_ids],
        contradiction_edges=[edge_view(edges_by_id[e], users, access) for e in result.contradiction_edge_ids],
        summary=summary,
        review_blockers=trace_problems(graph, result) if graph.nodes[node_id].node_type == "CONCLUSION" else [],
        limitations=limitations,
    )


# ── conclusions ──────────────────────────────────────────────────────────────

@router.get("/{case_id}/evidence-graph/conclusions", response_model=ConclusionList)
def list_conclusions(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> ConclusionList:
    case, role = _load(db, case_id, principal.user.id)
    rows = list(db.scalars(select(EvidenceConclusion).where(EvidenceConclusion.case_id == case_id)
                           .order_by(EvidenceConclusion.created_at, EvidenceConclusion.id)))
    return ConclusionList(items=_conclusion_views(db, case, _access(case, role, principal.user), rows),
                          limitations=list(CONCLUSION_LIMITATIONS))


@router.post("/{case_id}/evidence-graph/conclusions", response_model=ConclusionView,
             status_code=status.HTTP_201_CREATED)
def create_conclusion(case_id: UUID, body: ConclusionCreate, principal: CurrentPrincipal,
                      db: DbSession) -> ConclusionView:
    """OWNER/EDITOR. Starts PENDING. Every citation must exist in this case; supporting and
    contradicting nodes must trace back to original evidence."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    if _count(db, EvidenceConclusion, case_id) >= MAX_CONCLUSIONS:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"A case can hold at most {MAX_CONCLUSIONS} conclusions.")
    planned = [(c.node_id, relation, c.note) for relation, items in (
        ("SUPPORTS", body.supporting), ("CONTRADICTS", body.contradicting), ("LIMITS", body.limited_by))
        for c in items]
    if _count(db, EvidenceGraphEdge, case_id) + len(planned) + len(body.addresses_hypothesis_ids) > MAX_EDGES:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"A case can hold at most {MAX_EDGES} stored edges.")
    user = principal.user
    now = utcnow()
    conclusion = EvidenceConclusion(
        id=uuid4(), case_id=case_id, title=body.title, statement=body.statement, limitations=list(body.limitations),
        review_status="PENDING", contributor_ids=[str(user.id)], created_by_id=user.id, created_at=now,
        updated_at=now, version=1,
    )
    graph = load_graph(db, case, include_superseded=True)
    node = conclusion_node(case_id, conclusion)
    graph.add_node(node)
    triples = [(source, node.id, relation, note) for source, relation, note in planned]
    triples += [(node.id, f"hypothesis:{h}", "ADDRESSES", ADDRESSES_NOTE) for h in body.addresses_hypothesis_ids]
    for source, target, relation, note in triples:
        _check_new_edge(graph, source, target, relation)
        graph.add_edge(Edge(id=f"pending:{len(graph.edges)}", source=source, target=target, relation=relation,
                            origin="MANUAL", review_status="PENDING"))
    db.add(conclusion)
    db.flush()
    rows = [_new_edge(case_id, s, t, r, note, user, conclusion.id) for s, t, r, note in triples]
    db.add_all(rows)
    db.flush()
    _record(db, case, user, "CONCLUSION_CREATED",
            {"conclusion_id": str(conclusion.id),
             "conclusion": {"before": None, "after": _conclusion_snapshot(conclusion, rows)}}, bump=False)
    db.commit()
    return _conclusion_views(db, case, _access(case, role, user), [conclusion])[0]


@router.get("/{case_id}/evidence-graph/conclusions/{conclusion_id}", response_model=ConclusionView)
def get_conclusion(case_id: UUID, conclusion_id: UUID, principal: CurrentPrincipal, db: DbSession) -> ConclusionView:
    case, role = _load(db, case_id, principal.user.id)
    row = _conclusion_or_404(db, case_id, conclusion_id)
    return _conclusion_views(db, case, _access(case, role, principal.user), [row])[0]


@router.patch("/{case_id}/evidence-graph/conclusions/{conclusion_id}", response_model=ConclusionView)
def update_conclusion(case_id: UUID, conclusion_id: UUID, body: ConclusionUpdate, principal: CurrentPrincipal,
                      db: DbSession) -> ConclusionView:
    """OWNER/EDITOR. Text changes return the conclusion to PENDING; citations change through the edge routes."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    row = _conclusion_or_404(db, case_id, conclusion_id, lock=True)
    _require_item_version("conclusion", row.version, body.version)
    changes: dict[str, Any] = {}
    for name in ("title", "statement", "limitations"):
        if name not in body.model_fields_set:
            continue
        new = getattr(body, name)
        new = list(new) if isinstance(new, list) else new
        if getattr(row, name) != new:
            changes[name] = {"before": getattr(row, name), "after": new}
            setattr(row, name, new)
    if changes:
        reset = _touch_conclusion(db, row, principal.user)
        _record(db, case, principal.user, "CONCLUSION_UPDATED",
                {"conclusion_id": str(row.id), "conclusion_version": row.version, **changes, **reset}, bump=False,
                note="Review reset to PENDING because the conclusion changed." if reset else None)
        db.commit()
    return _conclusion_views(db, case, _access(case, role, principal.user), [row])[0]


@router.delete("/{case_id}/evidence-graph/conclusions/{conclusion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conclusion(
    case_id: UUID, conclusion_id: UUID, principal: CurrentPrincipal, db: DbSession,
    version: int = Query(ge=1, description="Current conclusion version"),
) -> Response:
    """OWNER/EDITOR. Only conclusions that never received a review decision (reviewed ones are kept for
    audit; edit or reject them). Its citations are removed with it; the content stays in the case history."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    row = _conclusion_or_404(db, case_id, conclusion_id, lock=True)
    _require_item_version("conclusion", row.version, version)
    if _ever_reviewed(db, case_id, row.id):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="This conclusion has review decisions and is kept for audit; edit or reject it "
                                   "instead.")
    edges = _conclusion_edges(db, row.id)
    _record(db, case, principal.user, "CONCLUSION_DELETED",
            {"conclusion_id": str(row.id), "conclusion": {"before": _conclusion_snapshot(row, edges), "after": None}},
            bump=False)
    db.execute(delete(EvidenceGraphEdge).where(EvidenceGraphEdge.conclusion_id == row.id))
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{case_id}/evidence-graph/conclusions/{conclusion_id}/review", response_model=ConclusionView)
def review_conclusion(case_id: UUID, conclusion_id: UUID, body: GraphReview, principal: CurrentPrincipal,
                      db: DbSession) -> ConclusionView:
    """OWNER/EDITOR/REVIEWER who did not contribute to the conclusion or its citations. ACCEPTED needs
    every cited branch to reach original evidence, every cited literature claim to be reviewed and
    every cited hypothesis to be evaluated. The decision applies to the conclusion and its citations."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, REVIEW_ROLES)
    _require_editable(case)
    row = _conclusion_or_404(db, case_id, conclusion_id, lock=True)
    _require_item_version("conclusion", row.version, body.version)
    if str(principal.user.id) in (row.contributor_ids or []):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="You wrote or edited this conclusion or its citations; a different member must "
                                   "review it.")
    if body.decision not in DECISIONS_FROM.get(row.review_status, frozenset()):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"A {row.review_status} conclusion cannot receive a {body.decision} decision.")
    if body.decision == "ACCEPTED":
        graph = load_graph(db, case, include_superseded=True)
        blockers = trace_problems(graph, trace(graph, f"conclusion:{row.id}"))
        if blockers:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Cannot accept: " + "; ".join(blockers) + ".")
    previous = row.review_status
    now = utcnow()
    row.review_status, row.reviewed_by, row.reviewed_at, row.review_note = body.decision, principal.user.id, now, body.note
    row.version += 1
    row.updated_at = now
    for edge in _conclusion_edges(db, row.id):
        edge.review_status, edge.reviewed_by, edge.reviewed_at = body.decision, principal.user.id, now
        edge.review_note = body.note
        edge.version += 1
    _record(db, case, principal.user, "CONCLUSION_REVIEWED",
            {"conclusion_id": str(row.id), "conclusion_version": row.version,
             "review_status": {"before": previous, "after": body.decision}}, bump=False, note=body.note)
    db.commit()
    return _conclusion_views(db, case, _access(case, role, principal.user), [row])[0]


# ── manual edges ─────────────────────────────────────────────────────────────

def _edge_response(db: Session, case: Case, role: str, user: User, row: EvidenceGraphEdge) -> GraphEdgeView:
    edge = stored_edge(row)
    return edge_view(edge, _user_map(db, {edge.author_id, edge.reviewed_by}), _access(case, role, user))


@router.get("/{case_id}/evidence-graph/edges", response_model=EdgeList)
def list_edges(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> EdgeList:
    """Every member. Stored (MANUAL) edges only, including conclusion citations."""
    case, role = _load(db, case_id, principal.user.id)
    rows = list(db.scalars(select(EvidenceGraphEdge).where(EvidenceGraphEdge.case_id == case_id)
                           .order_by(EvidenceGraphEdge.created_at, EvidenceGraphEdge.id)))
    edges = [stored_edge(r) for r in rows]
    users = _user_map(db, {u for e in edges for u in (e.author_id, e.reviewed_by)})
    access = _access(case, role, principal.user)
    return EdgeList(items=[edge_view(e, users, access) for e in edges], limitations=list(EDGE_LIMITATIONS))


@router.post("/{case_id}/evidence-graph/edges", response_model=GraphEdgeView, status_code=status.HTTP_201_CREATED)
def create_edge(case_id: UUID, body: EdgeCreate, principal: CurrentPrincipal, db: DbSession) -> GraphEdgeView:
    """OWNER/EDITOR. Both endpoints must exist in this case. Adding a citation to a conclusion returns
    the conclusion to PENDING."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    if _count(db, EvidenceGraphEdge, case_id) >= MAX_EDGES:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"A case can hold at most {MAX_EDGES} stored edges.")
    graph = load_graph(db, case, include_superseded=True)
    _check_new_edge(graph, body.from_, body.to, body.relation)
    conclusion_id = conclusion_uuid(body.from_) or conclusion_uuid(body.to)
    user = principal.user
    row = _new_edge(case_id, body.from_, body.to, body.relation, body.note, user, conclusion_id)
    changes: dict[str, Any] = {"edge_id": str(row.id)}
    if conclusion_id is not None:
        conclusion = _conclusion_or_404(db, case_id, conclusion_id, lock=True)
        changes.update(conclusion_id=str(conclusion_id), **_touch_conclusion(db, conclusion, user))
        changes["conclusion_version"] = conclusion.version
    db.add(row)
    db.flush()
    _record(db, case, user, "GRAPH_EDGE_CREATED", {**changes, "edge": {"before": None, "after": _edge_snapshot(row)}},
            bump=False)
    db.commit()
    return _edge_response(db, case, role, user, row)


@router.patch("/{case_id}/evidence-graph/edges/{edge_id}", response_model=GraphEdgeView)
def update_edge(case_id: UUID, edge_id: UUID, body: EdgeUpdate, principal: CurrentPrincipal,
                db: DbSession) -> GraphEdgeView:
    """OWNER/EDITOR. Only the note can change (endpoints and relation are fixed: delete and recreate).
    A change returns the edge, and its conclusion if any, to PENDING."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    row = _edge_or_404(db, case_id, edge_id, lock=True)
    _require_item_version("edge", row.version, body.version)
    user = principal.user
    if row.note != body.note:
        changes: dict[str, Any] = {"edge_id": str(row.id), "note": {"before": row.note, "after": body.note}}
        if row.conclusion_id is not None:
            conclusion = _conclusion_or_404(db, case_id, row.conclusion_id, lock=True)
            conclusion_changes = _touch_conclusion(db, conclusion, user)
            changes.update(conclusion_id=str(conclusion.id), conclusion_version=conclusion.version,
                           **conclusion_changes)
        elif row.review_status != "PENDING":
            changes["review_status"] = {"before": row.review_status, "after": "PENDING"}
            _clear_review(row)
        row.note = body.note
        row.contributor_ids = _with_contributor(row.contributor_ids, user)
        row.version += 1
        row.updated_at = utcnow()
        changes["edge_version"] = row.version
        _record(db, case, user, "GRAPH_EDGE_UPDATED", changes, bump=False)
        db.commit()
    return _edge_response(db, case, role, user, row)


@router.delete("/{case_id}/evidence-graph/edges/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_edge(
    case_id: UUID, edge_id: UUID, principal: CurrentPrincipal, db: DbSession,
    version: int = Query(ge=1, description="Current edge version"),
) -> Response:
    """OWNER/EDITOR. A conclusion keeps at least one SUPPORTS citation (409). Removing a citation returns
    the conclusion to PENDING. The deleted edge stays in the case history."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_editable(case)
    row = _edge_or_404(db, case_id, edge_id, lock=True)
    _require_item_version("edge", row.version, version)
    user = principal.user
    changes: dict[str, Any] = {"edge_id": str(row.id), "edge": {"before": _edge_snapshot(row), "after": None}}
    if row.conclusion_id is not None:
        conclusion = _conclusion_or_404(db, case_id, row.conclusion_id, lock=True)
        siblings = _conclusion_edges(db, conclusion.id)
        supports = [e for e in siblings if e.relation == "SUPPORTS" and e.target_node == f"conclusion:{conclusion.id}"]
        if row.relation == "SUPPORTS" and len(supports) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                detail="A conclusion must keep at least one supporting citation; add another one "
                                       "first or delete the conclusion.")
        changes.update(conclusion_id=str(conclusion.id), **_touch_conclusion(db, conclusion, user))
        changes["conclusion_version"] = conclusion.version
    _record(db, case, user, "GRAPH_EDGE_DELETED", changes, bump=False)
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{case_id}/evidence-graph/edges/{edge_id}/review", response_model=GraphEdgeView)
def review_edge(case_id: UUID, edge_id: UUID, body: GraphReview, principal: CurrentPrincipal,
                db: DbSession) -> GraphEdgeView:
    """OWNER/EDITOR/REVIEWER who did not write or edit the edge. Conclusion citations are reviewed
    together with their conclusion (409 here)."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, REVIEW_ROLES)
    _require_editable(case)
    row = _edge_or_404(db, case_id, edge_id, lock=True)
    _require_item_version("edge", row.version, body.version)
    if row.conclusion_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Conclusion citations are reviewed together with their conclusion.")
    if str(principal.user.id) in (row.contributor_ids or []):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="You wrote or edited this edge; a different member must review it.")
    if body.decision not in DECISIONS_FROM.get(row.review_status, frozenset()):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"A {row.review_status} edge cannot receive a {body.decision} decision.")
    previous = row.review_status
    row.review_status, row.reviewed_by, row.reviewed_at = body.decision, principal.user.id, utcnow()
    row.review_note = body.note
    row.version += 1
    row.updated_at = row.reviewed_at
    _record(db, case, principal.user, "GRAPH_EDGE_REVIEWED",
            {"edge_id": str(row.id), "edge_version": row.version,
             "review_status": {"before": previous, "after": body.decision}}, bump=False, note=body.note)
    db.commit()
    return _edge_response(db, case, role, principal.user, row)
