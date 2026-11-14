# Changelog — human-verified behavior only

## Unreleased

- Shared cross-model coding context, governance/templates, product 1.0 specifications and team workflow initialized.
- Previous development-baseline endpoints preserved; Python development tooling migrated to uv and Omarchy agent setup documented.
- ABB-13 (pending PR review): `/api/literature` now verifies each DOI against Crossref, normalizes authors/venue/licence/retrieval time, removes duplicates and labels every result `LITERATURE_METADATA` / `BIBLIOGRAPHIC_MATCH_ONLY` with a DOI status. Fixed: an upstream error could expose `OPENALEX_API_KEY` in the 502 response detail.

A successful specification or design document is not a completed product feature. Add entries only when user-visible behavior actually changes.
