"""Evidence graph assembly, edge rules and tracing (ABB-16).

Pure functions only (no database, no network): the inputs are already-loaded case records,
so the rules are deterministic and unit tested. See docs/science/EVIDENCE_GRAPH.md.

Scientific guard rails:

- Edges record *which record refers to which*: a value derived from a retrieval, a claim
  citing a paper, a person linking evidence to a hypothesis or conclusion. No edge is a causal
  link, and no node or edge carries a weight, probability or score.
- Derived edges are generated from the stored records on every read and never stored, so they
  cannot drift from their source. Only human-added edges are stored.
- A conclusion is always written by a person. It must cite at least one supporting node, and
  every cited node must trace back to original evidence: a NASA POWER source manifest, a
  farmer-reported case record or a registered paper.
- Rival hypotheses coexist: the same observation may support one hypothesis and contradict
  another; nothing is ranked or resolved automatically.
"""
from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from .forensics import HYPOTHESIS_LIMITATION, SEVERITY_RULE_ID, classify_departure
from .metrics import VARIABLES

NodeType = Literal[
    "SOURCE_MANIFEST", "OBSERVATION", "ANOMALY", "FARMER_REPORT", "FIELD", "PAPER", "EVIDENCE_CLAIM",
    "HYPOTHESIS", "CONCLUSION", "MISSING_DATA",
]
NodeKind = Literal[
    "OBSERVED", "FARMER_REPORTED", "LITERATURE_METADATA", "LITERATURE_REVIEWED", "HYPOTHESIS", "CONCLUSION",
    "MISSING_DATA",
]
Relation = Literal["SUPPORTS", "CONTRADICTS", "LIMITS", "ADDRESSES", "DERIVED_FROM", "CITES"]
EdgeOrigin = Literal["STRUCTURAL", "HYPOTHESIS_LINK", "MANUAL"]
EdgeReviewStatus = Literal["NOT_APPLICABLE", "PENDING", "EVALUATED", "ACCEPTED", "CHANGES_REQUESTED", "REJECTED"]

NODE_TYPES: tuple[str, ...] = NodeType.__args__  # type: ignore[attr-defined]
NODE_KINDS: tuple[str, ...] = NodeKind.__args__  # type: ignore[attr-defined]
RELATIONS: tuple[str, ...] = Relation.__args__  # type: ignore[attr-defined]
MANUAL_RELATIONS: tuple[str, ...] = ("SUPPORTS", "CONTRADICTS", "LIMITS", "ADDRESSES")
SYSTEM_RELATIONS = frozenset({"DERIVED_FROM", "CITES"})
POLARITY = frozenset({"SUPPORTS", "CONTRADICTS"})
#: Relations along which evidence flows backwards during a trace.
GROUNDS_INCOMING = POLARITY            # x SUPPORTS n → x grounds n
GROUNDS_OUTGOING = SYSTEM_RELATIONS    # n DERIVED_FROM x, n CITES x → x grounds n
MAX_TRACE_PATHS = 500

#: Node types that are evidence a person may cite as support or contradiction.
EVIDENCE_TYPES = frozenset({"OBSERVATION", "ANOMALY", "EVIDENCE_CLAIM", "FARMER_REPORT", "FIELD"})
#: Same pattern as the database constraint on stored edges (``db.models.GRAPH_STORABLE_NODE``).
STORABLE_NODE = re.compile(
    r"^(observation|anomaly|claim|hypothesis|conclusion|field):"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    r"|^farmer:(incident|crop-history)$|^missing:no-local-measurements$"
)
NODE_ID = re.compile(r"^[a-z-]+:[0-9a-z:-]{1,120}$")

RELATION_DESCRIPTIONS: dict[str, str] = {
    "DERIVED_FROM": "The source value was computed from the target record (anomaly from observation, observation "
                    "from a NASA POWER retrieval). Generated from stored records.",
    "CITES": "The evidence claim is attributed to the target paper. Generated from stored records.",
    "SUPPORTS": "A person recorded that the source is consistent with the target statement. Not proof and not a "
                "causal link.",
    "CONTRADICTS": "A person recorded that the source argues against the target statement.",
    "LIMITS": "The source (missing data, a limitation or a quality issue) restricts what the target can show.",
    "ADDRESSES": "The conclusion discusses the target hypothesis.",
}

FARMER_LIMITATION = "Reported by the case team; not independently verified."
CONCLUSION_LIMITATION = ("A conclusion is a statement written by a case member over the cited evidence. The system "
                         "does not generate it and does not verify that the evidence establishes it; it is not a "
                         "demonstrated cause and carries no probability or score.")
PAPER_LIMITATION = "Bibliographic metadata does not establish a scientific finding"
UNREVIEWED_CLAIM_LIMITATION = ("Not reviewed: a working note linked to bibliographic metadata, not a reviewed "
                               "finding.")
