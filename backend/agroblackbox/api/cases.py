"""Authenticated case, field (parcel), workflow and permission management (ABB-05, ABB-06).

Access rules (ADR-0004):
- A user without a permission row gets 404 for the case (existence is not revealed).
- A member whose role does not allow the action gets 403.
- Content changes need the current ``version`` (optimistic concurrency, 409 on conflict),
  bump the version and append a ``case_history`` row with author, time and before/after.
- Coordinates are redacted server-side for REVIEWER/VIEWER (see ``agroblackbox.privacy``).
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db.models import Case, CaseHistory, CasePermission, Field, User, utcnow
from ..privacy import PRECISE_ROLES, redact_coordinates, visible_location
from .deps import CurrentPrincipal, DbSession
from .graph_guard import require_unreferenced
from .dto import (
    ArchiveRequest,
    CaseCreate,
    CaseFieldView,
    CaseList,
    CaseUpdate,
    CaseView,
    MAX_FIELDS,
    FieldCreate,
    FieldInput,
    FieldPatch,
    HistoryEntry,
    PermissionGrant,
    PermissionView,
    StatusChange,
    UserSummary,
    check_incident_dates,
    check_location,
)

router = APIRouter(prefix="/api/v1/cases", tags=["cases (ABB-05/ABB-06)"])

CASE_NOT_FOUND = "Case not found."
EDITOR_ROLES = frozenset({"OWNER", "EDITOR"})
OWNER_ONLY = frozenset({"OWNER"})
EDITABLE_STATUSES = frozenset({"DRAFT", "INVESTIGATING"})

# (from, to) -> roles allowed to perform the transition.
TRANSITIONS: dict[tuple[str, str], frozenset[str]] = {
    ("DRAFT", "INVESTIGATING"): EDITOR_ROLES,
    ("INVESTIGATING", "DRAFT"): EDITOR_ROLES,
    ("INVESTIGATING", "REVIEWED"): frozenset({"REVIEWER"}),
    ("REVIEWED", "INVESTIGATING"): frozenset({"OWNER", "EDITOR", "REVIEWER"}),
    ("REVIEWED", "PUBLISHED"): OWNER_ONLY,
    ("PUBLISHED", "INVESTIGATING"): OWNER_ONLY,
}

CASE_ATTRIBUTES = ("title", "incident_start", "incident_end", "crop_history", "incident_notes")
FIELD_ATTRIBUTES = (
    "label", "privacy_tier", "latitude", "longitude", "region_label", "area_hectares",
    "precise_location_consent", "rounding_deg", "limitations",
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _json(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_json(item) for item in value]
    return value


def _field_snapshot(field: Field) -> dict[str, Any]:
    return {"id": str(field.id), **{name: _json(getattr(field, name)) for name in FIELD_ATTRIBUTES}}


def _load(db: Session, case_id: UUID, user_id: UUID, *, lock: bool = False) -> tuple[Case, str]:
    role = db.scalar(
        select(CasePermission.role).where(CasePermission.case_id == case_id, CasePermission.user_id == user_id)
    )
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=CASE_NOT_FOUND)
    case = db.get(Case, case_id, with_for_update=lock, populate_existing=lock)
    if case is None:  # pragma: no cover - permissions cascade with the case
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=CASE_NOT_FOUND)
    return case, role


def _require_role(role: str, allowed: frozenset[str]) -> None:
    if role not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Your role on this case does not allow this action.")


def _require_version(case: Case, version: int) -> None:
    if case.version != version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"The case changed since you loaded it (current version {case.version}). Reload and retry.",
        )


def _require_editable(case: Case) -> None:
    if case.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The case is archived; unarchive it before editing.")
    if case.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"The case is {case.status}; move it back to INVESTIGATING before editing.",
        )


def _record(
    db: Session, case: Case, actor: User, action: str, changes: dict[str, Any], *,
    bump: bool = True, note: str | None = None,
) -> None:
    if bump:
        case.version += 1
        # Never earlier than created_at: a wall clock that steps back (e.g. WSL2/VM time sync)
        # would otherwise produce a CaseView that fails its own updated_at >= created_at check.
        case.updated_at = max(utcnow(), case.created_at)
    db.add(CaseHistory(
        case_id=case.id, version=case.version, action=action, actor_id=actor.id,
        created_at=utcnow(), changes=changes, note=note,
    ))


def _diff(target: Any, updates: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for name, new in updates.items():
        old = getattr(target, name)
        new_value = new.value if isinstance(new, Enum) else new
        if old != new_value:
            changes[name] = {"before": _json(old), "after": _json(new_value)}
            setattr(target, name, new_value)
    return changes


def _summary(user: User | None) -> UserSummary | None:
    return None if user is None else UserSummary(id=user.id, display_name=user.display_name)


def _field_view(field: Field, role: str) -> CaseFieldView:
    location = visible_location(
        role=role, privacy_tier=field.privacy_tier, latitude=field.latitude, longitude=field.longitude,
        rounding_deg=field.rounding_deg, precise_location_consent=field.precise_location_consent,
    )
    return CaseFieldView(
        id=field.id, label=field.label, privacy_tier=field.privacy_tier,
        latitude=location.latitude, longitude=location.longitude, region_label=field.region_label,
        area_hectares=field.area_hectares, limitations=list(field.limitations or []),
        location_precision=location.precision, rounding_deg=field.rounding_deg,
        precise_location_consent=field.precise_location_consent,
    )


def _case_view(db: Session, case: Case, role: str) -> CaseView:
    fields = db.scalars(select(Field).where(Field.case_id == case.id).order_by(Field.label, Field.id)).all()
    owner = db.get(User, case.owner_id)
    return CaseView(
        id=case.id, title=case.title, incident_start=case.incident_start, incident_end=case.incident_end,
        fields=[_field_view(field, role) for field in fields], crop_history=list(case.crop_history or []),
        incident_notes=case.incident_notes, visibility=case.visibility, created_at=case.created_at,
        updated_at=case.updated_at, version=case.version, status=case.status, archived_at=case.archived_at,
        owner=_summary(owner), my_role=role,
    )


def _new_field(case_id: UUID, data: FieldInput) -> Field:
    return Field(
        case_id=case_id, label=data.label, privacy_tier=data.privacy_tier.value, latitude=data.latitude,
        longitude=data.longitude, region_label=data.region_label, area_hectares=data.area_hectares,
        precise_location_consent=data.precise_location_consent, rounding_deg=data.rounding_deg,
        limitations=list(data.limitations),
    )


def _sync_visibility(db: Session, case: Case) -> None:
    members = db.scalar(select(func.count()).select_from(CasePermission).where(CasePermission.case_id == case.id))
    case.visibility = "SHARED" if (members or 0) > 1 else "PRIVATE"


# ── cases ────────────────────────────────────────────────────────────────────

@router.post("", response_model=CaseView, status_code=status.HTTP_201_CREATED)
def create_case(body: CaseCreate, principal: CurrentPrincipal, db: DbSession) -> CaseView:
    """Create a private case (status DRAFT, version 1) with at least one field; caller is OWNER."""
    user = principal.user
    case = Case(
        owner_id=user.id, title=body.title, incident_start=body.incident_start, incident_end=body.incident_end,
        crop_history=list(body.crop_history), incident_notes=body.incident_notes, visibility="PRIVATE",
        status="DRAFT", version=1,
    )
    db.add(case)
    db.flush()
    db.add(CasePermission(case_id=case.id, user_id=user.id, role="OWNER"))
    fields = [_new_field(case.id, item) for item in body.fields]
    db.add_all(fields)
    db.flush()
    _record(db, case, user, "CREATED", {
        **{name: {"before": None, "after": _json(getattr(case, name))} for name in CASE_ATTRIBUTES},
        "fields": [_field_snapshot(field) for field in fields],
    }, bump=False)
    db.commit()
    return _case_view(db, case, "OWNER")


@router.get("", response_model=CaseList)
def list_cases(
    principal: CurrentPrincipal, db: DbSession,
    include_archived: bool = Query(default=False, description="Include archived cases"),
) -> CaseList:
    """Only cases where the caller holds a permission, most recently updated first."""
    query = (
        select(Case, CasePermission.role)
        .join(CasePermission, CasePermission.case_id == Case.id)
        .where(CasePermission.user_id == principal.user.id)
        .order_by(Case.updated_at.desc(), Case.id)
    )
    if not include_archived:
        query = query.where(Case.archived_at.is_(None))
    return CaseList(items=[_case_view(db, case, role) for case, role in db.execute(query).all()])


@router.get("/{case_id}", response_model=CaseView)
def get_case(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> CaseView:
    case, role = _load(db, case_id, principal.user.id)
    return _case_view(db, case, role)


@router.patch("/{case_id}", response_model=CaseView)
def update_case(case_id: UUID, body: CaseUpdate, principal: CurrentPrincipal, db: DbSession) -> CaseView:
    """OWNER/EDITOR; send the ``version`` you read. Previous values go to the history."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_version(case, body.version)
    _require_editable(case)
    updates = {name: getattr(body, name) for name in CASE_ATTRIBUTES if name in body.model_fields_set}
    start = updates.get("incident_start", case.incident_start)
    end = updates["incident_end"] if "incident_end" in updates else case.incident_end
    try:
        check_incident_dates(start, end)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    if "crop_history" in updates:
        updates["crop_history"] = list(updates["crop_history"])
    changes = _diff(case, updates)
    if changes:
        _record(db, case, principal.user, "UPDATED", changes)
        db.commit()
    return _case_view(db, case, role)


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    case_id: UUID, principal: CurrentPrincipal, db: DbSession,
    version: int = Query(ge=1, description="Current case version"),
) -> Response:
    """OWNER only. Permanently erases the case, its fields, permissions and history."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, OWNER_ONLY)
    _require_version(case, version)
    db.delete(case)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{case_id}/status", response_model=CaseView)
def change_status(case_id: UUID, body: StatusChange, principal: CurrentPrincipal, db: DbSession) -> CaseView:
    """Workflow DRAFT → INVESTIGATING → REVIEWED → PUBLISHED. REVIEWED is set by a REVIEWER;
    PUBLISHED by the OWNER. Publishing does not make the case public."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_version(case, body.version)
    if case.archived_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The case is archived; unarchive it first.")
    allowed = TRANSITIONS.get((case.status, body.status))
    if allowed is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"Transition {case.status} → {body.status} is not allowed."
        )
    _require_role(role, allowed)
    changes = {"status": {"before": case.status, "after": body.status}}
    case.status = body.status
    _record(db, case, principal.user, "STATUS_CHANGED", changes, note=body.note)
    db.commit()
    return _case_view(db, case, role)


