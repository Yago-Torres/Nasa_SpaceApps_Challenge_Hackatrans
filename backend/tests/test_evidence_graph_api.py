"""ABB-16 evidence graph API against a disposable PostgreSQL database (TEST_DATABASE_URL).

Observed values, papers and claims are written directly as SYNTHETIC rows (no network);
hypotheses, conclusions and edges go through the API. People, parcels and coordinates are
SYNTHETIC.
"""
from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from agroblackbox.api.deps import get_session_factory
from agroblackbox.app import app
from agroblackbox.db.models import (
    Anomaly,
    EvidenceClaim,
    EvidenceConclusion,
    EvidenceGraphEdge,
    Observation,
    Paper,
    SourceManifest,
)
from agroblackbox.db.session import create_database_engine, session_factory

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration")

PASSWORD = "synthetic-correct-horse-42"
EXACT_LAT, EXACT_LON = 41.6543, -0.8765
V1 = "/api/v1"
T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
RES = {"value": 0.5, "unit": "degree", "description": "Synthetic grid cell"}
MONTH = {"value": 1, "unit": "month", "description": "Synthetic monthly aggregate"}


def alembic_config() -> Config:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_URL or "")
    return config


@pytest.fixture(scope="module")
def api_engine():
    engine = create_database_engine(TEST_URL)
    command.downgrade(alembic_config(), "base")
    command.upgrade(alembic_config(), "head")
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def factory(api_engine):
    tables = [t for t in inspect(api_engine).get_table_names() if t != "alembic_version"]
    with api_engine.begin() as connection:
        connection.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE"))
    factory = session_factory(api_engine)
    app.dependency_overrides[get_session_factory] = lambda: factory
    yield factory
    app.dependency_overrides.pop(get_session_factory, None)


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── helpers ──────────────────────────────────────────────────────────────────

