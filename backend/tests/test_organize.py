from conftest import csrf_headers
from test_roles import login


def test_central_tags(admin):
    h = csrf_headers(admin)
    web = admin.post("/api/tags", json={"name": "Web", "color": "blue"}, headers=h).json()
    shop = admin.post("/api/tags", json={"name": "Shop", "color": "teal"}, headers=h).json()
    assert admin.post("/api/tags", json={"name": "web"}, headers=h).status_code == 409
    assert admin.post("/api/tags", json={"name": "X", "color": "rainbow"}, headers=h).status_code == 422
    ag = admin.post("/api/agents", json={"name": "web-01", "kind": "linux"}, headers=h).json()
    c = admin.post("/api/customers", json={"name": "ACME", "tags": ["Web", "Shop"]}, headers=h).json()
    admin.put(f"/api/agents/{ag['id']}/meta", json={"tags": ["web"]}, headers=h)
    listed = {t["name"]: t for t in admin.get("/api/tags").json()}
    assert listed["Web"]["servers"] == 1 and listed["Web"]["customers"] == 1 and listed["Shop"]["customers"] == 1
    # rename changes it on servers and customers, colour is kept separately
    r = admin.put(f"/api/tags/{web['id']}", json={"name": "Website", "color": "green"}, headers=h).json()
    assert r["name"] == "Website" and r["color"] == "green" and r["servers"] == 1
    assert admin.get(f"/api/customers/{c['id']}").json()["tags"] == ["Website", "Shop"]
    assert [x for x in admin.get("/api/agents").json() if x["id"] == ag["id"]][0]["tags"] == ["Website"]
    # merge: everything with "Shop" gets "Website", no duplicate on the customer
    assert admin.post(f"/api/tags/{shop['id']}/merge", json={"into": shop["id"]}, headers=h).status_code == 422
    assert admin.post(f"/api/tags/{shop['id']}/merge", json={"into": web["id"]}, headers=h).status_code == 200
    assert admin.get(f"/api/customers/{c['id']}").json()["tags"] == ["Website"]
    assert [t["name"] for t in admin.get("/api/tags").json()] == ["Website"]
    # delete removes it from everything
    assert admin.delete(f"/api/tags/{web['id']}", headers=h).status_code == 204
    assert admin.get(f"/api/customers/{c['id']}").json()["tags"] == []
    assert [x for x in admin.get("/api/agents").json() if x["id"] == ag["id"]][0]["tags"] == []
    assert admin.delete(f"/api/tags/{web['id']}", headers=h).status_code == 404


def test_colours_of_categories_and_groups(admin):
    h = csrf_headers(admin)
    cat = admin.post("/api/customer-categories", json={"name": "A-customer", "color": "red"}, headers=h).json()
    grp = admin.post("/api/server-groups", json={"name": "Production", "color": "orange"}, headers=h).json()
    assert cat["color"] == "red" and grp["color"] == "orange"
    assert admin.put(f"/api/customer-categories/{cat['id']}", json={"name": "A", "color": "purple"}, headers=h).json()["color"] == "purple"
    assert admin.put(f"/api/server-groups/{grp['id']}", json={"name": "Prod", "color": "nope"}, headers=h).status_code == 422
    assert admin.get("/api/server-groups").json()[0]["color"] == "orange"


def test_only_the_organize_permission_changes_the_lists(admin):
    h = csrf_headers(admin)
    tag = admin.post("/api/tags", json={"name": "Web"}, headers=h).json()
    ops = login(admin, "olivia", "operator")  # an operator may pick, not manage
    oh = csrf_headers(ops)
    assert ops.get("/api/tags").status_code == 200
    for method, url, body in (("post", "/api/tags", {"name": "New"}), ("put", f"/api/tags/{tag['id']}", {"name": "Web2"}),
                              ("delete", f"/api/tags/{tag['id']}", None), ("post", "/api/customer-categories", {"name": "C"}),
                              ("post", "/api/server-groups", {"name": "G"})):
        assert getattr(ops, method)(url, headers=oh, **({"json": body} if body else {})).status_code == 403, url
    ag = admin.post("/api/agents", json={"name": "s1", "kind": "linux"}, headers=h).json()
    assert ops.put(f"/api/agents/{ag['id']}/meta", json={"tags": ["Web"]}, headers=oh).status_code == 200  # picking is fine
    assert ops.put(f"/api/agents/{ag['id']}/meta", json={"tags": ["Nope"]}, headers=oh).status_code == 422


def test_migration_builds_the_central_list(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    from app.core import config, db

    monkeypatch.setenv("XT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("XT_MONITOR", "false")
    config.get_settings.cache_clear()
    db.reset_engine()
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(db.__file__).resolve().parents[1] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", config.get_settings().database_url)
    db.get_engine()
    command.upgrade(cfg, "d6f7a8b9c0d1")
    with db.get_engine().begin() as c:
        c.execute(text("INSERT INTO agents (id, name, kind, key_hash, disabled, created_at, tags, notes) "
                       "VALUES ('a1', 'one', 'linux', 'x', 0, '2026-01-01', :t, '')"), {"t": json.dumps(["web", "Db", "WEB"])})
        c.execute(text("INSERT INTO customers (id, name, owner, agreements, notes, created_at, tags, support_hours, response_time) "
                       "VALUES ('c1', 'ACME', '', '', '', '2026-01-01', :t, '', '')"), {"t": json.dumps(["Web"])})
    command.upgrade(cfg, "head")
    with db.get_engine().begin() as c:
        names = sorted(r[0] for r in c.execute(text("SELECT name FROM tags")).fetchall())
        assert names == ["Db", "web"]  # one spelling per tag (the first one found)
        assert json.loads(c.execute(text("SELECT tags FROM agents")).scalar()) == ["web", "Db"]
        assert json.loads(c.execute(text("SELECT tags FROM customers")).scalar()) == ["web"]