@router.post("/{case_id}/archive", response_model=CaseView)
def archive_case(case_id: UUID, body: ArchiveRequest, principal: CurrentPrincipal, db: DbSession) -> CaseView:
    """OWNER only. Archived cases are read-only and hidden from the default list."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, OWNER_ONLY)
    _require_version(case, body.version)
    if (case.archived_at is not None) != body.archived:
        before = _json(case.archived_at)
        case.archived_at = utcnow() if body.archived else None
        _record(db, case, principal.user, "ARCHIVED" if body.archived else "UNARCHIVED",
                {"archived_at": {"before": before, "after": _json(case.archived_at)}})
        db.commit()
    return _case_view(db, case, role)


@router.get("/{case_id}/history", response_model=list[HistoryEntry])
def case_history(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> list[HistoryEntry]:
    """Audit trail, oldest first. Coordinates are REDACTED for REVIEWER/VIEWER."""
    _, role = _load(db, case_id, principal.user.id)
    rows = db.scalars(
        select(CaseHistory).where(CaseHistory.case_id == case_id).order_by(CaseHistory.created_at, CaseHistory.id)
    ).all()
    actors = {user.id: user for user in db.scalars(
        select(User).where(User.id.in_({row.actor_id for row in rows if row.actor_id}))
    )}
    return [
        HistoryEntry(
            id=row.id, version=row.version, action=row.action,
            actor=_summary(actors.get(row.actor_id)) if row.actor_id else None, created_at=row.created_at,
            changes=row.changes if role in PRECISE_ROLES else redact_coordinates(row.changes), note=row.note,
        )
        for row in rows
    ]


# ── fields (parcels) ─────────────────────────────────────────────────────────

def _field_or_404(db: Session, case_id: UUID, field_id: UUID) -> Field:
    field = db.get(Field, field_id)
    if field is None or field.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Field not found.")
    return field


@router.post("/{case_id}/fields", response_model=CaseView, status_code=status.HTTP_201_CREATED)
def add_field(case_id: UUID, body: FieldCreate, principal: CurrentPrincipal, db: DbSession) -> CaseView:
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_version(case, body.version)
    _require_editable(case)
    if db.scalar(select(func.count()).select_from(Field).where(Field.case_id == case_id)) >= MAX_FIELDS:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"A case can hold at most {MAX_FIELDS} fields.")
    field = _new_field(case_id, body.field)
    db.add(field)
    db.flush()
    _record(db, case, principal.user, "FIELD_ADDED", {"field": {"before": None, "after": _field_snapshot(field)}})
    db.commit()
    return _case_view(db, case, role)


@router.patch("/{case_id}/fields/{field_id}", response_model=CaseView)
def update_field(
    case_id: UUID, field_id: UUID, body: FieldPatch, principal: CurrentPrincipal, db: DbSession,
) -> CaseView:
    """Partial update; also how consent to share the precise location is given or revoked."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_version(case, body.version)
    _require_editable(case)
    field = _field_or_404(db, case_id, field_id)
    updates = {name: getattr(body, name) for name in FIELD_ATTRIBUTES if name in body.model_fields_set}
    merged = {name: updates.get(name, getattr(field, name)) for name in FIELD_ATTRIBUTES}
    if merged["privacy_tier"] == "APPROXIMATE" and merged["rounding_deg"] is None:
        updates["rounding_deg"] = merged["rounding_deg"] = 0.1
    try:
        check_location(
            privacy_tier=merged["privacy_tier"], latitude=merged["latitude"], longitude=merged["longitude"],
            precise_location_consent=merged["precise_location_consent"], rounding_deg=merged["rounding_deg"],
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    if "limitations" in updates:
        updates["limitations"] = list(updates["limitations"])
    changes = _diff(field, updates)
    if changes:
        _record(db, case, principal.user, "FIELD_UPDATED", {"field_id": str(field.id), **changes})
        db.commit()
    return _case_view(db, case, role)


@router.delete("/{case_id}/fields/{field_id}", response_model=CaseView)
def remove_field(
    case_id: UUID, field_id: UUID, principal: CurrentPrincipal, db: DbSession,
    version: int = Query(ge=1, description="Current case version"),
) -> CaseView:
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, EDITOR_ROLES)
    _require_version(case, version)
    _require_editable(case)
    field = _field_or_404(db, case_id, field_id)
    if db.scalar(select(func.count()).select_from(Field).where(Field.case_id == case_id)) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A case must keep at least one field.")
    require_unreferenced(db, case_id, f"field:{field.id}", "field")  # ABB-16: no orphan graph edges
    snapshot = _field_snapshot(field)
    db.execute(delete(Field).where(Field.id == field.id))
    _record(db, case, principal.user, "FIELD_REMOVED", {"field": {"before": snapshot, "after": None}})
    db.commit()
    return _case_view(db, case, role)


