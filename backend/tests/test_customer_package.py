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
    assert user.get("/api/overview").json()["customer_todos"] == []  # no contract right: no contract hint


def test_tickets_and_journal(admin):
    c = make(admin)
    h = csrf_headers(admin)
    t = admin.post(f"/api/customers/{c['id']}/tickets", json={"title": "Renew certificate", "due": "2026-12-01", "priority": "high"}, headers=h)
    assert t.status_code == 201 and t.json()["number"] == 1 and t.json()["status"] == "open"
    tid = t.json()["id"]
    assert admin.post(f"/api/customers/{c['id']}/tickets", json={"title": "Second"}, headers=h).json()["number"] == 2
    me = admin.get("/api/tickets/assignees").json()[0]
    body = {"title": "Renew certificate", "due": "2026-12-01", "priority": "urgent", "status": "progress", "assignee_id": me["id"], "description": "ACME shop"}
    r = admin.put(f"/api/tickets/{tid}", json=body, headers=h)
    assert r.status_code == 200 and r.json()["assignee"] == me["username"] and r.json()["status"] == "progress"
    assert admin.post(f"/api/tickets/{tid}/comments", json={"text": "Called the customer"}, headers=h).status_code == 201
    full = admin.get(f"/api/tickets/{tid}").json()
    assert [e["kind"] for e in full["entries"]] == ["event", "event", "event", "event", "note"]  # created, status, priority, assignee, comment
    # free notes and the timeline of the customer (newest first, ticket entries included)
    assert admin.post(f"/api/customers/{c['id']}/journal", json={"text": "Phone call about the move"}, headers=h).status_code == 201
    entries = admin.get(f"/api/customers/{c['id']}/journal").json()
    assert entries[0]["text"] == "Phone call about the move" and entries[0]["ticket"] is None and len(entries) == 7
    assert [e["text"] for e in admin.get(f"/api/customers/{c['id']}/journal?q=called").json()] == ["Called the customer"]
    assert admin.delete(f"/api/journal/{entries[0]['id']}", headers=h).status_code == 204
    event = [e for e in entries if e["kind"] == "event"][0]
    assert admin.delete(f"/api/journal/{event['id']}", headers=h).status_code == 404  # the log of changes stays
    # list: open only by default, urgent first
    assert [x["number"] for x in admin.get("/api/tickets").json()] == [1, 2]
    admin.put(f"/api/tickets/{tid}", json={**body, "status": "done"}, headers=h)
    assert [x["number"] for x in admin.get("/api/tickets").json()] == [2]
    assert [x["number"] for x in admin.get("/api/tickets?status=all").json()][0] == 2
    assert admin.get(f"/api/customers/{c['id']}").json()["tickets_open"] == 1
    assert admin.put(f"/api/tickets/{tid}", json={**body, "status": "bogus"}, headers=h).status_code == 422
    assert admin.put(f"/api/tickets/{tid}", json={**body, "assignee_id": 9999}, headers=h).status_code == 422
    assert admin.delete(f"/api/tickets/{tid}", headers=h).status_code == 204
    assert admin.get(f"/api/tickets/{tid}").status_code == 404
    assert admin.post("/api/customers/nope/tickets", json={"title": "x"}, headers=h).status_code == 404


def test_ticket_permission(admin):
    c = make(admin)
    h = csrf_headers(admin)
    t = admin.post(f"/api/customers/{c['id']}/tickets", json={"title": "x"}, headers=h).json()
    admin.post("/api/roles", json={"name": "Reader", "permissions": ["customers.edit"]}, headers=h)
    rid = [r["id"] for r in admin.get("/api/roles").json()["roles"] if r["name"] == "Reader"][0]
    user = login(admin, "lee", rid)
    assert user.get("/api/tickets").status_code == 200 and user.get(f"/api/tickets/{t['id']}").status_code == 200
    uh = csrf_headers(user)
    assert user.post(f"/api/customers/{c['id']}/tickets", json={"title": "y"}, headers=uh).status_code == 403
    assert user.post(f"/api/tickets/{t['id']}/comments", json={"text": "y"}, headers=uh).status_code == 403
    assert user.post(f"/api/customers/{c['id']}/journal", json={"text": "free note"}, headers=uh).status_code == 201  # customers.edit


def test_links_and_tags(admin):
    h = csrf_headers(admin)
    for name in ("Hosting", "Shop"):
        admin.post("/api/tags", json={"name": name}, headers=h)
    c = make(admin, tags=["Hosting", "hosting", " Shop "], links=[{"title": "Contract", "url": "https://files.example.org/c.pdf"}])
    assert c["tags"] == ["Hosting", "Shop"] and c["links"][0]["title"] == "Contract"
    bad = admin.put(f"/api/customers/{c['id']}", json={"name": "ACME", "links": [{"title": "x", "url": "javascript:alert(1)"}]}, headers=h)
    assert bad.status_code == 422
    assert admin.put(f"/api/customers/{c['id']}", json={"name": "ACME", "tags": ["Shop"]}, headers=h).json()["links"][0]["title"] == "Contract"  # not sent: kept
    assert admin.put(f"/api/customers/{c['id']}", json={"name": "ACME", "tags": ["Unlisted"]}, headers=h).status_code == 422


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


def test_overview_shows_deadlines_and_tickets(admin):
    h = csrf_headers(admin)
    soon = date.today() + timedelta(days=40)
    c = make(admin, contract={"contract_end": soon.isoformat(), "notice_days": 10})
    cid = c["id"]
    new = lambda **kw: admin.post(f"/api/customers/{cid}/tickets", json=kw, headers=h)  # noqa: E731
    new(title="Call back", due=(date.today() - timedelta(days=2)).isoformat())
    new(title="Far away", due=(date.today() + timedelta(days=90)).isoformat())
    new(title="Server on fire", priority="urgent")
    todos = admin.get("/api/overview").json()["customer_todos"]
    kinds = sorted((t["kind"], t["level"]) for t in todos)
    assert kinds == [("contract", "warn"), ("ticket", "down"), ("ticket", "warn")] and len(todos) == 3


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


def test_migration_turns_tasks_into_tickets(tmp_path, monkeypatch):
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
    command.upgrade(cfg, "c5e6f7a8b9c0")
    with db.get_engine().begin() as c:
        c.execute(text("INSERT INTO customers (id, name, owner, agreements, notes, created_at) VALUES ('c1', 'Old', '', '', '', '2026-01-01')"))
        c.execute(text("INSERT INTO customer_tasks (id, customer_id, title, due, done, created_at) VALUES "
                       "('t1', 'c1', 'First', '2026-12-01', 0, '2026-02-01'), ('t2', 'c1', 'Second', NULL, 1, '2026-03-01')"))
    command.upgrade(cfg, "head")
    with db.get_engine().begin() as c:
        rows = c.execute(text("SELECT number, title, status, due FROM tickets ORDER BY number")).fetchall()
        assert [tuple(r) for r in rows] == [(1, "First", "open", "2026-12-01"), (2, "Second", "done", None)]
        assert "tickets.edit" in c.execute(text("SELECT permissions FROM roles WHERE id='operator'")).scalar()
