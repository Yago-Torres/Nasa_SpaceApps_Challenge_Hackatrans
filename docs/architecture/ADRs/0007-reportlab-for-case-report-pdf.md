# ADR-0007 — ReportLab for the case report PDF

- Status: accepted
- Date: 2026-11-14
- Related GitHub Issue: ABB-26 (#26), follow-up to PR #60
- Reviewers / coordination notes: approved by the project owner (Yago) in the project thread; backend reviewers (A/B) to confirm the dependency and the stored-bytes approach.

## Context

ABB-26 asks for a PDF export "if technically viable". The merged report (PR #60) offers Markdown, HTML and JSON; the HTML has print styles. A PDF
needs a renderer. The report is already built as one neutral block list that feeds the Markdown and HTML renderers, and a stored version must stay
byte-for-byte identical (write-once trigger, hashes).

## Options considered

1. **WeasyPrint** (HTML to PDF). Reuses the HTML, but needs system libraries (Pango, Cairo, fonts) in every developer machine, CI image and
   deployment (WSL/Omarchy setups included). Rejected: native dependencies conflict with the `uv sync` only workflow.
2. **Headless browser** (Playwright/Chromium print). Rejected: heavyweight, not installed in CI, large attack surface for a server component.
3. **Browser print of the HTML** (status quo). Zero dependency, but nothing server-side to hash or verify and the result depends on the user's browser.
4. **ReportLab** (pure Python wheel, BSD licence) rendering the same block list. Chosen.

## Decision

Add `reportlab` (5.1.0 locked; pulls `pillow` and `charset-normalizer` transitively) to `backend/pyproject.toml` and `uv.lock`.
`services/case_report_pdf.py` renders the neutral blocks with the bundled Bitstream Vera fonts, `invariant=1` (no creation date or random ID).
`POST …/reports` renders the PDF once and stores the bytes in `reports.content_pdf` with `pdf_sha256` (migration `e8a4c1d7f905`; the write-once trigger
covers both columns). `GET …/download?format=pdf` serves the stored bytes; `verify` recomputes the hash. Versions created before the migration have no
PDF and answer 404 for it: a stored version is never re-rendered later, because a ReportLab upgrade could change the bytes.

## Tradeoffs and consequences

- The PDF is a plain, accessible-enough text layout (headings, tables, lists), not a pixel copy of the HTML. It carries no digital signature.
- Characters the bundled font lacks are drawn as `?`; a few symbols are transliterated (`→` to `->`). CJK or other scripts in free text are not supported yet.
- ReportLab renders text as embedded font subsets, so PDF text is not trivially greppable; privacy is guaranteed because the PDF is built from the same
  private-data-free blocks as the other formats, and tests assert the exact coordinates and notes never appear in the bytes.
- Storage grows by tens of kilobytes per version.
- New transitive dependencies (pillow) increase supply-chain surface; versions are locked and CI uses `uv sync --locked`.

## Rollout / rollback

Roll forward: apply migration `e8a4c1d7f905`, deploy. Rollback: downgrade the migration (drops the two columns, restores the previous trigger), remove the
dependency with `uv remove reportlab`, and remove `format=pdf`; Markdown, HTML and JSON are unaffected.
