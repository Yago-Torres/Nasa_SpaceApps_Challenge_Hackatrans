"""Orphan-reference guard for the evidence graph (ABB-16).

Stored graph edges and hypothesis evidence links refer to case records by id. Deleting a
referenced record would leave a dangling reference, so the routes that delete hypotheses,
evidence claims and fields call these checks first (409). Imports only the ORM, so
``api.cases``, ``api.hypotheses`` and ``api.evidence`` can use it without import cycles.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db.models import EvidenceGraphEdge, Hypothesis

REFERENCED = ("This {what} is referenced by the case evidence graph ({where}); remove those links first.")


def graph_edges_referencing(db: Session, case_id: UUID, node_id: str) -> list[EvidenceGraphEdge]:
    return list(db.scalars(select(EvidenceGraphEdge).where(
        EvidenceGraphEdge.case_id == case_id,
        or_(EvidenceGraphEdge.source_node == node_id, EvidenceGraphEdge.target_node == node_id),
    )))


def require_unreferenced(db: Session, case_id: UUID, node_id: str, what: str, *,
                         check_hypotheses: bool = False) -> None:
    """409 when a stored edge (or, optionally, a hypothesis evidence link) refers to ``node_id``."""
    where: list[str] = []
    edges = graph_edges_referencing(db, case_id, node_id)
    if edges:
        where.append(f"{len(edges)} graph edge(s)")
    if check_hypotheses:
        raw = node_id.split(":", 1)[1]
        citing = db.scalars(select(Hypothesis.id).where(
            Hypothesis.case_id == case_id,
            or_(Hypothesis.supporting_evidence_ids.contains([raw]),
                Hypothesis.contradicting_evidence_ids.contains([raw])),
        )).all()
        if citing:
            where.append(f"evidence links of {len(citing)} hypothesis/hypotheses")
    if where:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=REFERENCED.format(what=what, where=", ".join(where)))
