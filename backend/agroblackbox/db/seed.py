"""Opt-in development seed. Every value is synthetic and labelled as such."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from .repositories import CaseRepository


def add_synthetic_development_case(session: Session):
    repo = CaseRepository(session)
    user = repo.create_user(
        email="synthetic-owner@example.invalid",
        display_name="Synthetic development owner",
    )
    return repo.create_case(
        owner_id=user.id,
        title="SYNTHETIC FIXTURE — not a real agricultural incident",
        incident_start=date(2022, 5, 1),
        crop_history=["illustrative wheat"],
        incident_notes="Synthetic development seed. Contains no NASA observation or real farm data.",
    )
