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
    writes: list = []

    def log_message(self, *args):
        pass

    def _write(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else None
        path = urlparse(self.path).path
        FakeCF.writes.append((self.command, path, body))
        if self.command == "PUT" and path.endswith("/configurations"):
            ROUTES[path] = body
        elif path.startswith("/zones/z1/dns_records"):
            records = ROUTES["/zones/z1/dns_records"]
            if self.command == "POST":
                records.append({**body, "id": f"r{len(records) + 1}"})
            elif self.command == "DELETE":
                ROUTES["/zones/z1/dns_records"] = [r for r in records if r.get("id") != path.rsplit("/", 1)[1]]
        data = json.dumps({"success": True, "result": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_POST = do_PUT = do_DELETE = _write

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
    assert cf.get("/api/cloudflare").json() == {"configured": False, "allow_write": False, "snapshot": None,
                                                "hosts": []}


def test_foreign_domains_ignored(cf):
    h = csrf_headers(cf)
    cf.put("/api/cloudflare/settings", json={"token": TOKEN}, headers=h)
    cf.post("/api/services", json={"name": "Elsewhere", "domains": ["shop.other-registrar.net"]}, headers=h)
    hosts = [r["hostname"] for r in cf.get("/api/cloudflare").json()["hosts"]]
    assert "shop.other-registrar.net" not in hosts and "app.example.com" in hosts


def test_cloudflare_changes(cf):
    import copy
    saved = copy.deepcopy(ROUTES)
    FakeCF.writes = []
    try:
        h = csrf_headers(cf)
        cf.put("/api/cloudflare/settings", json={"token": TOKEN}, headers=h)
        route = {"tunnel_id": TUNNEL, "hostname": "new.example.com", "service": "http://localhost:8200"}
        assert cf.post("/api/cloudflare/routes", json=route, headers=h).status_code == 409  # read-only by default
        assert cf.put("/api/cloudflare/settings/write", json={"allow_write": True}, headers=h).json()["allow_write"]

        assert cf.post("/api/cloudflare/routes", json={**route, "service": "rm -rf /"}, headers=h).status_code == 422
        assert cf.post("/api/cloudflare/routes", json=route, headers=h).status_code == 200
        config_put = next(w for w in FakeCF.writes if w[0] == "PUT")
        ingress = config_put[2]["config"]["ingress"]
        assert ingress[-1] == {"service": "http_status:404"}  # catch-all stays last
        assert {"hostname": "new.example.com", "service": "http://localhost:8200"} in ingress
        dns = next(w for w in FakeCF.writes if w[0] == "POST")
        assert dns[2] == {"type": "CNAME", "name": "new.example.com", "content": f"{TUNNEL}.cfargotunnel.com",
                          "ttl": 1, "proxied": True}
        hosts = {r["hostname"]: r for r in cf.get("/api/cloudflare").json()["hosts"]}
        assert hosts["new.example.com"]["problems"] == []

        # DNS record outside the zone is refused, inside works; delete
        rec = {"zone_id": "z1", "type": "TXT", "name": "x.other.org", "content": "hello"}
        assert cf.post("/api/cloudflare/dns", json=rec, headers=h).status_code == 502
        assert cf.post("/api/cloudflare/dns", json={**rec, "name": "x.example.com"}, headers=h).status_code == 200
        rid = next(r["id"] for r in ROUTES["/zones/z1/dns_records"] if r.get("name") == "x.example.com")
        assert cf.delete(f"/api/cloudflare/dns/z1/{rid}", headers=h).status_code == 204

        assert cf.post("/api/cloudflare/routes/delete", json={**route, "dns": True}, headers=h).status_code == 200
        assert not any(r.get("name") == "new.example.com" for r in ROUTES["/zones/z1/dns_records"])
        actions = [a["action"] for a in cf.get("/api/audit").json()]
        assert {"cloudflare.route_saved", "cloudflare.dns_created", "cloudflare.dns_deleted",
                "cloudflare.route_deleted"} <= set(actions)
    finally:
        ROUTES.clear()
        ROUTES.update(saved)
