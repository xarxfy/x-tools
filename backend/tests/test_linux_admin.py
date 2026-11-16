import base64
import os
import pwd
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.collector import agent, linux_admin as la
from conftest import csrf_headers
from test_linux import REPORT, answer, fake_bin

BLOB = base64.b64encode(len(b"ssh-ed25519").to_bytes(4, "big") + b"ssh-ed25519" + b"\x00\x00\x00\x20" + b"k" * 32).decode()
KEY = f"ssh-ed25519 {BLOB} laptop@home"


def sh_bin(tmp_path, monkeypatch, name, body):
    return fake_bin(tmp_path, monkeypatch, name, "#!/bin/sh\n" + body.replace("LOG", '"$FAKE_LOG"'))


def test_validate():
    assert la.validate("user.key_add", "marc", {"key": KEY}) == {"key": KEY}
    for bad in ("", "ssh-ed25519", "command=\"id\" " + KEY, KEY + "\n" + KEY, "ssh-rsa " + BLOB, "ssh-ed25519 !!!"):
        with pytest.raises(la.AdminError):
            la.validate("user.key_add", "marc", {"key": bad})
    for name in ("Marc", "a b", "-x", "x;y", "", "a" * 40):
        with pytest.raises(la.AdminError):
            la.validate("user.lock", name, {})
    assert la.validate("ufw.add", "host", {"rule": "allow", "port": "443", "proto": "tcp", "source": "10.0.0.5"}) == {
        "rule": "allow", "port": "443", "proto": "tcp", "source": "10.0.0.5/32", "comment": ""}
    for args in ({"rule": "x", "port": "1"}, {"rule": "allow", "port": "0"}, {"rule": "allow", "port": "80;ls"},
                 {"rule": "allow", "port": "9:1"}, {"rule": "allow", "port": "80", "source": "evil"},
                 {"rule": "limit", "port": "22", "proto": "udp"}, {"rule": "allow", "port": "80", "comment": "a;b"}):
        with pytest.raises(la.AdminError):
            la.validate("ufw.add", "host", args)
    with pytest.raises(la.AdminError):
        la.validate("ufw.enable", "someone", {})
    with pytest.raises(la.AdminError):
        la.validate("rm.all", "host", {})


def fake_user(tmp_path, monkeypatch, name="marc"):
    home = tmp_path / name
    home.mkdir()
    p = pwd.struct_passwd((name, "x", os.getuid(), os.getgid(), "", str(home), "/bin/bash"))
    monkeypatch.setattr(la, "_user", lambda n: p)
    monkeypatch.setattr(la, "_group_members", lambda g: {name, "other"})
    monkeypatch.setattr(la, "_shadow", lambda: {})
    return p, home


def test_keys(tmp_path, monkeypatch):
    p, home = fake_user(tmp_path, monkeypatch)
    (home / ".ssh").mkdir(mode=0o700)
    la.user_action("user.key_add", "marc", {"key": KEY})
    keys = la.read_keys(p)
    assert len(keys) == 1 and keys[0]["fingerprint"].startswith("SHA256:") and keys[0]["comment"] == "laptop@home"
    assert oct((home / ".ssh" / "authorized_keys").stat().st_mode & 0o777) == "0o600"
    with pytest.raises(la.AdminError, match="already"):
        la.user_action("user.key_add", "marc", {"key": KEY})
    la.user_action("user.key_remove", "marc", {"fingerprint": keys[0]["fingerprint"]})
    assert la.read_keys(p) == []
    with pytest.raises(la.AdminError, match="not found"):
        la.user_action("user.key_remove", "marc", {"fingerprint": keys[0]["fingerprint"]})


def test_keys_refuse_symlinks(tmp_path, monkeypatch):
    p, home = fake_user(tmp_path, monkeypatch)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (home / ".ssh").symlink_to(target)
    with pytest.raises(la.AdminError):
        la.user_action("user.key_add", "marc", {"key": KEY})
    assert not list(target.iterdir())


def test_user_commands(tmp_path, monkeypatch):
    fake_user(tmp_path, monkeypatch)
    log = sh_bin(tmp_path, monkeypatch, "usermod", "echo \"$@\" >> LOG")
    monkeypatch.setattr(la, "_would_orphan", lambda n: False)
    monkeypatch.setattr(la, "_admin_group", lambda: "sudo")
    la.user_action("user.lock", "marc", {})
    la.user_action("user.unlock", "marc", {})
    la.user_action("user.sudo", "marc", {})
    lines = log.read_text().splitlines()
    assert lines == ["-e 1 marc", "-e  marc", "-aG sudo marc"]


def test_last_admin_is_protected(tmp_path, monkeypatch):
    fake_user(tmp_path, monkeypatch)
    monkeypatch.setattr(la, "_would_orphan", lambda n: True)
    for action in ("user.lock", "user.nosudo", "user.delete"):
        with pytest.raises(la.AdminError, match="only administrator"):
            la.user_action(action, "marc", {})


