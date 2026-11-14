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
            "quality": body["quality"]["status"], "warnings": len(body["quality"]["warnings"])}


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
