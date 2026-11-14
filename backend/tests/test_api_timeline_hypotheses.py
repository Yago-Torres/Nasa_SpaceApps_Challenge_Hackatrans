"""ABB-10 API integration tests: case-bound NASA POWER ingestion, timeline and rival hypotheses.

PostgreSQL only (TEST_DATABASE_URL). NASA POWER is simulated with httpx.MockTransport; every
payload, person, parcel and coordinate is SYNTHETIC.

Synthetic series (reference years 2010-2021, event year 2022):
- PRECTOTCORR: reference year y has 1.0 + 0.1*(y-2010) mm/day every day (mean 1.55 mm/day).
  Event year: 1.55 mm/day except June = 0 (large deficit), August = 2.05 (moderate surplus)
  and one fill-value day on 2022-03-15 (March cannot be aggregated).
- T2M_MAX: reference year y has 20 + 0.1*(y-2010) C (mean 20.55). Event year 20.55 except July = 30.
"""
from __future__ import annotations

import calendar
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text

from agroblackbox.api.deps import get_session_factory
from agroblackbox.app import app
from agroblackbox.db.models import Anomaly, CaseHistory, Observation, SourceManifest
from agroblackbox.db.session import create_database_engine, session_factory
from agroblackbox.services import power

TEST_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL is required for PostgreSQL integration")

PASSWORD = "synthetic-correct-horse-42"
EXACT_LAT, EXACT_LON = 41.6543, -0.8765
V1 = "/api/v1"
T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


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


# ── synthetic NASA POWER ─────────────────────────────────────────────────────

def power_payload(*, june_rain: float = 0.0) -> dict:
    rain, tmax = {}, {}
    for year in range(2010, 2023):
        for month in range(1, 13):
            for day in range(1, calendar.monthrange(year, month)[1] + 1):
                key = f"{year:04d}{month:02d}{day:02d}"
                if year < 2022:
                    rain[key] = round(1.0 + 0.1 * (year - 2010), 6)
                    tmax[key] = round(20.0 + 0.1 * (year - 2010), 6)
                else:
                    rain[key] = june_rain if month == 6 else 2.05 if month == 8 else 1.55
                    tmax[key] = 30.0 if month == 7 else 20.55
    rain["20220315"] = -999.0
    return {
        "type": "Feature", "geometry": {"type": "Point", "coordinates": [EXACT_LON, EXACT_LAT, 250.0]},
        "properties": {"parameter": {"PRECTOTCORR": rain, "T2M_MAX": tmax}},
        "header": {"title": "NASA/POWER Source Native Resolution Daily Data",
                   "api": {"version": "v2.10.3", "name": "POWER Daily API"}, "sources": ["MERRA2", "POWER"],
                   "fill_value": -999.0, "time_standard": "UTC", "start": "20100101", "end": "20221231"},
        "parameters": {"PRECTOTCORR": {"units": "mm/day", "longname": "Precipitation Corrected"},
                       "T2M_MAX": {"units": "C", "longname": "Temperature at 2 Meters Maximum"}},
        "messages": [f"Synthetic message echoing {EXACT_LAT}, {EXACT_LON}"], "times": {"data": 0.1},
    }


class Upstream:
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []

    def __call__(self, request):
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=reply)


@pytest.fixture
def nasa(monkeypatch, tmp_path):
    state = {"now": T0}
    monkeypatch.setattr(power, "CACHE", tmp_path / "power")
    monkeypatch.setattr(power, "_now", lambda: state["now"])

    async def no_sleep(_):
        return None
    monkeypatch.setattr(power, "_sleep", no_sleep)

    def use(upstream: Upstream) -> Upstream:
        monkeypatch.setattr(power, "_make_client",
                            lambda: httpx.AsyncClient(transport=httpx.MockTransport(upstream)))
        return upstream
    state["use"] = use
    return state


# ── API helpers ──────────────────────────────────────────────────────────────

