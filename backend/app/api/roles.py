"""Roles and permissions (administrators): your own roles with freely chosen permissions."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, permissions_of, require
from app.core.audit import audit
from app.core.db import get_db
from app.core.permissions import AREAS, BUILTIN, PERMISSIONS
from app.models import Role, User

router = APIRouter(prefix="/api/roles", tags=["roles"], dependencies=[Depends(current_user)])


class RoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    permissions: list[str] = Field(default_factory=list, max_length=len(PERMISSIONS))

    @field_validator("name")
    @classmethod
    def strip(cls, value: str) -> str:
        return " ".join(value.split())


def out(role: Role, users: int) -> dict:
    perms = sorted(PERMISSIONS) if role.id == "admin" else sorted(role.permissions or [])
    return {"id": role.id, "name": role.name, "builtin": role.builtin, "permissions": perms, "users": users,
            "locked": role.id == "admin"}


def user_counts(db: Session) -> dict[str, int]:
    return dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())


def get_role(db: Session, rid: str) -> Role:
    role = db.get(Role, rid)
    if role is None:
        raise HTTPException(404, "Role not found")
    return role


def clean(db: Session, body: RoleIn, actor: User, own: str = "") -> list[str]:
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name is missing")
    if any(r.id != own and r.name.lower() == name.lower() for r in db.scalars(select(Role))):
        raise HTTPException(409, "A role with this name already exists")
    unknown = set(body.permissions) - set(PERMISSIONS)
    if unknown:
        raise HTTPException(422, f"Unknown permission: {sorted(unknown)[0]}")
    perms = sorted(set(body.permissions))
    if not set(perms) <= permissions_of(actor, db):
        raise HTTPException(403, "You cannot give a role more permissions than you have yourself")
    return perms


def can_list(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    if not permissions_of(user, db) & {"admin.users", "admin.roles"}:
        raise HTTPException(403, "You are not allowed to do this")
    return user


@router.get("", dependencies=[Depends(can_list)])
def list_roles(db: Session = Depends(get_db)):
    counts = user_counts(db)
    order = {"viewer": 0, "operator": 1, "admin": 2}
    roles = sorted(db.scalars(select(Role)), key=lambda r: (order.get(r.id, 3), r.name.lower()))
    return {"roles": [out(r, counts.get(r.id, 0)) for r in roles],
            "permissions": [{"key": k, "area": a} for k, a in PERMISSIONS.items()], "areas": list(AREAS)}


@router.post("", status_code=201)
def create_role(body: RoleIn, me: User = Depends(require("admin.roles")), db: Session = Depends(get_db)):
    perms = clean(db, body, me)
    role = Role(name=body.name.strip(), permissions=perms, builtin=False)
    db.add(role)
    db.commit()
    audit("role.created", role.name, f"{len(perms)} permissions")
    return out(role, 0)


@router.put("/{rid}")
def update_role(rid: str, body: RoleIn, me: User = Depends(require("admin.roles")), db: Session = Depends(get_db)):
    role = get_role(db, rid)
    if role.id == "admin":
        raise HTTPException(409, "The Administrator role always has every permission and cannot be changed")
    perms = clean(db, body, me, own=rid)
    if role.builtin and body.name.strip() != role.name:
        raise HTTPException(409, "Built-in roles keep their name")
    before = set(role.permissions or [])
    role.name, role.permissions = body.name.strip(), perms
    # the last user manager must stay one: a change must not leave nobody who can manage users
    from app.api.users import active_admins
    if active_admins(db) < 1:
        db.rollback()
        raise HTTPException(409, "At least one active user must be able to manage users")
    db.commit()
    audit("role.updated", role.name, f"+{sorted(set(perms) - before)} -{sorted(before - set(perms))}")
    return out(role, user_counts(db).get(role.id, 0))


@router.delete("/{rid}", status_code=204, dependencies=[Depends(require("admin.roles"))])
def delete_role(rid: str, db: Session = Depends(get_db)):
    role = get_role(db, rid)
    if role.builtin:
        raise HTTPException(409, "Built-in roles cannot be deleted")
    if user_counts(db).get(role.id):
        raise HTTPException(409, "This role is still assigned to users – give them another role first")
    db.delete(role)
    db.commit()
    audit("role.deleted", role.name)
    return Response(status_code=204)
