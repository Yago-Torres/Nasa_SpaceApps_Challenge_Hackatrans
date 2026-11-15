"""ABB-29 MANUAL smoke test against the REAL NASA POWER, Crossref and OpenAlex services.

Never runs in CI and never runs by accident: it needs ``RUN_REAL_SOURCES=1`` and outbound HTTPS to
power.larc.nasa.gov, api.crossref.org and api.openalex.org. Run it before a release and record the output in
``docs/operations/E2E_AND_CONTRACTS.md``:

    cd backend && RUN_REAL_SOURCES=1 uv run --extra dev pytest -q -m real_network -s tests/test_real_sources_smoke.py

The HLS (ABB-12) and GPM (ABB-09) tests also need ``EARTHDATA_TOKEN``; the ``earthdata-smoke`` workflow runs it with the repository secret.

It sends only a public, region-level coordinate (Ebro valley, no farm) and a pilot-paper DOI: no private data.
Assertions live in ``real_source_checks`` (also exercised offline by ``test_real_source_checks_offline.py``).
"""
from __future__ import annotations

import json
import os

import httpx
import pytest

from agroblackbox.app import app
from agroblackbox.evidence_seed import PILOT_SEED
from agroblackbox.services import literature, power
from real_source_checks import (check_climate_payload, check_doi_verification, check_paper_record, check_search_result,
                                check_precipitation_payload, check_vegetation_payload)

pytestmark = [pytest.mark.real_network,
              pytest.mark.skipif(os.getenv("RUN_REAL_SOURCES") != "1",
                                 reason="manual smoke test: set RUN_REAL_SOURCES=1 (real network)")]
DOI = PILOT_SEED[0]["doi"]
LAT, LON, YEAR = 41.65, -0.88, 2022      # public Ebro-valley grid cell, not a farm
QUERY = "legume rotation wheat yield"     # broad agronomic query, no private data


@pytest.mark.asyncio
async def test_real_nasa_power_through_the_public_climate_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(power, "CACHE", tmp_path / "power")   # force a live download, not a stale cache
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=120) as c:
        response = await c.get("/api/climate", params={"latitude": LAT, "longitude": LON, "event_year": YEAR,
                                                       "reference_start": 2010, "reference_end": 2021})
    assert response.status_code == 200, response.text
    print("NASA POWER:", json.dumps(check_climate_payload(response.json(), event_year=YEAR, expect_live=True)))


@pytest.mark.asyncio
async def test_real_crossref_and_openalex_for_a_pilot_paper():
    check = await literature.verify_doi(DOI)
    print("Crossref:", json.dumps(check_doi_verification(check, doi=DOI)))
    record = await literature.lookup_paper(doi=DOI)
    print("OpenAlex+Crossref:", json.dumps(check_paper_record(record, doi=DOI)))


@pytest.mark.asyncio
async def test_real_openalex_search_through_the_public_literature_endpoint():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=120) as c:
        response = await c.get("/api/literature", params={"query": QUERY})
    assert response.status_code == 200, response.text   # 502 = OpenAlex refused (e.g. 429 without OPENALEX_API_KEY)
    print("OpenAlex search:", json.dumps(check_search_result(response.json(), query=QUERY)))


HLS_START, HLS_END = "2023-04-01", "2023-06-30"   # one spring season, 91 days


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("EARTHDATA_TOKEN"), reason="ABB-12 HLS smoke needs EARTHDATA_TOKEN")
async def test_real_hls_through_the_public_vegetation_endpoint(monkeypatch, tmp_path):
    from agroblackbox.services import hls
    monkeypatch.setattr(hls, "CACHE", tmp_path / "hls")   # live download, not a stale cache
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=300) as c:
        response = await c.get("/api/vegetation/hls", params={"latitude": LAT, "longitude": LON,
                                                               "start": HLS_START, "end": HLS_END})
    assert response.status_code == 200, response.text
    print("NASA HLS:", json.dumps(check_vegetation_payload(response.json(), start=HLS_START, end=HLS_END)))
    if os.getenv("HLS_SMOKE_OUT"):   # optional evidence file (CI artifact), public coordinate only
        with open(os.environ["HLS_SMOKE_OUT"], "w", encoding="utf-8") as fh:
            json.dump(response.json(), fh, indent=1)


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("EARTHDATA_TOKEN"), reason="ABB-09 GPM smoke needs EARTHDATA_TOKEN")
async def test_real_gpm_through_the_public_precipitation_endpoint(monkeypatch, tmp_path):
    from agroblackbox.services import gpm
    monkeypatch.setattr(gpm, "CACHE", tmp_path / "gpm")
    monkeypatch.setattr(power, "CACHE", tmp_path / "power")
    import time
    # A slow GES DISC can leave months NOT_READ at the time budget (kept under the demo proxy's 100 s
    # limit); like a user, retry: months already read come from the cache and the rest are read.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=300) as c:
        for attempt in range(1, 4):
            start = time.monotonic()
            response = await c.get("/api/precipitation/gpm", params={"latitude": LAT, "longitude": LON, "year": YEAR})
            elapsed = time.monotonic() - start
            assert response.status_code == 200, response.text
            assert elapsed < gpm.PROXY_LIMIT_SECONDS - 5, f"answer took {elapsed:.0f} s, past the proxy limit"
            summary = response.json()["summary"]
            print(f"GPM attempt {attempt}: {elapsed:.0f} s, observed {summary['observed']}, "
                  f"not_read {summary['not_read']}")
            if summary["not_read"] == 0:
                break
    print("NASA GPM:", json.dumps(check_precipitation_payload(response.json(), year=YEAR)))
    if os.getenv("GPM_SMOKE_OUT"):
        with open(os.environ["GPM_SMOKE_OUT"], "w", encoding="utf-8") as fh:
            json.dump(response.json(), fh, indent=1)
