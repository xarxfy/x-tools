"""The logged-in user's own account: password and two-factor login."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.deps import current_session
from app.core.audit import audit
from app.core.db import get_db
from app.core.security import (
    decrypt_json, encrypt_json, hash_password, new_recovery_codes, new_totp_secret, recovery_hash, totp_uri,
    totp_verify, validate_new_password, verify_password,
)
from app.models import User, UserSession

router = APIRouter(prefix="/api/account", tags=["account"])


class PasswordChange(BaseModel):
    current: str = Field(min_length=1, max_length=256)
    new: str = Field(min_length=1, max_length=256)


class Code(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class Disable(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=32)


def me(db: Session, session: UserSession) -> User:
    return db.get(User, session.user_id)


@router.get("")
def account(session: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    user = me(db, session)
    return {"username": user.username, "role": user.role, "totp_enabled": user.totp_enabled,
            "recovery_codes_left": len(user.recovery_codes or []) if user.totp_enabled else 0}


@router.post("/password", status_code=204)
def change_password(body: PasswordChange, session: UserSession = Depends(current_session),
                    db: Session = Depends(get_db)):
    user = me(db, session)
    if not verify_password(user.password_hash, body.current):
        raise HTTPException(403, "The current password is wrong")
    try:
        validate_new_password(body.new)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    user.password_hash = hash_password(body.new)
    # Log out everywhere else.
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != session.id))
    db.commit()
    audit("account.password_changed", user.username)
    return Response(status_code=204)


@router.post("/2fa/setup")
def setup_2fa(session: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    """Start: new secret (not active until confirmed with a code)."""
    user = me(db, session)
    if user.totp_enabled:
        raise HTTPException(409, "Two-factor login is already on")
    secret = new_totp_secret()
    user.totp_secret = encrypt_json(secret)
    db.commit()
    return {"secret": secret, "uri": totp_uri(secret, user.username)}


@router.post("/2fa/enable")
def enable_2fa(body: Code, session: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    user = me(db, session)
    if user.totp_enabled or not user.totp_secret:
        raise HTTPException(409, "Start the setup first")
    step = totp_verify(decrypt_json(user.totp_secret), body.code)
    if step is None:
        raise HTTPException(422, "Wrong code – check the time on your phone and try again")
    codes = new_recovery_codes()
    user.totp_enabled, user.totp_last_step = True, step
    user.recovery_codes = [recovery_hash(c) for c in codes]
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != session.id))
    db.commit()
    audit("account.2fa_enabled", user.username)
    return {"recovery_codes": codes}  # shown once


@router.post("/2fa/disable", status_code=204)
def disable_2fa(body: Disable, session: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    from app.api.auth import check_second_factor
    user = me(db, session)
    if not user.totp_enabled:
        return Response(status_code=204)
    if not verify_password(user.password_hash, body.password) or not check_second_factor(user, body.code):
        raise HTTPException(403, "Password or code is wrong")
    user.totp_enabled, user.totp_secret, user.recovery_codes, user.totp_last_step = False, None, [], 0
    db.commit()
    audit("account.2fa_disabled", user.username)
    return Response(status_code=204)


@router.post("/2fa/recovery-codes")
def new_codes(body: Code, session: UserSession = Depends(current_session), db: Session = Depends(get_db)):
    from app.api.auth import check_second_factor
    user = me(db, session)
    if not user.totp_enabled:
        raise HTTPException(409, "Two-factor login is off")
    if not check_second_factor(user, body.code):
        raise HTTPException(403, "Wrong code")
    codes = new_recovery_codes()
    user.recovery_codes = [recovery_hash(c) for c in codes]
    db.commit()
    audit("account.recovery_codes", user.username)
    return {"recovery_codes": codes}
