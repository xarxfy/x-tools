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
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    expires = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        db.delete(session)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    if request.method not in SAFE_METHODS:
        if not csrf_matches(request.cookies.get(CSRF_COOKIE, ""), request.headers.get(CSRF_HEADER, ""), session.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token")
    return session


def current_user(session: UserSession = Depends(current_session)) -> User:
    return session.user
