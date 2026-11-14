import pytest
from fastapi.testclient import TestClient

from app.core import config, db, security


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A fresh app with its own empty data directory."""
    monkeypatch.setenv("XT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("XT_SECRET_KEY", "")
    monkeypatch.setenv("XT_MONITOR", "false")
    config.get_settings.cache_clear()
    db.reset_engine()
    security.reset_fernet()
    security.login_throttle.reset()

    from app.main import create_app

    with TestClient(create_app(), base_url="http://testserver") as c:
        yield c
    db.reset_engine()
    config.get_settings.cache_clear()


def csrf_headers(client) -> dict:
    return {"X-CSRF-Token": client.cookies.get("xt_csrf", "")}


@pytest.fixture()
def admin(client):
    """Client that has completed setup and is logged in."""
    r = client.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
    assert r.status_code == 200, r.text
    return client