SUPERSEDED_LIMITATION = "This retrieval was superseded by a newer one; the value is kept because evidence cites it."
FIELD_REMOVED_LIMITATION = "The field these values were retrieved for has been removed from the case."
LABELS = {spec.key: spec.label for spec in VARIABLES}


class GraphRuleError(ValueError):
    """A requested edge or conclusion breaks a graph rule. ``status`` is the HTTP status to use."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Node:
    id: str
    node_type: str
    kind: str
    label: str
    entity_id: UUID | None
    original_evidence: bool
    linkable: bool
    provenance: dict[str, Any]
    limitations: list[str]
    active: bool = True
    status: str | None = None
    start: date | None = None
    end: date | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    id: str
    source: str
    target: str
    relation: str
    origin: str
    review_status: str
    note: str | None = None
    record_id: UUID | None = None
    conclusion_id: UUID | None = None
    author_id: UUID | None = None
    created_at: datetime | None = None
    version: int | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    contributor_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrphanReference:
    referenced_by: str
    missing_node: str
    relation: str
    origin: str


@dataclass
class Graph:
    case_id: UUID
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    orphan_references: list[OrphanReference] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        self.nodes.setdefault(node.id, node)

    def add_edge(self, edge: Edge) -> None:
        if (edge.source, edge.target, edge.relation) not in self.edge_keys():
            self.edges.append(edge)

    def edge_keys(self) -> set[tuple[str, str, str]]:
        return {(e.source, e.target, e.relation) for e in self.edges}

    def incoming(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.target == node_id]

    def outgoing(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.source == node_id]


@dataclass
class GraphInputs:
    """Records of one case. Any object with the ORM attributes works (tests use transient ORM rows)."""
    case: Any
    fields: list[Any] = field(default_factory=list)
    manifests: list[Any] = field(default_factory=list)
    observations: list[Any] = field(default_factory=list)
    anomalies: list[Any] = field(default_factory=list)
    papers: dict[UUID, Any] = field(default_factory=dict)
    claims: list[Any] = field(default_factory=list)
    hypotheses: list[Any] = field(default_factory=list)
    conclusions: list[Any] = field(default_factory=list)
    edges: list[Any] = field(default_factory=list)


# ── node ids ─────────────────────────────────────────────────────────────────

def nid(prefix: str, key: UUID | str) -> str:
    return f"{prefix}:{key}"


INCIDENT = "farmer:incident"
CROP_HISTORY = "farmer:crop-history"
NO_LOCAL_MEASUREMENTS = "missing:no-local-measurements"


def is_storable(node_id: str) -> bool:
    return bool(STORABLE_NODE.match(node_id))


def conclusion_uuid(node_id: str) -> UUID | None:
    if node_id.startswith("conclusion:"):
        try:
            return UUID(node_id.split(":", 1)[1])
        except ValueError:
            return None
    return None


# ── node builders ────────────────────────────────────────────────────────────

def _month(observation: Any) -> str:
    return f"{LABELS.get(observation.variable, observation.variable)}, {observation.observed_at:%b %Y}"


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _manifest_provenance(manifest: Any, fields: dict[UUID, Any]) -> dict[str, Any]:
    field_row = fields.get(manifest.field_id) if manifest.field_id else None
    # Request parameters (which hold the stored field coordinates) are deliberately never copied.
    return {
        "source_manifest_id": manifest.id, "provider": manifest.provider, "dataset": manifest.dataset,
        "dataset_version": manifest.dataset_version, "source_uri": manifest.source_uri,
        "retrieved_at": manifest.retrieved_at, "checksum_sha256": manifest.checksum_sha256,
        "content_sha256": manifest.content_sha256, "processing_version": manifest.processing_version,
        "revision": manifest.revision, "field_id": manifest.field_id,
        "field_label": field_row.label if field_row else None,
    }


def manifest_node(case_id: UUID, manifest: Any, fields: dict[UUID, Any]) -> Node:
    active = manifest.superseded_at is None
    limitations = list(manifest.limitations or [])
    if manifest.field_id is None:
        limitations.append(FIELD_REMOVED_LIMITATION)
    if not active:
        limitations.append(SUPERSEDED_LIMITATION)
    window = (f"{manifest.event_year}, reference {manifest.reference_start}–{manifest.reference_end}"
              if manifest.event_year else "period not recorded")
    return Node(
        id=nid("manifest", manifest.id), node_type="SOURCE_MANIFEST", kind="OBSERVED",
        label=f"{manifest.provider} retrieval r{manifest.revision} ({window})", entity_id=manifest.id,
        original_evidence=True, linkable=False, active=active,
        provenance={"source_kind": "OBSERVED", "case_id": case_id,
                    "description": "Source manifest of a NASA POWER retrieval stored for this case: endpoint, "
                                   "retrieval time, checksums and processing version.",
                    **_manifest_provenance(manifest, fields),
                    "spatial_resolution": manifest.spatial_resolution,
                    "temporal_resolution": manifest.temporal_resolution},
        limitations=limitations or ["Source manifest without recorded limitations."],
        details={"event_year": manifest.event_year, "reference_start": manifest.reference_start,
                 "reference_end": manifest.reference_end, "revision": manifest.revision,
                 "superseded_by_id": str(manifest.superseded_by_id) if manifest.superseded_by_id else None},
    )


def observation_node(case_id: UUID, observation: Any, manifest: Any, fields: dict[UUID, Any]) -> Node:
    active = manifest.superseded_at is None
    has_value = observation.value is not None
    coverage = observation.coverage or {}
    label = (f"{_month(observation)}: {observation.value:.2f} {observation.units}" if has_value
             else f"{_month(observation)}: no value ({coverage.get('reason') or 'incomplete month'})")
    limitations = list(observation.limitations or [])
    if not active:
        limitations.append(SUPERSEDED_LIMITATION)
    return Node(
        id=nid("observation", observation.id), node_type="OBSERVATION",
        kind="OBSERVED" if has_value else "MISSING_DATA", label=label, entity_id=observation.id,
        original_evidence=False, linkable=True, active=active, start=observation.period_start,
        end=observation.period_end,
        provenance={"source_kind": "OBSERVED", "case_id": case_id,
                    "description": "Monthly value aggregated by CropStory from NASA POWER daily point data.",
                    "observation_id": observation.id, **_manifest_provenance(manifest, fields),
                    "spatial_resolution": observation.spatial_resolution,
                    "temporal_resolution": observation.temporal_resolution},
        limitations=limitations or ["Observation without recorded limitations."],
        details={"variable": observation.variable, "value": observation.value, "units": observation.units,
                 "quality_flags": list(observation.quality_flags or []),
                 "coverage_status": coverage.get("status"), "coverage_reason": coverage.get("reason")},
    )


def anomaly_node(case_id: UUID, anomaly: Any, observation: Any, manifest: Any, fields: dict[UUID, Any]) -> Node:
    active = manifest.superseded_at is None
    has_value = anomaly.value is not None
    ref = f"{anomaly.reference_start.year}–{anomaly.reference_end.year}"
    departure = classify_departure(
        anomaly=anomaly.value, observed=observation.value, reference_sd=anomaly.reference_standard_deviation,
        reference_min=anomaly.reference_minimum, reference_max=anomaly.reference_maximum,
        reference_sample_count=anomaly.reference_sample_count,
    )
    label = (f"Anomaly: {_month(observation)}: {anomaly.value:+.2f} {anomaly.units} vs {ref} mean" if has_value
             else f"Anomaly not computed: {_month(observation)}")
    limitations = list(anomaly.limitations or [])
    if not active:
        limitations.append(SUPERSEDED_LIMITATION)
    return Node(
        id=nid("anomaly", anomaly.id), node_type="ANOMALY", kind="OBSERVED" if has_value else "MISSING_DATA",
        label=label, entity_id=anomaly.id, original_evidence=False, linkable=True, active=active,
        start=observation.period_start, end=observation.period_end,
        provenance={"source_kind": "OBSERVED", "case_id": case_id,
                    "description": "Descriptive monthly anomaly against the stored reference years.",
                    "anomaly_id": anomaly.id, "observation_id": observation.id,
                    **_manifest_provenance(manifest, fields),
                    "spatial_resolution": observation.spatial_resolution,
                    "temporal_resolution": observation.temporal_resolution},
        limitations=limitations or ["Anomaly without recorded limitations."],
        details={"value": anomaly.value, "units": anomaly.units, "reference_value": anomaly.reference_value,
                 "reference_start": ref.split("–")[0], "reference_end": ref.split("–")[1],
                 "reference_sample_count": anomaly.reference_sample_count,
                 "reference_status": anomaly.reference_status, "method": anomaly.method,
                 "severity_rule": SEVERITY_RULE_ID, "severity": departure.severity, "direction": departure.direction,
                 "departure_in_reference_sd": departure.departure_in_reference_sd},
    )


def farmer_nodes(case: Any) -> list[Node]:
    base = {"source_kind": "FARMER_REPORTED", "case_id": case.id, "case_version": case.version,
            "description": "Case record entered by the case team."}
    end = case.incident_end.isoformat() if case.incident_end else "end not reported"
    crops = list(case.crop_history or [])
    return [
        Node(id=INCIDENT, node_type="FARMER_REPORT", kind="FARMER_REPORTED",
             label=f"Reported incident period {case.incident_start.isoformat()} – {end}", entity_id=case.id,
             original_evidence=True, linkable=True, start=case.incident_start, end=case.incident_end,
             provenance=dict(base),
             limitations=[FARMER_LIMITATION] + ([] if case.incident_end else ["The incident end date was not "
                                                                                "reported."]),
             details={"incident_start": case.incident_start.isoformat(),
                      "incident_end": _iso(case.incident_end), "incident_notes": case.incident_notes}),
        Node(id=CROP_HISTORY, node_type="FARMER_REPORT", kind="FARMER_REPORTED" if crops else "MISSING_DATA",
             label=("Reported crop history: " + ", ".join(crops)) if crops else "Crop history not reported",
             entity_id=case.id, original_evidence=bool(crops), linkable=True, provenance=dict(base),
             limitations=[FARMER_LIMITATION, "Crop history is undated in the current case record."],
             details={"crops": crops}),
    ]


def field_node(case: Any, field_row: Any) -> Node:
    region = field_row.region_label
    return Node(
        id=nid("field", field_row.id), node_type="FIELD", kind="FARMER_REPORTED",
        label=f"Field: {field_row.label} ({region})", entity_id=field_row.id, original_evidence=True, linkable=True,
        # Never coordinates: the field location is served by GET /cases/{id} with role-based redaction.
        provenance={"source_kind": "FARMER_REPORTED", "case_id": case.id, "case_version": case.version,
                    "description": "Field (parcel) described by the case team.", "field_id": field_row.id,
                    "field_label": field_row.label, "region_label": region},
        limitations=[FARMER_LIMITATION, *[x for x in (field_row.limitations or []) if x != FARMER_LIMITATION]],
        details={"region_label": region, "area_hectares": field_row.area_hectares,
                 "privacy_tier": field_row.privacy_tier},
    )


def paper_node(case_id: UUID, paper: Any) -> Node:
    meta = paper.bibliographic_metadata or {}
    doi = meta.get("doi") if isinstance(meta.get("doi"), str) and meta["doi"].startswith("https://doi.org/") else None
    year = f" ({paper.year})" if paper.year else ""
    return Node(
        id=nid("paper", paper.id), node_type="PAPER", kind="LITERATURE_METADATA",
        label=f"{paper.title[:200]}{year}", entity_id=paper.id, original_evidence=True, linkable=False,
        provenance={"source_kind": "LITERATURE_METADATA", "case_id": case_id,
                    "description": "Registered bibliographic record (OpenAlex metadata, DOI checked in Crossref). "
                                   "It shows that the work exists, not what it found.",
                    "paper_id": paper.id, "doi": doi, "doi_id": paper.doi_id, "doi_status": paper.doi_status,
                    "openalex_id": paper.openalex_id},
        limitations=list(paper.limitations or []) or [PAPER_LIMITATION],
        details={"year": paper.year, "venue": meta.get("venue"), "doi_status": paper.doi_status},
    )


def claim_node(case_id: UUID, claim: Any) -> Node:
    reviewed = claim.review_status == "ACCEPTED"
    limitations = list(claim.limitations or [])
    if not reviewed:
        limitations.insert(0, UNREVIEWED_CLAIM_LIMITATION)
    return Node(
        id=nid("claim", claim.id), node_type="EVIDENCE_CLAIM",
        kind="LITERATURE_REVIEWED" if reviewed else "LITERATURE_METADATA", label=claim.claim_text[:160],
        entity_id=claim.id, original_evidence=False, linkable=True, status=claim.review_status,
        provenance={"source_kind": "LITERATURE_REVIEWED" if reviewed else "LITERATURE_METADATA", "case_id": case_id,
                    "description": ("Claim checked by a named member against the full text of the cited paper."
                                    if reviewed else "Claim written by a case member; not reviewed."),
                    "claim_id": claim.id, "paper_id": claim.paper_id, "created_by_id": claim.created_by,
                    "created_at": claim.created_at, "reviewed_by_id": claim.reviewed_by,
                    "reviewed_at": claim.reviewed_at, "origin": claim.origin},
        limitations=limitations or [UNREVIEWED_CLAIM_LIMITATION],
        details={"review_status": claim.review_status, "is_reviewed": reviewed,
                 "evidence_basis": claim.evidence_basis, "study_design": claim.study_design},
    )


def hypothesis_node(case_id: UUID, hypothesis: Any) -> Node:
    return Node(
        id=nid("hypothesis", hypothesis.id), node_type="HYPOTHESIS", kind="HYPOTHESIS",
        label=hypothesis.title or hypothesis.statement[:160], entity_id=hypothesis.id, original_evidence=False,
        linkable=True, status=hypothesis.status,
        provenance={"source_kind": "HYPOTHESIS", "case_id": case_id,
                    "description": ("Template hypothesis added by the case team." if hypothesis.origin == "TEMPLATE"
                                    else "Hypothesis written by the case team."),
                    "hypothesis_id": hypothesis.id, "created_by_id": hypothesis.created_by_id,
                    "created_at": hypothesis.created_at, "evaluated_by_id": hypothesis.evaluated_by_id,
                    "evaluated_at": hypothesis.evaluated_at, "origin": hypothesis.origin},
        limitations=list(hypothesis.limitations or []) or [HYPOTHESIS_LIMITATION],
        details={"statement": hypothesis.statement, "status": hypothesis.status,
                 "evaluation_note": hypothesis.evaluation_note},
    )


def conclusion_node(case_id: UUID, conclusion: Any) -> Node:
    return Node(
        id=nid("conclusion", conclusion.id), node_type="CONCLUSION", kind="CONCLUSION",
        label=conclusion.title or conclusion.statement[:160], entity_id=conclusion.id, original_evidence=False,
        linkable=True, status=conclusion.review_status,
        provenance={"source_kind": "CONCLUSION", "case_id": case_id,
                    "description": "Conclusion written by a case member over the cited evidence.",
                    "conclusion_id": conclusion.id, "created_by_id": conclusion.created_by_id,
                    "created_at": conclusion.created_at, "reviewed_by_id": conclusion.reviewed_by,
                    "reviewed_at": conclusion.reviewed_at},
        limitations=[CONCLUSION_LIMITATION, *[x for x in (conclusion.limitations or [])
                                              if x != CONCLUSION_LIMITATION]],
        details={"statement": conclusion.statement, "review_status": conclusion.review_status,
                 "review_note": conclusion.review_note},
    )


def _missing_node(case: Any, node_id: str, label: str, description: str, limitation: str, *,
                  linkable: bool, start: date | None = None, end: date | None = None,
                  details: dict[str, Any] | None = None) -> Node:
    return Node(id=node_id, node_type="MISSING_DATA", kind="MISSING_DATA", label=label, entity_id=None,
                original_evidence=False, linkable=linkable, start=start, end=end,
                provenance={"source_kind": "MISSING_DATA", "case_id": case.id, "case_version": case.version,
                            "description": description},
                limitations=[limitation], details=details or {})


# ── assembly ─────────────────────────────────────────────────────────────────

def _structural(source: str, target: str, relation: str) -> Edge:
    return Edge(id=f"{relation.lower()}:{source}->{target}", source=source, target=target, relation=relation,
                origin="STRUCTURAL", review_status="NOT_APPLICABLE")


def stored_edge(row: Any) -> Edge:
    return Edge(
        id=nid("edge", row.id), source=row.source_node, target=row.target_node, relation=row.relation,
        origin="MANUAL", review_status=row.review_status, note=row.note, record_id=row.id,
        conclusion_id=row.conclusion_id, author_id=row.created_by_id, created_at=row.created_at, version=row.version,
        reviewed_by=row.reviewed_by, reviewed_at=row.reviewed_at, review_note=row.review_note,
        contributor_ids=tuple(row.contributor_ids or ()),
    )


def build_graph(data: GraphInputs, *, include_superseded: bool = False) -> Graph:
    """Assemble the case graph. Superseded retrievals are included when ``include_superseded`` is
    set or when evidence (a hypothesis link or a stored edge) refers to them."""
    case = data.case
    graph = Graph(case_id=case.id)
    fields = {f.id: f for f in data.fields}
    manifests = {m.id: m for m in data.manifests}
    observations = {o.id: o for o in data.observations}
    anomaly_by_observation = {a.observation_id: a for a in data.anomalies}
    anomaly_by_id = {a.id: a for a in data.anomalies}
    claims = {c.id: c for c in data.claims}

    referenced: set[str] = set()
    for hypothesis in data.hypotheses:
        referenced.update(str(i) for i in (*hypothesis.supporting_evidence_ids, *hypothesis.contradicting_evidence_ids))
    for row in data.edges:
        referenced.update(n.split(":", 1)[1] for n in (row.source_node, row.target_node) if ":" in n)

    # observed data: manifest ← observation ← anomaly
    for observation in sorted(observations.values(), key=lambda o: (o.observed_at, o.variable, str(o.id))):
        manifest = manifests.get(observation.source_manifest_id)
        if manifest is None:  # pragma: no cover - composite FK guarantees the manifest
            continue
        anomaly = anomaly_by_observation.get(observation.id)
        wanted = (include_superseded or manifest.superseded_at is None or str(observation.id) in referenced
                  or (anomaly is not None and str(anomaly.id) in referenced))
        if not wanted:
            continue
        graph.add_node(manifest_node(case.id, manifest, fields))
        obs_node = observation_node(case.id, observation, manifest, fields)
        graph.add_node(obs_node)
        graph.add_edge(_structural(obs_node.id, nid("manifest", manifest.id), "DERIVED_FROM"))
        if anomaly is not None:
            node = anomaly_node(case.id, anomaly, observation, manifest, fields)
            graph.add_node(node)
            graph.add_edge(_structural(node.id, obs_node.id, "DERIVED_FROM"))

    # farmer-reported facts and fields (never coordinates)
    for node in farmer_nodes(case):
        graph.add_node(node)
    for field_row in sorted(fields.values(), key=lambda f: (f.label, str(f.id))):
        graph.add_node(field_node(case, field_row))

    # missing data that applies to the whole case
    graph.add_node(_missing_node(
        case, NO_LOCAL_MEASUREMENTS, "No field-scale measurements recorded",
        "The case holds no rain-gauge, soil-moisture, irrigation or crop-stage records.",
        "Regional NASA POWER values cannot replace field measurements.", linkable=True,
        start=case.incident_start, end=case.incident_end))
    covered = {m.event_year for m in manifests.values() if m.superseded_at is None and m.event_year is not None}
    last = (case.incident_end or case.incident_start).year
    for year in range(case.incident_start.year, last + 1):
        if year not in covered:
            graph.add_node(_missing_node(
                case, f"missing:no-observations:{year}", f"No NASA POWER observations stored for {year}",
                "No active retrieval covers this year of the reported incident period.",
                "Absence of stored observations is not evidence of normal conditions.", linkable=False,
                details={"year": year}))

    # literature: claim → paper
    for claim in sorted(claims.values(), key=lambda c: (c.created_at, str(c.id))):
        node = claim_node(case.id, claim)
        graph.add_node(node)
        paper = data.papers.get(claim.paper_id)
        if paper is not None:
            graph.add_node(paper_node(case.id, paper))
            graph.add_edge(_structural(node.id, nid("paper", paper.id), "CITES"))
        else:  # pragma: no cover - the claim → paper FK is RESTRICT
            graph.orphan_references.append(OrphanReference(node.id, nid("paper", claim.paper_id), "CITES",
                                                           "STRUCTURAL"))

    # hypotheses with their evidence links and missing evidence
    def evidence_node_id(raw: str) -> str | None:
        try:
            key = UUID(str(raw))
        except ValueError:
            return None
        if key in anomaly_by_id:
            return nid("anomaly", key)
        if key in observations:
            return nid("observation", key)
        if key in claims:
            return nid("claim", key)
        return None

    for hypothesis in sorted(data.hypotheses, key=lambda h: (h.created_at, str(h.id))):
        node = hypothesis_node(case.id, hypothesis)
        graph.add_node(node)
        review = "PENDING" if hypothesis.status == "OPEN" else "EVALUATED"
        for relation, ids in (("SUPPORTS", hypothesis.supporting_evidence_ids),
                              ("CONTRADICTS", hypothesis.contradicting_evidence_ids)):
            for raw in ids:
                source = evidence_node_id(raw)
                if source is None or source not in graph.nodes:
                    graph.orphan_references.append(OrphanReference(node.id, str(raw), relation, "HYPOTHESIS_LINK"))
                    continue
                graph.add_edge(Edge(id=f"hypothesis-link:{relation.lower()}:{source}->{node.id}", source=source,
                                    target=node.id, relation=relation, origin="HYPOTHESIS_LINK",
                                    review_status=review, note=hypothesis.evaluation_note,
                                    reviewed_by=hypothesis.evaluated_by_id, reviewed_at=hypothesis.evaluated_at))
        for index, text in enumerate(hypothesis.missing_evidence or [], start=1):
            missing = _missing_node(case, f"missing:hypothesis:{hypothesis.id}:{index}", f"Missing: {text[:160]}",
                                    "Evidence the hypothesis needs and the case does not hold.",
                                    "Recorded as missing on the hypothesis; nothing is estimated in its place.",
                                    linkable=False, details={"hypothesis_id": str(hypothesis.id), "text": text})
            graph.add_node(missing)
            graph.add_edge(Edge(id=f"hypothesis-link:limits:{missing.id}->{node.id}", source=missing.id,
                                target=node.id, relation="LIMITS", origin="HYPOTHESIS_LINK",
                                review_status=review))

    for conclusion in sorted(data.conclusions, key=lambda c: (c.created_at, str(c.id))):
        graph.add_node(conclusion_node(case.id, conclusion))

    # human-added edges; endpoints must exist in this case's graph
    for row in sorted(data.edges, key=lambda r: (r.created_at, str(r.id))):
        edge = stored_edge(row)
        missing = [n for n in (edge.source, edge.target) if n not in graph.nodes]
        if missing:
            for node_id in missing:
                graph.orphan_references.append(OrphanReference(edge.id, node_id, edge.relation, "MANUAL"))
            continue
        graph.add_edge(edge)
    return graph


# ── tracing ──────────────────────────────────────────────────────────────────

def grounds(graph: Graph, node_id: str) -> list[tuple[Edge, str]]:
    """Edges that ground ``node_id`` in other records, with the record they lead to."""
    result = [(e, e.source) for e in graph.edges if e.target == node_id and e.relation in GROUNDS_INCOMING]
    result += [(e, e.target) for e in graph.edges if e.source == node_id and e.relation in GROUNDS_OUTGOING]
    return result


def grounded(graph: Graph, node_id: str, _memo: dict[str, bool] | None = None,
             _stack: frozenset[str] = frozenset()) -> bool:
    """True when every grounding branch from ``node_id`` ends at original evidence (a source manifest,
    a farmer-reported record or a registered paper). A node with no grounds is grounded only if it is
    original evidence itself; cycles count as ungrounded."""
    memo = {} if _memo is None else _memo
    if node_id in memo:
        return memo[node_id]
    node = graph.nodes.get(node_id)
    if node is None or node_id in _stack:
        return False
    if node.original_evidence:
        memo[node_id] = True
        return True
    nexts = grounds(graph, node_id)
    result = bool(nexts) and all(grounded(graph, nxt, memo, _stack | {node_id}) for _, nxt in nexts)
    memo[node_id] = result
    return result


@dataclass(frozen=True)
class TraceStep:
    node_id: str
    edge_id: str | None
    relation: str | None


@dataclass
class TracePath:
    steps: list[TraceStep]
    ends_at_original_evidence: bool


@dataclass
class Trace:
    root: str
    complete: bool
    paths: list[TracePath]
    truncated: bool
    node_ids: list[str]            # root and every node reached through grounding edges
    edge_ids: list[str]            # grounding edges
    limiting_edge_ids: list[str]   # LIMITS edges into the traced nodes
    limiting_node_ids: list[str]   # their sources (not traversed further)
    original_evidence: list[str]
    dead_ends: list[str]


def trace(graph: Graph, root: str, *, max_paths: int = MAX_TRACE_PATHS) -> Trace:
    """Every path from ``root`` back to original evidence, following SUPPORTS/CONTRADICTS
    backwards and DERIVED_FROM/CITES forwards. LIMITS edges into the traced nodes are returned
    separately: they qualify the evidence but are not part of a path."""
    if root not in graph.nodes:
        raise KeyError(root)
    # Subgraph reachable through grounding edges (breadth first, always complete).
    nodes: dict[str, None] = {root: None}
    edges: dict[str, None] = {}
    dead_ends: dict[str, None] = {}
    queue = [root]
    while queue:
        current = queue.pop(0)
        nexts = grounds(graph, current)
        if not nexts and not graph.nodes[current].original_evidence:
            dead_ends.setdefault(current)
        for edge, nxt in nexts:
            edges.setdefault(edge.id)
            if nxt not in nodes:
                nodes[nxt] = None
                queue.append(nxt)

    # Individual paths for display (depth first, capped).
    paths: list[TracePath] = []
    truncated = False

    def walk(node_id: str, steps: list[TraceStep], visiting: frozenset[str]) -> None:
        nonlocal truncated
        if truncated:
            return
        node = graph.nodes[node_id]
        nexts = [(e, n) for e, n in grounds(graph, node_id) if n not in visiting]
        if node.original_evidence or not nexts:
            if len(paths) >= max_paths:
                truncated = True
                return
            paths.append(TracePath(steps=steps, ends_at_original_evidence=node.original_evidence))
            return
        for edge, nxt in nexts:
            walk(nxt, [*steps, TraceStep(nxt, edge.id, edge.relation)], visiting | {nxt})

    walk(root, [TraceStep(root, None, None)], frozenset({root}))
    limiting = [e for e in graph.edges if e.relation == "LIMITS" and e.target in nodes]
    original = [n for n in nodes if graph.nodes[n].original_evidence]
    return Trace(root=root, complete=grounded(graph, root), paths=paths, truncated=truncated, node_ids=list(nodes),
                 edge_ids=list(edges), limiting_edge_ids=[e.id for e in limiting],
                 limiting_node_ids=list(dict.fromkeys(e.source for e in limiting if e.source not in nodes)),
                 original_evidence=original, dead_ends=list(dead_ends))


def trace_problems(graph: Graph, result: Trace) -> list[str]:
    """Reasons a traced conclusion cannot be accepted as reviewed (empty when none): a branch that
    does not reach original evidence, an unreviewed literature claim or an unevaluated hypothesis
    on a grounding path."""
    problems: list[str] = []
    if not result.complete:
        ends = ", ".join(result.dead_ends) or result.root
        problems.append(f"not every cited branch reaches original evidence (dead ends: {ends})")
    for node_id in result.node_ids:
        node = graph.nodes[node_id]
        if node_id == result.root:
            continue
        if node.node_type == "EVIDENCE_CLAIM" and node.status != "ACCEPTED":
            problems.append(f"{node_id} is not a reviewed claim (status {node.status})")
        elif node.node_type == "HYPOTHESIS" and node.status == "OPEN":
            problems.append(f"{node_id} has not been evaluated (status OPEN)")
    return problems


# ── edge rules ───────────────────────────────────────────────────────────────

def _creates_cycle(graph: Graph, source: str, target: str) -> bool:
    """Would ``source → target`` (source grounds target) close a cycle? Yes when ``target`` already
    grounds ``source``, i.e. walking the grounds of ``source`` reaches ``target``."""
    seen: set[str] = set()
    stack = [source]
    while stack:
        current = stack.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(nxt for _, nxt in grounds(graph, current))
    return False


def check_edge(graph: Graph, source: str, target: str, relation: str) -> None:
    """Raise ``GraphRuleError`` unless a person may add ``source -relation-> target`` to this graph.

    Unknown node ids and ids of another case are rejected identically (422): a stored edge can
    never point at a node that does not exist in the same case."""
    if relation not in MANUAL_RELATIONS:
        raise GraphRuleError(422, f"{relation} edges are generated from stored records and cannot be added by hand.")
    if source == target:
        raise GraphRuleError(422, "An edge cannot connect a node to itself.")
    missing = [n for n in (source, target) if n not in graph.nodes]
    if missing:
        raise GraphRuleError(422, "Node not found in this case's evidence graph: " + ", ".join(missing))
    s, t = graph.nodes[source], graph.nodes[target]
    for node in (s, t):
        if not node.linkable or not is_storable(node.id):
            raise GraphRuleError(422, f"{node.id} is derived on read and cannot be referenced by a stored edge.")
    if relation in POLARITY:
        if t.node_type == "HYPOTHESIS":
            raise GraphRuleError(422, "Use the hypothesis evidence links (PATCH …/hypotheses/{id}) to support or "
                                      "contradict a hypothesis.")
        if t.node_type not in ("CONCLUSION", "EVIDENCE_CLAIM"):
            raise GraphRuleError(422, f"{relation} edges must point to a conclusion or an evidence claim.")
        allowed = EVIDENCE_TYPES | ({"HYPOTHESIS"} if t.node_type == "CONCLUSION" else set())
        if s.node_type not in allowed:
            raise GraphRuleError(422, f"A {s.node_type} node cannot {relation.lower()[:-1]} a {t.node_type} node.")
        if s.kind == "MISSING_DATA":
            raise GraphRuleError(422, "Missing data cannot support or contradict anything; link it with LIMITS.")
    elif relation == "LIMITS":
        if t.node_type not in ("CONCLUSION", "HYPOTHESIS", "EVIDENCE_CLAIM"):
            raise GraphRuleError(422, "LIMITS edges must point to a conclusion, a hypothesis or an evidence claim.")
        if s.node_type not in EVIDENCE_TYPES | {"MISSING_DATA"}:
            raise GraphRuleError(422, f"A {s.node_type} node cannot limit another node.")
    elif relation == "ADDRESSES" and (s.node_type != "CONCLUSION" or t.node_type != "HYPOTHESIS"):
        raise GraphRuleError(422, "ADDRESSES edges go from a conclusion to a hypothesis.")
    keys = graph.edge_keys()
    if (source, target, relation) in keys:
        raise GraphRuleError(409, "This edge already exists in the graph.")
    if relation in POLARITY and (source, target, ({"SUPPORTS", "CONTRADICTS"} - {relation}).pop()) in keys:
        raise GraphRuleError(422, "A node cannot both support and contradict the same target.")
    if relation in POLARITY and _creates_cycle(graph, source, target):
        raise GraphRuleError(422, "This edge would make the evidence circular.")


def require_grounded(graph: Graph, source: str) -> None:
    """A node cited as support or contradiction must itself trace back to original evidence."""
    if not grounded(graph, source):
        raise GraphRuleError(422, f"{source} does not trace back to original evidence (for a hypothesis: link "
                                  "observed or literature evidence to it first).")


def edges_of_conclusion(graph: Graph, conclusion_node_id: str) -> list[Edge]:
    return [e for e in graph.edges if e.origin == "MANUAL"
            and conclusion_node_id in (e.source, e.target)]


def counts(nodes: Iterable[Node], edges: Iterable[Edge]) -> dict[str, dict[str, int]]:
    by_kind: dict[str, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    by_relation: dict[str, int] = defaultdict(int)
    by_origin: dict[str, int] = defaultdict(int)
    for node in nodes:
        by_kind[node.kind] += 1
        by_type[node.node_type] += 1
    for edge in edges:
        by_relation[edge.relation] += 1
        by_origin[edge.origin] += 1
    return {"nodes_by_kind": dict(by_kind), "nodes_by_type": dict(by_type),
            "edges_by_relation": dict(by_relation), "edges_by_origin": dict(by_origin)}
