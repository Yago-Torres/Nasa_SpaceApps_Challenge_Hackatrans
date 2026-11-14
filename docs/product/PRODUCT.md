# Product definition — AGRO BLACK BOX

**Positioning:** agricultural incident investigation and crop-rotation decision-support grounded in NASA Earth observations, locally supplied agronomic information, and traceable scientific literature.

## Users

- Farmer: reports a local incident, enters crop history and constraints, explores rotation alternatives.
- Agronomist/researcher: validates hypotheses, reviews uncertainty and studies; can challenge a claim with evidence.
- Community collaborator: reviews cases from another region and proposes measurements or comparable practices without seeing private fields by default.
- Administrator: moderates collaborators, privacy/consent and dataset access.

## Canonical end-to-end product journey

1. Sign in or choose an allowed public read-only journey.
2. Create a case, locate field at privacy-appropriate granularity, record crop rotation/history and symptoms. Mark observations vs farmer reports.
3. Fetch NASA POWER and additional supported data products; display source, period, units, spatial footprint, quality flags and original retrieval metadata.
4. Reconstruct event timeline and contextual anomalies; display alternative explanations, confidence limits and local measurements needed.
5. Search scientific literature and assemble a reviewed evidence graph, with DOI and study scope; avoid citing article titles as though they prove conclusions.
6. Enter priorities and local constraints; compare **>=3** agronomically plausible rotation options including current, using a consistent scenario and explicit limitations.
7. Optional second person comments, reviews a hypothesis, adds a local note and requests clarification; protect farm privacy and preserve audit trail.
8. Export a user-facing, reproducible **case investigation report**.

## Product invariants

- Never confuse observed satellite/regional data with parcel ground truth.
- Never infer causes of crop failure from correlation alone.
- Never invent yield, water savings, confidence intervals, scientific citations or consensus.
- Provenance, uncertainty and farmer priorities are first-class data objects.
- Every automated recommendation must be contestable and explainable.
- Collaboration requires consent and moderation, not public GPS by default.

## Non-goals until after release stabilization

Automatic crop prescriptions, autonomous purchases and full causal identification without local validation.
