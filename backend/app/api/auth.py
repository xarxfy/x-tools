"""First-run setup, login, logout and the current user."""

import hmac
import secrets
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_session, current_user
from app.core.audit import audit
from app.core.config import VERSION, get_settings
from app.core.db import get_db
from app.core.security import (
    CSRF_COOKIE, SESSION_COOKIE, decrypt_json, hash_password, login_throttle, new_token, recovery_hash,
    session_expiry, token_hash, totp_verify, validate_new_password, verify_password,
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
    audit("setup", user=user)
    return UserOut(id=user.id, username=user.username, role=user.role)


# Second login step: after the password, users with two-factor login get a short-lived ticket.
_tickets: dict[str, tuple[int, float, int]] = {}  # hash → (user id, expires, failed attempts)
_tickets_lock = threading.Lock()
TICKET_SECONDS = 300
TICKET_ATTEMPTS = 5


class SecondFactor(BaseModel):
    ticket: str = Field(min_length=10, max_length=100)
    code: str = Field(min_length=6, max_length=32)


def check_second_factor(user: User, code: str) -> bool:
    """TOTP code (each one only once) or an unused recovery code (consumed)."""
    if user.totp_secret:
        step = totp_verify(decrypt_json(user.totp_secret), code, user.totp_last_step or 0)
        if step is not None:
            user.totp_last_step = step
            return True
    digest = recovery_hash(code)
    codes = list(user.recovery_codes or [])
    for stored in codes:
        if hmac.compare_digest(stored, digest):
            codes.remove(stored)
            user.recovery_codes = codes
            return True
    return False


@router.post("/auth/login")
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    wait = login_throttle.retry_after(body.username, ip)
    if wait:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many failed attempts. Try again in {wait} s.",
                            headers={"Retry-After": str(wait)})
    user = db.scalar(select(User).where(func.lower(User.username) == body.username.lower()))
    # Verify against a dummy hash when the user does not exist to keep timing similar.
    ok = verify_password(user.password_hash if user else _DUMMY_HASH, body.password) and user is not None
    if not ok or user.disabled:
        login_throttle.failed(body.username, ip)
        audit("login.failed", "", "disabled account" if ok else "wrong password",
              username=body.username[:64])
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    login_throttle.succeeded(body.username, ip)
    if user.totp_enabled:
        ticket = new_token()
        with _tickets_lock:
            now = time.time()
            for key in [k for k, v in _tickets.items() if v[1] < now]:
                _tickets.pop(key)
            _tickets[token_hash(ticket)] = (user.id, now + TICKET_SECONDS, 0)
        return {"totp_required": True, "ticket": ticket}
    _start_session(db, user, request, response)
    audit("login", user=user)
    return UserOut(id=user.id, username=user.username, role=user.role)


@router.post("/auth/login/2fa", response_model=UserOut)
def login_second_factor(body: SecondFactor, request: Request, response: Response, db: Session = Depends(get_db)):
    key = token_hash(body.ticket)
    with _tickets_lock:
        entry = _tickets.get(key)
    if entry is None or entry[1] < time.time():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login expired – enter your password again")
    user = db.get(User, entry[0])
    if user is None or user.disabled or not check_second_factor(user, body.code):
        audit("login.failed", "", "wrong two-factor code", user=user)
        with _tickets_lock:
            attempts = entry[2] + 1
            if attempts >= TICKET_ATTEMPTS:
                _tickets.pop(key, None)
            else:
                _tickets[key] = (entry[0], entry[1], attempts)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong code")
    with _tickets_lock:
        _tickets.pop(key, None)
    _start_session(db, user, request, response)
    audit("login", "", "with two-factor code", user=user)
    return UserOut(id=user.id, username=user.username, role=user.role)


@router.post("/auth/logout", status_code=204)
def logout(response: Response, session: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    audit("logout", user=session.user)
    db.delete(db.merge(session))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut(id=user.id, username=user.username, role=user.role)


_DUMMY_HASH = hash_password("x-tools-dummy-password")
