"""x-tools reset-admin: the way back in after losing the password or the 2FA device."""

import pytest

from conftest import csrf_headers


def test_reset_admin(admin):
    h = csrf_headers(admin)
    # turn on 2FA so there is something to reset
    from app.core.db import session_scope
    from app.models import User
    with session_scope() as db:
        u = db.query(User).one()
        u.totp_enabled, u.totp_secret = True, "x"
        db.commit()
    from app.cli_admin import reset
    name, generated = reset(None, None)
    assert name == "admin" and len(generated) >= 16
    with session_scope() as db:
        u = db.query(User).one()
        assert not u.totp_enabled and u.totp_secret is None
    assert admin.get("/api/auth/me").status_code == 401  # old session ended
    r = admin.post("/api/auth/login", json={"username": "admin", "password": generated})
    assert r.status_code == 200, r.text
    log = admin.get("/api/audit").json()
    assert any(e["action"] == "user.reset_cli" for e in log)
    # explicit password, weak password, unknown user
    assert reset("admin", "another long password")[1] is None
    with pytest.raises(ValueError):
        reset("admin", "short")
    with pytest.raises(SystemExit):
        reset("nobody", None)


def test_reset_needs_a_name_with_several_admins(admin):
    h = csrf_headers(admin)
    admin.post("/api/users", json={"username": "second", "password": "second password 1", "role": "admin"}, headers=h)
    from app.cli_admin import reset
    with pytest.raises(SystemExit):
        reset(None, None)
    assert reset("second", None)[0] == "second"
