"""Commands for agents: queue, long-poll, results, permissions."""

import threading
import time

from fastapi.testclient import TestClient

from conftest import csrf_headers

REPORT = {"version": "3", "hostname": "pve", "control": True,
          "docker": {"collected_at": 1, "projects": [{"name": "p", "containers": [{"name": "web"}]}], "containers": []},
          "proxmox": {"guests": [{"vmid": 101, "node": "pve", "type": "lxc", "status": "running"}]}}


def setup_agent(admin, report):
    h = csrf_headers(admin)
    r = admin.post("/api/agents", json={"name": "PVE", "kind": "docker", "control": True}, headers=h).json()
    agent = TestClient(admin.app)
    assert agent.post("/api/agent/report", json=report, headers={"X-Agent-Key": r["key"]}).status_code == 200
    return r, agent


def fake_agent(agent, key, results, seen):
    commands = agent.get("/api/agent/commands?wait=10", headers={"X-Agent-Key": key}).json()
    for c in commands:
        seen.append(c)
        agent.post(f"/api/agent/commands/{c['id']}", json=results, headers={"X-Agent-Key": key})


def test_actions(admin):
    r, agent = setup_agent(admin, REPORT)
    h = csrf_headers(admin)
    seen = []
    t = threading.Thread(target=fake_agent, args=(agent, r["key"], {"ok": True}, seen))
    t.start()
    time.sleep(0.2)
    res = admin.post(f"/api/agents/{r['id']}/action", json={"action": "docker.restart", "target": "web"}, headers=h)
    t.join()
    assert res.status_code == 200, res.text
    assert seen[0]["action"] == "docker.restart" and seen[0]["target"] == "web"

    t = threading.Thread(target=fake_agent, args=(agent, r["key"], {"ok": False, "error": "HTTP 403"}, seen))
    t.start()
    time.sleep(0.2)
    res = admin.post(f"/api/agents/{r['id']}/action",
                     json={"action": "proxmox.shutdown", "target": "101", "node": "pve", "type": "lxc"}, headers=h)
    t.join()
    assert res.status_code == 424 and "403" in res.json()["detail"]
    assert seen[1]["params"] == {"node": "pve", "type": "lxc"}

    # validation before anything is queued
    bad = [{"action": "docker.rm", "target": "web"}, {"action": "docker.stop", "target": "ghost"},
           {"action": "proxmox.stop", "target": "999", "node": "pve", "type": "lxc"},
           {"action": "docker.stop", "target": "web;rm"}]
    for body in bad:
        assert admin.post(f"/api/agents/{r['id']}/action", json=body, headers=h).status_code == 422, body
    actions = [a["action"] for a in admin.get("/api/audit").json()]
    assert "docker.restart" in actions and "proxmox.shutdown" in actions


def test_control_off_and_roles(admin):
    r, agent = setup_agent(admin, {**REPORT, "control": False})
    h = csrf_headers(admin)
    assert admin.post(f"/api/agents/{r['id']}/action", json={"action": "docker.stop", "target": "web"},
                      headers=h).status_code == 409
    admin.post("/api/users", json={"username": "vic", "role": "viewer", "password": "viewer password"}, headers=h)
    admin.cookies.clear()
    admin.post("/api/auth/login", json={"username": "vic", "password": "viewer password"})
    assert admin.post(f"/api/agents/{r['id']}/action", json={"action": "docker.stop", "target": "web"},
                      headers=csrf_headers(admin)).status_code == 403
    assert agent.get("/api/agent/commands?wait=0", headers={"X-Agent-Key": "wrong"}).status_code == 401


def test_agent_execute_whitelist(monkeypatch):
    from app.collector import agent
    assert agent.execute({"action": "shell.run", "target": "x"})["ok"] is False
    monkeypatch.setenv("PROXMOX_URL", "https://127.0.0.1:1")
    res = agent.execute({"action": "proxmox.stop", "target": "101; rm", "params": {"node": "pve", "type": "lxc"}})
    assert res == {"ok": False, "error": "Invalid Proxmox command"}
    res = agent.execute({"action": "proxmox.stop", "target": "101", "params": {"node": "pve/../x", "type": "lxc"}})
    assert res["ok"] is False and "Invalid" in res["error"]


def test_install_command_control(admin):
    h = csrf_headers(admin)
    r = admin.post("/api/agents", json={"name": "C", "control": True}, headers=h).json()
    url = r["install"]["command"].split("'")[1].replace("http://testserver", "")
    admin.cookies.clear()
    assert "XT_AGENT_CONTROL=1" in admin.get(url).text
