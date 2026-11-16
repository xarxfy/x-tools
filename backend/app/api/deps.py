"""Shared request dependencies: client IP, current user, CSRF protection."""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, csrf_matches, token_hash
from app.models import Role, User, UserSession

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

def client_ip(request: Request) -> str:
    if get_settings().trust_proxy:
        forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def current_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(token)))
    if session is None or session.user.disabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    expires = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        db.delete(session)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    if request.method not in SAFE_METHODS:
        if not csrf_matches(request.cookies.get(CSRF_COOKIE, ""), request.headers.get(CSRF_HEADER, ""), session.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token")
    request.state.user = session.user
    return session


def current_user(session: UserSession = Depends(current_session)) -> User:
    return session.user


def permissions_of(user: User, db: Session | None = None) -> frozenset[str]:
    """What the user's role allows (cached per request through the user object)."""
    cached = getattr(user, "_xt_permissions", None)
    if cached is not None:
        return cached
    from app.core.db import session_scope
    from app.core.permissions import ALL, PERMISSIONS

    def load(session: Session) -> frozenset[str]:
        role = session.get(Role, user.role)
        if role is None:
            return frozenset()  # unknown role: nothing is allowed
        return ALL if role.id == "admin" else frozenset(p for p in role.permissions or [] if p in PERMISSIONS)
    if db is not None:
        perms = load(db)
    else:
        with session_scope() as session:
            perms = load(session)
    user._xt_permissions = perms
    return perms


def require(permission: str):
    """Dependency: the logged-in user's role needs this permission (core/permissions.py)."""
    from app.core.permissions import PERMISSIONS
    if permission not in PERMISSIONS:
        raise ValueError(f"unknown permission {permission}")

    def check(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if permission not in permissions_of(user, db):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not allowed to do this")
        return user
    return check
