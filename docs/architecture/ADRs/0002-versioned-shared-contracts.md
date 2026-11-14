# ADR-0002 — Versioned shared data contracts before route migration

- Status: accepted for ABB-02 implementation
- Date: 2026-11-14
- Related GitHub Issue: `ABB-02` / `#2`
- Reviewers / coordination notes: A implements the backend contract; B reviews evidence and rotation semantics; C consumes the OpenAPI components when generating frontend types.

## Context

The development baseline exposes unversioned `/api/*` routes and the React client duplicates a few response types locally. Release 1.0 needs stable, provenance-aware models before persistent cases, additional NASA sources, evidence review and collaboration can integrate. Migrating every route in this Issue would mix contract definition with unfinished storage and authorization work.

## Options considered

1. Continue adding route-specific dictionaries and infer types in the frontend. Rejected because nulls, provenance and source classifications would drift.
2. Introduce `/api/v1` endpoints immediately. Rejected for ABB-02 because their persistence and permission behavior depends on later Issues.
3. Publish versioned Pydantic components in OpenAPI while preserving current routes. Selected because downstream work can generate and review types without claiming unavailable behavior.

## Decision

- `backend/agroblackbox/schemas.py` owns the shared 1.0 models: `Case`, `Field`, `SourceManifest`, `Observation`, `Anomaly`, `Hypothesis`, `Paper`, `EvidenceClaim`, `Rotation`, `Review`, `Report` and `ApiError`.
- Domain resources carry `schema_version: "1.0"`; unknown fields are rejected.
- Source observations include manifest identity, units, spatial/temporal resolution, quality flags and limitations. Missing numeric observations use explicit `null`, never a fabricated value.
- Source categories follow `SCIENTIFIC_POLICY.md`. Hypotheses contain evidence links and gaps, not a causal probability.
- Exact coordinates are allowed only with an explicit privacy tier; `WITHHELD` records cannot carry coordinates.
- Literature metadata is not a reviewed claim. A reviewed claim requires reviewer identity, timestamp and non-pending status.
- `Paper` aligns with ABB-13's merged literature response: bibliographic DOI status, structured authors, licences and retrieval provenance remain distinct from a reviewed `EvidenceClaim`.
- Rotation outputs are `MODEL_SCENARIO` or `ILLUSTRATIVE`; `verified_impact` remains `null` until a separately validated method exists.
- The OpenAPI document exposes these models in `components.schemas` and declares `x-agro-contract-version: "1.0"`.
- Existing `/api/*` payloads and validation-error bodies remain compatible. Route-by-route adoption and `/api/v1` resources occur in their owning Issues.

## Tradeoffs and consequences

- B and C can work against stable schema names before persistence and UI generation are complete.
- OpenAPI describes target data components that are not all returned by a live endpoint yet; documentation must continue distinguishing schema availability from implemented behavior.
- Any incompatible field change requires a schema-version change or an explicit compatibility plan and contract tests.

## Rollout / rollback

Adopt components incrementally in case, observation, evidence, rotation, review and report Issues. Rollback removes OpenAPI component registration without changing current `/api/*` routes. Do not silently reuse `1.0` for an incompatible contract.
