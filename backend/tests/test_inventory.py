import json
from datetime import date

from fastapi.testclient import TestClient

from app.api import inventory as inv
from app.collector import linux
from app.monitor.eol import support
from conftest import csrf_headers
from test_linux import REPORT, fake_bin

IP_JSON = json.dumps([
    {"ifname": "lo", "operstate": "UNKNOWN", "address": "00:00:00:00:00:00",
     "addr_info": [{"local": "127.0.0.1", "prefixlen": 8, "scope": "host"}]},
    {"ifname": "eth0", "operstate": "UP", "address": "aa:bb:cc:dd:ee:01", "addr_info": [
        {"local": "10.0.0.5", "prefixlen": 24, "scope": "global"}, {"local": "fe80::1", "prefixlen": 64, "scope": "link"},
        {"local": "2001:db8::5", "prefixlen": 64, "scope": "global"}]},
    {"ifname": "docker0", "operstate": "DOWN", "address": "02:42:00:00:00:01",
     "addr_info": [{"local": "172.17.0.1", "prefixlen": 16, "scope": "global"}]},
    {"ifname": "wlan0", "operstate": "DOWN", "address": "aa:bb:cc:dd:ee:02", "addr_info": []},
])


def test_support_dates():
    assert support("debian", "11", date(2026, 11, 16))["state"] == "eol"
    assert support("debian", "12", date(2026, 11, 16))["state"] == "ok"
    assert support("ubuntu", "22.04", date(2027, 2, 1)) == {"state": "soon", "until": "2027-04-30"}
    assert support("arch", "", date(2026, 1, 1))["state"] == "unknown"


def test_interfaces_from_ip(tmp_path, monkeypatch):
    fake_bin(tmp_path, monkeypatch, "ip", "#!/bin/sh\ncat <<'EOF2'\n" + IP_JSON + "\nEOF2\n")
    found = linux.interfaces()
    assert [i["name"] for i in found] == ["eth0", "docker0"]  # lo has no global address, wlan0 none at all
    eth = found[0]
    assert eth["mac"] == "aa:bb:cc:dd:ee:01" and not eth["virtual"] and found[1]["virtual"]
    assert [a["ip"] for a in eth["addrs"]] == ["10.0.0.5", "2001:db8::5"]  # link-local left out


def test_interfaces_without_ip_command(monkeypatch):
    monkeypatch.setattr(linux.shutil, "which", lambda name: None)
    result = linux.interfaces()  # real machine: must not fail
    assert isinstance(result, list) and all(i["name"] != "lo" for i in result)


def report_with(network, guests=None):
    r = {**REPORT, "network": network}
    if guests:
        r["proxmox"] = guests
    return r


def post_report(admin, name, report, kind="linux"):
    h = csrf_headers(admin)
    extra = ({"proxmox_url": "https://127.0.0.1:8006", "proxmox_token_id": "root@pam!x", "proxmox_token_secret": "s"}
             if kind == "proxmox" else {})
    ag = admin.post("/api/agents", json={"name": name, "kind": kind, **extra}, headers=h).json()
    assert TestClient(admin.app).post("/api/agent/report", json=report, headers={"X-Agent-Key": ag["key"]}).status_code == 200
    return ag


def iface(name, ip, prefix=24, virtual=False):
    return {"name": name, "mac": "aa:bb:cc:00:00:01", "state": "up", "virtual": virtual, "addrs": [{"ip": ip, "prefix": prefix}]}


