"""Every API route must refuse people without the right: not logged in (401) and a role without permissions (403)."""

import re

from fastapi.testclient import TestClient

from conftest import csrf_headers

# Routes that are public on purpose (or authenticate by themselves, e.g. with an agent key or a secret token).
PUBLIC = re.compile(r"^/api/(health|status|setup|auth/login|auth/login/2fa|heartbeat/.*|agent/.*)$")

# What a role WITHOUT any permission (viewer) may do: reading overviews, and managing its own account.
VIEWER_OK = re.compile("|".join([
    r"^/api/auth/.*", r"^/api/account.*", r"^/api/search$", r"^/api/inventory$", r"^/api/reports/pdf$", r"^/api/network$", r"^/api/overview$", r"^/api/features$", r"^/api/sitechecks$",
    r"^/api/services(/ports)?$", r"^/api/customers(/[^/]+)?$", r"^/api/customer-categories$", r"^/api/tags$", r"^/api/tickets(/[^/]+)?$", r"^/api/customers/[^/]+/journal$", r"^/api/docker$",
    r"^/api/agents$", r"^/api/agents/(?!keys$)[^/]+$", r"^/api/server-groups$", r"^/api/maintenance$", r"^/api/jobs$",
    r"^/api/history/.*", r"^/api/cloudflare$", r"^/api/sites$", r"^/api/sites/[^/]+/log$", r"^/api/services/uptime$",
    r"^/api/jobs/.*", r"^/api/status$", r"^/api/metrics.*", r"^/api/events.*", r"^/api/ports$", r"^/api/uptime.*",
]))


def routes(app):
    for r in app.routes:
        path = getattr(r, "path", "")
        if not path.startswith("/api/") or not getattr(r, "methods", None):
            continue
        for method in sorted(r.methods - {"HEAD", "OPTIONS"}):
            yield method, re.sub(r"\{[^}]+\}", "x1x1x1x1x1x1", path), path


def call(client, method, path, headers=None):
    return client.request(method, path, json={}, headers=headers or {})


def test_not_logged_in(admin):
    anon = TestClient(admin.app)
    failures = []
    for method, path, template in routes(admin.app):
        if PUBLIC.match(path):
            continue
        r = call(anon, method, path)
        if r.status_code != 401:
            failures.append(f"{method} {template} -> {r.status_code}")
    assert not failures, "\n".join(failures)


def test_role_without_permissions(admin):
    h = csrf_headers(admin)
    admin.post("/api/users", json={"username": "nobody1", "role": "viewer", "password": "user password 1"}, headers=h)
    c = TestClient(admin.app)
    assert c.post("/api/auth/login", json={"username": "nobody1", "password": "user password 1"}).status_code == 200
    hc = csrf_headers(c)
    failures = []
    for method, path, template in routes(admin.app):
        if PUBLIC.match(path):
            continue
        if path.startswith("/api/auth/") or path.startswith("/api/account"):
            continue  # own account: password, two-factor, logout
        if template == "/api/agents/{aid}/action":
            continue  # the permission depends on the action in the body; covered by test_agent_action_needs_the_right_permission
        r = call(c, method, path, hc)
        allowed_read = method == "GET" and VIEWER_OK.match(path)
        if allowed_read:
            if r.status_code == 403:
                failures.append(f"viewer should read {template}")
        elif r.status_code != 403:
            failures.append(f"{method} {template} -> {r.status_code} (expected 403 for a role without permissions)")
    assert not failures, "\n".join(failures)


def test_agent_action_needs_the_right_permission(admin):
    """The permission of /agents/{id}/action depends on the kind of action (docker, proxmox, servers)."""
    h = csrf_headers(admin)
    ag = admin.post("/api/agents", json={"name": "Perm1", "kind": "linux", "control": True}, headers=h).json()
    bodies = {"docker.restart": "docker.control", "proxmox.reboot": "proxmox.control", "systemd.restart": "servers.control",
              "system.reboot": "servers.control"}
    for action, needed in bodies.items():
        others = [p for p in ("docker.control", "proxmox.control", "servers.control") if p != needed]
        rid = admin.post("/api/roles", json={"name": f"only-{action}", "permissions": others}, headers=h).json()["id"]
        user = "u" + action.replace(".", "")
        admin.post("/api/users", json={"username": user, "role": rid, "password": "user password 1"}, headers=h)
        c = TestClient(admin.app)
        c.post("/api/auth/login", json={"username": user, "password": "user password 1"})
        r = c.post(f"/api/agents/{ag['id']}/action", json={"action": action, "target": "x"}, headers=csrf_headers(c))
        assert r.status_code == 403, (action, r.status_code)


def test_job_tokens_follow_the_permission(admin):
    """The secret heartbeat address is shown to roles with jobs.edit, not by the role's name."""
    h = csrf_headers(admin)
    admin.post("/api/jobs", json={"name": "Dump", "interval_minutes": 60, "grace_minutes": 5, "paused": False}, headers=h)
    def tokens(role_id, name):
        admin.post("/api/users", json={"username": name, "role": role_id, "password": "user password 1"}, headers=h)
        c = TestClient(admin.app)
        c.post("/api/auth/login", json={"username": name, "password": "user password 1"})
        return c.get("/api/jobs").json()[0]["token"]
    custom = admin.post("/api/roles", json={"name": "Cron", "permissions": ["jobs.edit"]}, headers=h).json()["id"]
    other = admin.post("/api/roles", json={"name": "Looker", "permissions": ["services.edit"]}, headers=h).json()["id"]
    assert tokens(custom, "cronuser") and tokens(other, "lookuser") is None and tokens("viewer", "viewuser") is None
    # an operator preset whose jobs.edit was taken away does not see it either
    ops = [r for r in admin.get("/api/roles").json()["roles"] if r["id"] == "operator"][0]
    admin.put("/api/roles/operator", json={"name": "Operator", "permissions": [p for p in ops["permissions"] if p != "jobs.edit"]}, headers=h)
    assert tokens("operator", "opsuser2") is None


def test_unknown_heartbeat_addresses_are_throttled(admin):
    from app.core.security import login_throttle
    login_throttle.reset()
    anon = TestClient(admin.app)
    codes = [anon.get("/api/heartbeat/" + "x" * 24 + str(i)).status_code for i in range(8)]
    assert codes[:5] == [404] * 5 and codes[5:] == [429] * 3
    # a known address still works while the client is throttled
    h = csrf_headers(admin)
    admin.post("/api/jobs", json={"name": "Dump", "interval_minutes": 60, "grace_minutes": 5, "paused": False}, headers=h)
    token = admin.get("/api/jobs").json()[0]["token"]
    assert anon.get(f"/api/heartbeat/{token}").status_code == 200
    login_throttle.reset()
