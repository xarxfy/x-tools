"""Agents, issues, notifications and website checks."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conftest import csrf_headers

TG_TOKEN = "123456:" + "A" * 35


def test_agents_and_reports(admin):
    h = csrf_headers(admin)
    r = admin.post("/api/agents", json={"name": "Home"}, headers=h)
    assert r.status_code == 201
    agent, key = r.json(), r.json()["key"]
    assert "key" not in admin.get("/api/agents").json()[0]
    assert admin.post("/api/agents", json={"name": "home"}, headers=h).status_code == 409

    admin.cookies.clear()  # agents have no session
    report = {"version": "1", "hostname": "pve", "system": {"cpus": 4},
              "docker": {"collectedAt": 1, "projects": [{"name": "p", "workingDir": "/x", "containers": []}],
                         "containers": []}}
    assert admin.post("/api/agent/report", json=report, headers={"X-Agent-Key": "wrong"}).status_code == 401
    r = admin.post("/api/agent/report", json=report, headers={"X-Agent-Key": key})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert admin.post("/api/agent/report", json=report, headers={"X-Agent-Key": key}).status_code == 429
    assert admin.get("/api/agents").status_code == 401

    admin.post("/api/auth/login", json={"username": "admin", "password": "correct horse battery"})
    h = csrf_headers(admin)
    detail = admin.get(f"/api/agents/{agent['id']}").json()
    assert detail["hostname"] == "pve"
    assert detail["report"]["docker"]["projects"][0]["working_dir"] == "/x"  # camelCase of old agents normalised

    admin.put(f"/api/agents/{agent['id']}", json={"disabled": True}, headers=h)
    admin.cookies.clear()
    assert admin.post("/api/agent/report", json=report, headers={"X-Agent-Key": key}).status_code == 403


def test_issues(admin):
    h = csrf_headers(admin)
    admin.post("/api/services", json={"name": "Dead", "ports": [{"port": 1, "label": "Web"}]}, headers=h)
    admin.post("/api/agents", json={"name": "Silent"}, headers=h)
    issues = admin.get("/api/overview").json()["issues"]
    texts = {i["key"]: i["text"] for i in issues}
    assert any(k.startswith("port:") and "port 1 (Web)" in v for k, v in texts.items())
    assert "docker:none" in texts
    assert any(k.startswith("agent:") for k in texts)


class FakeTelegram(BaseHTTPRequestHandler):
    sent: list = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeTelegram.sent.append((self.path, body))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')


@pytest.fixture()
def telegram(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeTelegram)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("XT_TELEGRAM_API", f"http://127.0.0.1:{server.server_port}")
    from app.core import config
    config.get_settings.cache_clear()
    FakeTelegram.sent = []
    yield FakeTelegram.sent
    server.shutdown()


def test_notification_settings(admin, telegram, tmp_path):
    h = csrf_headers(admin)
    base = {"enabled": True, "delay": 0, "recovery": True, "events": {"port": True},
            "telegram": {"enabled": True, "chat_id": "4242", "token": TG_TOKEN}, "ntfy": {}}
    assert admin.put("/api/settings/notifications", json={**base, "telegram": {"enabled": True, "chat_id": "x",
                     "token": TG_TOKEN}}, headers=h).status_code == 422
    r = admin.put("/api/settings/notifications", json=base, headers=h)
    assert r.status_code == 200, r.text
    got = admin.get("/api/settings/notifications").json()
    assert got["telegram"]["has_token"] and TG_TOKEN not in json.dumps(got)
    assert TG_TOKEN.encode() not in (tmp_path / "x-tools.db").read_bytes()
    # empty token field keeps the stored token
    admin.put("/api/settings/notifications", json={**base, "telegram": {"enabled": True, "chat_id": "4242"}}, headers=h)
    assert admin.post("/api/settings/notifications/test", json={"channel": "telegram"}, headers=h).status_code == 200
    path, body = telegram[-1]
    assert path == f"/bot{TG_TOKEN}/sendMessage" and body["chat_id"] == "4242"


def test_alert_flow(admin, telegram):
    h = csrf_headers(admin)
    admin.put("/api/settings/notifications", json={
        "enabled": True, "delay": 0, "recovery": True, "events": {"port": True},
        "telegram": {"enabled": True, "chat_id": "4242", "token": TG_TOKEN}}, headers=h)
    sid = admin.post("/api/services", json={"name": "Dead", "ports": [{"port": 1}]}, headers=h).json()["id"]
    from app.monitor.alerts import check_alerts
    sent = check_alerts()
    assert sent and "port 1" in sent["body"] and "docker" not in sent["body"].lower()  # docker events are off
    assert check_alerts() is None  # sent only once
    admin.delete(f"/api/services/{sid}", headers=h)
    solved = check_alerts()
    assert solved and "back to normal" in solved["title"]
    assert len(telegram) == 2


def test_sitechecks(admin, monkeypatch):
    h = csrf_headers(admin)
    sid = admin.post("/api/services", json={"name": "Shop", "domains": ["shop.example"]}, headers=h).json()["id"]
    cid = admin.post("/api/customers", json={"name": "ACME", "service_ids": [sid]}, headers=h).json()["id"]
    from app.monitor import sites
    monkeypatch.setattr(sites, "check_site", lambda d: {"level": "down", "label": "HTTP 502", "checked_at": 1})
    r = admin.post("/api/sitechecks", json={"customer_id": cid}, headers=h)
    assert r.json()["shop.example"]["label"] == "HTTP 502"
    issues = admin.get("/api/overview").json()["issues"]
    assert any(i["key"] == "site:shop.example" and i["link"] == f"/customers/{cid}" for i in issues)


def test_site_check_dns_failure():
    from app.monitor.sites import check_site
    result = check_site("does-not-exist.invalid")
    assert result["level"] == "down" and "DNS" in result["label"]


def test_agent_install(admin, tmp_path):
    import subprocess
    h = csrf_headers(admin)
    bad = admin.post("/api/agents", json={"name": "PVE", "proxmox_url": "https://10.0.0.2:8006"}, headers=h)
    assert bad.status_code == 422  # proxmox needs all three values
    bad = admin.post("/api/agents", json={"name": "PVE", "proxmox_url": "https://x';rm -rf /;'",
                                          "proxmox_token_id": "a", "proxmox_token_secret": "b"}, headers=h)
    assert bad.status_code == 422
    r = admin.post("/api/agents", json={"name": "PVE", "proxmox_url": "https://10.0.0.2:8006",
                                        "proxmox_token_id": "xtools@pve!agent",
                                        "proxmox_token_secret": "1111-2222-3333"}, headers=h)
    assert r.status_code == 201, r.text
    cmd = r.json()["install"]["command"]
    assert cmd.startswith("curl -fsSL 'http://testserver/api/agent/install/") and cmd.endswith("| sh")
    url = cmd.split("'")[1].replace("http://testserver", "")
    assert b"1111-2222-3333" not in (tmp_path / "x-tools.db").read_bytes()  # only encrypted, temporarily

    admin.cookies.clear()
    script = admin.get(url)
    assert script.status_code == 200
    text = script.text
    assert r.json()["key"] in text and "PROXMOX_TOKEN_SECRET=1111-2222-3333" in text and "__" not in text
    (tmp_path / "install.sh").write_text(text)
    assert subprocess.run(["sh", "-n", str(tmp_path / "install.sh")]).returncode == 0
    assert admin.get(url).status_code == 404  # one-time

    assert admin.get("/api/agent/bundle").status_code == 401
    bundle = admin.get("/api/agent/bundle", headers={"X-Agent-Key": r.json()["key"]})
    assert bundle.status_code == 200 and bundle.content[:2] == b"PK"

    # a new install command replaces the key
    admin.post("/api/auth/login", json={"username": "admin", "password": "correct horse battery"})
    r2 = admin.post(f"/api/agents/{r.json()['id']}/install", json={}, headers=csrf_headers(admin))
    assert r2.status_code == 200 and r2.json()["key"] != r.json()["key"]
    admin.cookies.clear()
    assert admin.get("/api/agent/bundle", headers={"X-Agent-Key": r.json()["key"]}).status_code == 401


def test_features(admin):
    h = csrf_headers(admin)
    assert admin.get("/api/features").json() == {"customers": False}
    admin.post("/api/customers", json={"name": "ACME"}, headers=h)
    assert admin.get("/api/features").json() == {"customers": True}  # undecided: on when customers exist
    admin.put("/api/features", json={"customers": False}, headers=h)
    assert admin.get("/api/features").json() == {"customers": False}
