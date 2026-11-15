"""ABB-29 assertions shared by the MANUAL real-source smoke test and its offline self-test.

The checks only look at the shape and internal consistency of what the real services return (provenance,
units, anomaly arithmetic, DOI verification). They never compare against remembered scientific values, because
real upstream data legitimately changes (NASA POWER reprocessing, Crossref corrections).
"""
from __future__ import annotations

import re

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def check_climate_payload(body: dict, *, event_year: int, expect_live: bool) -> dict:
    """Return a small summary (used as manual evidence) after asserting the /api/climate contract holds."""
    assert body["kind"] == "observation" and body["source_kind"] == "OBSERVED"
    assert body["event_year"] == event_year and len(body["monthly"]) == 12
    assert [m["month"] for m in body["monthly"]] == list(range(1, 13))
    prov = body["provenance"]
    assert prov["provider"] == "NASA POWER" and HEX64.match(prov["checksum_sha256"])
    assert HEX64.match(body["data_sha256"]) and body["data_sha256"] == prov["checksum_sha256"]
    assert prov["source_uri"].startswith("https://power.larc.nasa.gov/")
    assert prov["spatial_resolution"]["unit"] and prov["temporal_resolution"]["unit"]
    assert body["retrieved_at"] and prov["limitations"], "provenance without retrieval time or limitations"
    if expect_live:
        assert body["cache"]["served_from_cache"] is False and body["cache"]["upstream_attempts"] >= 1
    computed = 0
    for month in body["monthly"]:
        for value, reference, anomaly in (
                (month["precipitation_mm"], month["reference_precipitation_mm"], month["precipitation_anomaly_mm"]),
                (month["max_temperature_c"], month["reference_max_temperature_c"],
                 month["max_temperature_anomaly_c"])):
            if anomaly is None:
                continue                      # a month without usable data must be null, never a number
            assert value is not None and reference is not None, "anomaly computed from missing data"
            assert abs((value - reference) - anomaly) <= 0.011, "anomaly is not value minus reference"
            computed += 1
    assert computed > 0, "no anomaly could be computed for any month"
    assert body["quality"]["status"] in {"complete", "partial", "insufficient"}
    return {"dataset_version": prov["dataset_version"], "retrieved_at": body["retrieved_at"],
            "sha256": body["data_sha256"], "anomalies_computed": computed,
            "quality": body["quality"]["status"], "warnings": len(body["quality"]["warnings"]),
            "warning_texts": [str(w)[:160] for w in body["quality"]["warnings"]]}


def check_doi_verification(check, *, doi: str) -> dict:
    assert check.status == "VERIFIED_CROSSREF", f"Crossref did not verify {doi}: {check.status}"
    assert check.crossref_doi == doi.lower() and check.title and check.year
    assert check.retrieval.source == "Crossref"
    return {"doi": doi, "title": check.title, "year": check.year, "licenses": len(check.licenses)}


def check_paper_record(record, *, doi: str) -> dict:
    assert record.doi_id == doi.lower() and record.doi_status == "VERIFIED_CROSSREF"
    assert record.source_kind == "LITERATURE_METADATA" and record.evidence_status == "BIBLIOGRAPHIC_MATCH_ONLY"
    assert record.retrievals, "a paper without retrieval records has no provenance"
    return {"doi": record.doi_id, "doi_status": record.doi_status, "sources": sorted({r.source for r in record.retrievals})}


DOI_STATUSES = {"VERIFIED_CROSSREF", "METADATA_MISMATCH", "NOT_FOUND_IN_CROSSREF", "VERIFICATION_UNAVAILABLE",
                "MALFORMED_DOI", "NO_DOI"}