async def account(client, email: str, name: str = "Synthetic user") -> dict[str, str]:
    registered = await client.post(f"{V1}/auth/register",
                                   json={"email": email, "password": PASSWORD, "display_name": name})
    assert registered.status_code == 201, registered.text
    login = await client.post(f"{V1}/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


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


async def team(client):
    owner = await account(client, "owner@example.test", "Synthetic owner")
    reviewer = await account(client, "reviewer@example.test", "Synthetic reviewer")
    viewer = await account(client, "viewer@example.test", "Synthetic viewer")
    stranger = await account(client, "stranger@example.test", "Synthetic stranger")
    case = await new_case(client, owner)
    await share(client, owner, case["id"], "reviewer@example.test", "REVIEWER")
    await share(client, owner, case["id"], "viewer@example.test", "VIEWER")
    return case, owner, reviewer, viewer, stranger


async def ingest(client, headers, case_id, body=None):
    return await client.post(f"{V1}/cases/{case_id}/observations/nasa-power", json=body or {}, headers=headers)


def counts(factory) -> tuple[int, int, int]:
    with factory() as session:
        return tuple(session.scalar(select(func.count()).select_from(m)) for m in (SourceManifest, Observation,
                                                                                    Anomaly))


def by_month(items, variable):
    return {o["observed_at"][:7]: o for o in items if o["variable"] == variable}


# ── migration ────────────────────────────────────────────────────────────────

def test_abb10_migration_downgrades_and_upgrades(api_engine):
    command.downgrade(alembic_config(), "b7e2d4a91c03")
    inspector = inspect(api_engine)
    assert "anomalies" not in inspector.get_table_names()
    assert "version" not in {c["name"] for c in inspector.get_columns("hypotheses")}
    assert "ingestion_key" not in {c["name"] for c in inspector.get_columns("source_manifests")}
    command.upgrade(alembic_config(), "head")
    inspector = inspect(api_engine)
    assert "anomalies" in inspector.get_table_names()
    assert {"period_start", "coverage"} <= {c["name"] for c in inspector.get_columns("observations")}


# ── ingestion ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_owner_ingests_from_stored_location_with_provenance_and_qc(client, nasa, factory):
    upstream = nasa["use"](Upstream(power_payload()))
    case, owner, *_ = await team(client)
    response = await ingest(client, owner, case["id"])
    assert response.status_code == 201, response.text
    body = response.json()

    sent = dict(upstream.requests[0].url.params)
    assert (sent["latitude"], sent["longitude"]) == (str(EXACT_LAT), str(EXACT_LON))  # stored point, server-side
    assert (sent["start"], sent["end"]) == ("20100101", "20221231")  # event year 2022, reference 2010-2021

    manifest = body["manifest"]
    assert body["created"] is True and body["active"] is True and body["source_kind"] == "OBSERVED"
    assert manifest["provider"] == "NASA POWER" and manifest["revision"] == 1
    assert manifest["query_parameters"]["latitude"] == EXACT_LAT  # owner sees the exact request
    assert manifest["location_redacted"] is False and manifest["field_id"] == case["fields"][0]["id"]
    assert len(manifest["checksum_sha256"]) == 64 and len(manifest["content_sha256"]) == 64
    assert manifest["dataset_version"] == "POWER Daily API v2.10.3"
    assert (manifest["event_year"], manifest["reference_start"], manifest["reference_end"]) == (2022, 2010, 2021)
    assert any("grid cell" in item for item in manifest["limitations"])

    observations = body["observations"]
    assert len(observations) == 24 and counts(factory) == (1, 24, 24)
    rain = by_month(observations, "precipitation")
    june = rain["2022-06"]
    assert june["value"] == 0.0 and june["units"] == "mm" and june["source_parameter"] == "PRECTOTCORR"
    assert (june["period_start"], june["period_end"]) == ("2022-06-01", "2022-06-30")
    assert june["temporal_resolution"]["unit"] == "month" and june["coverage"]["status"] == "complete"
    anomaly = june["anomaly"]
    assert anomaly["value"] == pytest.approx(-46.5, abs=0.006)
    assert anomaly["reference_value"] == pytest.approx(46.5, abs=0.006)
    assert anomaly["reference_sample_count"] == 12 and anomaly["reference_status"] == "complete"
    assert (anomaly["reference_start"], anomaly["reference_end"]) == ("2010-01-01", "2021-12-31")
    assert anomaly["departure"]["severity"] == "LARGE_DEPARTURE"
    assert anomaly["departure"]["direction"] == "BELOW_REFERENCE"
    assert rain["2022-08"]["anomaly"]["departure"]["severity"] == "MODERATE_DEPARTURE"
    assert rain["2022-05"]["anomaly"]["departure"]["severity"] == "WITHIN_REFERENCE_SPREAD"

    march = rain["2022-03"]
    assert march["value"] is None and march["anomaly"]["value"] is None
    assert {"EVENT_MONTH_PARTIAL", "FILL_VALUES_PRESENT"} <= set(march["quality_flags"])
    assert march["coverage"]["fill_value_days"] == 1
    assert march["anomaly"]["departure"]["severity"] == "NOT_CLASSIFIED"

    july = by_month(observations, "max_temperature")["2022-07"]
    assert july["anomaly"]["departure"]["severity"] == "LARGE_DEPARTURE" and july["units"] == "°C"

    history = (await client.get(f"{V1}/cases/{case['id']}/history", headers=owner)).json()
    ingested = [h for h in history if h["action"] == "OBSERVATIONS_INGESTED"]
    assert len(ingested) == 1 and ingested[0]["changes"]["observation_count"] == 24
    assert ingested[0]["version"] == 1  # evidence does not bump the case version
    assert str(EXACT_LAT) not in str(ingested[0]["changes"])


@pytest.mark.asyncio
async def test_reingestion_is_idempotent_then_versioned(client, nasa, factory):
    nasa["use"](Upstream(power_payload()))
    owner = await account(client, "owner@example.test")
    case = await new_case(client, owner)
    first = await ingest(client, owner, case["id"])
    again = await ingest(client, owner, case["id"])  # served from cache: identical values
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["created"] is False and again.json()["manifest"]["id"] == first.json()["manifest"]["id"]
    assert counts(factory) == (1, 24, 24)

    nasa["now"] = T0 + timedelta(days=2)  # cache expired; upstream now returns revised values
    nasa["use"](Upstream(power_payload(june_rain=0.5)))
    revised = await ingest(client, owner, case["id"])
    assert revised.status_code == 201, revised.text
    body = revised.json()
    assert body["manifest"]["revision"] == 2 and body["superseded_manifest_id"] == first.json()["manifest"]["id"]
    assert counts(factory) == (2, 48, 48)

    active = (await client.get(f"{V1}/cases/{case['id']}/observations", headers=owner)).json()["items"]
    assert [item["manifest"]["revision"] for item in active] == [2]
    every = (await client.get(f"{V1}/cases/{case['id']}/observations?include_superseded=true",
                              headers=owner)).json()["items"]
    assert sorted((i["manifest"]["revision"], i["active"]) for i in every) == [(1, False), (2, True)]
    old = next(i for i in every if not i["active"])
    assert old["manifest"]["superseded_by_id"] == body["manifest"]["id"]

    timeline = (await client.get(f"{V1}/cases/{case['id']}/timeline", headers=owner)).json()
    manifests = {e["provenance"]["source_manifest_id"] for e in timeline["events"]
                 if e["provenance"]["source_manifest_id"]}
    assert manifests == {body["manifest"]["id"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [
    httpx.Response(500), httpx.Response(429, headers={"Retry-After": "60"}), httpx.Response(200, json={"bad": 1}),
])
async def test_upstream_failure_returns_502_and_persists_nothing(client, nasa, factory, reply):
    nasa["use"](Upstream(reply))
    owner = await account(client, "owner@example.test")
    case = await new_case(client, owner)
    response = await ingest(client, owner, case["id"])
    assert response.status_code == 502
    assert "power.larc.nasa.gov" not in response.text and str(EXACT_LAT) not in response.text
    assert counts(factory) == (0, 0, 0)
    with factory() as session:
        assert not session.scalar(select(func.count()).select_from(CaseHistory)
                                  .where(CaseHistory.action == "OBSERVATIONS_INGESTED"))


@pytest.mark.asyncio
async def test_ingestion_input_and_field_selection_errors(client, nasa):
    upstream = nasa["use"](Upstream(power_payload()))
    owner = await account(client, "owner@example.test")
    case = await new_case(client, owner, fields=[
        parcel(), parcel(label="Synthetic parcel B", latitude=41.1, longitude=-0.5),
        parcel(label="Synthetic region-only parcel", privacy_tier="WITHHELD", latitude=None, longitude=None,
               rounding_deg=None),
    ])
    withheld = next(f for f in case["fields"] if f["privacy_tier"] == "WITHHELD")
    other_owner = await account(client, "other@example.test")
    other_case = await new_case(client, other_owner)
    first = case["fields"][0]["id"]
    cases = [
        ({}, 422),  # several located fields: field_id required
        ({"field_id": withheld["id"]}, 422),  # no stored coordinates
        ({"field_id": other_case["fields"][0]["id"]}, 404),  # another case's field
        ({"field_id": first, "latitude": 1.0, "longitude": 2.0}, 422),  # clients never send coordinates
        ({"field_id": first, "reference_start": 2015, "reference_end": 2023}, 422),  # contains event year
        ({"field_id": first, "reference_start": 2020, "reference_end": 2021}, 422),  # fewer than 3 years
        ({"field_id": first, "reference_start": 2010}, 422),  # unpaired reference year
        ({"field_id": first, "event_year": datetime.now(UTC).year + 1}, 422),  # future
    ]
    statuses = [(await ingest(client, owner, case["id"], body)).status_code for body, _ in cases]
    assert statuses == [expected for _, expected in cases]
    assert not upstream.requests  # invalid requests never reach NASA POWER
    explicit = await ingest(client, owner, case["id"], {"field_id": first, "event_year": 2015})
    assert explicit.status_code == 201  # default reference window: the 12 preceding years
    assert (explicit.json()["manifest"]["reference_start"], explicit.json()["manifest"]["reference_end"]) == (
        2003, 2014)
    assert len(upstream.requests) == 1


# ── permissions and privacy ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_roles_for_ingestion_and_reading(client, nasa):
    upstream = nasa["use"](Upstream(power_payload()))
    case, owner, reviewer, viewer, stranger = await team(client)
    cid = case["id"]
    assert (await ingest(client, {}, cid)).status_code == 401
    assert (await ingest(client, stranger, cid)).status_code == 404
    assert (await ingest(client, viewer, cid)).status_code == 403
    assert (await ingest(client, reviewer, cid)).status_code == 403
    assert not upstream.requests  # rejected callers never trigger an upstream request
    for path in ("observations", "timeline", "hypotheses"):
        assert (await client.get(f"{V1}/cases/{cid}/{path}", headers=stranger)).status_code == 404
        assert (await client.get(f"{V1}/cases/{cid}/{path}", headers=viewer)).status_code == 200
    assert (await client.get(f"{V1}/cases/{uuid4()}/timeline", headers=owner)).status_code == 404


@pytest.mark.asyncio
async def test_ingestion_requires_an_editable_case(client, nasa):
    nasa["use"](Upstream(power_payload()))
    case, owner, reviewer, *_ = await team(client)
    cid = case["id"]
    status = await client.post(f"{V1}/cases/{cid}/status", json={"version": 1, "status": "INVESTIGATING"},
                               headers=owner)
    reviewed = await client.post(f"{V1}/cases/{cid}/status", json={"version": 2, "status": "REVIEWED"},
                                 headers=reviewer)
    assert status.status_code == reviewed.status_code == 200
    assert (await ingest(client, owner, cid)).status_code == 409
    reopened = await client.post(f"{V1}/cases/{cid}/status", json={"version": 3, "status": "INVESTIGATING"},
                                 headers=owner)
    archived = await client.post(f"{V1}/cases/{cid}/archive", json={"version": 4, "archived": True}, headers=owner)
    assert reopened.status_code == archived.status_code == 200
    assert (await ingest(client, owner, cid)).status_code == 409


@pytest.mark.asyncio
async def test_reviewer_and_viewer_never_receive_stored_coordinates(client, nasa):
    nasa["use"](Upstream(power_payload()))
    case, owner, reviewer, viewer, _ = await team(client)
    cid = case["id"]
    assert (await ingest(client, owner, cid)).status_code == 201
    owner_view = (await client.get(f"{V1}/cases/{cid}/observations", headers=owner)).json()
    assert owner_view["items"][0]["manifest"]["query_parameters"]["latitude"] == EXACT_LAT
    assert owner_view["items"][0]["upstream"]["messages"]  # owners see upstream messages verbatim
    for guest in (reviewer, viewer):
        payloads = [
            await client.get(f"{V1}/cases/{cid}/observations", headers=guest),
            await client.get(f"{V1}/cases/{cid}/observations?include_superseded=true", headers=guest),
            await client.get(f"{V1}/cases/{cid}/timeline", headers=guest),
            await client.get(f"{V1}/cases/{cid}/history", headers=guest),
        ]
        for response in payloads:
            assert response.status_code == 200
            assert str(EXACT_LAT) not in response.text and str(EXACT_LON) not in response.text
        item = payloads[0].json()["items"][0]
        assert item["manifest"]["query_parameters"]["latitude"] == "REDACTED"
        assert item["manifest"]["query_parameters"]["longitude"] == "REDACTED"
        assert item["manifest"]["location_redacted"] is True
        assert "messages" not in item["upstream"] and item["upstream"]["messages_withheld"] == 1


# ── timeline ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeline_layers_events_and_missing_data(client, nasa):
    nasa["use"](Upstream(power_payload()))
    owner = await account(client, "owner@example.test")
    case = await new_case(client, owner, incident_start="2022-05-01", incident_end="2023-03-31")
    cid = case["id"]
    empty = (await client.get(f"{V1}/cases/{cid}/timeline", headers=owner)).json()
    gaps = [e for e in empty["events"] if e["event_type"] == "NO_OBSERVATIONS"]
    assert sorted(e["start"] for e in gaps) == ["2022-05-01", "2023-01-01"]
    assert not [e for e in empty["events"] if e["kind"] == "OBSERVED"]

    assert (await ingest(client, owner, cid, {"event_year": 2022})).status_code == 201
    timeline = (await client.get(f"{V1}/cases/{cid}/timeline", headers=owner)).json()
    layers = {layer["kind"]: layer["event_count"] for layer in timeline["layers"]}
    assert list(layers) == ["OBSERVED", "FARMER_REPORTED", "HYPOTHESIS", "MISSING_DATA"]
    events = timeline["events"]
    assert all(e["limitations"] and e["provenance"]["case_id"] == cid for e in events)
    observed = [e for e in events if e["kind"] == "OBSERVED"]
    assert len(observed) == 23 == layers["OBSERVED"]  # March precipitation is a data gap
    june = next(e for e in observed if e["start"] == "2022-06-01" and e["observed"]["variable"] == "precipitation")
    assert june["event_type"] == "CLIMATE_ANOMALY" and june["end"] == "2022-06-30"
    assert june["departure"]["severity"] == "LARGE_DEPARTURE" and june["overlaps_incident"] is True
    assert june["provenance"]["provider"] == "NASA POWER" and june["provenance"]["checksum_sha256"]
    assert june["data_quality"]["status"] == "complete" and june["observed"]["reference_sample_count"] == 12
    assert "query_parameters" not in june["provenance"]
    january = next(e for e in observed if e["start"] == "2022-01-01")
    assert january["overlaps_incident"] is False
    assert not [e for e in events if e["kind"] == "OBSERVED" and "cause" in e["title"].lower()]

    missing = [e for e in events if e["kind"] == "MISSING_DATA"]
    types = {e["event_type"] for e in missing}
    assert {"DATA_GAP", "NO_OBSERVATIONS", "NO_LOCAL_MEASUREMENTS"} == types
    gap = next(e for e in missing if e["event_type"] == "DATA_GAP")
    assert gap["start"] == "2022-03-01" and "fill value" in gap["description"]
    assert [e["start"] for e in missing if e["event_type"] == "NO_OBSERVATIONS"] == ["2023-01-01"]

    farmer = [e for e in events if e["kind"] == "FARMER_REPORTED"]
    assert {e["event_type"] for e in farmer} == {"INCIDENT_PERIOD", "CROP_HISTORY"}
    incident = next(e for e in farmer if e["event_type"] == "INCIDENT_PERIOD")
    assert (incident["start"], incident["end"]) == ("2022-05-01", "2023-03-31")
    assert "yellowing" in incident["description"]
    crops = next(e for e in farmer if e["event_type"] == "CROP_HISTORY")
    assert crops["crops"] == ["wheat", "barley"] and crops["start"] is None and events[-1]["start"] is None
    dated = [e["start"] for e in events if e["start"]]
    assert dated == sorted(dated)
    assert timeline["severity_rule"]["id"] == "abb10-departure-vs-reference-sd-1"
    assert any("not evidence of a cause" in item for item in timeline["limitations"])


# ── hypotheses ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rival_hypotheses_workflow_with_evidence_links(client, nasa):
    nasa["use"](Upstream(power_payload()))
    case, owner, reviewer, viewer, stranger = await team(client)
    cid = case["id"]
    observations = (await ingest(client, owner, cid)).json()["observations"]
    june = by_month(observations, "precipitation")["2022-06"]
    july_heat = by_month(observations, "max_temperature")["2022-07"]
    may = by_month(observations, "precipitation")["2022-05"]

    templates = await client.post(f"{V1}/cases/{cid}/hypotheses/templates", json={}, headers=owner)
    assert templates.status_code == 201
    created = templates.json()["items"]
    assert len(created) == 6 and all(h["status"] == "OPEN" and h["origin"] == "TEMPLATE" for h in created)
    assert all(h["verification_questions"] and h["source_kind"] == "HYPOTHESIS" for h in created)
    again = await client.post(f"{V1}/cases/{cid}/hypotheses/templates", json={}, headers=owner)
    assert again.status_code == 200 and again.json()["items"] == []
    assert (await client.post(f"{V1}/cases/{cid}/hypotheses/templates", json={}, headers=reviewer)).status_code == 403

    water = next(h for h in created if h["template_code"] == "WATER_DEFICIT")
    linked = await client.patch(f"{V1}/cases/{cid}/hypotheses/{water['id']}", headers=owner, json={
        "version": 1, "supporting_evidence_ids": [june["anomaly"]["id"]],
        "contradicting_evidence_ids": [may["id"]]})
    assert linked.status_code == 200, linked.text
    water = linked.json()
    assert water["version"] == 2 and {e["evidence_type"] for e in water["evidence"]} == {"ANOMALY", "OBSERVATION"}
    assert all(e["kind"] == "OBSERVED" and e["active"] for e in water["evidence"])

    # orphan or foreign evidence is rejected
    other_owner = await account(client, "other@example.test")
    other_case = await new_case(client, other_owner)
    for bad in (str(uuid4()), other_case["fields"][0]["id"]):
        orphan = await client.post(f"{V1}/cases/{cid}/hypotheses", headers=owner,
                                   json={"statement": "Synthetic hypothesis", "supporting_evidence_ids": [bad]})
        assert orphan.status_code == 422 and bad in orphan.text

    # evaluation rules
    heat = next(h for h in created if h["template_code"] == "HEAT_STRESS")
    url = f"{V1}/cases/{cid}/hypotheses/{heat['id']}/status"
    no_support = await client.post(url, headers=reviewer,
                                   json={"version": 1, "status": "COMPATIBLE", "note": "Synthetic note"})
    assert no_support.status_code == 422 and "supporting" in no_support.text
    for forbidden in ("SUPPORTED", "REJECTED"):
        assert (await client.post(url, headers=reviewer, json={"version": 1, "status": forbidden,
                                                                "note": "x"})).status_code == 422
    assert (await client.post(url, headers=viewer, json={"version": 1, "status": "NOT_EVALUABLE",
                                                          "note": "x"})).status_code == 403
    assert (await client.post(url, headers=stranger, json={"version": 1, "status": "NOT_EVALUABLE",
                                                            "note": "x"})).status_code == 404
    not_evaluable = await client.post(url, headers=reviewer, json={
        "version": 1, "status": "NOT_EVALUABLE", "note": "Crop stage during July is unknown."})
    assert not_evaluable.status_code == 200
    assert not_evaluable.json()["evaluated_by"]["display_name"] == "Synthetic reviewer"
    stale = await client.post(url, headers=reviewer, json={"version": 1, "status": "OPEN"})
    assert stale.status_code == 409

    water_url = f"{V1}/cases/{cid}/hypotheses/{water['id']}/status"
    compatible = await client.post(water_url, headers=reviewer, json={
        "version": 2, "status": "COMPATIBLE", "note": "June precipitation far below the reference mean."})
    assert compatible.status_code == 200 and compatible.json()["status"] == "COMPATIBLE"
    contradicted = await client.post(water_url, headers=owner, json={
        "version": 3, "status": "CONTRADICTED", "note": "May was within the reference spread."})
    assert contradicted.status_code == 200 and contradicted.json()["version"] == 4

    # content edits reset the evaluation; reviewers and viewers cannot edit content
    assert (await client.patch(f"{V1}/cases/{cid}/hypotheses/{water['id']}", headers=reviewer,
                               json={"version": 4, "statement": "x"})).status_code == 403
    edited = await client.patch(f"{V1}/cases/{cid}/hypotheses/{water['id']}", headers=owner, json={
        "version": 4, "supporting_evidence_ids": [june["anomaly"]["id"], july_heat["anomaly"]["id"]]})
    assert edited.status_code == 200 and edited.json()["status"] == "OPEN"
    assert edited.json()["evaluation_note"] is None

    # user-written hypothesis
    custom = await client.post(f"{V1}/cases/{cid}/hypotheses", headers=owner, json={
        "title": "Late sowing", "statement": "Late sowing may have shifted flowering into the July heat.",
        "supporting_evidence_ids": [july_heat["anomaly"]["id"]], "missing_evidence": ["Sowing date"],
        "status": "COMPATIBLE"})
    assert custom.status_code == 422  # status cannot be set on creation
    custom = await client.post(f"{V1}/cases/{cid}/hypotheses", headers=owner, json={
        "title": "Late sowing", "statement": "Late sowing may have shifted flowering into the July heat.",
        "supporting_evidence_ids": [july_heat["anomaly"]["id"]], "missing_evidence": ["Sowing date"]})
    assert custom.status_code == 201 and custom.json()["status"] == "OPEN" and custom.json()["origin"] == "USER"
    assert custom.json()["limitations"][0].startswith("A hypothesis is a candidate explanation")
    assert (await client.post(f"{V1}/cases/{cid}/hypotheses", headers=viewer,
                              json={"statement": "x"})).status_code == 403

    # timeline hypothesis layer links to observed events
    timeline = (await client.get(f"{V1}/cases/{cid}/timeline", headers=viewer)).json()
    hyp_events = {e["id"]: e for e in timeline["events"] if e["kind"] == "HYPOTHESIS"}
    assert len(hyp_events) == 7
    water_event = hyp_events[water["id"]]
    assert water_event["hypothesis"]["supporting_event_ids"] == [june["anomaly"]["id"], july_heat["anomaly"]["id"]]
    assert water_event["hypothesis"]["contradicting_event_ids"] == [may["anomaly"]["id"]]
    observed_ids = {e["id"] for e in timeline["events"] if e["kind"] == "OBSERVED"}
    assert set(water_event["hypothesis"]["supporting_event_ids"]) <= observed_ids
    statuses = {h["status"] for h in (await client.get(f"{V1}/cases/{cid}/hypotheses", headers=viewer)).json()["items"]}
    assert statuses <= {"OPEN", "COMPATIBLE", "CONTRADICTED", "NOT_EVALUABLE"}

    # delete and history
    custom_id = custom.json()["id"]
    assert (await client.delete(f"{V1}/cases/{cid}/hypotheses/{custom_id}?version=1",
                                headers=reviewer)).status_code == 403
    assert (await client.delete(f"{V1}/cases/{cid}/hypotheses/{custom_id}?version=9",
                                headers=owner)).status_code == 409
    assert (await client.delete(f"{V1}/cases/{cid}/hypotheses/{custom_id}?version=1",
                                headers=owner)).status_code == 204
    assert (await client.get(f"{V1}/cases/{cid}/hypotheses/{custom_id}", headers=owner)).status_code == 404
    history = (await client.get(f"{V1}/cases/{cid}/history", headers=owner)).json()
    actions = [h["action"] for h in history]
    assert actions.count("HYPOTHESIS_CREATED") == 7 and "HYPOTHESIS_DELETED" in actions
    assert actions.count("HYPOTHESIS_EVALUATED") == 3 and actions.count("HYPOTHESIS_UPDATED") == 2
    reset = [h for h in history if h["action"] == "HYPOTHESIS_UPDATED" and h["note"]]
    assert reset and reset[0]["changes"]["status"] == {"before": "CONTRADICTED", "after": "OPEN"}


@pytest.mark.asyncio
async def test_hypotheses_frozen_when_case_reviewed_and_case_deletion_erases_evidence(client, nasa, factory):
    nasa["use"](Upstream(power_payload()))
    case, owner, reviewer, *_ = await team(client)
    cid = case["id"]
    assert (await ingest(client, owner, cid)).status_code == 201
    created = (await client.post(f"{V1}/cases/{cid}/hypotheses/templates", json={"codes": ["PEST_DISEASE"]},
                                 headers=owner)).json()["items"]
    assert [h["template_code"] for h in created] == ["PEST_DISEASE"]
    hid = created[0]["id"]
    await client.post(f"{V1}/cases/{cid}/status", json={"version": 1, "status": "INVESTIGATING"}, headers=owner)
    await client.post(f"{V1}/cases/{cid}/status", json={"version": 2, "status": "REVIEWED"}, headers=reviewer)
    frozen = await client.post(f"{V1}/cases/{cid}/hypotheses/{hid}/status", headers=reviewer, json={
        "version": 1, "status": "NOT_EVALUABLE", "note": "No field inspection recorded."})
    assert frozen.status_code == 409
    assert (await client.post(f"{V1}/cases/{cid}/hypotheses", headers=owner,
                              json={"statement": "x"})).status_code == 409

    version = (await client.get(f"{V1}/cases/{cid}", headers=owner)).json()["version"]
    assert (await client.delete(f"{V1}/cases/{cid}?version={version}", headers=owner)).status_code == 204
    assert counts(factory) == (0, 0, 0)
