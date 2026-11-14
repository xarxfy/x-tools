"""Cloudflare integration against a fake API."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest

from conftest import csrf_headers

TOKEN = "cf_test_token_1234567890abcdef"
TUNNEL = "11111111-2222-3333-4444-555555555555"
ROUTES = {
    "/zones": [{"id": "z1", "name": "example.com", "status": "active", "account": {"id": "acc1", "name": "Me"}}],
    "/zones/z1/dns_records": [
        {"type": "CNAME", "name": "app.example.com", "content": f"{TUNNEL}.cfargotunnel.com", "proxied": True},
        {"type": "CNAME", "name": "wrong.example.com", "content": f"{TUNNEL}.cfargotunnel.com", "proxied": True},
        {"type": "CNAME", "name": "orphan.example.com", "content": f"{TUNNEL}.cfargotunnel.com", "proxied": True},
        {"type": "A", "name": "example.com", "content": "203.0.113.5", "proxied": False},
    ],
    "/accounts/acc1/cfd_tunnel": [{"id": TUNNEL, "name": "home", "status": "healthy", "remote_config": True,
                                   "connections": [{}, {}]}],
    f"/accounts/acc1/cfd_tunnel/{TUNNEL}/configurations": {"config": {"ingress": [
        {"hostname": "app.example.com", "service": "http://localhost:3000"},
        {"hostname": "wrong.example.com", "service": "http://localhost:9999"},
        {"service": "http_status:404"}]}},
    "/accounts/acc1/access/apps": [{"name": "App login", "type": "self_hosted", "domain": "app.example.com",
                                    "self_hosted_domains": ["app.example.com"]}],
}


class FakeCF(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            body, code = {"success": False, "errors": [{"message": "Invalid API Token"}]}, 403
        else:
            result = ROUTES.get(urlparse(self.path).path)
            if result is None:
                body, code = {"success": False, "errors": [{"message": "not found"}]}, 404
            else:
                body, code = {"success": True, "result": result, "result_info": {"total_pages": 1}}, 200
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def cf(admin, monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeCF)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("XT_CLOUDFLARE_API", f"http://127.0.0.1:{server.server_port}")
    from app.core import config
    config.get_settings.cache_clear()
    yield admin
    server.shutdown()


def test_cloudflare(cf, tmp_path):
    h = csrf_headers(cf)
    assert cf.get("/api/features").json()["cloudflare"] is False
    assert cf.put("/api/cloudflare/settings", json={"token": "wrong_token_0123456789abcd"}, headers=h).status_code == 422
    r = cf.put("/api/cloudflare/settings", json={"token": TOKEN}, headers=h)
    assert r.status_code == 200 and r.json()["zones"] == 1, r.text
    assert cf.get("/api/features").json()["cloudflare"] is True
    assert TOKEN.encode() not in (tmp_path / "x-tools.db").read_bytes()

    cf.post("/api/services", json={"name": "App", "domains": ["app.example.com"], "ports": [{"port": 3000}]}, headers=h)
    cf.post("/api/services", json={"name": "Wrong", "domains": ["wrong.example.com"], "ports": [{"port": 4000}]},
            headers=h)
    cf.post("/api/services", json={"name": "Missing", "domains": ["missing.example.com"]}, headers=h)
    hosts = {r["hostname"]: r for r in cf.get("/api/cloudflare").json()["hosts"]}
    assert hosts["app.example.com"]["problems"] == []
    assert hosts["app.example.com"]["route"]["service"] == "http://localhost:3000"
    assert hosts["app.example.com"]["access"][0]["name"] == "App login"
    assert hosts["app.example.com"]["tunnel"]["name"] == "home"
    assert "port 9999" in hosts["wrong.example.com"]["problems"][0]
    assert "no route" in hosts["orphan.example.com"]["problems"][0]
    assert "without DNS record" in hosts["missing.example.com"]["problems"][0]

    issues = [i["text"] for i in cf.get("/api/overview").json()["issues"] if i["kind"] == "cloudflare"]
    assert any("wrong.example.com" in i for i in issues) and not any("orphan" in i for i in issues)

    assert cf.delete("/api/cloudflare/settings", headers=h).status_code == 204
    assert cf.get("/api/features").json()["cloudflare"] is False
    assert cf.get("/api/cloudflare").json() == {"configured": False, "snapshot": None, "hosts": []}


def test_foreign_domains_ignored(cf):
    h = csrf_headers(cf)
    cf.put("/api/cloudflare/settings", json={"token": TOKEN}, headers=h)
    cf.post("/api/services", json={"name": "Elsewhere", "domains": ["shop.other-registrar.net"]}, headers=h)
    hosts = [r["hostname"] for r in cf.get("/api/cloudflare").json()["hosts"]]
    assert "shop.other-registrar.net" not in hosts and "app.example.com" in hosts
