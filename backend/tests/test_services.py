import socket

from conftest import csrf_headers

SERVICE = {"name": " Website ", "domains": ["HTTPS://Example.com/", "example.com", ""],
           "ports": [{"port": 3000, "label": "Web"}], "folder": "~/site", "type": "Docker Compose", "notes": ""}


def test_requires_login(client):
    assert client.get("/api/services").status_code == 401
    assert client.get("/api/customers").status_code == 401


def test_service_crud(admin):
    h = csrf_headers(admin)
    assert admin.post("/api/services", json=SERVICE).status_code == 403  # CSRF
    r = admin.post("/api/services", json=SERVICE, headers=h)
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["name"] == "Website" and s["domains"] == ["example.com"] and s["credential_count"] == 0

    r = admin.put(f"/api/services/{s['id']}", json={**SERVICE, "name": "Site"}, headers=h)
    assert r.json()["name"] == "Site"
    assert [x["name"] for x in admin.get("/api/services").json()] == ["Site"]

    assert admin.post("/api/services", json={**SERVICE, "domains": ["bad domain"]}, headers=h).status_code == 422
    assert admin.post("/api/services", json={**SERVICE, "ports": [{"port": 70000}]}, headers=h).status_code == 422
    assert admin.post("/api/services", json={**SERVICE, "name": " "}, headers=h).status_code == 422
    assert admin.post("/api/services", json={**SERVICE, "customer_id": "nope"}, headers=h).status_code == 422

    assert admin.delete(f"/api/services/{s['id']}", headers=h).status_code == 204
    assert admin.get("/api/services").json() == []
    assert admin.delete(f"/api/services/{s['id']}", headers=h).status_code == 404


def test_credentials_encrypted(admin, tmp_path):
    h = csrf_headers(admin)
    sid = admin.post("/api/services", json=SERVICE, headers=h).json()["id"]
    assert admin.get(f"/api/services/{sid}/credentials").json() == []
    creds = [{"label": "Admin", "username": "root", "password": "very-secret-pw"}, {"label": ""}]
    r = admin.put(f"/api/services/{sid}/credentials", json=creds, headers=h)
    assert r.status_code == 200 and len(r.json()) == 1  # empty entries dropped
    assert admin.get("/api/services").json()[0]["credential_count"] == 1
    assert "very-secret-pw" not in admin.get("/api/services").text
    assert admin.get(f"/api/services/{sid}/credentials").json()[0]["password"] == "very-secret-pw"
    assert b"very-secret-pw" not in (tmp_path / "x-tools.db").read_bytes()

    assert admin.put(f"/api/services/{sid}/credentials", json=[{"label": "x"}] * 21, headers=h).status_code == 422
    admin.put(f"/api/services/{sid}/credentials", json=[], headers=h)
    assert admin.get("/api/services").json()[0]["credential_count"] == 0


def test_port_status(admin, monkeypatch):
    monkeypatch.setenv("XT_CHECK_HOST", "127.0.0.1")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    open_port = listener.getsockname()[1]
    h = csrf_headers(admin)
    admin.post("/api/services", json={**SERVICE, "ports": [{"port": open_port}, {"port": 1}]}, headers=h)
    admin.post("/api/services", json={**SERVICE, "name": "Remote", "host": "127.0.0.1",
                                      "ports": [{"port": open_port}]}, headers=h)
    status = admin.get("/api/services/ports").json()
    listener.close()
    assert status == {str(open_port): True, "1": False, f"127.0.0.1:{open_port}": True}
    assert admin.post("/api/services", json={**SERVICE, "host": "bad host;"}, headers=h).status_code == 422


def test_customers(admin):
    h = csrf_headers(admin)
    s1 = admin.post("/api/services", json=SERVICE, headers=h).json()["id"]
    s2 = admin.post("/api/services", json={**SERVICE, "name": "Shop"}, headers=h).json()["id"]
    r = admin.post("/api/customers", json={"name": "ACME", "email": "a@example.com", "service_ids": [s1]}, headers=h)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["service_ids"] == [s1]
    names = {s["name"]: s["customer_name"] for s in admin.get("/api/services").json()}
    assert names == {"Website": "ACME", "Shop": None}

    r = admin.put(f"/api/customers/{cid}", json={"name": "ACME Inc", "service_ids": [s2]}, headers=h)
    assert r.json()["service_ids"] == [s2]
    assert admin.post("/api/customers", json={"name": "X", "service_ids": ["unknown"]}, headers=h).status_code == 422

    assert admin.delete(f"/api/customers/{cid}", headers=h).status_code == 204
    assert all(s["customer_id"] is None for s in admin.get("/api/services").json())
    assert admin.get(f"/api/customers/{cid}").status_code == 404


def test_checklist(admin):
    h = csrf_headers(admin)
    items = [{"text": "Start the container", "done": False}, {"text": "Add tunnel route"}]
    s = admin.post("/api/services", json={**SERVICE, "checklist": items}, headers=h).json()
    assert [i["done"] for i in s["checklist"]] == [False, False]
    # normal edit without checklist keeps it
    s = admin.put(f"/api/services/{s['id']}", json={**SERVICE, "name": "Renamed"}, headers=h).json()
    assert len(s["checklist"]) == 2
    s = admin.put(f"/api/services/{s['id']}", json={**SERVICE, "checklist": [{**items[0], "done": True}]},
                  headers=h).json()
    assert s["checklist"] == [{"text": "Start the container", "done": True}]
