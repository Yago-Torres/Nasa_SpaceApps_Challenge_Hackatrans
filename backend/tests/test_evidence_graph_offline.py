"""ABB-16 evidence graph assembly, edge rules and tracing without a database.

Inputs are transient (never persisted) ORM rows. Every record, person and value is SYNTHETIC.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from agroblackbox.api.evidence_graph import edge_view, node_view
from agroblackbox.api.graph_dto import ConclusionView, EvidenceGraphView, GraphEdgeView
from agroblackbox.db.models import (
    GRAPH_STORABLE_NODE,
    Anomaly,
    Case,
    ClaimDisagreementReview,
    EvidenceClaim,
    EvidenceConclusion,
    EvidenceGraphEdge,
    Field,
    Hypothesis,
    Observation,
    Paper,
    SourceManifest,
)
from agroblackbox.services import evidence_graph as eg

T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
LAT, LON = 41.6543, -0.8765
RES = {"value": 0.5, "unit": "degree", "description": "Synthetic grid cell"}
MONTH = {"value": 1, "unit": "month", "description": "Synthetic monthly aggregate"}


def manifest(case_id, field_id, *, superseded: bool = False) -> SourceManifest:
    return SourceManifest(
        id=uuid4(), case_id=case_id, provider="NASA POWER", dataset="Synthetic POWER fixture",
        source_uri="https://power.larc.nasa.gov/api/temporal/daily/point",
        query_parameters={"latitude": LAT, "longitude": LON}, retrieved_at=T0, checksum_sha256="a" * 64,
        dataset_version="POWER Daily API v2.10.3", processing_version="synthetic-1", license=None,
        spatial_resolution=RES, temporal_resolution=MONTH, limitations=["Synthetic manifest"], field_id=field_id,
        content_sha256="b" * 64, revision=1, superseded_at=T0 if superseded else None, superseded_by_id=None,
        event_year=2022, reference_start=2010, reference_end=2021, details={},
    )


def observation(case_id, manifest_row, month: int, value: float | None) -> Observation:
    return Observation(
        id=uuid4(), case_id=case_id, source_manifest_id=manifest_row.id, source_kind="OBSERVED",
        variable="precipitation", value=value, units="mm", observed_at=datetime(2022, month, 1, tzinfo=UTC),
        spatial_resolution=RES, temporal_resolution=MONTH, quality_flags=[] if value is not None else ["PARTIAL"],
        limitations=["Synthetic observation"], period_start=date(2022, month, 1), period_end=date(2022, month, 28),
        coverage={"status": "complete" if value is not None else "partial",
                  "reason": None if value is not None else "Synthetic gap"},
    )


def anomaly(case_id, observation_row, value: float | None) -> Anomaly:
    return Anomaly(
        id=uuid4(), case_id=case_id, observation_id=observation_row.id, value=value, units="mm",
        method="synthetic", reference_start=date(2010, 1, 1), reference_end=date(2021, 12, 31),
        reference_sample_count=12, reference_status="complete", reference_value=46.5,
        reference_standard_deviation=10.0, reference_minimum=30.0, reference_maximum=60.0,
        reference_years_excluded=[], quality_flags=[], limitations=["Synthetic anomaly"], created_at=T0,
    )


def hypothesis(case_id, title, *, supports=(), contradicts=(), status="OPEN", missing=()) -> Hypothesis:
    return Hypothesis(
        id=uuid4(), case_id=case_id, title=title, statement=f"{title} may have contributed (synthetic).",
        status=status, supporting_evidence_ids=[str(i) for i in supports],
        contradicting_evidence_ids=[str(i) for i in contradicts], missing_evidence=list(missing),
        limitations=["Synthetic hypothesis"], origin="USER", template_code=None, verification_questions=[],
        evaluation_note=None if status == "OPEN" else "Synthetic note", evaluated_by_id=None, evaluated_at=None,
        version=1, created_by_id=None, created_at=T0, updated_at=T0,
    )


def claim(case_id, paper_id, text, *, status="PENDING") -> EvidenceClaim:
    return EvidenceClaim(
        id=uuid4(), case_id=case_id, paper_id=paper_id, claim_text=text, study_context="Synthetic context",
        review_status=status, reviewed_by=uuid4() if status == "ACCEPTED" else None,
        reviewed_at=T0 if status == "ACCEPTED" else None, limitations=["Synthetic claim"], created_by=None,
        created_at=T0, updated_at=T0, version=1, study_design="FIELD_EXPERIMENT", context={}, reported_outcome={},
        source_locator={}, quoted_fragment=None, evidence_basis="FULL_TEXT", access_basis="AUTHOR_PROVIDED_COPY",
        content_license="synthetic", origin="MANUAL", origin_ref=None,
    )


def conclusion(case_id, *, status="PENDING") -> EvidenceConclusion:
    return EvidenceConclusion(
        id=uuid4(), case_id=case_id, title="Synthetic conclusion", statement="Synthetic conclusion statement.",
        limitations=["Synthetic limitation"], review_status=status, review_note=None, reviewed_by=None,
        reviewed_at=None, contributor_ids=[], created_by_id=None, created_at=T0, updated_at=T0, version=1,
    )


def stored(case_id, source, target, relation, *, conclusion_id=None) -> EvidenceGraphEdge:
    return EvidenceGraphEdge(
        id=uuid4(), case_id=case_id, source_node=source, target_node=target, relation=relation,
        note="Synthetic note", conclusion_id=conclusion_id, review_status="PENDING", review_note=None,
        reviewed_by=None, reviewed_at=None, contributor_ids=[], created_by_id=None, created_at=T0, updated_at=T0,
        version=1,
    )


@pytest.fixture
def world():
    case = Case(id=uuid4(), title="SYNTHETIC case", incident_start=date(2022, 5, 1), incident_end=date(2023, 3, 31),
                crop_history=["wheat"], incident_notes="Synthetic yellowing in June.", version=3)
    field = Field(id=uuid4(), case_id=case.id, label="Synthetic parcel", privacy_tier="APPROXIMATE", latitude=LAT,
                  longitude=LON, region_label="Synthetic region", area_hectares=4.0, precise_location_consent=False,
                  limitations=["Synthetic parcel"], rounding_deg=0.5)
    active = manifest(case.id, field.id)
    old = manifest(case.id, field.id, superseded=True)
    june = observation(case.id, active, 6, 0.0)
    march = observation(case.id, active, 3, None)
    old_june = observation(case.id, old, 6, 0.2)
    june_a, march_a, old_june_a = anomaly(case.id, june, -46.5), anomaly(case.id, march, None), anomaly(
        case.id, old_june, -46.3)
    paper = Paper(id=uuid4(), title="Synthetic paper", year=2020, doi_id="10.5555/synthetic.1",
                  doi_status="VERIFIED_CROSSREF", openalex_id=None,
                  bibliographic_metadata={"doi": "https://doi.org/10.5555/synthetic.1"},
                  limitations=["Bibliographic metadata does not establish a scientific finding"])
    reviewed = claim(case.id, paper.id, "Synthetic reviewed claim", status="ACCEPTED")
    pending = claim(case.id, paper.id, "Synthetic pending claim")
    water = hypothesis(case.id, "Water deficit", supports=[june_a.id, reviewed.id], status="COMPATIBLE",
                       missing=["Soil moisture"])
    excess = hypothesis(case.id, "Excess water", contradicts=[june_a.id])
    bare = hypothesis(case.id, "Pest", missing=["Field inspection"])
    data = eg.GraphInputs(case=case, fields=[field], manifests=[active, old], observations=[june, march, old_june],
                          anomalies=[june_a, march_a, old_june_a], papers={paper.id: paper},
                          claims=[reviewed, pending], hypotheses=[water, excess, bare])
    return {"data": data, "case": case, "field": field, "active": active, "old": old, "june": june, "march": march,
            "june_a": june_a, "march_a": march_a, "old_june": old_june, "old_june_a": old_june_a, "paper": paper,
            "reviewed": reviewed, "pending": pending, "water": water, "excess": excess, "bare": bare}


def ids(prefix, row):
    return f"{prefix}:{row.id}"


# ── assembly ─────────────────────────────────────────────────────────────────

def test_graph_assembles_every_layer_with_structural_edges(world):
    graph = eg.build_graph(world["data"])
    nodes = graph.nodes
    june_a, june, active = ids("anomaly", world["june_a"]), ids("observation", world["june"]), ids("manifest",
                                                                                                    world["active"])
    assert nodes[june_a].kind == "OBSERVED" and nodes[june].kind == "OBSERVED"
    assert nodes[active].original_evidence and not nodes[active].linkable
    assert nodes[ids("anomaly", world["march_a"])].kind == "MISSING_DATA"  # null anomaly is a data gap
    assert nodes[eg.INCIDENT].kind == "FARMER_REPORTED" and nodes[eg.INCIDENT].original_evidence
    assert nodes[ids("field", world["field"])].node_type == "FIELD"
    assert nodes[ids("claim", world["reviewed"])].kind == "LITERATURE_REVIEWED"
    assert nodes[ids("claim", world["pending"])].kind == "LITERATURE_METADATA"
    assert nodes[ids("paper", world["paper"])].provenance["doi"] == "https://doi.org/10.5555/synthetic.1"
    assert eg.NO_LOCAL_MEASUREMENTS in nodes and "missing:no-observations:2023" in nodes
    assert "missing:no-observations:2022" not in nodes  # 2022 is covered by the active retrieval
    keys = graph.edge_keys()
    assert (june_a, june, "DERIVED_FROM") in keys and (june, active, "DERIVED_FROM") in keys
    assert (ids("claim", world["reviewed"]), ids("paper", world["paper"]), "CITES") in keys
    assert {e.origin for e in graph.edges} == {"STRUCTURAL", "HYPOTHESIS_LINK"}
    assert all(e.source in nodes and e.target in nodes for e in graph.edges)  # no orphan edges
    assert graph.orphan_references == []
    tallies = eg.counts(nodes.values(), graph.edges)
    assert sum(tallies["nodes_by_kind"].values()) == len(nodes)
    assert sum(tallies["edges_by_relation"].values()) == len(graph.edges)


def test_contradictory_hypotheses_coexist_without_ranking(world):
    graph = eg.build_graph(world["data"])
    june_a = ids("anomaly", world["june_a"])
    water, excess = ids("hypothesis", world["water"]), ids("hypothesis", world["excess"])
    links = {(e.target, e.relation, e.review_status) for e in graph.edges if e.source == june_a
             and e.origin == "HYPOTHESIS_LINK"}
    assert links == {(water, "SUPPORTS", "EVALUATED"), (excess, "CONTRADICTS", "PENDING")}
    assert graph.nodes[water].status == "COMPATIBLE" and graph.nodes[excess].status == "OPEN"
    missing = [e for e in graph.edges if e.relation == "LIMITS" and e.target == water]
    assert len(missing) == 1 and graph.nodes[missing[0].source].kind == "MISSING_DATA"
    for node in graph.nodes.values():
        blob = json.dumps(node.details, default=str).lower()
        assert "probability" not in blob and "score" not in blob


def test_superseded_values_only_when_referenced_or_requested(world):
    old = ids("observation", world["old_june"])
    assert old not in eg.build_graph(world["data"]).nodes
    assert eg.build_graph(world["data"], include_superseded=True).nodes[old].active is False
    world["excess"].supporting_evidence_ids = [str(world["old_june_a"].id)]
    graph = eg.build_graph(world["data"])
    assert graph.nodes[ids("anomaly", world["old_june_a"])].active is False
    assert graph.nodes[ids("manifest", world["old"])].active is False  # its trace stays complete
    assert eg.grounded(graph, ids("anomaly", world["old_june_a"]))


def test_no_node_carries_coordinates(world):
    graph = eg.build_graph(world["data"], include_superseded=True)
    blob = json.dumps([n.__dict__ for n in graph.nodes.values()], default=str)
    assert str(LAT) not in blob and str(LON) not in blob
    assert "query_parameters" not in blob


def test_orphan_references_are_reported_and_never_drawn(world):
    world["excess"].contradicting_evidence_ids = [str(uuid4())]
    world["data"].edges = [stored(world["case"].id, f"claim:{uuid4()}", ids("claim", world["pending"]), "SUPPORTS")]
    graph = eg.build_graph(world["data"])
    origins = sorted(o.origin for o in graph.orphan_references)
    assert origins == ["HYPOTHESIS_LINK", "MANUAL"]
    assert all(e.source in graph.nodes and e.target in graph.nodes for e in graph.edges)


# ── tracing ──────────────────────────────────────────────────────────────────

def _with_conclusion(world, *edges):
    c = conclusion(world["case"].id)
    node = ids("conclusion", c)
    world["data"].conclusions = [c]
    world["data"].edges = [stored(world["case"].id, s, node, r, conclusion_id=c.id) for s, r in edges]
    return c, node


def test_conclusion_traces_back_to_original_evidence(world):
    _, node = _with_conclusion(world, (ids("anomaly", world["june_a"]), "SUPPORTS"),
                               (ids("hypothesis", world["water"]), "SUPPORTS"), (eg.INCIDENT, "SUPPORTS"),
                               (eg.NO_LOCAL_MEASUREMENTS, "LIMITS"))
    graph = eg.build_graph(world["data"])
    result = eg.trace(graph, node)
    assert result.complete and not result.dead_ends and not result.truncated
    assert all(p.ends_at_original_evidence for p in result.paths)
    assert set(result.original_evidence) == {ids("manifest", world["active"]), ids("paper", world["paper"]),
                                             eg.INCIDENT}
    # anomaly → observation → manifest, directly and through the hypothesis; hypothesis → claim → paper
    assert len(result.paths) == 4
    via_claim = next(p for p in result.paths if p.steps[-1].node_id == ids("paper", world["paper"]))
    assert [s.relation for s in via_claim.steps] == [None, "SUPPORTS", "SUPPORTS", "CITES"]
    assert eg.NO_LOCAL_MEASUREMENTS in result.limiting_node_ids
    assert any(graph.nodes[n].kind == "MISSING_DATA" for n in result.limiting_node_ids)  # hypothesis gap
    assert eg.trace_problems(graph, result) == []  # reviewed claim, evaluated hypothesis


def test_incomplete_trace_and_review_blockers(world):
    _, node = _with_conclusion(world, (ids("hypothesis", world["bare"]), "SUPPORTS"),
                               (ids("claim", world["pending"]), "CONTRADICTS"))
    graph = eg.build_graph(world["data"])
    result = eg.trace(graph, node)
    assert not result.complete and result.dead_ends == [ids("hypothesis", world["bare"])]
    problems = " ".join(eg.trace_problems(graph, result))
    assert "dead ends" in problems and "not a reviewed claim" in problems and "not been evaluated" in problems
    with pytest.raises(eg.GraphRuleError):
        eg.require_grounded(graph, ids("hypothesis", world["bare"]))
    with pytest.raises(KeyError):
        eg.trace(graph, "conclusion:" + str(uuid4()))


def test_original_evidence_trace_is_a_single_complete_path(world):
    graph = eg.build_graph(world["data"])
    result = eg.trace(graph, eg.INCIDENT)
    assert result.complete and len(result.paths) == 1 and result.paths[0].steps[0].edge_id is None


def test_trace_paths_are_capped_but_subgraph_is_complete(world):
    _, node = _with_conclusion(world, (ids("anomaly", world["june_a"]), "SUPPORTS"),
                               (ids("hypothesis", world["water"]), "SUPPORTS"))
    graph = eg.build_graph(world["data"])
    result = eg.trace(graph, node, max_paths=1)
    assert result.truncated and len(result.paths) == 1
    assert ids("paper", world["paper"]) in result.node_ids and result.complete


# ── edge rules ───────────────────────────────────────────────────────────────

def test_edge_rules(world):
    c, node = _with_conclusion(world, (ids("anomaly", world["june_a"]), "SUPPORTS"))
    graph = eg.build_graph(world["data"])
    reviewed, pending = ids("claim", world["reviewed"]), ids("claim", world["pending"])
    june_a = ids("anomaly", world["june_a"])

    def status_of(source, target, relation):
        try:
            eg.check_edge(graph, source, target, relation)
        except eg.GraphRuleError as exc:
            return exc.status
        return None

    foreign_anomaly = f"anomaly:{uuid4()}"  # another case's record is not in this graph
    assert status_of(foreign_anomaly, node, "SUPPORTS") == 422
    assert status_of(june_a, f"conclusion:{uuid4()}", "SUPPORTS") == 422
    assert status_of(june_a, june_a, "LIMITS") == 422
    assert status_of(june_a, ids("observation", world["june"]), "DERIVED_FROM") == 422  # system-only
    assert status_of(june_a, ids("hypothesis", world["water"]), "SUPPORTS") == 422  # use hypothesis links
    assert status_of(ids("anomaly", world["march_a"]), node, "SUPPORTS") == 422  # missing data cannot support
    assert status_of(ids("paper", world["paper"]), node, "SUPPORTS") == 422  # cite the claim, not the paper
    assert status_of(ids("manifest", world["active"]), node, "SUPPORTS") == 422
    assert status_of("missing:no-observations:2023", node, "LIMITS") == 422  # derived, may disappear
    assert status_of(june_a, node, "SUPPORTS") == 409  # duplicate
    assert status_of(june_a, node, "CONTRADICTS") == 422  # both polarities
    assert status_of(node, ids("hypothesis", world["water"]), "ADDRESSES") is None
    assert status_of(june_a, ids("hypothesis", world["water"]), "ADDRESSES") == 422
    assert status_of(eg.NO_LOCAL_MEASUREMENTS, node, "LIMITS") is None
    assert status_of(ids("hypothesis", world["water"]), node, "CONTRADICTS") is None
    assert status_of(node, reviewed, "SUPPORTS") == 422  # conclusions are not evidence
    assert status_of(reviewed, pending, "SUPPORTS") is None
    graph.add_edge(eg.Edge(id="x", source=reviewed, target=pending, relation="SUPPORTS", origin="MANUAL",
                           review_status="PENDING"))
    assert status_of(pending, reviewed, "CONTRADICTS") == 422  # circular evidence
    assert c.id == eg.conclusion_uuid(node) and eg.conclusion_uuid(june_a) is None


def test_confirmed_claim_contradictions_qualify_but_never_ground(world):
    reviewed, pending = world["reviewed"], world["pending"]
    a, b = sorted((reviewed, pending), key=lambda c: str(c.id))
    pair = uuid4()

    def decision(kind, at, versions=(1, 1)):
        return ClaimDisagreementReview(id=uuid4(), case_id=world["case"].id, pair_id=pair, claim_a_id=a.id,
                                       claim_b_id=b.id, claim_a_version=versions[0], claim_b_version=versions[1],
                                       decision=kind, note="Synthetic decision", reviewer_id=uuid4(),
                                       reviewed_at=datetime(2026, 11, 14, at, tzinfo=UTC), snapshot={})

    world["data"].disagreements = [decision("CONFIRMED_CONTRADICTION", 10)]
    graph = eg.build_graph(world["data"])
    edges = [e for e in graph.edges if e.origin == "DISAGREEMENT_REVIEW"]
    assert [(e.source, e.target, e.relation, e.review_status) for e in edges] == [
        (ids("claim", a), ids("claim", b), "CONTRADICTS", "ACCEPTED")]
    # symmetric: never part of a grounding path, reported on the trace of either claim
    for claim_row in (a, b):
        result = eg.trace(graph, ids("claim", claim_row))
        assert result.contradiction_edge_ids == [edges[0].id] and result.complete
        assert edges[0].id not in result.edge_ids
    with pytest.raises(eg.GraphRuleError):
        eg.check_edge(graph, ids("claim", b), ids("claim", a), "SUPPORTS")
    # a later decision, or an edit of either claim, withdraws the edge
    world["data"].disagreements.append(decision("INCONCLUSIVE", 11))
    assert not [e for e in eg.build_graph(world["data"]).edges if e.origin == "DISAGREEMENT_REVIEW"]
    world["data"].disagreements = [decision("CONFIRMED_CONTRADICTION", 10, versions=(1, 2))]
    assert not [e for e in eg.build_graph(world["data"]).edges if e.origin == "DISAGREEMENT_REVIEW"]


def test_storable_pattern_matches_database_constraint():
    assert eg.STORABLE_NODE.pattern == GRAPH_STORABLE_NODE
    assert eg.is_storable(f"anomaly:{uuid4()}") and eg.is_storable(eg.INCIDENT)
    assert not eg.is_storable(f"paper:{uuid4()}") and not eg.is_storable(f"manifest:{uuid4()}")
    assert not eg.is_storable("missing:no-observations:2022") and not eg.is_storable("anomaly:not-a-uuid")


# ── contract ─────────────────────────────────────────────────────────────────

def test_views_use_requested_shape_and_no_scores(world):
    from agroblackbox.api.evidence_graph import Access

    graph = eg.build_graph(world["data"])
    access = Access(role="VIEWER", user_id=uuid4(), editable=True)
    edge = edge_view(graph.edges[0], {}, access)
    dumped = edge.model_dump(by_alias=True, mode="json")
    assert {"from", "to", "relation", "note"} <= dumped.keys() and "from_" not in dumped
    assert not edge.can_edit and not edge.can_review
    node = node_view(graph.nodes[eg.INCIDENT], {}).model_dump(mode="json")
    assert {"id", "kind", "label", "provenance"} <= node.keys()
    assert GraphEdgeView.model_validate(dumped).from_ == graph.edges[0].source
    for model in (EvidenceGraphView, ConclusionView):
        schema = json.dumps(model.model_json_schema()).lower()
        assert "probability" not in schema and "confidence" not in schema and '"score"' not in schema
