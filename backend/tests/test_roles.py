"""Custom roles with free permissions."""

from fastapi.testclient import TestClient

from conftest import csrf_headers


def login(admin, name, role, password="user password 1"):
    h = csrf_headers(admin)
    r = admin.post("/api/users", json={"username": name, "role": role, "password": password}, headers=h)
    assert r.status_code == 201, r.text
    c = TestClient(admin.app)
    assert c.post("/api/auth/login", json={"username": name, "password": password}).status_code == 200
    return c


def test_builtin_roles(admin):
    data = admin.get("/api/roles").json()
    roles = {r["id"]: r for r in data["roles"]}
    assert set(roles) == {"viewer", "operator", "admin"} and all(r["builtin"] for r in roles.values())
    assert roles["viewer"]["permissions"] == []
    assert "services.edit" in roles["operator"]["permissions"] and "admin.users" not in roles["operator"]["permissions"]
    assert "servers.manage" not in roles["operator"]["permissions"]
    assert set(roles["admin"]["permissions"]) == {p["key"] for p in data["permissions"]} and roles["admin"]["locked"]
    me = admin.get("/api/auth/me").json()
    assert "admin.roles" in me["permissions"]


def test_role_crud_and_protection(admin):
    h = csrf_headers(admin)
    r = admin.post("/api/roles", json={"name": "Support", "permissions": ["services.edit", "docker.control"]}, headers=h)
    assert r.status_code == 201 and r.json()["permissions"] == ["docker.control", "services.edit"]
    rid = r.json()["id"]
    assert admin.post("/api/roles", json={"name": "support", "permissions": []}, headers=h).status_code == 409
    assert admin.post("/api/roles", json={"name": "X", "permissions": ["root.everything"]}, headers=h).status_code == 422
    assert admin.put(f"/api/roles/{rid}", json={"name": "Support L1", "permissions": ["services.edit"]}, headers=h).json()["name"] == "Support L1"
    assert admin.put("/api/roles/admin", json={"name": "Administrator", "permissions": []}, headers=h).status_code == 409
    assert admin.put("/api/roles/viewer", json={"name": "Guest", "permissions": []}, headers=h).status_code == 409  # name
    assert admin.put("/api/roles/viewer", json={"name": "Viewer", "permissions": ["services.edit"]}, headers=h).status_code == 200
    assert admin.delete("/api/roles/viewer", headers=h).status_code == 409
    # a role in use cannot be deleted
    admin.post("/api/users", json={"username": "sam", "role": rid, "password": "user password 1"}, headers=h)
    assert admin.delete(f"/api/roles/{rid}", headers=h).status_code == 409
    uid = [u["id"] for u in admin.get("/api/users").json() if u["username"] == "sam"][0]
    admin.put(f"/api/users/{uid}", json={"role": "viewer"}, headers=h)
    assert admin.delete(f"/api/roles/{rid}", headers=h).status_code == 204


def test_permissions_are_enforced(admin):
    h = csrf_headers(admin)
    rid = admin.post("/api/roles", json={"name": "Shop", "permissions": ["services.edit"]}, headers=h).json()["id"]
    c = login(admin, "shopper", rid)
    hc = csrf_headers(c)
    assert c.post("/api/services", json={"name": "Blog"}, headers=hc).status_code == 201     # allowed
    assert c.post("/api/customers", json={"name": "ACME"}, headers=hc).status_code == 403    # not allowed
    assert c.get("/api/users").status_code == 403 and c.get("/api/roles").status_code == 403
    assert c.get("/api/audit").status_code == 403
    sid = c.get("/api/services").json()[0]["id"]
    assert c.get(f"/api/services/{sid}/credentials").status_code == 403                      # credentials.manage missing
    # give the role one more permission: effective at once
    admin.put(f"/api/roles/{rid}", json={"name": "Shop", "permissions": ["services.edit", "customers.edit"]}, headers=h)
    assert c.post("/api/customers", json={"name": "ACME"}, headers=hc).status_code == 201
    assert c.get("/api/auth/me").json()["permissions"] == ["customers.edit", "services.edit"]


def test_no_escalation(admin):
    h = csrf_headers(admin)
    # a user manager without the role editor cannot hand out roles with more rights than they have
    rid = admin.post("/api/roles", json={"name": "HR", "permissions": ["admin.users"]}, headers=h).json()["id"]
    hr = login(admin, "hruser", rid)
    hh = csrf_headers(hr)
    assert hr.post("/api/users", json={"username": "evil", "role": "admin", "password": "user password 1"}, headers=hh).status_code == 403
    assert hr.post("/api/users", json={"username": "okuser", "role": "viewer", "password": "user password 1"}, headers=hh).status_code == 201
    assert hr.post("/api/roles", json={"name": "Mine", "permissions": []}, headers=hh).status_code == 403  # admin.roles missing
    # a role editor cannot grant what they do not have
    rid2 = admin.post("/api/roles", json={"name": "Roles", "permissions": ["admin.roles", "admin.users"]}, headers=h).json()["id"]
    editor = login(admin, "editor", rid2)
    he = csrf_headers(editor)
    assert editor.post("/api/roles", json={"name": "Big", "permissions": ["admin.backup"]}, headers=he).status_code == 403
    assert editor.post("/api/roles", json={"name": "Small", "permissions": ["admin.users"]}, headers=he).status_code == 201


def test_last_user_manager_stays(admin):
    h = csrf_headers(admin)
    rid = admin.post("/api/roles", json={"name": "HR", "permissions": ["admin.users", "admin.roles"]}, headers=h).json()["id"]
    me = admin.get("/api/auth/me").json()
    # make the built-in admin a normal user manager through the custom role: demoting is fine while another exists
    other = login(admin, "hruser", rid)
    assert admin.put(f"/api/users/{me['id']}", json={"role": "viewer"}, headers=h).status_code == 200
    ho = csrf_headers(other)
    # `hr` is now the only user manager: cannot remove the right from its own role
    assert other.put(f"/api/roles/{rid}", json={"name": "HR", "permissions": ["admin.roles"]}, headers=ho).status_code == 409
    assert other.get("/api/roles").status_code == 200
