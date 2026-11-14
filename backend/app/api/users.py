"""User management (admins only) and the audit log."""

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.auth import USERNAME_PATTERN
from app.api.deps import ROLES, require
from app.core.audit import audit
from app.core.db import get_db
from app.core.security import hash_password, validate_new_password
from app.models import AuditLog, User, UserSession

router = APIRouter(prefix="/api", tags=["users"])
ADMIN = [Depends(require("admin"))]
ROLE_PATTERN = "^(" + "|".join(ROLES) + ")$"


class UserIn(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    role: str = Field(pattern=ROLE_PATTERN)
    password: str = Field(max_length=256)


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern=ROLE_PATTERN)
    disabled: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(max_length=256)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "disabled": u.disabled,
            "totp_enabled": u.totp_enabled, "created_at": utc(u.created_at), "last_login_at": utc(u.last_login_at)}


def get_user(db: Session, uid: int) -> User:
    user = db.get(User, uid)
    if user is None:
        raise HTTPException(404, "User not found")
    return user


def active_admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == "admin",
                                                                   User.disabled.is_(False))) or 0


def logout_everywhere(db: Session, user: User) -> None:
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))


@router.get("/users", dependencies=ADMIN)
def list_users(db: Session = Depends(get_db)):
    return [out(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("/users", status_code=201, dependencies=ADMIN)
def create_user(body: UserIn, db: Session = Depends(get_db)):
    try:
        validate_new_password(body.password)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    if db.scalar(select(User).where(func.lower(User.username) == body.username.lower())):
        raise HTTPException(409, "This username is taken")
    user = User(username=body.username, role=body.role, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    audit("user.created", user.username, f"role {user.role}")
    return out(user)


@router.put("/users/{uid}")
def update_user(uid: int, body: UserUpdate, me: User = Depends(require("admin")), db: Session = Depends(get_db)):
    user = get_user(db, uid)
    changes = []
    if body.role is not None and body.role != user.role:
        if user.role == "admin" and body.role != "admin" and active_admins(db) <= 1:
            raise HTTPException(409, "At least one active admin is needed")
        changes.append(f"role {user.role} → {body.role}")
        user.role = body.role
    if body.disabled is not None and body.disabled != user.disabled:
        if body.disabled and user.id == me.id:
            raise HTTPException(409, "You cannot disable yourself")
        if body.disabled and user.role == "admin" and active_admins(db) <= 1:
            raise HTTPException(409, "At least one active admin is needed")
        user.disabled = body.disabled
        changes.append("disabled" if body.disabled else "enabled")
        if body.disabled:
            logout_everywhere(db, user)
    db.commit()
    if changes:
        audit("user.updated", user.username, ", ".join(changes))
    return out(user)


@router.post("/users/{uid}/password", status_code=204, dependencies=ADMIN)
def reset_password(uid: int, body: PasswordReset, db: Session = Depends(get_db)):
    user = get_user(db, uid)
    try:
        validate_new_password(body.password)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    user.password_hash = hash_password(body.password)
    logout_everywhere(db, user)
    db.commit()
    audit("user.password_reset", user.username)
    return Response(status_code=204)


@router.post("/users/{uid}/reset-2fa", status_code=204, dependencies=ADMIN)
def reset_2fa(uid: int, db: Session = Depends(get_db)):
    """For users who lost their phone and their recovery codes."""
    user = get_user(db, uid)
    user.totp_enabled, user.totp_secret, user.recovery_codes, user.totp_last_step = False, None, [], 0
    logout_everywhere(db, user)
    db.commit()
    audit("user.2fa_reset", user.username)
    return Response(status_code=204)


@router.delete("/users/{uid}", status_code=204)
def delete_user(uid: int, me: User = Depends(require("admin")), db: Session = Depends(get_db)):
    user = get_user(db, uid)
    if user.id == me.id:
        raise HTTPException(409, "You cannot delete yourself")
    if user.role == "admin" and not user.disabled and active_admins(db) <= 1:
        raise HTTPException(409, "At least one active admin is needed")
    name = user.username
    db.delete(user)
    db.commit()
    audit("user.deleted", name)
    return Response(status_code=204)


@router.get("/audit", dependencies=ADMIN)
def audit_log(limit: int = Query(100, ge=1, le=500), before: int | None = Query(None, ge=1),
              user: str = Query("", max_length=64), action: str = Query("", max_length=60),
              db: Session = Depends(get_db)):
    """Newest first; `before` = id of the last entry already shown (paging)."""
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if before:
        q = q.where(AuditLog.id < before)
    if user:
        q = q.where(AuditLog.username == user)
    if action:
        q = q.where(AuditLog.action.startswith(action))
    return [{"id": a.id, "ts": utc(a.ts), "username": a.username, "action": a.action, "target": a.target,
             "detail": a.detail, "ip": a.ip} for a in db.scalars(q)]


@router.get("/audit/actions", dependencies=ADMIN)
def audit_actions(db: Session = Depends(get_db)):
    return sorted({a.split(".")[0] for a in db.scalars(select(AuditLog.action).distinct())})


@router.get("/users/names", dependencies=ADMIN)
def user_names(db: Session = Depends(get_db)):
    return sorted({n for n in db.scalars(select(AuditLog.username).distinct()) if n}
                  | {u.username for u in db.scalars(select(User))})


