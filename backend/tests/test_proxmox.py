"""Proxmox details parsing and config changes (agent side and server side)."""

import json
import threading
import time
from urllib.parse import parse_qs

from fastapi.testclient import TestClient

from conftest import csrf_headers


def test_parse_config():
    from app.collector.proxmox import parse_config
    lxc = parse_config({"cores": 2, "memory": 2048, "swap": 512, "hostname": "web",
                        "rootfs": "local-lvm:vm-101-disk-0,size=8G",
                        "mp0": "tank:subvol-101-disk-1,mp=/data,size=100G,backup=0",
                        "net0": "name=eth0,bridge=vmbr0,hwaddr=BC:24:11:AA:BB:CC,ip=dhcp,tag=20,firewall=1",
                        "features": "nesting=1,keyctl=1", "unprivileged": 1, "onboot": 1, "tags": "web;prod",
                        "ostype": "debian", "digest": "x"}, "lxc")
    assert lxc["disks"][0] == {"key": "rootfs", "volume": "local-lvm:vm-101-disk-0", "storage": "local-lvm",
                               "size": "8G", "size_bytes": 8 * 1024 ** 3, "mountpoint": "/", "backup": True}
    assert lxc["disks"][1]["mountpoint"] == "/data" and lxc["disks"][1]["backup"] is False
    assert lxc["nets"][0]["mac"] == "bc:24:11:aa:bb:cc" and lxc["nets"][0]["vlan"] == "20" and lxc["nets"][0]["firewall"]
    assert lxc["features"] == {"nesting": "1", "keyctl": "1"} and lxc["tags"] == ["web", "prod"]
    assert lxc["unprivileged"] and lxc["onboot"] and lxc["swap"] == 512 and "digest" not in lxc["raw"]

    vm = parse_config({"cores": 4, "sockets": 1, "memory": "8192", "name": "ha", "agent": "1,fstrim_cloned_disks=1",
                       "scsi0": "local-lvm:vm-102-disk-0,iothread=1,size=32G", "ide2": "none,media=cdrom",
                       "net0": "virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr1,firewall=1", "cipassword": "secret"}, "qemu")
    assert [d["key"] for d in vm["disks"]] == ["scsi0"]  # cdrom skipped
    assert vm["nets"][0]["model"] == "virtio" and vm["nets"][0]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert vm["agent"] is True and vm["swap"] is None and "cipassword" not in vm["raw"]


def test_validate_changes():
    import pytest

    from app.collector.proxmox import validate_changes
    assert validate_changes({"cores": 2, "memory": 4096, "onboot": True, "tags": ["a", "b-c"]}, "lxc") == \
        {"cores": 2, "memory": 4096, "onboot": 1, "tags": "a;b-c"}
    for bad, kind in (({"cores": 0}, "lxc"), ({"swap": 512}, "qemu"), ({"net0": "x"}, "lxc"), ({}, "lxc"),
                      ({"tags": ["UPPER"]}, "lxc"), ({"memory": "4096"}, "lxc")):
        with pytest.raises(ValueError):
            validate_changes(bad, kind)


def test_agent_sends_config_change(monkeypatch):
    """The agent turns a command into the right Proxmox API call."""
    from app.collector import agent, proxmox
    calls = []
    monkeypatch.setenv("PROXMOX_URL", "https://127.0.0.1:8006")
    monkeypatch.setattr(proxmox, "request", lambda path, method="GET", data=None, timeout=20: calls.append(
        (path, method, data)))
    r = agent.execute({"action": "proxmox.config", "target": "101",
                       "params": {"node": "pve", "type": "lxc", "changes": {"cores": 4, "description": ""}}})
    assert r == {"ok": True}
    assert calls[-1] == ("/nodes/pve/lxc/101/config", "PUT", {"cores": 4, "delete": "description"})
    r = agent.execute({"action": "proxmox.resize", "target": "101",
                       "params": {"node": "pve", "type": "lxc", "disk": "rootfs", "add_gb": 5}})
    assert r == {"ok": True} and calls[-1] == ("/nodes/pve/lxc/101/resize", "PUT", {"disk": "rootfs", "size": "+5G"})
    r = agent.execute({"action": "proxmox.config", "target": "101",
                       "params": {"node": "pve", "type": "lxc", "changes": {"rootfs": "evil"}}})
    assert r["ok"] is False and "cannot be changed" in r["error"]


