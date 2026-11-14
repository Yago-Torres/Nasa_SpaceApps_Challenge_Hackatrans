# Evidence graph, conclusions and traceability (ABB-16)

Status: **implemented in the case API, pending scientific review (B) and the ABB-23 graph view (C)**. Code: `backend/agroblackbox/services/evidence_graph.py` (assembly, edge rules, trace — pure functions), `backend/agroblackbox/api/evidence_graph.py` (routes), `api/graph_dto.py` (contract), `api/graph_guard.py` (deletion guard). Tests: `backend/tests/test_evidence_graph_offline.py` (no database), `backend/tests/test_evidence_graph_api.py` (PostgreSQL). Migration `f4b81d2c6e93` (after `e3a9c71f5b20`). Applies `SCIENTIFIC_POLICY.md`, `TIMELINE_HYPOTHESES.md` and `EVIDENCE_CLAIMS.md`.

The graph shows **which record refers to which**. An edge is never a causal link, and no node or edge carries a weight, probability, confidence or score. A conclusion is always written by a person; CropStory never generates one.

## 1. Nodes

Node ids are typed strings: `<type>:<uuid>` for records, fixed keys for case facts.

| `node_type` | id | `kind` | Original evidence | Linkable* |
|---|---|---|---|---|
| `SOURCE_MANIFEST` | `manifest:<uuid>` | OBSERVED | yes | no |
| `OBSERVATION` | `observation:<uuid>` | OBSERVED (MISSING_DATA when the value is null) | no | yes |
| `ANOMALY` | `anomaly:<uuid>` | OBSERVED (MISSING_DATA when not computed) | no | yes |
| `FARMER_REPORT` | `farmer:incident`, `farmer:crop-history` | FARMER_REPORTED (crop history MISSING_DATA when empty) | yes (when reported) | yes |
| `FIELD` | `field:<uuid>` | FARMER_REPORTED | yes | yes |
| `PAPER` | `paper:<uuid>` (only papers cited by a claim of the case) | LITERATURE_METADATA | yes | no |
| `EVIDENCE_CLAIM` | `claim:<uuid>` | LITERATURE_REVIEWED only when ACCEPTED, else LITERATURE_METADATA | no | yes |
| `HYPOTHESIS` | `hypothesis:<uuid>` | HYPOTHESIS | no | yes |
| `CONCLUSION` | `conclusion:<uuid>` | CONCLUSION (new kind) | no | yes |
| `MISSING_DATA` | `missing:no-local-measurements` (always), `missing:no-observations:<year>`, `missing:hypothesis:<uuid>:<n>` (hypothesis missing evidence) | MISSING_DATA | no | only `no-local-measurements` |

\* Linkable: may be referenced by a stored edge or a conclusion citation. Papers and manifests are reached through claims and observations; derived missing-data nodes can disappear (e.g. after an ingestion) and are therefore not linkable.

Every node has `label`, `entity_id`, `status` (claim/conclusion review status, hypothesis evaluation status), `active` (false for a superseded retrieval), `start`/`end`, `limitations` (≥ 1) and `provenance`. **Provenance never contains request parameters or coordinates, for any role**: manifests show provider, dataset, version, endpoint, retrieval time, raw and content checksums, processing version, resolution and the field label; fields show label and region only. The full manifest (coordinates for OWNER/EDITOR only, `"REDACTED"` otherwise) stays at `GET /observations`. Observation values still identify the ½° × ⅝° NASA POWER grid cell (`TIMELINE_HYPOTHESES.md`).

Values of superseded retrievals are included only when evidence refers to them (or with `include_superseded=true`), together with their manifest so their trace stays complete.

## 2. Edges

Direction reads "`from` RELATION `to`".

| Relation | Origin | Meaning | Allowed |
|---|---|---|---|
| `DERIVED_FROM` | STRUCTURAL | anomaly → observation → source manifest | generated only |
| `CITES` | STRUCTURAL | claim → paper | generated only |
| `SUPPORTS` / `CONTRADICTS` | HYPOTHESIS_LINK | evidence → hypothesis, from the hypothesis evidence lists | edited only through `PATCH …/hypotheses/{id}` |
| `LIMITS` | HYPOTHESIS_LINK | hypothesis missing-evidence entry → hypothesis | generated |
| `SUPPORTS` / `CONTRADICTS` | MANUAL | observation, anomaly (with a value), claim, farmer report, field → conclusion or claim; hypothesis → conclusion | stored |
| `LIMITS` | MANUAL | evidence or `missing:no-local-measurements` → conclusion, hypothesis or claim | stored |
| `ADDRESSES` | MANUAL | conclusion → hypothesis | stored |

STRUCTURAL and HYPOTHESIS_LINK edges are generated from the stored records on every read and never stored, so they cannot drift or be duplicated. HYPOTHESIS_LINK edges show `review_status` `PENDING` while the hypothesis is OPEN and `EVALUATED` once a member set COMPATIBLE / CONTRADICTED / NOT_EVALUABLE (the link was part of that evaluation; the link itself was not accepted). STRUCTURAL edges are `NOT_APPLICABLE`.