# ── permissions ──────────────────────────────────────────────────────────────

@router.get("/{case_id}/permissions", response_model=list[PermissionView])
def list_permissions(case_id: UUID, principal: CurrentPrincipal, db: DbSession) -> list[PermissionView]:
    """Members of the case. E-mail addresses are only shown to the OWNER."""
    _, role = _load(db, case_id, principal.user.id)
    rows = db.execute(
        select(CasePermission, User).join(User, User.id == CasePermission.user_id)
        .where(CasePermission.case_id == case_id).order_by(User.display_name, User.id)
    ).all()
    return [
        PermissionView(
            user_id=user.id, display_name=user.display_name,
            email=user.email if role == "OWNER" else None, role=permission.role,
        )
        for permission, user in rows
    ]


@router.post("/{case_id}/permissions", response_model=PermissionView, status_code=status.HTTP_201_CREATED)
def grant_permission(
    case_id: UUID, body: PermissionGrant, principal: CurrentPrincipal, db: DbSession, response: Response,
) -> PermissionView:
    """OWNER only. Grants or changes an existing account's role (EDITOR, REVIEWER, VIEWER).
    Returns 201 when access is granted, 200 when an existing role is changed."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, OWNER_ONLY)
    target = db.scalar(select(User).where(User.email == body.email))
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No account is registered with that email.")
    if target.id == case.owner_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The owner's role cannot be changed.")
    permission = db.scalar(
        select(CasePermission).where(CasePermission.case_id == case_id, CasePermission.user_id == target.id)
    )
    if permission is None:
        db.add(CasePermission(case_id=case_id, user_id=target.id, role=body.role))
        db.flush()
        _record(db, case, principal.user, "PERMISSION_GRANTED",
                {"user_id": str(target.id), "role": {"before": None, "after": body.role}}, bump=False)
    else:
        response.status_code = status.HTTP_200_OK
        if permission.role != body.role:
            _record(db, case, principal.user, "PERMISSION_CHANGED",
                    {"user_id": str(target.id), "role": {"before": permission.role, "after": body.role}}, bump=False)
            permission.role = body.role
    _sync_visibility(db, case)
    db.commit()
    return PermissionView(user_id=target.id, display_name=target.display_name, email=target.email, role=body.role)


@router.delete("/{case_id}/permissions/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_permission(case_id: UUID, user_id: UUID, principal: CurrentPrincipal, db: DbSession) -> Response:
    """OWNER only. Takes effect on the member's next request (permissions are never cached)."""
    case, role = _load(db, case_id, principal.user.id, lock=True)
    _require_role(role, OWNER_ONLY)
    if user_id == case.owner_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The owner's access cannot be revoked.")
    permission = db.scalar(
        select(CasePermission).where(CasePermission.case_id == case_id, CasePermission.user_id == user_id)
    )
    if permission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Permission not found.")
    _record(db, case, principal.user, "PERMISSION_REVOKED",
            {"user_id": str(user_id), "role": {"before": permission.role, "after": None}}, bump=False)
    db.delete(permission)
    db.flush()
    _sync_visibility(db, case)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
