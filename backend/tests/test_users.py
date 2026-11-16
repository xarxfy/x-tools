"""Users, roles and the audit log."""

from conftest import csrf_headers

PW = "correct horse battery"


def as_user(client, name, password="user password 1"):
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"username": name, "password": password})
    assert r.status_code == 200, r.text
    return csrf_headers(client)


def test_roles(admin):
    h = csrf_headers(admin)
    for name, role in (("olga", "operator"), ("vic", "viewer")):
        assert admin.post("/api/users", json={"username": name, "role": role, "password": "user password 1"},
                          headers=h).status_code == 201
    assert admin.post("/api/users", json={"username": "OLGA", "role": "viewer", "password": "user password 1"},
                      headers=h).status_code == 409
    assert admin.post("/api/users", json={"username": "x1", "role": "god", "password": "user password 1"},
                      headers=h).status_code == 422
    sid = admin.post("/api/services", json={"name": "Web"}, headers=h).json()["id"]
    admin.put(f"/api/services/{sid}/credentials", json=[{"label": "a", "password": "pw"}], headers=h)

    h = as_user(admin, "vic")
    assert admin.get("/api/services").status_code == 200
    assert admin.get("/api/overview").status_code == 200
    assert admin.get(f"/api/services/{sid}/credentials").status_code == 403
    assert admin.post("/api/services", json={"name": "X"}, headers=h).status_code == 403
    assert admin.post("/api/docker/logs", json={"container": "x"}, headers=h).status_code == 403
    assert admin.get("/api/users").status_code == 403
    assert admin.get("/api/settings/notifications").status_code == 403
    assert admin.post("/api/backup", json={"passphrase": "long enough pass"}, headers=h).status_code == 403

    h = as_user(admin, "olga")
    assert admin.get(f"/api/services/{sid}/credentials").status_code == 200
    assert admin.post("/api/services", json={"name": "X"}, headers=h).status_code == 201
    assert admin.post("/api/agents", json={"name": "A"}, headers=h).status_code == 201  # operators may add agents
    assert admin.get("/api/backup/auto").status_code == 403
    assert admin.put("/api/features", json={"customers": True}, headers=h).status_code == 403
    assert admin.get("/api/audit").status_code == 403


def test_user_management_rules(admin):
    h = csrf_headers(admin)
    me = admin.get("/api/auth/me").json()
    assert admin.put(f"/api/users/{me['id']}", json={"disabled": True}, headers=h).status_code == 409
    assert admin.put(f"/api/users/{me['id']}", json={"role": "viewer"}, headers=h).status_code == 409  # last admin
    assert admin.delete(f"/api/users/{me['id']}", headers=h).status_code == 409
    uid = admin.post("/api/users", json={"username": "bob", "role": "admin", "password": "user password 1"},
                     headers=h).json()["id"]
    assert admin.put(f"/api/users/{me['id']}", json={"role": "operator"}, headers=h).status_code == 200  # bob is admin

    # bob: disable → logged out and cannot log in; reset password works
    h = as_user(admin, "bob")
    assert admin.put(f"/api/users/{me['id']}", json={"role": "admin"}, headers=h).status_code == 200
    as_user(admin, "admin", PW)
    h = csrf_headers(admin)
    assert admin.put(f"/api/users/{uid}", json={"disabled": True}, headers=h).json()["disabled"]
    admin.cookies.clear()
    assert admin.post("/api/auth/login", json={"username": "bob", "password": "user password 1"}).status_code == 401
    h = as_user(admin, "admin", PW)
    admin.put(f"/api/users/{uid}", json={"disabled": False}, headers=h)
    assert admin.post(f"/api/users/{uid}/password", json={"password": "short"}, headers=h).status_code == 422
    assert admin.post(f"/api/users/{uid}/password", json={"password": "brand new pass"}, headers=h).status_code == 204
    as_user(admin, "bob", "brand new pass")
    h = as_user(admin, "admin", PW)
    assert admin.delete(f"/api/users/{uid}", headers=h).status_code == 204


def test_audit_log(admin):
    h = csrf_headers(admin)
    sid = admin.post("/api/services", json={"name": "Web"}, headers=h).json()["id"]
    admin.put(f"/api/services/{sid}/credentials", json=[{"label": "a", "password": "pw"}], headers=h)
    admin.get(f"/api/services/{sid}/credentials")
    admin.cookies.clear()
    admin.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    as_user(admin, "admin", PW)
    log = admin.get("/api/audit").json()
    actions = [a["action"] for a in log]
    assert actions[:6] == ["login", "login.failed", "credentials.viewed", "credentials.changed", "service.created",
                           "setup"]
    assert log[2]["username"] == "admin" and log[2]["target"] == "Web" and log[2]["ip"]
    assert "pw" not in str(log)
    assert [a["action"] for a in admin.get("/api/audit?action=login").json()] == ["login", "login.failed"]
    page = admin.get(f"/api/audit?before={log[1]['id']}&limit=2").json()
    assert [a["action"] for a in page] == ["credentials.viewed", "credentials.changed"]
    assert "service" in admin.get("/api/audit/actions").json()