Rejected (422 unless stated): endpoints that do not exist in the case (unknown and foreign ids get the same answer), self-loops, hand-made DERIVED_FROM/CITES, SUPPORTS/CONTRADICTS into a hypothesis, missing data as support or contradiction, a paper or manifest as an endpoint, non-linkable nodes, the same source both supporting and contradicting a target, edges that would make evidence circular, and duplicates (409). The database repeats the essentials: node-id pattern, relation set, no self-loop, unique (case, from, to, relation), and a composite FK `(conclusion_id, case_id)` that keeps a citation in the same case as its conclusion and removes citations with it.

**No orphans.** Deleting a hypothesis, claim or field that a stored edge refers to returns 409 (`api/graph_guard.py`). Deleting a claim cited by a hypothesis evidence link is also refused now (this closes an ABB-10/14 gap). A conclusion keeps at least one SUPPORTS citation (409 on deleting the last one). If a reference is nevertheless dangling (data changed outside the API), it is listed in `orphan_references` and never drawn.

**Rival hypotheses** coexist: the same anomaly may support one hypothesis and contradict another; nothing is ranked or resolved.

## 3. Conclusions

A conclusion has `title`, `statement` (≤ 2 000), `limitations` (≥ 1; a fixed limitation is always prepended), review state, authorship and `version`. On creation it must cite at least one supporting node; it may also cite contradicting and limiting nodes and name the hypotheses it addresses. Each supporting or contradicting node must **itself trace back to original evidence**; a hypothesis without evidence links cannot be cited as support (422).

Citations are stored edges with `conclusion_id`. After creation they are changed through the edge routes; any change to the text or the citations returns the conclusion to `PENDING`, bumps its version and makes the editor a contributor.

### Review

States `PENDING → ACCEPTED | REJECTED | CHANGES_REQUESTED`; `ACCEPTED → REJECTED | CHANGES_REQUESTED`. A decision needs a note, is recorded by someone who did not create or edit the conclusion or its citations (403; the database also forbids it), and applies to the conclusion and its citations together. `ACCEPTED` additionally requires (409 otherwise, `review_blockers` lists the reasons in advance):

1. every cited branch reaches original evidence (`trace_complete`);
2. every literature claim on a grounding path is ACCEPTED (reviewed literature);
3. every hypothesis on a grounding path has been evaluated (not OPEN).

`ACCEPTED` means **a member who did not write it checked the evidence trail**. It does not mean the case is scientifically validated, that a cause was demonstrated or that cited results transfer to this farm. Reviewed conclusions cannot be deleted (409); they are kept for audit.

Manual edges that are not conclusion citations are reviewed one by one with the same states and contributor rule; editing the note returns them to PENDING.

## 4. Trace

`GET …/evidence-graph/trace/{node_id}` follows grounding edges from any node: SUPPORTS/CONTRADICTS backwards (from the cited evidence) and DERIVED_FROM/CITES forwards. Original evidence — a NASA POWER source manifest, a farmer-reported record or field, a registered paper — ends a path. The response gives `complete` (every branch ends at original evidence), `paths` (each step with the edge and relation; capped at 500, `truncated` flag; nodes and edges are always complete), `dead_ends`, `original_evidence`, the LIMITS edges that qualify the traced nodes (not traversed), a summary (reaches observed data / farmer report / literature, reviewed and unreviewed claims, unevaluated hypotheses, superseded values, missing data) and, for conclusions, `review_blockers`. A trace lists recorded references; it does not show that the evidence establishes the statement.

## 5. Roles and audit

| Action | OWNER | EDITOR | REVIEWER | VIEWER | No permission |
|---|---|---|---|---|---|
| Read graph, trace, conclusions, edges | yes | yes | yes | yes | 404 |
| Create / edit / delete conclusions and edges | yes | yes | 403 | 403 | 404 |
| Review a conclusion or edge | yes* | yes* | yes* | 403 | 404 |

\* Never on content they contributed. Reviewers may review but not author: writing conclusions is case work, while checking that a conclusion is supported by its evidence trail is the review role (ADR-0004, as for hypotheses and claims). All writes require the case to be DRAFT or INVESTIGATING and not archived (409), carry the item `version` (409 when stale) and append `case_history` rows (`CONCLUSION_CREATED`, `CONCLUSION_UPDATED`, `CONCLUSION_REVIEWED`, `CONCLUSION_DELETED`, `GRAPH_EDGE_CREATED`, `GRAPH_EDGE_UPDATED`, `GRAPH_EDGE_REVIEWED`, `GRAPH_EDGE_DELETED`) with actor, time and before/after values, without bumping the case version. Limits: 100 conclusions and 1 000 stored edges per case.

## 6. Limitations

- Completeness is structural: the trace checks that references exist and end at original evidence, not that the evidence is sufficient, relevant or correctly interpreted. That judgement is the reviewer's, and the system cannot verify it.
- SUPPORTS/CONTRADICTS have no strength or polarity arithmetic; a CONTRADICTS deeper in a path is shown, not combined.
- Hypothesis evidence links have no per-link author or note in the graph (they are written through the hypotheses API; who changed them is in `case_history`).
- `incident_notes` (free text written by the team) is shown in the incident node as in the timeline; it is not scanned for personal data.
- The graph is rebuilt on every request (no cache); fine for case-sized data (tens to hundreds of nodes).
- No UI yet (ABB-23); the `CONCLUSION` kind is new and needs a label and design in the Field Survey design system.