def test_system_accounts_are_protected(monkeypatch):
    root = pwd.struct_passwd(("root", "x", 0, 0, "", "/root", "/bin/bash"))
    monkeypatch.setattr(la, "_user", lambda n: root)
    with pytest.raises(la.AdminError, match="cannot be changed"):
        la.user_action("user.delete", "root", {})


UFW_VERBOSE = "Status: active\nLogging: on (low)\nDefault: deny (incoming), allow (outgoing), disabled (routed)\n"
UFW_NUMBERED = """Status: active

     To                         Action      From
     --                         ------      ----
[ 1] 22/tcp                     ALLOW IN    Anywhere
[ 2] 80/tcp                     ALLOW IN    Anywhere                   # web
[ 3] 22/tcp (v6)                ALLOW IN    Anywhere (v6)
"""
UFW = f"""case "$1 $2" in
  "status verbose") printf '%s' '{UFW_VERBOSE}';;
  "status numbered") printf '%s' '{UFW_NUMBERED}';;
  *) echo "$@" >> LOG;;
esac"""


def test_ufw(tmp_path, monkeypatch):
    log = sh_bin(tmp_path, monkeypatch, "ufw", UFW)
    monkeypatch.setattr(la, "ssh_ports", lambda: [22])
    st = la.ufw_status()
    assert st["active"] and st["default"].startswith("deny (incoming)")
    assert [(r["number"], r["to"], r["action"], r["comment"]) for r in st["rules"]] == [
        (1, "22/tcp", "ALLOW", ""), (2, "80/tcp", "ALLOW", "web"), (3, "22/tcp (v6)", "ALLOW", "")]
    la.ufw_action("ufw.add", {"rule": "allow", "port": "443", "proto": "tcp", "source": "10.0.0.0/24", "comment": "x"})
    la.ufw_action("ufw.delete", {"number": 2, "to": "80/tcp", "action": "ALLOW", "from": "Anywhere"})
    la.ufw_action("ufw.enable", {})
    assert log.read_text().splitlines() == [
        "allow from 10.0.0.0/24 to any port 443 proto tcp comment x", "--force delete 2", "allow 22/tcp",
        "--force enable"]
    # never block or delete the way in
    with pytest.raises(la.AdminError, match="block SSH"):
        la.ufw_action("ufw.add", {"rule": "deny", "port": "20:30", "proto": "tcp"})
    with pytest.raises(la.AdminError, match="reload"):
        la.ufw_action("ufw.delete", {"number": 2, "to": "443/tcp", "action": "ALLOW", "from": "Anywhere"})
    with pytest.raises(la.AdminError, match="lock you out"):
        la.ufw_action("ufw.delete", {"number": 3, "to": "22/tcp (v6)", "action": "ALLOW", "from": "Anywhere (v6)"})


def test_update_job(tmp_path, monkeypatch):
    log = sh_bin(tmp_path, monkeypatch, "apt-get", 'echo "apt-get $@" >> LOG; echo working')
    la._job.update(state="idle", log="", started=None, finished=None)
    assert la.admin_action("system.update", "host", {}) == {"ok": True}
    if la.update_job()["state"] == "running":
        with pytest.raises(la.AdminError, match="already running"):
            la.admin_action("system.update", "host", {})
    for _ in range(50):
        if la.update_job()["state"] != "running":
            break
        time.sleep(0.1)
    job = la.update_job()
    assert job["state"] == "ok" and "working" in job["log"] and job["finished"]
    text = log.read_text()
    assert "apt-get update" in text and "-y" in text and "upgrade" in text
    monkeypatch.setenv("XT_AGENT_LINUX", "0")
    assert agent.execute({"action": "system.update", "target": "host", "params": {}})["ok"] is False


def test_manage_api(admin):
    h = csrf_headers(admin)
    report = {**REPORT, "linux": {**REPORT["linux"], "users": [{"name": "marc", "uid": 1000, "keys": []}]}}
    r = admin.post("/api/agents", json={"name": "Web2", "kind": "linux", "control": True}, headers=h).json()
    client = TestClient(admin.app)
    assert client.post("/api/agent/report", json=report, headers={"X-Agent-Key": r["key"]}).status_code == 200
    seen = []
    t = threading.Thread(target=answer, args=(client, r["key"], {"ok": True}, seen))
    t.start()
    time.sleep(0.2)
    res = admin.post(f"/api/agents/{r['id']}/manage", json={"action": "user.key_add", "target": "marc",
                                                          "args": {"key": KEY}}, headers=h)
    t.join()
    assert res.status_code == 200 and seen[0]["action"] == "user.key_add" and seen[0]["params"] == {"key": KEY}
    for body in ({"action": "user.lock", "target": "ghost"}, {"action": "ufw.add", "args": {"rule": "x", "port": "1"}},
                 {"action": "user.key_add", "target": "marc", "args": {"key": "nope"}}, {"action": "system.reboot"}):
        assert admin.post(f"/api/agents/{r['id']}/manage", json=body, headers=h).status_code == 422, body
    assert "user.key_add" in [a["action"] for a in admin.get("/api/audit").json()]


