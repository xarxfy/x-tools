from conftest import csrf_headers

PASSWORD = "correct horse battery"


def test_status_before_and_after_setup(client):
    assert client.get("/api/status").json()["needs_setup"] is True
    client.post("/api/setup", json={"username": "admin", "password": PASSWORD})
    assert client.get("/api/status").json()["needs_setup"] is False


def test_setup_creates_admin_and_logs_in(client):
    r = client.post("/api/setup", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 200
    assert r.json() == {"id": 1, "username": "admin", "role": "admin"}
    assert client.get("/api/auth/me").json()["username"] == "admin"


def test_setup_only_once(admin):
    r = admin.post("/api/setup", json={"username": "second", "password": PASSWORD})
    assert r.status_code == 409


def test_setup_rejects_short_password_and_bad_username(client):
    assert client.post("/api/setup", json={"username": "admin", "password": "short"}).status_code == 422
    assert client.post("/api/setup", json={"username": "a b", "password": PASSWORD}).status_code == 422
    assert client.get("/api/status").json()["needs_setup"] is True


def test_me_requires_login(client):
    assert client.get("/api/auth/me").status_code == 401


def test_login_logout(admin):
    admin.cookies.clear()
    assert admin.get("/api/auth/me").status_code == 401
    r = admin.post("/api/auth/login", json={"username": "ADMIN", "password": PASSWORD})
    assert r.status_code == 200
    assert admin.get("/api/auth/me").status_code == 200
    assert admin.post("/api/auth/logout", headers=csrf_headers(admin)).status_code == 204
    assert admin.get("/api/auth/me").status_code == 401


def test_session_cookie_flags(client):
    r = client.post("/api/setup", json={"username": "admin", "password": PASSWORD})
    cookies = r.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith("xt_session="))
    csrf = next(c for c in cookies if c.startswith("xt_csrf="))
    assert "HttpOnly" in session and "SameSite=lax" in session
    assert "HttpOnly" not in csrf


def test_wrong_password(admin):
    admin.cookies.clear()
    r = admin.post("/api/auth/login", json={"username": "admin", "password": "wrong password"})
    assert r.status_code == 401


def test_login_throttle(admin):
    admin.cookies.clear()
    for _ in range(5):
        assert admin.post("/api/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401
    r = admin.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


def test_state_changing_request_needs_csrf_token(admin):
    assert admin.post("/api/auth/logout").status_code == 403
    assert admin.post("/api/auth/logout", headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert admin.get("/api/auth/me").status_code == 200  # still logged in


def test_session_token_is_stored_hashed(admin, tmp_path):
    import sqlite3
    token = admin.cookies.get("xt_session")
    rows = sqlite3.connect(tmp_path / "x-tools.db").execute("select token_hash from sessions").fetchall()
    assert rows and all(token not in r[0] for r in rows)


def test_secret_key_generated_with_safe_permissions(client, tmp_path):
    key_file = tmp_path / "secret.key"
    assert key_file.exists()
    assert oct(key_file.stat().st_mode & 0o777) == "0o600"


def test_security_headers(client):
    r = client.get("/api/status")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"


def test_unknown_api_path_is_json_404(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json()["detail"] == "Not found"
