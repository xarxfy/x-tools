"""Maintenance windows, heartbeat jobs, automatic backups, update check."""

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conftest import csrf_headers
from test_monitor import TG_TOKEN, FakeTelegram, telegram  # noqa: F401  (fixture)


def notify_on(admin):
    admin.put("/api/settings/notifications", json={
        "enabled": True, "delay": 0, "recovery": True, "events": {"port": True, "job": True, "system": True},
        "telegram": {"enabled": True, "chat_id": "4242", "token": TG_TOKEN}}, headers=csrf_headers(admin))


# --- maintenance --------------------------------------------------------------------------


def test_maintenance_silences_alerts(admin, telegram):
    h = csrf_headers(admin)
    notify_on(admin)
    sid = admin.post("/api/services", json={"name": "Dead", "ports": [{"port": 1}]}, headers=h).json()["id"]
    other = admin.post("/api/services", json={"name": "Other", "ports": [{"port": 2}]}, headers=h).json()["id"]
    r = admin.post("/api/maintenance", json={"scope": "service", "target": sid, "minutes": 60, "reason": "update"}, headers=h)
    assert r.status_code == 201 and r.json()["label"] == "Dead"
    from app.monitor.alerts import check_alerts
    sent = check_alerts()
    assert sent and "port 2" in sent["body"] and "port 1" not in sent["body"]
    issues = {i["key"]: i for i in admin.get("/api/overview").json()["issues"]}
    assert issues[f"port:{sid}:1"]["paused"] is True and not issues[f"port:{other}:2"].get("paused")
    # while paused: no recovery message when the problem disappears
    admin.delete(f"/api/services/{sid}", headers=h)
    assert check_alerts() is None
    # unknown target, viewer cannot create, window can be ended
    assert admin.post("/api/maintenance", json={"scope": "agent", "target": "nope", "minutes": 5}, headers=h).status_code == 422
    wid = admin.get("/api/maintenance").json()[0]["id"]
    assert admin.delete(f"/api/maintenance/{wid}", headers=h).status_code == 204
    assert admin.get("/api/maintenance").json() == []


def test_maintenance_all_and_after_window(admin, telegram):
    h = csrf_headers(admin)
    notify_on(admin)
    admin.post("/api/services", json={"name": "Dead", "ports": [{"port": 1}]}, headers=h)
    wid = admin.post("/api/maintenance", json={"scope": "all", "minutes": 30}, headers=h).json()["id"]
    from app.monitor.alerts import check_alerts
    assert check_alerts() is None  # nothing sent during the window
    admin.delete(f"/api/maintenance/{wid}", headers=h)
    sent = check_alerts()  # window over: the still existing problem is reported
    assert sent and "port 1" in sent["body"]


# --- jobs --------------------------------------------------------------------------------------


def test_jobs(admin, telegram):
    h = csrf_headers(admin)
    notify_on(admin)
    job = admin.post("/api/jobs", json={"name": "Nightly backup", "interval_minutes": 60, "grace_minutes": 10}, headers=h).json()
    assert job["state"] == "waiting" and len(job["token"]) >= 20
    anon = type(admin)(admin.app)
    assert anon.get(f"/api/heartbeat/{job['token']}").json()["job"] == "Nightly backup"
    assert anon.get("/api/heartbeat/" + "x" * 30).status_code == 404
    assert admin.get("/api/jobs").json()[0]["state"] == "ok"

    from app.core.db import session_scope
    from app.models import Heartbeat
    with session_scope() as db:  # pretend the last success was 2 hours ago
        beat = db.get(Heartbeat, job["id"])
        beat.last_ok_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()
    assert admin.get("/api/jobs").json()[0]["state"] == "late"
    from app.monitor.alerts import check_alerts
    sent = check_alerts()
    assert sent and "Nightly backup" in sent["body"] and "did not report" in sent["body"]
    anon.get(f"/api/heartbeat/{job['token']}")  # it runs again
    assert "back to normal" in check_alerts()["title"]
    anon.get(f"/api/heartbeat/{job['token']}/fail")
    assert admin.get("/api/jobs").json()[0]["state"] == "fail"
    assert "reported a failure" in check_alerts()["body"]
    # paused jobs are quiet; the token changes on request
    admin.put(f"/api/jobs/{job['id']}", json={"name": "Nightly backup", "interval_minutes": 60, "paused": True}, headers=h)
    assert admin.get("/api/jobs").json()[0]["state"] == "paused"
    new = admin.post(f"/api/jobs/{job['id']}/new-token", headers=h).json()["token"]
    assert new != job["token"] and anon.get(f"/api/heartbeat/{job['token']}").status_code == 404


def test_job_token_hidden_from_viewer(admin):
    h = csrf_headers(admin)
    admin.post("/api/jobs", json={"name": "J", "interval_minutes": 60}, headers=h)
    admin.post("/api/users", json={"username": "view", "password": "correct horse battery", "role": "viewer"}, headers=h)
    admin.post("/api/auth/logout", headers=h)
    admin.post("/api/auth/login", json={"username": "view", "password": "correct horse battery"})
    assert admin.get("/api/jobs").json()[0]["token"] is None


