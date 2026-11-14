"""A small fake of the Proxmox VE API for tests (HTTP, token checked)."""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN = "PVEAPIToken=root@pam!xtools=1111-2222"
NOW = int(time.time())
DATA = {
    "/cluster/resources": [
        {"type": "node", "node": "pve", "status": "online", "cpu": 0.1, "maxcpu": 8, "mem": 8e9, "maxmem": 32e9,
         "uptime": 99999},
        {"type": "lxc", "vmid": 101, "name": "docker-lxc", "node": "pve", "status": "running", "cpu": 0.05, "maxcpu": 2,
         "mem": 1.2e9, "maxmem": 2147483648, "uptime": 5000, "tags": "docker;prod"},
        {"type": "qemu", "vmid": 102, "name": "homeassistant", "node": "pve", "status": "running", "cpu": 0.02,
         "maxcpu": 2, "mem": 3e9, "maxmem": 4294967296, "uptime": 5000},
        {"type": "lxc", "vmid": 103, "name": "test", "node": "pve", "status": "stopped", "maxcpu": 1,
         "maxmem": 536870912},
        {"type": "storage", "storage": "local", "node": "pve", "status": "available", "disk": 2e10, "maxdisk": 1e11,
         "content": "iso,vztmpl,backup", "plugintype": "dir"},
        {"type": "storage", "storage": "local-lvm", "node": "pve", "status": "available", "disk": 1e11,
         "maxdisk": 4e11, "content": "images,rootdir", "plugintype": "lvmthin"},
    ],
    "/nodes/pve/lxc/101/config": {"hostname": "docker-lxc", "cores": 2, "memory": 2048, "swap": 512, "ostype": "debian",
                                  "rootfs": "local-lvm:vm-101-disk-0,size=16G", "unprivileged": 1, "onboot": 1,
                                  "features": "nesting=1,keyctl=1", "tags": "docker;prod",
                                  "mp0": "local-lvm:vm-101-disk-1,mp=/srv/data,size=50G",
                                  "net0": "name=eth0,bridge=vmbr0,hwaddr=BC:24:11:12:34:56,ip=dhcp,type=veth",
                                  "description": "Docker host for the web apps\n", "digest": "abc"},
    "/nodes/pve/lxc/101/interfaces": [{"name": "lo", "inet": "127.0.0.1/8"},
                                      {"name": "eth0", "inet": "192.168.1.31/24", "inet6": "fe80::1/64"}],
    "/nodes/pve/lxc/101/snapshot": [{"name": "before-update", "snaptime": NOW - 86400, "description": "pre upgrade"},
                                    {"name": "current", "running": 1}],
    "/nodes/pve/qemu/102/config": {"name": "homeassistant", "cores": 2, "sockets": 1, "memory": "4096", "agent": "1",
                                   "ostype": "l26", "scsi0": "local-lvm:vm-102-disk-0,size=32G",
                                   "ide2": "none,media=cdrom", "net0": "virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0,tag=30",
                                   "onboot": 1},
    "/nodes/pve/qemu/102/agent/network-get-interfaces": {"result": [
        {"name": "lo", "ip-addresses": [{"ip-address": "127.0.0.1", "prefix": 8}]},
        {"name": "enp0s18", "ip-addresses": [{"ip-address": "192.168.1.40", "prefix": 24}]}]},
    "/nodes/pve/qemu/102/snapshot": [{"name": "current"}],
    "/nodes/pve/lxc/103/config": {"hostname": "test", "cores": 1, "memory": 512, "swap": 0,
                                  "rootfs": "local-lvm:vm-103-disk-0,size=4G",
                                  "net0": "name=eth0,bridge=vmbr0,ip=192.168.1.99/24,gw=192.168.1.1"},
    "/nodes/pve/lxc/103/snapshot": [{"name": "current"}],
    "/nodes/pve/storage/local/content": [
        {"content": "backup", "vmid": 101, "volid": "local:backup/vzdump-lxc-101-2026_11_14-03_00_01.tar.zst",
         "ctime": NOW - 3600 * 20, "size": 812345678, "notes": "docker-lxc nightly"},
        {"content": "backup", "vmid": 102, "volid": "local:backup/vzdump-qemu-102-2026_11_14-03_10_00.vma.zst",
         "ctime": NOW - 3600 * 19, "size": 2345678901},
        {"content": "iso", "volid": "local:iso/debian.iso"}],
    "/nodes/pve/status": {"pveversion": "pve-manager/8.3.0/abcdef", "kversion": "Linux 6.8.12-4-pve #1 SMP",
                          "cpuinfo": {"model": "Intel(R) N100"}, "boot-info": {"mode": "efi"}},
    "/nodes/pve/version": {"version": "8.3.0", "release": "8.3"},
    "/nodes/pve/network": [
        {"iface": "vmbr0", "type": "bridge", "active": 1, "autostart": 1, "cidr": "192.168.1.10/24",
         "gateway": "192.168.1.1", "bridge_ports": "enp1s0", "bridge_vlan_aware": 1, "comments": "LAN\n"},
        {"iface": "enp1s0", "type": "eth", "active": 1, "autostart": 1},
        {"iface": "vmbr0.30", "type": "vlan", "active": 1, "vlan-id": "30"}],
}
FORBIDDEN = {"/nodes/pve/apt/update"}


class FakeProxmox(BaseHTTPRequestHandler):
    writes: list = []

    def log_message(self, *args):
        pass

    def reply(self, code, data=None):
        body = json.dumps({"data": data}).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def route(self):
        if self.headers.get("Authorization") != TOKEN:
            return self.reply(401)
        path = urlparse(self.path).path.removeprefix("/api2/json")
        if path in FORBIDDEN:
            return self.reply(403)
        if self.command in ("PUT", "POST"):
            length = int(self.headers.get("Content-Length") or 0)
            body = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
            FakeProxmox.writes.append((self.command, path, body))
            if path.endswith("/config"):
                cfg = DATA.get(path, {})
                for key in (body.pop("delete", "") or "").split(","):
                    cfg.pop(key, None)
                cfg.update({k: (int(v) if v.isdigit() else v) for k, v in body.items()})
            return self.reply(200, "UPID:pve:task")
        if path not in DATA:
            return self.reply(500)
        self.reply(200, DATA[path])

    do_GET = do_PUT = do_POST = route


def serve(port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), FakeProxmox)
