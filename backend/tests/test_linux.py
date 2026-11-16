"""Generic Linux servers: collecting (fake systemctl), reports, control, install command."""

import os
import stat
import threading
import time

from fastapi.testclient import TestClient

from app.collector import agent, linux
from conftest import csrf_headers

SYSTEMCTL = """#!/bin/sh
echo "$@" >> "$FAKE_LOG"
case "$1" in
  list-units) cat <<'EOF2'
ssh.service loaded active running OpenBSD Secure Shell server
nginx.service loaded failed failed A high performance web server
cron.service loaded active running Regular background program processing daemon
foo.service not-found inactive dead foo.service
backup.service loaded inactive dead Nightly backup
EOF2
  ;;
  list-unit-files) cat <<'EOF2'
ssh.service enabled enabled
nginx.service enabled enabled
cron.service enabled enabled
backup.service static -
EOF2
  ;;
  restart) [ "$2" = "bad.service" ] && { echo "Unit bad.service not found." >&2; exit 5; }; exit 0 ;;
  *) exit 0 ;;
esac
"""


def fake_bin(tmp_path, monkeypatch, name, body):
    folder = tmp_path / "bin"
    folder.mkdir(exist_ok=True)
    exe = folder / name
    exe.write_text(body)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{folder}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.log"))
    return tmp_path / "calls.log"


def test_services_parsing(tmp_path, monkeypatch):
    fake_bin(tmp_path, monkeypatch, "systemctl", SYSTEMCTL)
    services = linux.services()
    names = [s["name"] for s in services]
    assert names[0] == "nginx.service" and services[0]["active"] == "failed"  # failed first
    assert "foo.service" not in names and "backup.service" not in names      # not found / inactive static
    assert {"ssh.service", "cron.service"} <= set(names)


def test_ports_and_disks_run_here():
    for p in linux.ports():
        assert isinstance(p["port"], int) and p["proto"] in ("tcp", "udp")
    for d in linux.disks():
        assert d["total"] >= d["used"] >= 0 and d["mount"].startswith("/")
    d = linux.details()
    assert d["kernel"] and "reboot_required" in d


def test_commands(tmp_path, monkeypatch):
    log = fake_bin(tmp_path, monkeypatch, "systemctl", SYSTEMCTL)
    monkeypatch.setenv("XT_AGENT_LINUX", "1")
    ok = agent.execute({"action": "systemd.restart", "target": "ssh.service", "params": {}})
    assert ok == {"ok": True} and "restart ssh.service" in log.read_text()
    bad = agent.execute({"action": "systemd.restart", "target": "bad.service", "params": {}})
    assert bad["ok"] is False and "not found" in bad["error"]
    assert agent.execute({"action": "systemd.restart", "target": "x-tools-agent.service", "params": {}})["ok"] is False
    assert agent.execute({"action": "systemd.restart", "target": "a b.service", "params": {}})["ok"] is False
    assert agent.execute({"action": "systemd.restart", "target": "ssh", "params": {}})["ok"] is False
    assert agent.execute({"action": "system.reboot", "target": "host", "params": {}}) == {"ok": True}
    assert "reboot" in log.read_text()
    monkeypatch.setenv("XT_AGENT_LINUX", "0")
    assert agent.execute({"action": "system.reboot", "target": "host", "params": {}})["ok"] is False


REPORT = {"version": "7", "hostname": "web1", "control": True,
          "system": {"cpus": 2, "mem_total": 100, "mem_used": 50, "disk_total": 100, "disk_used": 10},
          "docker": None, "proxmox": None,
          "linux": {"os": "Debian 13", "kernel": "6.12", "updates": ["curl"], "reboot_required": True,
                    "services": [{"name": "nginx.service", "active": "failed", "sub": "failed", "enabled": "enabled"},
                                 {"name": "x-tools-agent.service", "active": "active", "sub": "running",
                                  "enabled": "enabled"}],
                    "ports": [{"port": 22, "proto": "tcp", "address": "0.0.0.0", "process": "sshd"}], "disks": []}}


def setup_agent(admin):
    h = csrf_headers(admin)
    r = admin.post("/api/agents", json={"name": "Web1", "kind": "linux", "control": True}, headers=h).json()
    client = TestClient(admin.app)
    assert client.post("/api/agent/report", json=REPORT, headers={"X-Agent-Key": r["key"]}).status_code == 200
    return r, client


def answer(client, key, result, seen):
    for c in client.get("/api/agent/commands?wait=10", headers={"X-Agent-Key": key}).json():
        seen.append(c)
        client.post(f"/api/agent/commands/{c['id']}", json=result, headers={"X-Agent-Key": key})


def test_report_issue_and_control(admin):
    r, client = setup_agent(admin)
    h = csrf_headers(admin)
    summary = [a for a in admin.get("/api/agents").json() if a["id"] == r["id"]][0]
    assert summary["kind"] == "linux" and summary["has_linux"] and not summary["outdated"]
    issues = admin.get("/api/overview").json()["issues"]
    failed = [i for i in issues if i["key"] == f"service:{r['id']}:nginx.service"][0]
    assert failed["link"] == f"/servers/{r['id']}" and "failed" in failed["text"]

    seen = []
    t = threading.Thread(target=answer, args=(client, r["key"], {"ok": True}, seen))
    t.start()
    time.sleep(0.2)
    res = admin.post(f"/api/agents/{r['id']}/action", json={"action": "systemd.restart", "target": "nginx.service"}, headers=h)
    t.join()
    assert res.status_code == 200 and seen[0]["action"] == "systemd.restart" and seen[0]["target"] == "nginx.service"

    t = threading.Thread(target=answer, args=(client, r["key"], {"ok": True}, seen))
    t.start()
    time.sleep(0.2)
    assert admin.post(f"/api/agents/{r['id']}/action", json={"action": "system.reboot", "target": "host"},
                      headers=h).status_code == 200
    t.join()
    assert seen[1]["action"] == "system.reboot"

    for body in ({"action": "systemd.restart", "target": "unknown.service"},
                 {"action": "systemd.stop", "target": "x-tools-agent.service"},
                 {"action": "system.reboot", "target": "nginx.service"},
                 {"action": "docker.restart", "target": "web"}):
        assert admin.post(f"/api/agents/{r['id']}/action", json=body, headers=h).status_code == 422, body
    log = [a["action"] for a in admin.get("/api/audit").json()]
    assert "system.reboot" in log and "systemd.restart" in log


def test_install_script_for_linux(admin):
    from app.api.agent_install import InstallOptions, render_script
    plain = render_script("https://x.test", {"key": "k", **InstallOptions(kind="linux").model_dump()})
    assert "XT_AGENT_LINUX=1" in plain and "XT_AGENT_DOCKER=0" in plain
    with_docker = render_script("https://x.test", {"key": "k", **InstallOptions(kind="linux", docker=True).model_dump()})
    assert "XT_AGENT_DOCKER=1" in with_docker
    dock = render_script("https://x.test", {"key": "k", **InstallOptions(kind="docker").model_dump()})
    assert "XT_AGENT_LINUX=0" in dock and "XT_AGENT_DOCKER=1" in dock
