"""First-run setup, login, logout and the current user."""

import hmac
import secrets
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_session, current_user
from app.core.config import VERSION, get_settings
from app.core.db import get_db
from app.core.security import (
    CSRF_COOKIE, SESSION_COOKIE, hash_password, login_throttle, new_token, session_expiry, token_hash,
    validate_new_password, verify_password,
)
from app.models import User, UserSession

router = APIRouter(prefix="/api", tags=["auth"])
_setup_lock = threading.Lock()  # two simultaneous setup requests must not create two admins

USERNAME_PATTERN = r"^[A-Za-z0-9._-]{3,64}$"


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SetupRequest(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(max_length=256)
    code: str = Field(default="", max_length=32)


# One-time setup code: whoever reaches a fresh installation first must not be
# able to claim it. The code is only printed to the server log.
_SETUP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_setup_code: str | None = None


def setup_code() -> str:
    global _setup_code
    if _setup_code is None:
        raw = "".join(secrets.choice(_SETUP_ALPHABET) for _ in range(8))
        _setup_code = f"{raw[:4]}-{raw[4:]}"
    return _setup_code


def announce_setup_code(db: Session) -> None:
    """Called on startup: print the setup code while no account exists."""
    if _user_count(db) == 0:
        line = "=" * 60
        print(f"\n{line}\n  X-TOOLS is not set up yet.\n  Setup code: {setup_code()}\n"
              f"  Enter it on the setup page to create the admin account.\n{line}\n", flush=True)


def _normalize_code(code: str) -> str:
    return code.strip().upper().replace(" ", "").replace("-", "")


class UserOut(BaseModel):
    id: int
    username: str
    role: str


def _user_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


def _start_session(db: Session, user: User, request: Request, response: Response) -> None:
    token, csrf = new_token(), new_token()
    db.add(UserSession(token_hash=token_hash(token), csrf_token=csrf, user_id=user.id, expires_at=session_expiry(),
                       ip=client_ip(request), user_agent=request.headers.get("user-agent", "")[:255]))
    user.last_login_at = datetime.now(timezone.utc)
    # Drop expired sessions while we are at it.
    db.execute(delete(UserSession).where(UserSession.expires_at < datetime.now(timezone.utc)))
    db.commit()
    settings = get_settings()
    max_age = settings.session_hours * 3600
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, samesite="lax",
                        secure=settings.secure_cookies, path="/")
    # Readable by the frontend, which sends it back in the X-CSRF-Token header.
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, samesite="lax",
                        secure=settings.secure_cookies, path="/")


@router.get("/health", include_in_schema=False)
def health():
    return {"ok": True}


@router.get("/status")
def app_status(db: Session = Depends(get_db)):
    """Public: version and whether the first-run setup still has to be done."""
    return {"name": "X-TOOLS", "version": VERSION, "needs_setup": _user_count(db) == 0}


@router.post("/setup", response_model=UserOut)
def setup(body: SetupRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Create the first (admin) account. Only possible while no user exists."""
    try:
        validate_new_password(body.password)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from None
    ip = client_ip(request)
    wait = login_throttle.retry_after("\0setup", ip)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many attempts. Try again in {wait} s.",
                            headers={"Retry-After": str(wait)})
    with _setup_lock:
        if _user_count(db) > 0:
            raise HTTPException(status.HTTP_409_CONFLICT, "Setup has already been completed")
        if not hmac.compare_digest(_normalize_code(body.code), _normalize_code(setup_code())):
            login_throttle.failed("\0setup", ip)
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Wrong setup code – it is printed in the server log (docker logs x-tools)")
        user = User(username=body.username, password_hash=hash_password(body.password), role="admin")
        db.add(user)
        db.flush()
        _start_session(db, user, request, response)
    return UserOut(id=user.id, username=user.username, role=user.role)


@router.post("/auth/login", response_model=UserOut)
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    wait = login_throttle.retry_after(body.username, ip)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many failed attempts. Try again in {wait} s.",
                            headers={"Retry-After": str(wait)})
    user = db.scalar(select(User).where(func.lower(User.username) == body.username.lower()))
    # Verify against a dummy hash when the user does not exist to keep timing similar.
    ok = verify_password(user.password_hash if user else _DUMMY_HASH, body.password) and user is not None
    if not ok:
        login_throttle.failed(body.username, ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    login_throttle.succeeded(body.username, ip)
    _start_session(db, user, request, response)
    return UserOut(id=user.id, username=user.username, role=user.role)


@router.post("/auth/logout", status_code=204)
def logout(response: Response, session: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    db.delete(db.merge(session))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut(id=user.id, username=user.username, role=user.role)


_DUMMY_HASH = hash_password("x-tools-dummy-password")
