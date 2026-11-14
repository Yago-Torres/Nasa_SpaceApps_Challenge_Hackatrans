# Changelog — human-verified behavior only

## Unreleased

- Development governance simplified: roadmap Issues are directly executable without vote or approval labels, while contract coordination, technical review, scientific integrity and security checks remain required.
- ABB-01 tooling hardening delivered: mandatory uv/npm lockfiles, strict CI installs, Node/Python pin checks, repaired frontend lock data and explicit review of the esbuild install script; GitHub Actions passed all required jobs.
- Shared cross-model coding context, governance/templates, product 1.0 specifications and team workflow initialized.
- Previous development-baseline endpoints preserved; Python development tooling migrated to uv and Omarchy agent setup documented.
- ABB-13 (pending PR review): `/api/literature` now verifies each DOI against Crossref, normalizes authors/venue/licence/retrieval time, removes duplicates and labels every result `LITERATURE_METADATA` / `BIBLIOGRAPHIC_MATCH_ONLY` with a DOI status. Fixed: an upstream error could expose `OPENALEX_API_KEY` in the 502 response detail.

A successful specification or design document is not a completed product feature. Add entries only when user-visible behavior actually changes.
