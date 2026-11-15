"""``x-tools reset-admin``: get back into X-TOOLS when the admin password or the 2FA device is lost.

Runs on the server itself (``docker exec -it x-tools x-tools reset-admin`` or ``sudo x-tools-ctl reset-admin``),
so whoever can do this already controls the machine and the database.
"""

import getpass
import secrets
import string
import sys

from sqlalchemy import delete, select

from app.core.audit import audit
from app.core.db import run_migrations, session_scope
from app.core.security import hash_password, validate_new_password
from app.models import User, UserSession


def generate_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(18))


def reset(username: str | None, password: str | None) -> tuple[str, str | None]:
    """Sets a new password, switches off 2FA, enables the account and logs it out everywhere.
    Returns (username, generated password or None)."""
    run_migrations()
    with session_scope() as db:
        if username:
            user = db.scalar(select(User).where(User.username == username.strip().lower()))
            if user is None:
                raise SystemExit(f"No user '{username}'. Existing users: "
                                 + ", ".join(u.username for u in db.scalars(select(User).order_by(User.username))))
        else:
            admins = list(db.scalars(select(User).where(User.role == "admin").order_by(User.username)))
            if not admins:
                raise SystemExit("There is no user yet – open X-TOOLS and create the first account with the setup code.")
            if len(admins) > 1:
                raise SystemExit("Several admins exist, say which one: x-tools reset-admin <username>\n  "
                                 + ", ".join(a.username for a in admins))
            user = admins[0]
        generated = None
        if not password:
            password = generated = generate_password()
        validate_new_password(password)
        user.password_hash = hash_password(password)
        user.disabled = False
        user.totp_enabled, user.totp_secret, user.recovery_codes, user.totp_last_step = False, None, [], 0
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        db.commit()
        name = user.username
    audit("user.reset_cli", name, "password and 2FA reset on the server", username="(server)")
    return name, generated


def run(username: str | None, generate: bool) -> None:
    password = None
    if not generate:
        if not sys.stdin.isatty():
            raise SystemExit("No terminal for the password prompt – use --generate.")
        password = getpass.getpass("New password (at least 10 characters): ")
        if password != getpass.getpass("Repeat: "):
            raise SystemExit("The passwords differ.")
    try:
        name, generated = reset(username, password)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print(f"Password of '{name}' changed, two-factor login switched off, all sessions ended.")
    if generated:
        print(f"New password: {generated}\nLog in and change it under Settings → Account, then turn 2FA on again.")