def check_search_result(body: dict, *, query: str) -> dict:
    """/api/literature: bibliographic matches only, each with provenance; DOIs only as resolvable doi.org URLs
    that agree with the normalized id; no duplicate works (ABB-13 search, used by the ABB-23 'Add a study')."""
    assert body["query"] == query and body["source_kind"] == "LITERATURE_METADATA"
    assert body["retrieved_at"] and body["limitations"], "search without retrieval time or limitations"
    results = body["results"]
    assert results, "OpenAlex returned no work for a broad agronomic query"
    seen: set[str] = set()
    for paper in results:
        assert paper["title"] and paper["kind"] == "literature"
        assert paper["source_kind"] == "LITERATURE_METADATA" and paper["evidence_status"] == "BIBLIOGRAPHIC_MATCH_ONLY"
        assert paper["doi_status"] in DOI_STATUSES
        assert paper["retrievals"], "a search result without retrieval records has no provenance"
        if paper["doi"] is None:
            assert paper["doi_id"] is None and paper["doi_status"] in {"NO_DOI", "MALFORMED_DOI"}
        else:
            assert paper["doi"] == "https://doi.org/" + paper["doi_id"], "DOI link does not match the normalized DOI"
            assert paper["doi_status"] != "NO_DOI"
            assert paper["doi_id"] not in seen, "duplicate work in the results"
            seen.add(paper["doi_id"])
    return {"results": len(results), "with_doi": len(seen),
            "verified_crossref": sum(p["doi_status"] == "VERIFIED_CROSSREF" for p in results),
            "total_openalex_matches": body.get("total_openalex_matches"),
            "duplicates_removed": body.get("duplicates_removed")}


HLS_STATUSES = {"VALID", "OBSCURED", "NO_DATA", "NOT_READ"}


def check_vegetation_payload(body: dict, *, start: str, end: str) -> dict:
    """ABB-12: assert the /api/vegetation/hls contract on a real answer and summarise it."""
    assert body["kind"] == "observation" and body["source_kind"] == "OBSERVED"
    assert body["start"] == start and body["end"] == end
    prov = body["provenance"]
    assert prov["provider"] == "NASA LP DAAC" and HEX64.match(prov["checksum_sha256"])
    assert prov["dataset_version"] == "HLS v2.0" and prov["limitations"]
    assert body["spatial_resolution"]["value"] == 30 and body["spatial_resolution"]["unit"] == "m"
    obs = body["observations"]
    assert obs, "no HLS acquisition found over the point in the range"
    assert [o["acquired_at"] for o in obs] == sorted(o["acquired_at"] for o in obs)
    keys = [(o["product"], o["acquired_at"]) for o in obs]
    assert len(keys) == len(set(keys)), "the same overpass is reported twice"
    for o in obs:
        assert start <= o["date"] <= end and o["status"] in HLS_STATUSES
        assert o["granule_id"].startswith("HLS.") and o["granule_id"].endswith(".v2.0")
        if o["status"] == "VALID":
            assert o["ndvi"] is not None and -1 <= o["ndvi_min"] <= o["ndvi"] <= o["ndvi_max"] <= 1
            assert HEX64.match(o["data_sha256"]) and o["pixel_size_m"] == 30
            red, nir = o["red_reflectance"], o["nir_reflectance"]
            assert -0.01 <= red <= 1.6 and -0.01 <= nir <= 1.6
            assert o["pixels"]["clear"] * 2 > o["window_pixels"] - o["pixels"]["fill"]
            assert 32601 <= o["epsg"] <= 32760
        else:
            assert o["ndvi"] is None and o["reason"], "a non-valid acquisition must say why and carry no value"
    s = body["summary"]
    assert s["acquisitions"] == len(obs) == s["valid"] + s["obscured"] + s["no_data"] + s["not_read"]
    assert s["valid"] > 0, "no clear acquisition in the whole range"
    total = sum(g["days"] for g in body["gaps"])
    assert total == s["gap_days"] and all(g["start"] <= g["end"] for g in body["gaps"])
    return {"acquisitions": s["acquisitions"], "valid": s["valid"], "obscured": s["obscured"],
            "no_data": s["no_data"], "not_read": s["not_read"], "granules_found": s["granules_found"],
            "gap_days": s["gap_days"], "longest_gap_days": s["longest_gap_days"],
            "products": sorted({o["product"] for o in obs}), "tiles": sorted({o["mgrs_tile"] for o in obs}),
            "ndvi_valid": [(o["date"], o["product"], o["ndvi"]) for o in obs if o["status"] == "VALID"][:40],
            "upstream_requests": body["cache"]["upstream_requests"]}
