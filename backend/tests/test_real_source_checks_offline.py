"""ABB-29: the manual smoke test's assertions must themselves be correct, so they run offline in CI.

They are applied to the real application code fed with the SYNTHETIC upstream fixtures, and a set of broken
variants must make them fail (a check that cannot fail proves nothing).
"""
from __future__ import annotations

import copy

import httpx
import pytest
import pytest_asyncio

from agroblackbox.app import app
from agroblackbox.services import literature, power
from evidence_fakes import oa_work, pilot_upstream
from agroblackbox.evidence_seed import PILOT_SEED
from real_source_checks import check_climate_payload, check_doi_verification, check_paper_record, check_search_result
from test_api_timeline_hypotheses import Upstream, power_payload

DOI = PILOT_SEED[0]["doi"]


@pytest_asyncio.fixture
async def climate_body(monkeypatch, tmp_path):
    monkeypatch.setattr(power, "CACHE", tmp_path / "power")
    monkeypatch.setattr(power, "_make_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(Upstream(power_payload()))))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/api/climate", params={"latitude": 41.6543, "longitude": -0.8765,
                                                       "event_year": 2022, "reference_start": 2010,
                                                       "reference_end": 2021})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_climate_checks_accept_a_valid_payload(climate_body):
    summary = check_climate_payload(climate_body, event_year=2022, expect_live=True)
    assert summary["anomalies_computed"] > 0 and len(summary["sha256"]) == 64


@pytest.mark.asyncio
@pytest.mark.parametrize("mutate", [
    lambda b: b["monthly"].pop(),                                              # a month is missing
    lambda b: b["monthly"][5].update(precipitation_anomaly_mm=999.0),           # anomaly != value - reference
    lambda b: b["monthly"][5].update(precipitation_mm=None),                    # anomaly from missing data
    lambda b: b["provenance"].update(checksum_sha256="not-a-checksum"),
    lambda b: b["provenance"].update(source_uri="https://example.org/"),
    lambda b: b["cache"].update(served_from_cache=True),                        # "live" run served from cache
    lambda b: b.update(source_kind="SIMULATED"),
])
async def test_climate_checks_reject_broken_payloads(climate_body, mutate):
    broken = copy.deepcopy(climate_body)
    mutate(broken)
    with pytest.raises((AssertionError, KeyError, IndexError)):
        check_climate_payload(broken, event_year=2022, expect_live=True)


@pytest.mark.asyncio
async def test_literature_checks_accept_verified_and_reject_unverified(monkeypatch):
    fake = pilot_upstream()
    monkeypatch.setattr(literature, "_make_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    assert check_doi_verification(await literature.verify_doi(DOI), doi=DOI)["doi"] == DOI
    assert check_paper_record(await literature.lookup_paper(doi=DOI), doi=DOI)["doi_status"] == "VERIFIED_CROSSREF"

    down = pilot_upstream()
    down.crossref = {}
    monkeypatch.setattr(literature, "_make_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(down)))
    with pytest.raises(AssertionError, match="did not verify"):
        check_doi_verification(await literature.verify_doi(DOI), doi=DOI)


QUERY = "legume rotation wheat yield"


@pytest_asyncio.fixture
async def search_body(monkeypatch):
    fake = pilot_upstream()
    works = [oa_work(f"W90{i}", e["title"], e["doi"]) for i, e in enumerate(PILOT_SEED, start=1)]
    works.append(oa_work("W999", "SYNTHETIC work without DOI", None))
    fake.openalex = httpx.Response(200, json={"meta": {"count": len(works)}, "results": works})
    monkeypatch.setattr(literature, "_make_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/api/literature", params={"query": QUERY})
    assert response.status_code == 200, response.text
    return response.json()


def test_search_checks_accept_a_valid_result(search_body):
    summary = check_search_result(search_body, query=QUERY)
    assert summary["results"] == len(PILOT_SEED) + 1 and summary["with_doi"] == len(PILOT_SEED)


@pytest.mark.parametrize("mutate", [
    lambda b: b.update(results=[]),                                                   # nothing found
    lambda b: b["results"][0].update(doi="https://doi.org/10.9999/not-the-same"),      # link != normalized id
    lambda b: b["results"].append(copy.deepcopy(b["results"][0])),                     # duplicate work
    lambda b: b["results"][0].update(evidence_status="REVIEWED"),                      # metadata shown as evidence
    lambda b: b["results"][0].update(retrievals=[]),                                   # no provenance
    lambda b: b["results"][0].update(doi_status="NO_DOI"),                             # DOI present but "no DOI"
    lambda b: b.update(query="something else"),
])
def test_search_checks_reject_broken_results(search_body, mutate):
    broken = copy.deepcopy(search_body)
    mutate(broken)
    with pytest.raises((AssertionError, KeyError, IndexError)):
        check_search_result(broken, query=QUERY)
