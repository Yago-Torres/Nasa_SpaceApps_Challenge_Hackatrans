"""ABB-14 tests that need no database: single-work lookup, request rules, pilot seed, 503/OpenAPI.

Upstream APIs are simulated with httpx.MockTransport (see ``evidence_fakes``).
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from agroblackbox.api.deps import STORAGE_UNAVAILABLE, get_session_factory
from agroblackbox.api.evidence_dto import ClaimContent, ClaimView, PaperRegistration, ReviewDecision
from agroblackbox.app import app
from agroblackbox.evidence_seed import PILOT_SEED, PILOT_SEED_PATH, seed_claim_content
from agroblackbox.services import literature as lit
from evidence_fakes import FakeScholarly, crossref_reply, oa_work

DOI = "10.1038/s41467-022-32464-0"
TITLE = PILOT_SEED[0]["title"]


def lookup(fake: FakeScholarly, **kwargs) -> lit.PaperRecord:
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as client:
            return await lit.lookup_paper(client=client, **kwargs)
    return asyncio.run(go())


# ── lookup_paper ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("W2741809807", "https://openalex.org/W2741809807"),
    ("w2741809807", "https://openalex.org/W2741809807"),
    ("https://openalex.org/W2741809807", "https://openalex.org/W2741809807"),
    (" https://openalex.org/w1 ", "https://openalex.org/W1"),
    ("https://evil.example/W1", None),
    ("A123", None),
    ("W", None),
    (None, None),
])
def test_normalize_openalex_id(raw, expected):
    assert lit.normalize_openalex_id(raw) == expected


def test_doi_lookup_merges_openalex_and_crossref_with_provenance():
    fake = FakeScholarly([oa_work("W1", TITLE, DOI)], {DOI: crossref_reply(DOI, TITLE)})
    paper = lookup(fake, doi="https://doi.org/" + DOI.upper())
    assert (paper.doi_id, paper.doi_status, paper.openalex_id) == (DOI, "VERIFIED_CROSSREF", "https://openalex.org/W1")
    assert paper.source_kind == "LITERATURE_METADATA" and paper.evidence_status == "BIBLIOGRAPHIC_MATCH_ONLY"
    assert [r.source for r in paper.retrievals] == ["OpenAlex", "Crossref"]
    assert paper.retrievals[0].endpoint == f"https://api.openalex.org/works/doi:{DOI}"
    assert {lic.reported_by for lic in paper.licenses} == {"OpenAlex", "Crossref"}


# ---------------------------------------------------------------- ABB-27: dedup
#
# lookup_paper is deliberately NOT disk-cached (see services/literature.py): a
# degraded Crossref status (VERIFICATION_UNAVAILABLE) must stay re-triable on the
# very next call, which is exactly what api/evidence.py's own re-verification policy
# (test_evidence_claims.py::test_unverified_paper_is_reverified_on_next_registration)
# relies on. In-flight deduplication only, covered here and in that policy's own
# re-fetch-after-degradation test.

def test_sequential_lookups_of_the_same_doi_each_check_upstream_again():
    """lookup_paper has no disk cache (unlike search_literature): a degraded Crossref
    status must be re-checkable on the very next call, not stuck for a TTL window."""
    down = FakeScholarly([oa_work("W1", TITLE, DOI)], {DOI: httpx.Response(503)})
    first = lookup(down, doi=DOI)
    assert first.doi_status == "VERIFICATION_UNAVAILABLE"
    up = FakeScholarly([oa_work("W1", TITLE, DOI)], {DOI: crossref_reply(DOI, TITLE)})
    second = lookup(up, doi=DOI)
    assert second.doi_status == "VERIFIED_CROSSREF"


def test_concurrent_identical_lookups_trigger_one_openalex_call():
    calls = []
    release = asyncio.Event()

    async def router(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openalex.org":
            calls.append(request)
            await release.wait()
            return httpx.Response(200, json=oa_work("W1", TITLE, DOI))
        if request.url.host == "api.crossref.org":
            return crossref_reply(DOI, TITLE)
        raise AssertionError(f"unexpected host {request.url.host}")

    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(router)) as client:
            return await lit.lookup_paper(doi=DOI, client=client)

    async def go():
        t1 = asyncio.ensure_future(call())
        t2 = asyncio.ensure_future(call())
        await asyncio.sleep(0)
        release.set()
        return await asyncio.gather(t1, t2)

    p1, p2 = asyncio.run(go())
    assert len(calls) == 1
    assert p1.doi_status == p2.doi_status == "VERIFIED_CROSSREF"


def test_doi_lookup_falls_back_to_crossref_when_openalex_has_no_record():
    fake = FakeScholarly([], {DOI: crossref_reply(DOI, TITLE)})
    paper = lookup(fake, doi=DOI)
    assert paper.doi_status == "VERIFIED_CROSSREF" and paper.openalex_id is None and paper.title == TITLE
    assert paper.retrievals[0].outcome == "not_found" and "Crossref" in paper.source


def test_doi_lookup_title_mismatch_is_flagged_not_resolved():
    fake = FakeScholarly([oa_work("W1", TITLE, DOI)], {DOI: crossref_reply(DOI, "Nitrogen leaching in maize")})
    paper = lookup(fake, doi=DOI)
    assert paper.doi_status == "METADATA_MISMATCH" and paper.title == TITLE


def test_unknown_doi_raises_not_found_and_outage_raises_source_error():
    with pytest.raises(lit.PaperNotFoundError):
        lookup(FakeScholarly(), doi=DOI)
    outage = FakeScholarly(openalex=httpx.Response(503), crossref={DOI: httpx.Response(500)})
    with pytest.raises(lit.LiteratureSourceError) as err:
        lookup(outage, doi=DOI)
    assert not isinstance(err.value, lit.PaperNotFoundError)


def test_openalex_outage_with_crossref_404_is_not_reported_as_absent():
    fake = FakeScholarly(openalex=httpx.ConnectTimeout("timeout"))
    with pytest.raises(lit.LiteratureSourceError) as err:
        lookup(fake, doi=DOI)
    assert not isinstance(err.value, lit.PaperNotFoundError)


def test_openalex_record_reporting_another_doi_is_not_mixed_in():
    fake = FakeScholarly(crossref={DOI: crossref_reply(DOI, TITLE)})
    fake.by_doi[DOI] = oa_work("W7", "Unrelated work", "10.9999/other")
    paper = lookup(fake, doi=DOI)
    assert paper.openalex_id is None and paper.title == TITLE
    assert paper.retrievals[0].outcome == "doi_mismatch_ignored"


def test_openalex_id_lookup_without_doi_never_invents_one():
    fake = FakeScholarly([oa_work("W5", "Synthetic rotation study", None)])
    paper = lookup(fake, openalex_id="W5")
    assert paper.doi is None and paper.doi_status == "NO_DOI" and fake.hosts("api.crossref.org") == []
    with pytest.raises(lit.PaperNotFoundError):
        lookup(fake, openalex_id="W6")


def test_invalid_identifiers_make_no_request():
    fake = FakeScholarly()
    for kwargs in ({"doi": "not-a-doi"}, {"openalex_id": "X1"}, {}, {"doi": DOI, "openalex_id": "W1"}):
        with pytest.raises(ValueError):
            lookup(fake, **kwargs)
    assert fake.requests == []


def test_lookup_does_not_leak_api_key_into_provenance(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "SECRET-TEST-KEY")
    fake = FakeScholarly([oa_work("W1", TITLE, DOI)], {DOI: crossref_reply(DOI, TITLE)})
    paper = lookup(fake, doi=DOI)
    assert fake.hosts("api.openalex.org")[0].url.params["api_key"] == "SECRET-TEST-KEY"
    assert "SECRET" not in paper.model_dump_json()


# ── request rules ────────────────────────────────────────────────────────────

def content(**overrides):
    return {"claim_text": "Synthetic claim", "study_context": "Synthetic context", "study_design": "META_ANALYSIS",
            "evidence_basis": "FULL_TEXT", "access_basis": "OPEN_ACCESS_LICENSE", "content_license": "cc-by",
            "limitations": ["Synthetic test claim"], **overrides}


@pytest.mark.parametrize("overrides", [
    {"evidence_basis": "FULL_TEXT", "access_basis": "NONE"},
    {"evidence_basis": "FULL_TEXT", "access_basis": "PUBLIC_ABSTRACT"},
    {"content_license": None},
    {"evidence_basis": "ABSTRACT", "access_basis": "NONE"},
    {"evidence_basis": "METADATA_ONLY", "access_basis": "NONE", "quoted_fragment": "a quote",
     "source_locator": {"page": "3"}},
    {"quoted_fragment": "a quote without a locator"},
    {"quoted_fragment": "x" * 501, "source_locator": {"page": "3"}},
    {"evidence_basis": "METADATA_ONLY", "access_basis": "NONE", "reported_outcome": {"effect_as_stated": "+20%"}},
    {"limitations": []},
    {"review_status": "ACCEPTED"},
    {"source_kind": "LITERATURE_REVIEWED"},
    {"reviewed_by": str(uuid4())},
    {"study_design": "RANDOMISED_GUESS"},
])
def test_claim_content_rules_reject(overrides):
    with pytest.raises(ValidationError):
        ClaimContent.model_validate(content(**overrides))


def test_claim_content_accepts_attributed_quote_and_abstract_basis():
    ClaimContent.model_validate(content(quoted_fragment="short quote", source_locator={"section": "Results"}))
    ClaimContent.model_validate(content(evidence_basis="ABSTRACT", access_basis="PUBLIC_ABSTRACT", content_license=None,
                                        reported_outcome={"effect_as_stated": "+20%", "units_as_stated": "%"}))


def test_accept_decision_requires_full_text_and_every_decision_a_note():
    source = {"basis": "ABSTRACT", "access_basis": "PUBLIC_ABSTRACT"}
    with pytest.raises(ValidationError):
        ReviewDecision.model_validate({"version": 1, "decision": "ACCEPTED", "note": "ok", "source_consulted": source})
    ReviewDecision.model_validate({"version": 1, "decision": "REJECTED", "note": "no", "source_consulted": source})
    with pytest.raises(ValidationError):
        ReviewDecision.model_validate({"version": 1, "decision": "REJECTED", "note": " ", "source_consulted": source})
    with pytest.raises(ValidationError):  # full text without a licence
        ReviewDecision.model_validate({"version": 1, "decision": "ACCEPTED", "note": "ok", "source_consulted": {
            "basis": "FULL_TEXT", "access_basis": "INSTITUTIONAL_SUBSCRIPTION"}})


def test_paper_registration_takes_only_an_identifier():
    with pytest.raises(ValidationError):
        PaperRegistration.model_validate({"doi": DOI, "title": "client supplied title"})
    with pytest.raises(ValidationError):
        PaperRegistration.model_validate({})
    with pytest.raises(ValidationError):
        PaperRegistration.model_validate({"doi": DOI, "openalex_id": "W1"})


def test_claim_view_cannot_present_unaccepted_claim_as_reviewed():
    now = datetime.now(UTC)
    base = {
        "id": uuid4(), "paper_id": uuid4(), "case_id": uuid4(), "claim_text": "x", "study_context": "y",
        "limitations": ["z"], "version": 1, "created_at": now, "updated_at": now, "study_design": "UNKNOWN",
        "context": {}, "reported_outcome": {}, "source_locator": {}, "evidence_basis": "METADATA_ONLY",
        "access_basis": "NONE", "origin": "MANUAL", "can_edit": False, "can_review": False,
        "paper": {"id": uuid4(), "title": "t", "doi_status": "NO_DOI", "caveat": "c"},
    }
    with pytest.raises(ValidationError):  # REVIEWED kind on a pending claim
        ClaimView.model_validate({**base, "source_kind": "LITERATURE_REVIEWED", "is_reviewed": True,
                                  "review_status": "PENDING", "reviewed_by": uuid4(), "reviewed_at": now})
    with pytest.raises(ValidationError):  # accepted without reviewer identity
        ClaimView.model_validate({**base, "source_kind": "LITERATURE_REVIEWED", "is_reviewed": True,
                                  "review_status": "ACCEPTED"})
    with pytest.raises(ValidationError):  # metadata kind flagged as reviewed
        ClaimView.model_validate({**base, "source_kind": "LITERATURE_METADATA", "is_reviewed": True,
                                  "review_status": "PENDING"})
    ok = ClaimView.model_validate({**base, "source_kind": "LITERATURE_METADATA", "is_reviewed": False,
                                   "review_status": "REJECTED", "reviewed_by": uuid4(), "reviewed_at": now})
    assert not ok.is_reviewed


# ── pilot seed ───────────────────────────────────────────────────────────────

def test_pilot_seed_is_identical_to_the_documented_unverified_file():
    documented = json.loads((Path(__file__).parents[2] / PILOT_SEED_PATH).read_text(encoding="utf-8"))
    assert list(PILOT_SEED) == documented
    assert all(entry["review_status"] == "HUMAN_REVIEW_REQUIRED" for entry in PILOT_SEED)


def test_pilot_seed_maps_to_metadata_only_content_without_quantities():
    for entry in PILOT_SEED:
        mapped = ClaimContent.model_validate(seed_claim_content(entry))
        assert mapped.evidence_basis == "METADATA_ONLY" and mapped.access_basis == "NONE"
        assert mapped.quoted_fragment is None and not mapped.reported_outcome.has_quantities()
        assert mapped.study_design == "META_ANALYSIS"
        assert any("unverified pilot seed" in limitation for limitation in mapped.limitations)


# ── storage and OpenAPI ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evidence_routes_return_503_without_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app.dependency_overrides.pop(get_session_factory, None)
    case_id, claim_id = uuid4(), uuid4()
    headers = {"Authorization": "Bearer whatever"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        responses = [
            await client.post("/api/v1/evidence/papers", json={"doi": DOI}, headers=headers),
            await client.get(f"/api/v1/evidence/papers/{uuid4()}", headers=headers),
            await client.get(f"/api/v1/cases/{case_id}/claims", headers=headers),
            await client.post(f"/api/v1/cases/{case_id}/claims/pilot-import", headers=headers),
            await client.get(f"/api/v1/cases/{case_id}/claims/{claim_id}/history", headers=headers),
        ]
    assert [r.status_code for r in responses] == [503] * len(responses)
    assert all(r.json() == {"detail": STORAGE_UNAVAILABLE} for r in responses)


def test_openapi_documents_evidence_routes_and_reviewed_flags():
    schema = app.openapi()
    for path in ("/api/v1/evidence/papers", "/api/v1/evidence/papers/{paper_id}", "/api/v1/cases/{case_id}/claims",
                 "/api/v1/cases/{case_id}/claims/{claim_id}/review", "/api/v1/cases/{case_id}/claims/{claim_id}/history",
                 "/api/v1/cases/{case_id}/claims/pilot-import"):
        assert path in schema["paths"]
    components = schema["components"]["schemas"]
    assert {"ClaimView", "PaperView", "ClaimEventView", "ReviewDecision", "PilotImportResult"} <= set(components)
    assert {"is_reviewed", "source_kind", "reviewer", "warnings"} <= set(components["ClaimView"]["properties"])
    assert schema["paths"]["/api/v1/cases/{case_id}/claims"]["get"]["security"] == [{"HTTPBearer": []}]
