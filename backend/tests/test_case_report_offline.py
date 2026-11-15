"""ABB-26 offline tests of the pure report service (no database, no network). All data is SYNTHETIC."""
from __future__ import annotations

import copy

from agroblackbox.services import case_report as cr
from agroblackbox.services import case_report_pdf as pdf


def snapshot(**over):
    snap = {
        "schema": cr.SCHEMA,
        "case": {"id": "c" * 8, "title": "Synthetic | case <i>", "status": "INVESTIGATING", "case_version": 3,
                 "incident_start": "2022-05-01", "incident_end": None, "crop_history": ["wheat"]},
        "report": {"version": 1, "generated_at": "2026-11-14T12:00:00+00:00", "status": "PRELIMINARY",
                   "previous_version": None},
        "fields": [], "sources": [], "observations": [], "hypotheses": [], "claims": [], "conclusions": [],
        "rotations": None, "recorded_rotations": [],
        "collaboration": {"members_by_role": {"OWNER": 1}, "comments": 0, "claims_reviewed": 0,
                          "distinct_claim_reviewers": 0, "conclusions_reviewed": 0},
        "source_hash": cr.sources_hash([]), "limitations": list(cr.REPORT_LIMITATIONS),
        "privacy": {"coordinates_included": False, "incident_notes_included": False, "guard_removed": 0},
    }
    snap.update(over)
    snap["fingerprints"] = cr.make_fingerprints(snap)
    snap["changes"] = cr.diff_versions(None, snap)
    return snap


def claim(**over):
    base = {"id": "11111111-1111-4111-8111-111111111111", "claim_text": "Synthetic claim", "review_status": "PENDING",
            "evidence_class": "LITERATURE_METADATA", "paper_title": "Synthetic paper", "paper_year": 2020,
            "doi": "10.5555/abc", "study_design": "UNKNOWN", "evidence_basis": "METADATA_ONLY", "limitations": ["L"]}
    return base | over


def test_empty_case_says_so_explicitly_and_never_invents_data():
    md = cr.render_markdown(cr.build_blocks(snapshot()))
    for sentence in ("No observed-data source has been ingested", "No hypothesis is recorded",
                     "No literature claim is registered", "No conclusion has been written",
                     "no rotation comparison is included"):
        assert sentence in md
    assert "First stored version" in md and "not peer reviewed" in md


def test_spanish_report_has_localised_structure_and_html_language():
    snap = snapshot(language="es")
    blocks = cr.build_blocks(snap)
    md = cr.render_markdown(blocks)
    page = cr.render_html(blocks, "Informe", "es")
    assert "# CropStory — Informe del caso" in md
    assert "## Fuentes y procedencia" in md
    assert '<html lang="es">' in page
    assert cr.render_markdown(cr.build_blocks(copy.deepcopy(snap))) == md


def test_markdown_is_table_safe_and_tag_safe_and_html_is_escaped():
    snap = snapshot(claims=[claim(claim_text="a | b <script>alert(1)</script>")])
    blocks = cr.build_blocks(snap)
    md = cr.render_markdown(blocks)
    assert "<script>" not in md and "a / b &lt;script&gt;" in md and "Synthetic / case &lt;i&gt;" in md
    page = cr.render_html(blocks, "t <x>")
    assert "<script>" not in page and "&lt;script&gt;" in page and "<title>t &lt;x&gt;</title>" in page
    assert "default-src 'none'" in page


def test_only_valid_dois_become_links():
    assert cr.doi_url("10.5555/abc") == "https://doi.org/10.5555/abc"
    assert cr.doi_url("https://doi.org/10.5555/abc") == "https://doi.org/10.5555/abc"
    for bad in ("javascript:alert(1)", "10.5/abc", "not a doi", "", None):
        assert cr.doi_url(bad) is None
    odd = cr.doi_url('10.5555/a"onmouseover="x')  # legal DOI characters are percent-encoded, never raw quotes
    assert odd == "https://doi.org/10.5555/a%22onmouseover%3D%22x" and '"' not in odd
    page = cr.render_html(cr.build_blocks(snapshot(claims=[claim()])), "t")
    assert 'href="https://doi.org/10.5555/abc"' in page and 'rel="noopener noreferrer"' in page


