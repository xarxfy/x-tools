from datetime import date, timedelta

from conftest import csrf_headers
from test_roles import login


def make(admin, **extra):
    body = {"name": "ACME", "contacts": [{"name": "Eva", "role": "Technik", "email": "eva@acme.test"},
                                          {"name": "Bob", "role": "Rechnung"}], **extra}
    r = admin.post("/api/customers", json=body, headers=csrf_headers(admin))
    assert r.status_code == 201, r.text
    return r.json()


def test_contacts_are_kept_unless_sent(admin):
    c = make(admin)
    assert [p["name"] for p in c["contacts"]] == ["Eva", "Bob"]
    h = csrf_headers(admin)
    r = admin.put(f"/api/customers/{c['id']}", json={"name": "ACME 2"}, headers=h).json()
    assert r["name"] == "ACME 2" and len(r["contacts"]) == 2  # not sent → unchanged
    r = admin.put(f"/api/customers/{c['id']}", json={"name": "ACME 2", "contacts": [{"name": "Zed"}]}, headers=h).json()
    assert [p["name"] for p in r["contacts"]] == ["Zed"]


def test_contract_data_needs_its_permission(admin):
    end = date.today() + timedelta(days=90)
    c = make(admin, contract={"contract_end": end.isoformat(), "notice_days": 30, "support_hours": "Mo-Fr 9-17", "response_time": "4h"})
    assert c["contract"]["deadline"] == (end - timedelta(days=30)).isoformat() and c["contract"]["response_time"] == "4h"
    h = csrf_headers(admin)
    admin.post("/api/roles", json={"name": "Customers", "permissions": ["customers.edit"]}, headers=h)
    rid = [r["id"] for r in admin.get("/api/roles").json()["roles"] if r["name"] == "Customers"][0]
    user = login(admin, "kim", rid)
    seen = user.get(f"/api/customers/{c['id']}").json()
    assert seen["contract"] is None and "contract" not in str(user.get("/api/customers").json()).replace("'contract': None", "")
    # without the permission an edit leaves the contract alone
    uh = csrf_headers(user)
    r = user.put(f"/api/customers/{c['id']}", json={"name": "ACME", "contract": {"support_hours": "never"}}, headers=uh)
    assert r.status_code == 200 and r.json()["contract"] is None
    assert admin.get(f"/api/customers/{c['id']}").json()["contract"]["support_hours"] == "Mo-Fr 9-17"
    assert user.get("/api/overview").json()["customer_todos"] == []


def test_tasks(admin):
    c = make(admin)
    h = csrf_headers(admin)
    t = admin.post(f"/api/customers/{c['id']}/tasks", json={"title": "Renew certificate", "due": "2026-12-01"}, headers=h)
    assert t.status_code == 201
    tid = t.json()["id"]
    assert admin.put(f"/api/customer-tasks/{tid}", json={"title": "Renew certificate", "due": "2026-12-01", "done": True}, headers=h).json()["done"]
    got = admin.get(f"/api/customers/{c['id']}").json()["tasks"]
    assert got == [{"id": tid, "title": "Renew certificate", "due": "2026-12-01", "done": True}]
    assert admin.delete(f"/api/customer-tasks/{tid}", headers=h).status_code == 204
    assert admin.delete(f"/api/customer-tasks/{tid}", headers=h).status_code == 404
    assert admin.post("/api/customers/nope/tasks", json={"title": "x"}, headers=h).status_code == 404


def test_assign_servers_and_jobs(admin):
    h = csrf_headers(admin)
    ag = admin.post("/api/agents", json={"name": "web-01", "kind": "linux"}, headers=h).json()
    job = admin.post("/api/jobs", json={"name": "Backup", "interval_minutes": 60, "grace_minutes": 5}, headers=h).json()
    c = make(admin, agent_ids=[ag["id"]], job_ids=[job["id"]])
    assert c["agent_ids"] == [ag["id"]] and c["job_ids"] == [job["id"]]
    other = make(admin, agent_ids=[ag["id"]])  # moves to the other customer
    assert admin.get(f"/api/customers/{c['id']}").json()["agent_ids"] == [] and other["agent_ids"] == [ag["id"]]
    assert admin.put(f"/api/customers/{c['id']}", json={"name": "ACME", "agent_ids": ["nope"]}, headers=h).status_code == 422
    r = admin.get(f"/api/reports/pdf?customer={other['id']}&services=false")
    assert r.status_code == 200 and b"web-01" in r.content


def test_overview_shows_deadlines_and_tasks(admin):
    h = csrf_headers(admin)
    soon = date.today() + timedelta(days=40)
    c = make(admin, contract={"contract_end": soon.isoformat(), "notice_days": 10})
    admin.post(f"/api/customers/{c['id']}/tasks", json={"title": "Call back", "due": (date.today() - timedelta(days=2)).isoformat()}, headers=h)
    admin.post(f"/api/customers/{c['id']}/tasks", json={"title": "Far away", "due": (date.today() + timedelta(days=90)).isoformat()}, headers=h)
    todos = admin.get("/api/overview").json()["customer_todos"]
    kinds = {(t["kind"], t["level"]) for t in todos}
    assert ("task", "down") in kinds and ("contract", "warn") in kinds and len(todos) == 2


def test_migration_keeps_the_old_contact(tmp_path, monkeypatch):
    """An installation from before: the single contact becomes the first contact person, operators get the permission."""
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    from sqlalchemy import text

    from app.core import config, db

    monkeypatch.setenv("XT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("XT_MONITOR", "false")
    config.get_settings.cache_clear()
    db.reset_engine()
    here = Path(db.__file__).resolve().parents[1]
    cfg = Config()
    cfg.set_main_option("script_location", str(here / "migrations"))
    cfg.set_main_option("sqlalchemy.url", config.get_settings().database_url)
    db.get_engine()
    command.upgrade(cfg, "b4d5e6f7a8b9")
    with db.get_engine().begin() as c:
        c.execute(text("INSERT INTO customers (id, name, contact, email, phone, owner, agreements, notes, created_at) "
                       "VALUES ('c1', 'Old', 'Jane', 'j@x.test', '123', '', '', '', '2026-01-01'), "
                       "('c2', 'Empty', '', '', '', '', '', '', '2026-01-01')"))
    command.upgrade(cfg, "head")
    with db.get_engine().begin() as c:
        rows = c.execute(text("SELECT customer_id, name, email, phone FROM customer_contacts")).fetchall()
        assert [tuple(r) for r in rows] == [("c1", "Jane", "j@x.test", "123")]
        assert "customers.contracts" in c.execute(text("SELECT permissions FROM roles WHERE id='operator'")).scalar()
