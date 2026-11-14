"""Password change, two-factor login, backup/restore, history."""

import base64
import time

from conftest import csrf_headers

PW = "correct horse battery"


def login(client, password=PW):
    return client.post("/api/auth/login", json={"username": "admin", "password": password})


def test_change_password(admin):
    h = csrf_headers(admin)
    assert admin.post("/api/account/password", json={"current": "wrong", "new": "another long pw"},
                      headers=h).status_code == 403
    assert admin.post("/api/account/password", json={"current": PW, "new": "short"}, headers=h).status_code == 422
    assert admin.post("/api/account/password", json={"current": PW, "new": "another long pw"},
                      headers=h).status_code == 204
    admin.cookies.clear()
    assert login(admin).status_code == 401
    assert login(admin, "another long pw").status_code == 200


def test_two_factor(admin):
    from app.core.security import totp_code
    h = csrf_headers(admin)
    secret = admin.post("/api/account/2fa/setup", headers=h).json()["secret"]
    step = int(time.time() // 30)
    assert admin.post("/api/account/2fa/enable", json={"code": "000000" if totp_code(secret, step) != "000000"
                                                       else "111111"}, headers=h).status_code == 422
    r = admin.post("/api/account/2fa/enable", json={"code": totp_code(secret, step)}, headers=h)
    codes = r.json()["recovery_codes"]
    assert len(codes) == 10 and admin.get("/api/account").json()["totp_enabled"]

    admin.cookies.clear()
    r = login(admin)
    assert r.json()["totp_required"] and "xt_session" not in admin.cookies
    ticket = r.json()["ticket"]
    # the code used for enabling cannot be used again
    assert admin.post("/api/auth/login/2fa", json={"ticket": ticket, "code": totp_code(secret, step)}).status_code == 401
    assert admin.post("/api/auth/login/2fa", json={"ticket": ticket, "code": codes[0]}).status_code == 200
    assert admin.get("/api/auth/me").status_code == 200

    admin.cookies.clear()
    ticket = login(admin).json()["ticket"]
    assert admin.post("/api/auth/login/2fa", json={"ticket": ticket, "code": codes[0]}).status_code == 401  # used
    for _ in range(4):
        admin.post("/api/auth/login/2fa", json={"ticket": ticket, "code": "999999"})
    # ticket is gone after too many attempts
    assert admin.post("/api/auth/login/2fa", json={"ticket": ticket, "code": codes[1]}).status_code == 401

    ticket = login(admin).json()["ticket"]
    assert admin.post("/api/auth/login/2fa", json={"ticket": ticket, "code": codes[1]}).status_code == 200
    h = csrf_headers(admin)
    assert admin.post("/api/account/2fa/disable", json={"password": PW, "code": "123456"}, headers=h).status_code == 403
    assert admin.post("/api/account/2fa/disable", json={"password": PW, "code": codes[2]}, headers=h).status_code == 204
    admin.cookies.clear()
    assert login(admin).json()["username"] == "admin"


def test_backup_restore(admin, tmp_path):
    h = csrf_headers(admin)
    sid = admin.post("/api/services", json={"name": "Keep me"}, headers=h).json()["id"]
    admin.put(f"/api/services/{sid}/credentials", json=[{"label": "x", "password": "s3cret-pw"}], headers=h)
    assert admin.post("/api/backup", json={"passphrase": "short"}, headers=h).status_code == 422
    r = admin.post("/api/backup", json={"passphrase": "backup passphrase"}, headers=h)
    assert r.status_code == 200 and r.content.startswith(b"XTB1")
    assert b"s3cret-pw" not in r.content and b"Keep me" not in r.content  # encrypted
    blob = base64.b64encode(r.content).decode()

    admin.delete(f"/api/services/{sid}", headers=h)
    assert admin.get("/api/services").json() == []
    assert admin.post("/api/backup/restore", json={"passphrase": "wrong one", "data": blob},
                      headers=h).status_code == 403
    assert admin.post("/api/backup/restore", json={"passphrase": "x", "data": base64.b64encode(b"nope" * 20).decode()},
                      headers=h).status_code == 422
    assert admin.post("/api/backup/restore", json={"passphrase": "backup passphrase", "data": blob},
                      headers=h).status_code == 204
    assert admin.get("/api/services").status_code == 401  # sessions are reset
    login(admin)
    assert [s["name"] for s in admin.get("/api/services").json()] == ["Keep me"]
    assert admin.get(f"/api/services/{sid}/credentials").json()[0]["password"] == "s3cret-pw"


def test_history(admin):
    from datetime import datetime, timedelta, timezone

    from app.monitor import history
    h = csrf_headers(admin)
    sid = admin.post("/api/services", json={"name": "Web", "ports": [{"port": 1}]}, headers=h).json()["id"]
    start = datetime.now(timezone.utc) - timedelta(hours=7 * 24 * 0.1)  # 10 % of the week ago
    history.record_events([{"key": f"port:{sid}:1", "kind": "port", "level": "down", "text": "Web: port 1",
                            "link": "/services"}], now=start)
    history.record_events([], now=start + timedelta(hours=7 * 24 * 0.05))  # solved after 5 % of the week
    events = admin.get("/api/history/events").json()
    assert events[0]["text"] == "Web: port 1" and events[0]["ended_at"]
    assert 94.9 < admin.get("/api/history/uptime").json()[sid] < 95.1

    history.record_metrics(force=True)  # no snapshot, no agents: nothing to record, but must not fail
    assert admin.get("/api/history/metrics?source=local").json() == []