def test_customer_categories(admin):
    h = csrf_headers(admin)
    a = admin.post("/api/customer-categories", json={"name": "A-Kunde"}, headers=h).json()
    b = admin.post("/api/customer-categories", json={"name": "B-Kunde"}, headers=h).json()
    assert admin.post("/api/customer-categories", json={"name": "a-kunde"}, headers=h).status_code == 409
    assert [c["name"] for c in admin.get("/api/customer-categories").json()] == ["A-Kunde", "B-Kunde"]
    assert admin.put("/api/customer-categories/order", json={"ids": [b["id"], a["id"]]}, headers=h).status_code == 200
    assert [c["name"] for c in admin.get("/api/customer-categories").json()] == ["B-Kunde", "A-Kunde"]
    assert admin.put("/api/customer-categories/order", json={"ids": [a["id"]]}, headers=h).status_code == 422
    c = admin.post("/api/customers", json={"name": "ACME", "category_id": a["id"]}, headers=h).json()
    assert c["category_id"] == a["id"]
    assert admin.post("/api/customers", json={"name": "X", "category_id": "nope"}, headers=h).status_code == 422
    assert admin.put(f"/api/customer-categories/{a['id']}", json={"name": "Premium"}, headers=h).json()["name"] == "Premium"
    assert admin.delete(f"/api/customer-categories/{a['id']}", headers=h).status_code == 204
    assert admin.get(f"/api/customers/{c['id']}").json()["category_id"] is None


def test_standalone_agent_starts(tmp_path):
    """The zipapp that servers download must import all its modules (a missing one stops the agent at start)."""
    import subprocess
    import sys
    from app.collector.bundle import agent_bundle
    pyz = tmp_path / "agent.pyz"
    pyz.write_bytes(agent_bundle())
    out = subprocess.run([sys.executable, "-I", str(pyz)], capture_output=True, text=True, env={"PATH": os.environ["PATH"]})
    assert "XT_AGENT_URL and XT_AGENT_KEY must be set" in out.stderr, out.stderr


def test_service_unit_is_writable_only_for_controlled_linux_servers():
    from app.api.agent_install import InstallOptions, render_script
    def script(**kw):
        return render_script("https://x.test", {"key": "k", **InstallOptions(**kw).model_dump()})
    assert "ProtectSystem=strict" not in script(kind="linux", control=True)
    assert "__HARDENING__" not in script(kind="linux", control=True)
    for kw in ({"kind": "linux"}, {"kind": "docker", "control": True}, {"kind": "proxmox", "control": True,
               "proxmox_url": "https://127.0.0.1:8006", "proxmox_token_id": "a@pam!b", "proxmox_token_secret": "s"}):
        text = script(**kw)
        assert "ProtectSystem=strict" in text and "ProtectHome=read-only" in text and "NoNewPrivileges=yes" in text, kw


def test_read_only_system_gives_a_hint(tmp_path, monkeypatch):
    fake_user(tmp_path, monkeypatch)
    sh_bin(tmp_path, monkeypatch, "usermod", "echo 'usermod: cannot open /etc/passwd: Read-only file system' >&2; exit 1")
    monkeypatch.setattr(la, "_would_orphan", lambda n: False)
    with pytest.raises(la.AdminError, match="install command"):
        la.admin_action("user.sudo", "marc", {})
    (tmp_path / "marc" / ".ssh").mkdir(mode=0o700)
    import errno

    def boom(*a, **k):
        raise OSError(errno.EROFS, "Read-only file system")
    monkeypatch.setattr(la.os, "replace", boom)
    with pytest.raises(la.AdminError, match="install command"):
        la.admin_action("user.key_add", "marc", {"key": KEY})


def test_after_an_action_only_users_and_firewall_are_read_again(monkeypatch):
    calls = []
    monkeypatch.setenv("XT_AGENT_LINUX", "1")
    monkeypatch.setattr(agent.linux, "details", lambda: calls.append("details") or {"updates": []})
    monkeypatch.setattr(la, "users", lambda: calls.append("users") or [])
    monkeypatch.setattr(la, "ufw_status", lambda: calls.append("ufw") or {"installed": False})
    monkeypatch.setattr(agent.linux, "services", lambda: [])
    monkeypatch.setattr(agent.linux, "ports", lambda: [])
    monkeypatch.setattr(agent.linux, "disks", lambda: [])
    monkeypatch.setitem(agent._linux, "data", None)
    agent.linux_info()
    assert calls == ["details", "users", "ufw"]
    calls.clear()
    agent._linux["dirty"].add("users")
    out = agent.linux_info()
    assert calls == ["users"] and out["users"] == []