# --- automatic backup ------------------------------------------------------------------------


def test_auto_backup(admin, tmp_path):
    h = csrf_headers(admin)
    folder = tmp_path / "backups"
    body = {"enabled": True, "frequency": "daily", "time": "03:00", "weekday": 0, "keep": 2,
            "passphrase": "a long passphrase", "locations": [{"name": "Disk", "type": "folder", "path": str(folder)}]}
    assert admin.put("/api/backup/auto", json={**body, "passphrase": None}, headers=h).status_code == 422
    assert admin.put("/api/backup/auto", json={**body, "locations": [{"name": "x", "type": "folder", "path": "../x"}]},
                     headers=h).status_code == 422
    r = admin.put("/api/backup/auto", json=body, headers=h)
    assert r.status_code == 200 and r.json()["has_passphrase"] and "a long passphrase" not in r.text
    assert b"a long passphrase" not in (tmp_path / "x-tools.db").read_bytes()

    from app.monitor import autobackup
    assert autobackup.is_due(autobackup.load())  # never ran
    for i in range(3):  # keeps the newest two
        now = datetime(2026, 11, 17, 3, 5, i, tzinfo=timezone.utc)
        assert autobackup.run(now)["ok"]
    files = sorted(p.name for p in folder.iterdir())
    assert files == ["x-tools-20261117-030501.xtb", "x-tools-20261117-030502.xtb"]
    # the file is a real backup with the stored passphrase
    from app.api.backup import read_backup
    assert "x-tools.db" in read_backup((folder / files[0]).read_bytes(), "a long passphrase")
    assert not autobackup.is_due(autobackup.load(), datetime.fromtimestamp(time.time(), timezone.utc))
    # a broken location is a problem in the list
    admin.put("/api/backup/auto", json={**body, "passphrase": None,
              "locations": [{"name": "Gone", "type": "folder", "path": "/proc/nope/x"}]}, headers=h)
    r = admin.post("/api/backup/auto/run", headers=h)
    assert r.json()["last"]["ok"] is False
    assert any(i["key"] == "backup:auto" for i in admin.get("/api/overview").json()["issues"])


def test_backup_schedule_math(monkeypatch, tmp_path):
    monkeypatch.setenv("XT_TIMEZONE", "UTC")
    from app.core import config
    config.get_settings.cache_clear()
    from app.monitor.autobackup import last_due
    now = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)  # a Tuesday
    assert last_due({"frequency": "daily", "time": "03:00"}, now) == datetime(2026, 11, 17, 3, 0, tzinfo=timezone.utc)
    assert last_due({"frequency": "daily", "time": "12:00"}, now) == datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
    assert last_due({"frequency": "weekly", "time": "03:00", "weekday": 6}, now) == datetime(2026, 11, 15, 3, 0, tzinfo=timezone.utc)


class FakeDav(BaseHTTPRequestHandler):
    got: dict = {}

    def log_message(self, *a):
        pass

    def do_PUT(self):
        FakeDav.got[self.path] = (self.headers.get("Authorization"), self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(201)
        self.end_headers()


def test_webdav_location(admin):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeDav)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    h = csrf_headers(admin)
    loc = {"name": "Cloud", "type": "webdav", "url": f"http://127.0.0.1:{server.server_port}/dav/x-tools",
           "username": "marc", "password": "app-pass-123"}
    r = admin.put("/api/backup/auto", json={"enabled": True, "frequency": "daily", "time": "03:00", "keep": 5,
                  "passphrase": "a long passphrase", "locations": [loc]}, headers=h)
    assert r.status_code == 200 and "app-pass-123" not in r.text and r.json()["locations"][0]["has_password"]
    assert admin.post("/api/backup/auto/run", headers=h).json()["last"]["ok"] is True
    server.shutdown()
    path, (auth, data) = next(iter(FakeDav.got.items()))
    assert path.startswith("/dav/x-tools/x-tools-") and auth.startswith("Basic ") and data.startswith(b"XTB1")


# --- update check ----------------------------------------------------------------------------


def test_versions():
    from app.monitor.updates import is_newer, newest
    assert newest(["v0.1.0", "v0.10.0", "v0.2.0", "nightly", "v0.10.0-beta.1"]) == "0.10.0"
    assert newest(["v1.0.0-rc.1", "v0.9.0"]) == "1.0.0-rc.1"
    assert is_newer("0.2.0", "0.1.0") and not is_newer("0.1.0", "0.1.0") and not is_newer("0.1.0-beta.1", "0.1.0")
    assert not is_newer(None) and not is_newer("garbage")


def test_update_endpoint(admin, monkeypatch):
    h = csrf_headers(admin)
    from app.monitor import updates
    monkeypatch.setattr(updates, "fetch_latest", lambda: "99.0.0")
    r = admin.post("/api/update/check", headers=h)
    assert r.status_code == 200 and r.json()["available"] and r.json()["latest"] == "99.0.0"
    monkeypatch.setenv("XT_UPDATE_CHECK", "false")
    from app.core import config
    config.get_settings.cache_clear()
    assert admin.post("/api/update/check", headers=h).status_code == 409