def test_network_and_conflicts(admin, monkeypatch):
    monkeypatch.setattr(inv, "local_interfaces", lambda: [])
    h = csrf_headers(admin)
    post_report(admin, "web-01", {**report_with([iface("eth0", "10.0.0.5"), iface("docker0", "172.17.0.1", 16, True)]), "hostname": "web-01"})
    post_report(admin, "db-01", {**report_with([iface("eth0", "10.0.0.6"), iface("docker0", "172.17.0.1", 16, True)]), "hostname": "db-01"})
    px = {"guests": [{"vmid": 101, "node": "pve", "type": "lxc", "name": "web-01"}, {"vmid": 102, "node": "pve", "type": "lxc", "name": "mail"}],
          "details": {"guests": {"pve/101": {"ips": [{"interface": "eth0", "address": "10.0.0.5"}, {"interface": "eth0", "address": "fe80::1"}]},
                                 "pve/102": {"config": {"nets": [{"name": "eth0", "ip": "10.0.0.6/24"}, {"name": "eth1", "ip": "dhcp"}]}}}}}
    post_report(admin, "pve", {**REPORT, "linux": None, "network": [iface("vmbr0", "10.0.0.2")], "proxmox": px}, kind="proxmox")
    r = admin.post("/api/network/entries", json={"ip": "10.0.0.1", "name": "Router", "notes": "ground floor"}, headers=h)
    assert r.status_code == 201
    admin.post("/api/network/entries", json={"ip": "10.0.0.5", "name": "Old printer"}, headers=h)  # clashes with web-01

    data = admin.get("/api/network").json()
    by = lambda ip: [(i["name"], i["kind"]) for i in data["items"] if i["ip"] == ip]  # noqa: E731
    assert ("Router", "manual") in by("10.0.0.1") and by("10.0.0.2") == [("pve", "server")]
    # web-01 is an agent AND a Proxmox guest with the same name: one machine, not a conflict – but the printer is
    conflicts = {c["ip"]: c["names"] for c in data["conflicts"]}
    assert "10.0.0.5" in conflicts and sorted(conflicts["10.0.0.5"]) == ["Old printer", "web-01"]
    # mail (guest, configured address) and db-01 (agent) share 10.0.0.6 under different names
    assert sorted(conflicts["10.0.0.6"]) == ["db-01", "mail"]
    # Docker bridges exist on both servers but are virtual: never a conflict
    assert "172.17.0.1" not in conflicts and all(i["virtual"] for i in data["items"] if i["ip"] == "172.17.0.1")
    assert not [i for i in data["items"] if i["ip"].startswith("fe80") or i["ip"] == "dhcp"]
    assert [i["network"] for i in data["items"] if i["ip"] == "10.0.0.2"] == ["10.0.0.0/24"]
    pve_id = [a["id"] for a in admin.get("/api/agents").json() if a["name"] == "pve"][0]
    assert any(i["link"] == f"/proxmox/{pve_id}/pve/102" for i in data["items"])          # guest "mail"
    assert [i["kind"] for i in data["items"] if i["ip"] == "10.0.0.5" and i["name"] == "web-01"] == ["server"]  # not twice


def test_entries_crud_and_rights(admin):
    h = csrf_headers(admin)
    assert admin.post("/api/network/entries", json={"ip": "300.1.1.1", "name": "x"}, headers=h).status_code == 422
    e = admin.post("/api/network/entries", json={"ip": "2001:0db8:0:0:0:0:0:1", "name": "  NAS   one "}, headers=h).json()
    assert e["ip"] == "2001:db8::1" and e["name"] == "NAS one"
    assert admin.put(f"/api/network/entries/{e['id']}", json={"ip": "10.0.0.9", "name": "NAS"}, headers=h).json()["ip"] == "10.0.0.9"
    # viewer: may look, may not change
    admin.post("/api/users", json={"username": "lookonly", "role": "viewer", "password": "user password 1"}, headers=h)
    c = TestClient(admin.app)
    c.post("/api/auth/login", json={"username": "lookonly", "password": "user password 1"})
    assert c.get("/api/network").status_code == 200 and c.get("/api/inventory").status_code == 200
    assert c.post("/api/network/entries", json={"ip": "10.0.0.10", "name": "x"}, headers=csrf_headers(c)).status_code == 403
    assert admin.delete(f"/api/network/entries/{e['id']}", headers=h).status_code == 204
    assert admin.delete(f"/api/network/entries/{e['id']}", headers=h).status_code == 404


def test_inventory(admin, monkeypatch):
    monkeypatch.setattr(inv, "local_interfaces", lambda: [])
    rep = {**REPORT, "version": "7", "network": [iface("eth0", "10.0.0.5")]}
    rep["linux"] = {**REPORT["linux"], "os_id": "debian", "os_version": "11", "arch": "x86_64"}
    post_report(admin, "old-box", rep)
    rows = admin.get("/api/inventory").json()
    row = [r for r in rows if r["name"] == "old-box"][0]
    assert row["os"] == "Debian 13" and row["support"]["state"] == "eol" and row["outdated"] is True
    assert row["updates"] == 1 and row["reboot"] is True and row["ips"] == ["10.0.0.5"] and row["link"].startswith("/servers/")
