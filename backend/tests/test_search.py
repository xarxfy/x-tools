from fastapi.testclient import TestClient

from conftest import csrf_headers
from test_linux import REPORT


def find(admin, q):
    r = admin.get("/api/search", params={"q": q})
    assert r.status_code == 200
    return r.json()["results"]


def test_search(admin):
    h = csrf_headers(admin)
    admin.put("/api/features", json={"customers": True}, headers=h)
    admin.post("/api/services", json={"name": "Wiki", "domains": ["wiki.example.com"], "notes": "runs on the db host",
                                      "ports": [{"port": 8123, "label": "Web"}]}, headers=h)
    cust = admin.post("/api/customers", json={"name": "ACME Shop", "contacts": [{"name": "Anna", "email": "anna@acme-example.com"}]}, headers=h).json()
    admin.post("/api/jobs", json={"name": "Database dump", "interval_minutes": 60, "grace_minutes": 5, "paused": False}, headers=h)
    ag = admin.post("/api/agents", json={"name": "web-01", "kind": "linux"}, headers=h).json()
    TestClient(admin.app).post("/api/agent/report", json=REPORT, headers={"X-Agent-Key": ag["key"]})
    admin.post("/api/tags", json={"name": "Production"}, headers=h)
    admin.put(f"/api/agents/{ag['id']}/meta", json={"tags": ["Production"], "notes": "DB for ACME"}, headers=h)

    kinds = lambda q: {(r["type"], r["title"]) for r in find(admin, q)}  # noqa: E731
    assert ("service", "Wiki") in kinds("wiki") and ("domain", "wiki.example.com") in kinds("wiki")
    assert ("service", "Wiki") in kinds("8123") and ("service", "Wiki") in kinds("db host")  # port, notes
    assert ("customer", "ACME Shop") in kinds("acme") and ("server", "web-01") in kinds("acme")  # server note
    assert ("job", "Database dump") in kinds("dump")
    assert ("tag", "#Production") in kinds("production") and ("server", "web-01") in kinds("production")
    assert ("customer", "ACME Shop") in kinds("anna@acme")
    first = find(admin, "web-01")[0]
    assert first["type"] == "server" and first["link"] == f"/servers/{ag['id']}"
    assert find(admin, "zzzz-nothing") == []
    assert admin.get("/api/search", params={"q": ""}).status_code == 422
    # customers are hidden while the area is switched off
    admin.put("/api/features", json={"customers": False}, headers=h)
    assert not [r for r in find(admin, "acme") if r["type"] == "customer"]
    # not logged in
    assert TestClient(admin.app).get("/api/search", params={"q": "x"}).status_code == 401
