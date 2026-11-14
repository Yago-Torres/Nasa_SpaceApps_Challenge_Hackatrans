from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from .models import Case, CasePermission, User, utcnow


class ConcurrentUpdateError(RuntimeError):
    pass


class CaseRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_user(self, *, email: str, display_name: str) -> User:
        user = User(email=email, display_name=display_name)
        self.session.add(user)
        self.session.flush()
        return user

    def create_case(
        self, *, owner_id: UUID, title: str, incident_start: date,
        incident_end: date | None = None, crop_history: list[str] | None = None,
        incident_notes: str | None = None,
    ) -> Case:
        case = Case(
            owner_id=owner_id, title=title, incident_start=incident_start,
            incident_end=incident_end, crop_history=crop_history or [],
            incident_notes=incident_notes, visibility="PRIVATE",
        )
        self.session.add(case)
        self.session.flush()
        self.session.add(CasePermission(case_id=case.id, user_id=owner_id, role="OWNER"))
        self.session.flush()
        return case

    def get(self, case_id: UUID) -> Case | None:
        return self.session.get(Case, case_id)

    def update_title(self, case_id: UUID, *, title: str, expected_version: int) -> Case:
        result = self.session.execute(
            update(Case)
            .where(Case.id == case_id, Case.version == expected_version)
            .values(title=title, version=expected_version + 1, updated_at=utcnow())
        )
        if result.rowcount != 1:
            raise ConcurrentUpdateError("case changed since it was read")
        self.session.flush()
        self.session.expire_all()
        case = self.get(case_id)
        if case is None:  # pragma: no cover - guarded by rowcount
            raise ConcurrentUpdateError("case no longer exists")
        return case
