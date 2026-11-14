"""Secrets, encryption, passwords, sessions and login throttling."""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_password_hasher = PasswordHasher()
_fernet: Fernet | None = None

SESSION_COOKIE = "xt_session"
CSRF_COOKIE = "xt_csrf"
CSRF_HEADER = "X-CSRF-Token"


# --- Secret key / encryption --------------------------------------------------


def secret_key() -> str:
    """The Fernet key: XT_SECRET_KEY, or generated once and kept in data_dir/secret.key."""
    settings = get_settings()
    if settings.secret_key:
        return settings.secret_key
    path = settings.data_dir / "secret.key"
    if path.exists():
        return path.read_text().strip()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key().decode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    return key


def fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(secret_key().encode())
    return _fernet


def reset_fernet() -> None:
    global _fernet
    _fernet = None


def encrypt_json(value) -> str:
    return fernet().encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()


def decrypt_json(token: str):
    try:
        return json.loads(fernet().decrypt(token.encode()))
    except InvalidToken:
        raise ValueError("Encrypted data cannot be read – was the secret key changed?") from None


# --- Passwords ----------------------------------------------------------------

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
    if len(password) > 256:
        raise ValueError("Password is too long")


# --- Sessions -----------------------------------------------------------------


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=get_settings().session_hours)


def csrf_matches(cookie_value: str, header_value: str, session_value: str) -> bool:
    """Double submit: header must match the session's CSRF token (cookie is only the carrier)."""
    if not header_value or not session_value:
        return False
    return hmac.compare_digest(header_value, session_value) and hmac.compare_digest(cookie_value or "", session_value)


# --- Login throttling ------------------------------------------------------------


class LoginThrottle:
    """After 5 failed attempts per (username, ip) further attempts are blocked
    for an increasing time (30 s, 60 s, … up to 15 min)."""

    FREE_ATTEMPTS = 5

    def __init__(self):
        self._lock = threading.Lock()
        self._failures: dict[tuple[str, str], tuple[int, float]] = {}

    def retry_after(self, username: str, ip: str) -> int:
        with self._lock:
            count, last = self._failures.get((username.lower(), ip), (0, 0.0))
        if count < self.FREE_ATTEMPTS:
            return 0
        wait = min(900, 30 * 2 ** (count - self.FREE_ATTEMPTS))
        remaining = int(last + wait - time.time())
        return max(0, remaining)

    def failed(self, username: str, ip: str) -> None:
        key = (username.lower(), ip)
        with self._lock:
            count, _ = self._failures.get(key, (0, 0.0))
            self._failures[key] = (count + 1, time.time())

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()

    def succeeded(self, username: str, ip: str) -> None:
        with self._lock:
            self._failures.pop((username.lower(), ip), None)


login_throttle = LoginThrottle()


# --- Two-factor login (TOTP, RFC 6238) -----------------------------------------------

import base64  # noqa: E402
import struct  # noqa: E402

TOTP_PERIOD = 30
TOTP_DIGITS = 6


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** TOTP_DIGITS).zfill(TOTP_DIGITS)


def totp_verify(secret: str, code: str, last_step: int = 0, now: float | None = None) -> int | None:
    """Returns the matching time step (±1 step for clock drift), or None. A step may only be used once."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != TOTP_DIGITS:
        return None
    current = int((now if now is not None else time.time()) // TOTP_PERIOD)
    for step in (current - 1, current, current + 1):
        if step > last_step and hmac.compare_digest(totp_code(secret, step), code):
            return step
    return None


def totp_uri(secret: str, username: str, issuer: str = "X-TOOLS") -> str:
    from urllib.parse import quote
    return (f"otpauth://totp/{quote(issuer)}:{quote(username)}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD}")


def new_recovery_codes(count: int = 10) -> list[str]:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return ["-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(2)) for _ in range(count)]


def recovery_hash(code: str) -> str:
    return token_hash(code.strip().lower().replace(" ", ""))
