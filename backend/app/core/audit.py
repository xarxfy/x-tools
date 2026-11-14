"""Audit log: who did what. The current request is remembered per request (context
variable set by a middleware), so endpoints only call ``audit("service.created", name)``."""

import contextvars
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from starlette.requests import Request

from app.core.db import session_scope
from app.models import AuditLog

current_request: contextvars.ContextVar[Request | None] = contextvars.ContextVar("current_request", default=None)
KEEP_DAYS = 365


def audit(action: str, target: str = "", detail: str = "", *, user=None, username: str = "") -> None:
    request = current_request.get()
    if user is None and request is not None:
        user = getattr(request.state, "user", None)
    ip = ""
    if request is not None:
        from app.api.deps import client_ip
        ip = client_ip(request)
    with session_scope() as db:
        db.add(AuditLog(user_id=getattr(user, "id", None), username=(getattr(user, "username", None) or username)[:64],
                        action=action[:60], target=str(target)[:200], detail=str(detail)[:500], ip=ip))
        db.commit()


def cleanup() -> None:
    with session_scope() as db:
        db.execute(delete(AuditLog).where(AuditLog.ts < datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)))
        db.commit()