def test_server_validates_config_action(admin):
    h = csrf_headers(admin)
    r = admin.post("/api/agents", json={"name": "PVE", "kind": "docker", "control": True}, headers=h).json()
    agent = TestClient(admin.app)
    report = {"version": "4", "control": True, "proxmox": {"guests": [{"vmid": 101, "node": "pve", "type": "lxc"}]}}
    agent.post("/api/agent/report", json=report, headers={"X-Agent-Key": r["key"]})
    base = {"target": "101", "node": "pve", "type": "lxc"}
    assert admin.post(f"/api/agents/{r['id']}/action", json={**base, "action": "proxmox.config",
                      "changes": {"rootfs": "x"}}, headers=h).status_code == 422
    assert admin.post(f"/api/agents/{r['id']}/action", json={**base, "action": "proxmox.resize", "disk": "net0",
                      "add_gb": 5}, headers=h).status_code == 422

    seen = []

    def fake():
        cmds = agent.get("/api/agent/commands?wait=10", headers={"X-Agent-Key": r["key"]}).json()
        seen.extend(cmds)
        for c in cmds:
            agent.post(f"/api/agent/commands/{c['id']}", json={"ok": True}, headers={"X-Agent-Key": r["key"]})
    t = threading.Thread(target=fake)
    t.start()
    time.sleep(0.2)
    res = admin.post(f"/api/agents/{r['id']}/action", json={**base, "action": "proxmox.config",
                     "changes": {"memory": 4096, "cores": 2}}, headers=h)
    t.join()
    assert res.status_code == 200, res.text
    assert seen[0]["params"]["changes"] == {"memory": 4096, "cores": 2}
    log = admin.get("/api/audit?action=proxmox").json()[0]
    assert log["action"] == "proxmox.config" and "memory=4096" in log["detail"]
    _ = json, parse_qs


def test_details_against_fake_proxmox(monkeypatch):
    from fake_proxmox import serve
    from app.collector import proxmox
    server = serve()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("PROXMOX_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("PROXMOX_TOKEN_ID", "root@pam!xtools")
    monkeypatch.setenv("PROXMOX_TOKEN_SECRET", "1111-2222")
    monkeypatch.setattr(proxmox, "local_updates", lambda: ["pve-manager", "proxmox-kernel-6.8"])
    try:
        overview = proxmox.info()
        d = proxmox.details(overview)
    finally:
        server.shutdown()
    g101 = d["guests"]["pve/101"]
    assert g101["config"]["memory"] == 2048 and g101["ips"] == [{"interface": "eth0", "address": "192.168.1.31/24"}]
    assert [s["name"] for s in g101["snapshots"]] == ["before-update"]
    assert d["guests"]["pve/102"]["ips"] == [{"interface": "enp0s18", "address": "192.168.1.40/24"}]
    assert "ips" not in d["guests"]["pve/103"]  # stopped
    assert [b["vmid"] for b in d["backups"]] == [102, 101]
    node = d["nodes"]["pve"]
    assert node["version"] == "8.3.0" and node["kernel"].startswith("Linux 6.8")
    # apt/update is forbidden for the token; the agent runs on the host (localhost) and reads apt locally
    assert node["updates"] == ["pve-manager", "proxmox-kernel-6.8"]
    assert node["network"][0]["iface"] == "vmbr0" and node["network"][0]["vlan_aware"]
    conf = g101["conf"]
    assert conf["path"] == "/etc/pve/nodes/pve/lxc/101.conf" and conf["source"] == "api"
    assert conf["content"].startswith("#Docker host for the web apps\narch") or "cores: 2" in conf["content"]
    assert "digest" not in conf["content"] and "rootfs: local-lvm:vm-101-disk-0,size=16G" in conf["content"]


def test_conf_file_is_read_and_masked(tmp_path, monkeypatch):
    from app.collector.proxmox import read_conf
    conf = tmp_path / "etc/pve/nodes/pve/qemu-server/102.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("#notes\ncores: 2\ncipassword: $5$hash\nsshkeys: ssh-rsa%20AAA\n\n[snap1]\ncores: 1\n")
    monkeypatch.setenv("XT_HOST_ROOT", str(tmp_path))
    r = read_conf("pve", "qemu", 102, {})
    assert r["source"] == "file" and r["path"] == "/etc/pve/nodes/pve/qemu-server/102.conf"
    assert "cipassword: ••••••" in r["content"] and "$5$hash" not in r["content"] and "AAA" not in r["content"]
    assert "[snap1]" in r["content"]
