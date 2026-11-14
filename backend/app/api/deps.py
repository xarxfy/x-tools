"""Shared request dependencies: client IP, current user, CSRF protection."""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, csrf_matches, token_hash
from app.models import User, UserSession

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Roles, from least to most: viewer (read only, no credentials or logs) < operator (maintain services,
# customers, credentials, control containers) < admin (everything: users, settings, agents, backups, audit log).
ROLES = ("viewer", "operator", "admin")
RANK = {role: i for i, role in enumerate(ROLES)}


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


def require(role: str):
    """Dependency: the logged-in user needs at least this role."""
    def check(user: User = Depends(current_user)) -> User:
        if RANK.get(user.role, -1) < RANK[role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not allowed to do this")
        return user
    return check