def test_source_endpoint_and_query_never_carry_location():
    assert cr.safe_source_uri("https://power.larc.nasa.gov/api/temporal/daily/point?latitude=41.6&longitude=-0.8#x") \
        == "https://power.larc.nasa.gov/api/temporal/daily/point"
    assert cr.safe_source_uri("file:///etc/passwd") is None and cr.safe_source_uri("") is None
    assert cr.safe_query({"latitude": 41.6, "longitude": -0.8, "start": "20100101", "end": "20221231",
                          "parameters": "PRECTOTCORR"}) == {"end": "20221231", "parameters": "PRECTOTCORR",
                                                              "start": "20100101"}


def test_coordinate_guard_replaces_stored_values_everywhere_and_counts_hits():
    data = {"a": "at 41.6543, -0.8765", "b": ["41.6543"], "c": {"d": "clean"}}
    clean, hits = cr.scrub_coordinates(data, [41.6543, -0.8765, None])
    assert hits == 3 and "41.6543" not in str(clean) and clean["c"]["d"] == "clean"
    assert cr.scrub_coordinates("12", [12.0]) == ("12", 0)  # short strings are never searched


def test_hashes_are_deterministic_and_order_independent():
    a = [{"id": "1", "checksum_sha256": "aa", "content_sha256": "bb"}, {"id": "2", "checksum_sha256": "cc"}]
    assert cr.sources_hash(a) == cr.sources_hash(list(reversed(a))) != cr.sources_hash(a[:1])
    assert cr.canonical_json({"b": 1, "a": 2}) == cr.canonical_json({"a": 2, "b": 1})
    assert len(cr.sha256_text("x")) == 64


def test_diff_reports_added_removed_and_changed_records_by_id():
    old = snapshot(claims=[claim(), claim(id="22222222-2222-4222-8222-222222222222", claim_text="gone")])
    old["report"]["version"] = 4
    new = snapshot(claims=[claim(review_status="ACCEPTED"), claim(id="33333333-3333-4333-8333-333333333333",
                                                                  claim_text="new")])
    new["case"]["case_version"] = 5
    diff = cr.diff_versions(old, new)
    got = {(i["change"], i["label"]) for i in diff["items"]}
    assert got == {("CHANGED", "Synthetic claim"), ("REMOVED", "gone"), ("ADDED", "new")}
    assert diff["previous_version"] == 4 and (diff["previous_case_version"], diff["case_version"]) == (3, 5)
    assert cr.diff_versions(old, copy.deepcopy(old))["items"] == []
    new["changes"] = diff
    md = cr.render_markdown(cr.build_blocks(new))
    assert "Compared with version 4" in md and "ADDED" in md and "REMOVED" in md


def test_rendering_is_deterministic():
    snap = snapshot(claims=[claim()])
    assert cr.render_markdown(cr.build_blocks(snap)) == cr.render_markdown(cr.build_blocks(copy.deepcopy(snap)))
    assert cr.render_html(cr.build_blocks(snap), "t") == cr.render_html(cr.build_blocks(copy.deepcopy(snap)), "t")


def test_pdf_is_a_valid_deterministic_multi_section_document():
    snap = snapshot(claims=[claim(claim_text="Synthetic " + "long text " * 80, paper_title="Árbol → ⅝ 日本")])
    blocks = cr.build_blocks(snap)
    first = pdf.render_pdf(blocks, "Synthetic title")
    assert first.startswith(b"%PDF-") and first.rstrip().endswith(b"%%EOF") and len(first) > 2000
    assert first == pdf.render_pdf(copy.deepcopy(blocks), "Synthetic title")        # invariant: no date, no random ID
    assert first != pdf.render_pdf(cr.build_blocks(snapshot()), "Synthetic title")  # content really changes the bytes


def test_pdf_text_never_draws_missing_glyphs_and_escapes_markup():
    pdf._register()
    assert pdf._clean("a → b ⅝ ½ — °") == "a -> b 5/8 1/2 — °"
    assert pdf._clean("日") == "?" and pdf._clean("line\nbreak") == "line\nbreak"
    # reportlab mini-markup in data must be escaped, not interpreted
    out = pdf.render_pdf([("h1", "<b>x</b> & <font size=999>"), ("table", ["A"], [["<i>z</i>"]]), ("ul", ["<u>"])], "t")
    assert out.startswith(b"%PDF-")
