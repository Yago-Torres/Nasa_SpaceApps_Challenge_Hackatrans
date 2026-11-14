"""Pilot evidence cards (ABB-14): a verbatim copy of ``docs/science/evidence_seed_UNVERIFIED.json``.

The text of these entries was NOT checked against the papers. They are imported only on explicit
request (``POST /api/v1/cases/{case_id}/claims/pilot-import``) as PENDING, unreviewed claims with
``evidence_basis=METADATA_ONLY``. No code path marks them reviewed. A test keeps this copy identical
to the documentation file, so the backend does not depend on ``docs/`` at runtime.
"""
from __future__ import annotations

from typing import Final

PILOT_SEED_PATH: Final = "docs/science/evidence_seed_UNVERIFIED.json"

PILOT_SEED: Final[tuple[dict[str, str], ...]] = (
    {
        "id": "E-001",
        "doi": "10.1038/s41467-022-32464-0",
        "title": "Global systematic review with meta-analysis reveals yield advantage of legume-based rotations and its drivers",
        "study_type": "systematic review and meta-analysis",
        "reported_outcome": "Global average main-crop yield benefit for legume-based pre-crops; effect varies by fertilization and region",
        "context": "multiple crops and global field experiments",
        "potential_use": "reason to examine legume rotation hypothesis",
        "limitation": "Global aggregate is NOT a calibrated forecast for an individual farm",
        "review_status": "HUMAN_REVIEW_REQUIRED",
    },
    {
        "id": "E-002",
        "doi": "10.1038/s41467-025-64567-9",
        "title": "Crop rotations synergize yield, nutrition, and revenue: a meta-analysis",
        "study_type": "meta-analysis",
        "reported_outcome": "Pooled rotation effects on yield, nutrition and revenue",
        "context": "paired field trial observations across regions",
        "potential_use": "qualitative motivation for rotation diversification",
        "limitation": "Treatment effects vary with baseline and agronomic setting; no local extrapolation without checking study data",
        "review_status": "HUMAN_REVIEW_REQUIRED",
    },
    {
        "id": "E-003",
        "doi": "10.1038/s44264-025-00050-8",
        "title": "Optimizing cover cropping application for sustainable crop production",
        "study_type": "meta-analysis",
        "reported_outcome": "Soil carbon, yield and nitrous oxide tradeoffs associated with cover crop systems",
        "context": "many crop and soil contexts",
        "potential_use": "document both potential advantages and tradeoffs",
        "limitation": "Cover crops can increase water competition or emissions under some conditions; applicability must be checked",
        "review_status": "HUMAN_REVIEW_REQUIRED",
    },
)

# Seed ``study_type`` → structured design. Anything unknown stays UNKNOWN (never guessed).
STUDY_TYPE_TO_DESIGN: Final[dict[str, str]] = {
    "systematic review and meta-analysis": "META_ANALYSIS",
    "meta-analysis": "META_ANALYSIS",
}

SEED_LIMITATION: Final = (
    f"Imported from the unverified pilot seed ({PILOT_SEED_PATH}): the claim text was written before anyone "
    "read the paper and has not been checked against it."
)


def seed_claim_content(entry: dict[str, str]) -> dict:
    """Map one seed entry to claim fields. Only bibliographic-level information is used."""
    return {
        "claim_text": entry["reported_outcome"],
        "study_context": (
            f"{entry['context']} (unverified seed description). Intended use per seed: {entry['potential_use']}."
        ),
        "study_design": STUDY_TYPE_TO_DESIGN.get(entry["study_type"].strip().lower(), "UNKNOWN"),
        "evidence_basis": "METADATA_ONLY",
        "access_basis": "NONE",
        "limitations": [entry["limitation"], SEED_LIMITATION],
    }