async def account(client, email: str, name: str) -> dict[str, str]:
    registered = await client.post(f"{V1}/auth/register",
                                   json={"email": email, "password": PASSWORD, "display_name": name})
    assert registered.status_code == 201, registered.text
    login = await client.post(f"{V1}/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def user_id(client, headers) -> str:
    return (await client.get(f"{V1}/auth/me", headers=headers)).json()["id"]


def parcel(**overrides):
    return {"label": "Synthetic parcel A", "privacy_tier": "APPROXIMATE", "latitude": EXACT_LAT,
            "longitude": EXACT_LON, "region_label": "Synthetic region", "rounding_deg": 0.5,
            "limitations": ["Synthetic test parcel; not a real farm"], **overrides}


async def new_case(client, headers, **overrides) -> dict:
    body = {"title": "SYNTHETIC case - not a real incident", "incident_start": "2022-05-01",
            "incident_end": "2022-08-31", "crop_history": ["wheat", "barley"],
            "incident_notes": "Synthetic farmer report: yellowing in June.", "fields": [parcel()], **overrides}
    response = await client.post(f"{V1}/cases", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def share(client, owner, case_id, email, role):
    response = await client.post(f"{V1}/cases/{case_id}/permissions", json={"email": email, "role": role},
                                 headers=owner)
    assert response.status_code in (200, 201), response.text


def seed_observed(factory, case_id: str, field_id: str) -> dict[str, str]:
    """One NASA POWER-like retrieval: June (large deficit) and March (data gap). The manifest keeps the
    stored coordinates in ``query_parameters`` exactly like a real ingestion does."""
    with factory.begin() as session:
        manifest = SourceManifest(
            id=uuid4(), case_id=case_id, provider="NASA POWER", dataset="Synthetic POWER fixture",
            source_uri="https://power.larc.nasa.gov/api/temporal/daily/point",
            query_parameters={"latitude": EXACT_LAT, "longitude": EXACT_LON, "community": "AG"}, retrieved_at=T0,
            checksum_sha256="a" * 64, dataset_version="POWER Daily API v2.10.3", processing_version="synthetic-1",
            spatial_resolution=RES, temporal_resolution=MONTH, limitations=["Synthetic manifest"], field_id=field_id,
            ingestion_key="c" * 64, content_sha256="b" * 64, revision=1, event_year=2022, reference_start=2010,
            reference_end=2021, details={"upstream": {"messages": [f"echo {EXACT_LAT}, {EXACT_LON}"]}},
        )
        session.add(manifest)
        session.flush()
        rows = {}
        for month, value, anomaly_value in ((6, 0.0, -46.5), (3, None, None), (5, 45.0, -1.5)):
            obs = Observation(
                id=uuid4(), case_id=case_id, source_manifest_id=manifest.id, variable="precipitation", value=value,
                units="mm", observed_at=datetime(2022, month, 1, tzinfo=UTC), spatial_resolution=RES,
                temporal_resolution=MONTH, quality_flags=[], limitations=["Synthetic observation"],
                period_start=date(2022, month, 1), period_end=date(2022, month, 28),
                coverage={"status": "complete" if value is not None else "partial", "reason": None},
            )
            session.add(obs)
            session.flush()
            anomaly = Anomaly(
                id=uuid4(), case_id=case_id, observation_id=obs.id, value=anomaly_value, units="mm",
                method="synthetic", reference_start=date(2010, 1, 1), reference_end=date(2021, 12, 31),
                reference_sample_count=12, reference_status="complete", reference_value=46.5,
                reference_standard_deviation=10.0, reference_minimum=30.0, reference_maximum=60.0,
                reference_years_excluded=[], quality_flags=[], limitations=["Synthetic anomaly"],
            )
            session.add(anomaly)
            session.flush()
            rows[month] = (str(obs.id), str(anomaly.id))
    return {"manifest": str(manifest.id), "june_obs": rows[6][0], "june": rows[6][1], "march": rows[3][1],
            "may": rows[5][1]}


def seed_claims(factory, case_id: str, owner_id: str, reviewer_id: str) -> dict[str, str]:
    with factory.begin() as session:
        paper = Paper(title="Synthetic paper on water deficit", year=2020, doi_id=f"10.5555/{uuid4().hex[:8]}",
                      doi_status="VERIFIED_CROSSREF", bibliographic_metadata={"doi": "https://doi.org/10.5555/x"},
                      limitations=["Synthetic fixture; not a real paper"])
        session.add(paper)
        session.flush()
        common = dict(case_id=case_id, paper_id=paper.id, study_context="Synthetic context",
                      limitations=["Synthetic claim"], created_by=owner_id, study_design="FIELD_EXPERIMENT",
                      reported_outcome={"outcome": "Synthetic outcome"})
        accepted = EvidenceClaim(claim_text="Synthetic reviewed claim", review_status="ACCEPTED",
                                 reviewed_by=reviewer_id, reviewed_at=T0, evidence_basis="FULL_TEXT",
                                 access_basis="AUTHOR_PROVIDED_COPY", content_license="synthetic terms", **common)
        pending = EvidenceClaim(claim_text="Synthetic unreviewed claim", review_status="PENDING", **common)
        other = EvidenceClaim(claim_text="Synthetic second unreviewed claim", review_status="PENDING", **common)
        session.add_all([accepted, pending, other])
        session.flush()
        return {"paper": str(paper.id), "accepted": str(accepted.id), "pending": str(pending.id),
                "other": str(other.id)}


async def hypothesis(client, headers, case_id, title, **links) -> dict:
    response = await client.post(f"{V1}/cases/{case_id}/hypotheses", headers=headers,
                                 json={"title": title, "statement": f"{title} may have contributed (synthetic).",
                                       **links})
    assert response.status_code == 201, response.text
    return response.json()


async def scenario(client, factory) -> dict:
    owner = await account(client, "owner@example.test", "Synthetic owner")
    editor = await account(client, "editor@example.test", "Synthetic editor")
    reviewer = await account(client, "reviewer@example.test", "Synthetic reviewer")
    viewer = await account(client, "viewer@example.test", "Synthetic viewer")
    stranger = await account(client, "stranger@example.test", "Synthetic stranger")
    case = await new_case(client, owner)
    cid = case["id"]
    for email, role in (("editor@example.test", "EDITOR"), ("reviewer@example.test", "REVIEWER"),
                        ("viewer@example.test", "VIEWER")):
        await share(client, owner, cid, email, role)
    observed = seed_observed(factory, cid, case["fields"][0]["id"])
    claims = seed_claims(factory, cid, await user_id(client, owner), await user_id(client, reviewer))
    water = await hypothesis(client, owner, cid, "Water deficit",
                             supporting_evidence_ids=[observed["june"], claims["accepted"]],
                             missing_evidence=["Soil moisture"])
    excess = await hypothesis(client, owner, cid, "Excess water", contradicting_evidence_ids=[observed["june"]])
    bare = await hypothesis(client, owner, cid, "Pest pressure")
    return {"owner": owner, "editor": editor, "reviewer": reviewer, "viewer": viewer, "stranger": stranger,
            "case": case, "cid": cid, "obs": observed, "claims": claims, "water": water, "excess": excess,
            "bare": bare}


def graph_url(cid: str, suffix: str = "") -> str:
    return f"{V1}/cases/{cid}/evidence-graph{suffix}"


def cite(node_id: str, note: str = "Synthetic reason") -> dict:
    return {"node_id": node_id, "note": note}


async def create_conclusion(client, headers, cid, **body) -> httpx.Response:
    payload = {"statement": "June precipitation far below the reference is consistent with a water deficit; "
                            "not demonstrated as the cause (synthetic).",
               "limitations": ["Regional grid-cell data only."], **body}
    return await client.post(graph_url(cid, "/conclusions"), headers=headers, json=payload)


def table_counts(factory) -> tuple[int, int]:
    with factory() as session:
        return (session.scalar(select(func.count()).select_from(EvidenceConclusion)),
                session.scalar(select(func.count()).select_from(EvidenceGraphEdge)))


# ── migration ────────────────────────────────────────────────────────────────

def test_abb16_migration_downgrades_and_upgrades(api_engine):
    command.downgrade(alembic_config(), "e3a9c71f5b20")  # ABB-10, the parent revision
    tables = set(inspect(api_engine).get_table_names())
    assert not {"evidence_conclusions", "evidence_graph_edges"} & tables
    command.upgrade(alembic_config(), "head")
    assert {"evidence_conclusions", "evidence_graph_edges"} <= set(inspect(api_engine).get_table_names())


# ── graph ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_graph_is_built_from_case_records_and_keeps_rival_hypotheses(client, factory):
    s = await scenario(client, factory)
    response = await client.get(graph_url(s["cid"]), headers=s["owner"])
    assert response.status_code == 200, response.text
    graph = response.json()
    nodes = {n["id"]: n for n in graph["nodes"]}
    june, water, excess = f"anomaly:{s['obs']['june']}", f"hypothesis:{s['water']['id']}", \
        f"hypothesis:{s['excess']['id']}"
    assert nodes[june]["kind"] == "OBSERVED" and nodes[f"anomaly:{s['obs']['march']}"]["kind"] == "MISSING_DATA"
    assert nodes[f"manifest:{s['obs']['manifest']}"]["original_evidence"] is True
    assert nodes[f"claim:{s['claims']['accepted']}"]["kind"] == "LITERATURE_REVIEWED"
    assert nodes[f"claim:{s['claims']['pending']}"]["kind"] == "LITERATURE_METADATA"
    assert nodes["farmer:incident"]["kind"] == "FARMER_REPORTED"
    assert {"FIELD", "PAPER", "MISSING_DATA", "HYPOTHESIS"} <= {n["node_type"] for n in graph["nodes"]}
    assert all(n["limitations"] and n["provenance"]["case_id"] == s["cid"] for n in graph["nodes"])

    edges = graph["edges"]
    assert all(e["from"] in nodes and e["to"] in nodes for e in edges)  # never an orphan endpoint
    assert graph["orphan_references"] == []
    keys = {(e["from"], e["to"], e["relation"]) for e in edges}
    assert (june, f"observation:{s['obs']['june_obs']}", "DERIVED_FROM") in keys
    assert (f"claim:{s['claims']['accepted']}", f"paper:{s['claims']['paper']}", "CITES") in keys
    # the same anomaly supports one hypothesis and contradicts its rival; both stay OPEN, nothing is ranked
    assert (june, water, "SUPPORTS") in keys and (june, excess, "CONTRADICTS") in keys
    assert nodes[water]["status"] == nodes[excess]["status"] == "OPEN"
    assert {e["origin"] for e in edges} == {"STRUCTURAL", "HYPOTHESIS_LINK"}
    assert graph["counts"]["total_nodes"] == len(nodes) and graph["counts"]["total_edges"] == len(edges)
    assert {r["relation"] for r in graph["relations"]} == {"SUPPORTS", "CONTRADICTS", "LIMITS", "ADDRESSES",
                                                           "DERIVED_FROM", "CITES"}
    numeric_keys = {k for n in graph["nodes"] for k in n["details"]} | {k for e in edges for k in e}
    assert not {"score", "probability", "confidence", "weight"} & numeric_keys


# ── conclusions and trace ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_conclusion_traces_back_to_original_evidence_and_review_rules(client, factory):
    s = await scenario(client, factory)
    cid, owner, reviewer = s["cid"], s["owner"], s["reviewer"]
    june, water = f"anomaly:{s['obs']['june']}", f"hypothesis:{s['water']['id']}"
    pending = f"claim:{s['claims']['pending']}"
    created = await create_conclusion(
        client, owner, cid, title="Water deficit compatible", supporting=[cite(june), cite(water),
                                                                          cite("farmer:incident")],
        contradicting=[cite(pending, "An unreviewed claim argues otherwise.")],
        limited_by=[cite("missing:no-local-measurements", "No rain gauge or soil moisture records.")],
        addresses_hypothesis_ids=[s["water"]["id"]])
    assert created.status_code == 201, created.text
    conclusion = created.json()
    assert conclusion["review_status"] == "PENDING" and conclusion["version"] == 1
    assert conclusion["trace_complete"] is True and len(conclusion["citations"]) == 6
    assert conclusion["limitations"][0].startswith("A conclusion is a statement written by a case member")
    assert any("not a reviewed claim" in b for b in conclusion["review_blockers"])
    assert any("not been evaluated" in b for b in conclusion["review_blockers"])

    node = conclusion["node_id"]
    trace = (await client.get(graph_url(cid, f"/trace/{node}"), headers=s["viewer"])).json()
    assert trace["complete"] is True and trace["dead_ends"] == [] and trace["truncated"] is False
    assert all(p["ends_at_original_evidence"] for p in trace["paths"])
    assert set(trace["original_evidence"]) == {f"manifest:{s['obs']['manifest']}", f"paper:{s['claims']['paper']}",
                                               "farmer:incident"}
    assert trace["summary"]["reaches_observed_data"] and trace["summary"]["reaches_literature"]
    assert trace["summary"]["reaches_farmer_report"]
    assert trace["summary"]["unreviewed_claim_ids"] == [pending]
    assert water in trace["summary"]["unevaluated_hypothesis_ids"]
    assert {e["from"] for e in trace["limiting_edges"]} >= {"missing:no-local-measurements"}
    path = next(p for p in trace["paths"] if p["steps"][1]["node_id"] == june)
    assert [st["node_id"] for st in path["steps"]] == [node, june, f"observation:{s['obs']['june_obs']}",
                                                       f"manifest:{s['obs']['manifest']}"]

    url = graph_url(cid, f"/conclusions/{conclusion['id']}/review")
    accept = {"version": 1, "decision": "ACCEPTED", "note": "Checked the cited evidence trail."}
    assert (await client.post(url, headers=owner, json=accept)).status_code == 403  # author
    assert (await client.post(url, headers=s["viewer"], json=accept)).status_code == 403
    blocked = await client.post(url, headers=reviewer, json=accept)
    assert blocked.status_code == 409 and "not a reviewed claim" in blocked.text

    # resolve the blockers: drop the unreviewed contradiction, evaluate the hypothesis
    citation = next(c for c in conclusion["citations"] if c["from"] == pending)
    assert (await client.delete(graph_url(cid, f"/edges/{citation['record_id']}?version=1"),
                                headers=s["editor"])).status_code == 204
    evaluated = await client.post(f"{V1}/cases/{cid}/hypotheses/{s['water']['id']}/status", headers=reviewer,
                                  json={"version": 1, "status": "COMPATIBLE", "note": "June deficit."})
    assert evaluated.status_code == 200
    current = (await client.get(graph_url(cid, f"/conclusions/{conclusion['id']}"), headers=reviewer)).json()
    assert current["version"] == 2 and current["review_blockers"] == [] and current["can_review"] is True
    editor_view = (await client.get(graph_url(cid, f"/conclusions/{conclusion['id']}"), headers=s["editor"])).json()
    assert editor_view["can_review"] is False  # the editor removed a citation, so contributed
    stale = await client.post(url, headers=reviewer, json=accept)
    assert stale.status_code == 409
    accepted = await client.post(url, headers=reviewer, json={**accept, "version": 2})
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["review_status"] == "ACCEPTED" and body["reviewer"]["display_name"] == "Synthetic reviewer"
    assert all(c["review_status"] == "ACCEPTED" for c in body["citations"])

    # a text edit invalidates the review; reviewed conclusions cannot be deleted
    edited = await client.patch(graph_url(cid, f"/conclusions/{conclusion['id']}"), headers=owner,
                                json={"version": 3, "statement": "Revised synthetic statement."})
    assert edited.status_code == 200 and edited.json()["review_status"] == "PENDING"
    assert all(c["review_status"] == "PENDING" for c in edited.json()["citations"])
    assert (await client.delete(graph_url(cid, f"/conclusions/{conclusion['id']}?version=4"),
                                headers=owner)).status_code == 409
    history = (await client.get(f"{V1}/cases/{cid}/history", headers=owner)).json()
    actions = [h["action"] for h in history]
    for action in ("CONCLUSION_CREATED", "GRAPH_EDGE_DELETED", "CONCLUSION_REVIEWED", "CONCLUSION_UPDATED"):
        assert action in actions
    assert all(h["version"] == 1 for h in history if h["action"].startswith(("CONCLUSION", "GRAPH_EDGE")))


@pytest.mark.asyncio
async def test_orphan_and_cross_case_references_are_rejected(client, factory):
    s = await scenario(client, factory)
    cid, owner = s["cid"], s["owner"]
    other_case = await new_case(client, owner, title="SYNTHETIC second case")
    foreign = seed_observed(factory, other_case["id"], other_case["fields"][0]["id"])
    june = f"anomaly:{s['obs']['june']}"
    bad_supports = [
        f"anomaly:{uuid4()}",  # nonexistent
        f"anomaly:{foreign['june']}",  # exists, but in another case
        f"paper:{s['claims']['paper']}",  # a paper is cited through a claim
        f"anomaly:{s['obs']['march']}",  # missing data cannot support
        f"hypothesis:{s['bare']['id']}",  # hypothesis without evidence: no trace to original evidence
        "missing:no-observations:2022",
    ]
    for node_id in bad_supports:
        response = await create_conclusion(client, owner, cid, supporting=[cite(node_id)])
        assert response.status_code == 422, (node_id, response.text)
    unknown = await create_conclusion(client, owner, cid, supporting=[cite(f"anomaly:{foreign['june']}")])
    nonexistent = await create_conclusion(client, owner, cid, supporting=[cite(f"anomaly:{uuid4()}")])
    assert unknown.json()["detail"].split(":")[0] == nonexistent.json()["detail"].split(":")[0]
    assert (await create_conclusion(client, owner, cid, supporting=[])).status_code == 422
    assert (await create_conclusion(client, owner, cid, supporting=[cite(june)], limitations=[])).status_code == 422
    assert (await create_conclusion(client, owner, cid, supporting=[cite(june)],
                                    contradicting=[cite(june)])).status_code == 422
    assert (await create_conclusion(client, owner, cid, supporting=[cite(june)],
                                    addresses_hypothesis_ids=[str(uuid4())])).status_code == 422
    assert table_counts(factory) == (0, 0)  # nothing stored by rejected requests

    edges = graph_url(cid, "/edges")
    claim_a, claim_b = f"claim:{s['claims']['pending']}", f"claim:{s['claims']['other']}"
    for body, expected in [
        ({"from": f"claim:{uuid4()}", "to": claim_a, "relation": "SUPPORTS"}, 422),
        ({"from": june, "to": f"hypothesis:{s['water']['id']}", "relation": "SUPPORTS"}, 422),
        ({"from": june, "to": f"observation:{s['obs']['june_obs']}", "relation": "DERIVED_FROM"}, 422),
        ({"from": claim_a, "to": claim_a, "relation": "SUPPORTS"}, 422),
        ({"from": f"manifest:{s['obs']['manifest']}", "to": claim_a, "relation": "LIMITS"}, 422),
    ]:
        response = await client.post(edges, headers=owner, json={**body, "note": "Synthetic"})
        assert response.status_code == expected, (body, response.text)

    # references are protected: deleting a referenced record is refused
    field_node = f"field:{s['case']['fields'][0]['id']}"
    created = await create_conclusion(client, owner, cid, supporting=[cite(june), cite(field_node)],
                                      limited_by=[cite(claim_b)], addresses_hypothesis_ids=[s["excess"]["id"]])
    assert created.status_code == 201, created.text
    conclusion = created.json()
    assert (await client.delete(f"{V1}/cases/{cid}/hypotheses/{s['excess']['id']}?version=1",
                                headers=owner)).status_code == 409
    assert (await client.delete(f"{V1}/cases/{cid}/claims/{s['claims']['other']}?version=1",
                                headers=owner)).status_code == 409
    # a claim cited only by a hypothesis evidence link is protected too
    by_link = await client.delete(f"{V1}/cases/{cid}/claims/{s['claims']['accepted']}?version=1", headers=owner)
    assert by_link.status_code == 409 and "hypothes" in by_link.text
    second_field = await client.post(f"{V1}/cases/{cid}/fields", headers=owner,
                                     json={"version": 1, "field": parcel(label="Synthetic parcel B")})
    assert second_field.status_code == 201
    case_version = second_field.json()["version"]
    assert (await client.delete(f"{V1}/cases/{cid}/fields/{s['case']['fields'][0]['id']}?version={case_version}",
                                headers=owner)).status_code == 409
    supports = [c for c in conclusion["citations"] if c["relation"] == "SUPPORTS"]
    assert (await client.delete(graph_url(cid, f"/edges/{supports[0]['record_id']}?version=1"),
                                headers=owner)).status_code == 204
    last = await client.delete(graph_url(cid, f"/edges/{supports[1]['record_id']}?version=1"), headers=owner)
    assert last.status_code == 409 and "at least one supporting" in last.text
    graph = (await client.get(graph_url(cid), headers=owner)).json()
    node_ids = {n["id"] for n in graph["nodes"]}
    assert graph["orphan_references"] == [] and all(e["from"] in node_ids and e["to"] in node_ids
                                                    for e in graph["edges"])


@pytest.mark.asyncio
async def test_manual_edges_crud_review_and_cycles(client, factory):
    s = await scenario(client, factory)
    cid, owner, reviewer = s["cid"], s["owner"], s["reviewer"]
    claim_a, claim_b = f"claim:{s['claims']['pending']}", f"claim:{s['claims']['other']}"
    created = await client.post(graph_url(cid, "/edges"), headers=owner,
                                json={"from": claim_a, "to": claim_b, "relation": "SUPPORTS",
                                      "note": "Both report lower yields under deficit (synthetic)."})
    assert created.status_code == 201, created.text
    edge = created.json()
    assert edge["origin"] == "MANUAL" and edge["review_status"] == "PENDING" and edge["can_edit"] is True
    assert edge["author"]["display_name"] == "Synthetic owner" and edge["id"] == f"edge:{edge['record_id']}"
    duplicate = await client.post(graph_url(cid, "/edges"), headers=s["editor"],
                                  json={"from": claim_a, "to": claim_b, "relation": "SUPPORTS", "note": "x"})
    assert duplicate.status_code == 409
    circular = await client.post(graph_url(cid, "/edges"), headers=owner,
                                 json={"from": claim_b, "to": claim_a, "relation": "CONTRADICTS", "note": "x"})
    assert circular.status_code == 422 and "circular" in circular.text

    url = graph_url(cid, f"/edges/{edge['record_id']}")
    decision = {"version": 1, "decision": "ACCEPTED", "note": "Link stated correctly."}
    assert (await client.post(f"{url}/review", headers=owner, json=decision)).status_code == 403  # author
    assert (await client.post(f"{url}/review", headers=s["viewer"], json=decision)).status_code == 403
    assert (await client.post(f"{url}/review", headers=s["stranger"], json=decision)).status_code == 404
    reviewed = await client.post(f"{url}/review", headers=reviewer, json=decision)
    assert reviewed.status_code == 200 and reviewed.json()["review_status"] == "ACCEPTED"
    assert reviewed.json()["reviewed_by"]["display_name"] == "Synthetic reviewer"
    assert (await client.patch(url, headers=reviewer, json={"version": 2, "note": "x"})).status_code == 403
    assert (await client.patch(url, headers=owner, json={"version": 1, "note": "x"})).status_code == 409
    edited = await client.patch(url, headers=s["editor"], json={"version": 2, "note": "Revised synthetic note."})
    assert edited.status_code == 200 and edited.json()["review_status"] == "PENDING"
    listed = (await client.get(graph_url(cid, "/edges"), headers=s["viewer"])).json()
    assert [e["record_id"] for e in listed["items"]] == [edge["record_id"]] and not listed["items"][0]["can_edit"]

    # a conclusion citation cannot be reviewed on its own
    conclusion = (await create_conclusion(client, owner, cid,
                                          supporting=[cite(f"anomaly:{s['obs']['june']}")])).json()
    citation = conclusion["citations"][0]
    alone = await client.post(graph_url(cid, f"/edges/{citation['record_id']}/review"), headers=reviewer,
                              json=decision)
    assert alone.status_code == 409
    # adding a citation through the edge route bumps the conclusion and makes the editor a contributor
    added = await client.post(graph_url(cid, "/edges"), headers=s["editor"],
                              json={"from": "farmer:incident", "to": conclusion["node_id"], "relation": "SUPPORTS",
                                    "note": "Reported yellowing in June."})
    assert added.status_code == 201 and added.json()["conclusion_id"] == conclusion["id"]
    after = (await client.get(graph_url(cid, f"/conclusions/{conclusion['id']}"), headers=s["editor"])).json()
    assert after["version"] == 2 and len(after["citations"]) == 2 and after["can_review"] is False

    assert (await client.delete(f"{url}?version=3", headers=s["viewer"])).status_code == 403
    assert (await client.delete(f"{url}?version=3", headers=owner)).status_code == 204
    actions = [h["action"] for h in (await client.get(f"{V1}/cases/{cid}/history", headers=owner)).json()]
    for action in ("GRAPH_EDGE_CREATED", "GRAPH_EDGE_REVIEWED", "GRAPH_EDGE_UPDATED", "GRAPH_EDGE_DELETED"):
        assert action in actions


# ── permissions and privacy ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_private_case_permissions_and_redaction(client, factory):
    s = await scenario(client, factory)
    cid = s["cid"]
    june = f"anomaly:{s['obs']['june']}"
    conclusion = (await create_conclusion(client, s["owner"], cid, supporting=[cite(june)])).json()
    reads = [graph_url(cid), graph_url(cid, "?include_superseded=true"), graph_url(cid, f"/trace/{june}"),
             graph_url(cid, f"/trace/{conclusion['node_id']}"), graph_url(cid, "/conclusions"),
             graph_url(cid, f"/conclusions/{conclusion['id']}"), graph_url(cid, "/edges")]
    for path in reads:
        assert (await client.get(path)).status_code == 401
        assert (await client.get(path, headers=s["stranger"])).status_code == 404  # existence not revealed
        for member in ("owner", "editor", "reviewer", "viewer"):
            response = await client.get(path, headers=s[member])
            assert response.status_code == 200, (path, member, response.text)
            # no role ever receives the stored point or upstream text echoing it through the graph
            assert str(EXACT_LAT) not in response.text and str(EXACT_LON) not in response.text
            assert "query_parameters" not in response.text and "@example.test" not in response.text
    assert (await client.get(graph_url(str(uuid4())), headers=s["owner"])).status_code == 404
    assert (await client.get(graph_url(cid, f"/trace/anomaly:{uuid4()}"), headers=s["owner"])).status_code == 404

    writes = [
        ("post", graph_url(cid, "/conclusions"), {"statement": "x", "limitations": ["x"], "supporting": [cite(june)]}),
        ("patch", graph_url(cid, f"/conclusions/{conclusion['id']}"), {"version": 1, "statement": "x"}),
        ("post", graph_url(cid, "/edges"), {"from": "farmer:incident", "to": conclusion["node_id"],
                                            "relation": "SUPPORTS", "note": "x"}),
        ("delete", graph_url(cid, f"/conclusions/{conclusion['id']}?version=1"), None),
    ]
    for method, path, body in writes:
        kwargs = {"json": body} if body is not None else {}
        assert (await client.request(method, path, headers=s["stranger"], **kwargs)).status_code == 404
        for guest in ("reviewer", "viewer"):
            assert (await client.request(method, path, headers=s[guest], **kwargs)).status_code == 403

    # writes need an editable case
    owner, reviewer = s["owner"], s["reviewer"]
    await client.post(f"{V1}/cases/{cid}/status", json={"version": 1, "status": "INVESTIGATING"}, headers=owner)
    await client.post(f"{V1}/cases/{cid}/status", json={"version": 2, "status": "REVIEWED"}, headers=reviewer)
    frozen = await create_conclusion(client, owner, cid, supporting=[cite(june)])
    assert frozen.status_code == 409
    review = await client.post(graph_url(cid, f"/conclusions/{conclusion['id']}/review"), headers=reviewer,
                               json={"version": 1, "decision": "REJECTED", "note": "x"})
    assert review.status_code == 409
    view = (await client.get(graph_url(cid, f"/conclusions/{conclusion['id']}"), headers=owner)).json()
    assert view["can_edit"] is False and view["can_review"] is False


# ── database guarantees ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_database_rejects_malformed_or_cross_case_edges_and_self_review(client, factory):
    s = await scenario(client, factory)
    other = await new_case(client, s["owner"], title="SYNTHETIC second case")
    conclusion = (await create_conclusion(client, s["owner"], s["cid"],
                                          supporting=[cite(f"anomaly:{s['obs']['june']}")])).json()
    owner_id = await user_id(client, s["owner"])
    base = dict(note="x", review_status="PENDING", contributor_ids=[], version=1)
    bad_rows = [
        dict(case_id=s["cid"], source_node="paper:" + str(uuid4()), target_node="farmer:incident",
             relation="LIMITS"),  # not a storable node id
        dict(case_id=s["cid"], source_node="farmer:incident", target_node="farmer:incident", relation="LIMITS"),
        dict(case_id=s["cid"], source_node="farmer:incident", target_node=f"claim:{s['claims']['other']}",
             relation="DERIVED_FROM"),
        # conclusion of this case attached to an edge of another case
        dict(case_id=other["id"], source_node="farmer:incident", target_node=conclusion["node_id"],
             relation="SUPPORTS", conclusion_id=conclusion["id"]),
        # conclusion endpoint without its conclusion_id
        dict(case_id=s["cid"], source_node="farmer:incident", target_node=conclusion["node_id"], relation="LIMITS"),
    ]
    for row in bad_rows:
        with pytest.raises(IntegrityError):
            with factory.begin() as session:
                session.add(EvidenceGraphEdge(**base, **row))
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.execute(text(
                "UPDATE evidence_conclusions SET review_status='ACCEPTED', reviewed_by=:u, reviewed_at=now(), "
                "review_note='self' WHERE id=:id"), {"u": owner_id, "id": conclusion["id"]})

    # deleting the case erases its graph records
    version = (await client.get(f"{V1}/cases/{s['cid']}", headers=s["owner"])).json()["version"]
    assert (await client.delete(f"{V1}/cases/{s['cid']}?version={version}", headers=s["owner"])).status_code == 204
    assert table_counts(factory) == (0, 0)
