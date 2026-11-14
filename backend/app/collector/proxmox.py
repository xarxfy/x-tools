"""Proxmox VE API for the agent (standard library only).

Read: nodes, guests, storage (every report), and every few minutes the details:
guest configuration (resources, disks, network, options), current IP addresses,
snapshots, backups, and per node version, kernel, available updates and network.
Write (only with control on): power actions, a small set of config options,
growing a disk.
"""

import json
import os
import re
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


class ProxmoxError(Exception):
    pass


def _ctx():
    ctx = ssl.create_default_context()
    if os.environ.get("PROXMOX_VERIFY_TLS", "0") == "0":  # Proxmox usually has a self-signed certificate
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def base_url() -> str:
    return os.environ.get("PROXMOX_URL", "").rstrip("/")


def request(path: str, method: str = "GET", data: dict | None = None, timeout: float = 20):
    url = base_url()
    if not url:
        raise ProxmoxError("Proxmox is not configured on this agent")
    token = f"PVEAPIToken={os.environ.get('PROXMOX_TOKEN_ID', '')}={os.environ.get('PROXMOX_TOKEN_SECRET', '')}"
    body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
    req = urllib.request.Request(url + "/api2/json" + path, data=body, method=method,
                                 headers={"Authorization": token,
                                          **({"Content-Type": "application/x-www-form-urlencoded"} if body else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as res:
            return json.loads(res.read() or b"{}").get("data")
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read() or b"{}")
            message = detail.get("message") or "; ".join(f"{k}: {v}" for k, v in (detail.get("errors") or {}).items())
        except (ValueError, AttributeError):
            message = ""
        raise ProxmoxError(f"Proxmox API: HTTP {error.code}{' – ' + message.strip() if message else ''}") from None
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise ProxmoxError(f"Proxmox API not reachable: {getattr(error, 'reason', error)}") from None


# --- Overview (every report) -------------------------------------------------------------

def info() -> dict | None:
    if not base_url():
        return None
    try:
        data = request("/cluster/resources", timeout=15) or []
    except ProxmoxError as error:
        message = str(error)
        if "HTTP 401" in message or "HTTP 403" in message:
            message += " – check token and permissions"
        return {"error": message}
    keys = ("cpu", "maxcpu", "mem", "maxmem", "disk", "maxdisk", "uptime")
    nodes = [{"name": r.get("node", ""), "status": r.get("status", ""), **{k: r.get(k, 0) for k in keys}}
             for r in data if r.get("type") == "node"]
    guests = [{"vmid": r.get("vmid"), "name": r.get("name", ""), "type": r.get("type"), "status": r.get("status", ""),
               "node": r.get("node", ""), "tags": r.get("tags", ""), **{k: r.get(k, 0) for k in keys}}
              for r in data if r.get("type") in ("lxc", "qemu") and not r.get("template")]
    storage = [{"storage": r.get("storage", ""), "node": r.get("node", ""), "status": r.get("status", ""),
                "disk": r.get("disk", 0), "maxdisk": r.get("maxdisk", 0), "content": r.get("content", ""),
                "plugintype": r.get("plugintype", "")}
               for r in data if r.get("type") == "storage" and r.get("maxdisk")]
    return {"nodes": sorted(nodes, key=lambda n: n["name"]),
            "guests": sorted(guests, key=lambda g: g["vmid"] or 0),
            "storage": sorted(storage, key=lambda s: (s["node"], s["storage"]))}


# --- Parsing of guest configuration -------------------------------------------------------

DISK_KEY = re.compile(r"^(rootfs|mp\d+|scsi\d+|virtio\d+|sata\d+|ide\d+|efidisk\d+|tpmstate\d+)$")
NET_KEY = re.compile(r"^net\d+$")
HIDDEN_KEYS = {"cipassword", "sshkeys", "digest", "lock"}
SIZE = re.compile(r"^(\d+(?:\.\d+)?)([KMGT]?)$")


def size_bytes(value: str) -> int | None:
    m = SIZE.match(value or "")
    if not m:
        return None
    return int(float(m.group(1)) * 1024 ** "BKMGT".index(m.group(2) or "B"))


def options(value: str) -> tuple[str, dict]:
    """'local-lvm:vm-101-disk-0,size=8G,mp=/data' → ('local-lvm:vm-101-disk-0', {'size': '8G', 'mp': '/data'})"""
    first, rest = "", {}
    for i, part in enumerate(str(value).split(",")):
        if "=" in part:
            k, _, v = part.partition("=")
            rest[k.strip()] = v.strip()
        elif i == 0:
            first = part.strip()
    return first, rest


def parse_disk(key: str, value: str) -> dict | None:
    volume, opts = options(value)
    if opts.get("media") == "cdrom":
        return None
    return {"key": key, "volume": volume, "storage": volume.split(":")[0] if ":" in volume else "",
            "size": opts.get("size", ""), "size_bytes": size_bytes(opts.get("size", "")),
            "mountpoint": "/" if key == "rootfs" else opts.get("mp", ""),
            "backup": opts.get("backup", "1") != "0"}


def parse_net(key: str, value: str, kind: str) -> dict:
    first, opts = options(value)
    mac = opts.get("hwaddr", "")
    model = ""
    if kind == "qemu" and "=" in str(value).split(",")[0]:  # virtio=AA:BB:…,bridge=vmbr0
        model, _, mac = str(value).split(",")[0].partition("=")
    return {"key": key, "name": opts.get("name", "") or key, "bridge": opts.get("bridge", ""), "mac": mac.lower(),
            "model": model, "vlan": opts.get("tag", ""), "ip": opts.get("ip", ""), "gw": opts.get("gw", ""),
            "ip6": opts.get("ip6", ""), "firewall": opts.get("firewall", "0") == "1", "rate": opts.get("rate", "")}


def parse_config(config: dict, kind: str) -> dict:
    disks = [d for k, v in config.items() if DISK_KEY.match(k) and (d := parse_disk(k, v))]
    nets = [parse_net(k, v, kind) for k, v in config.items() if NET_KEY.match(k)]
    disks.sort(key=lambda d: (d["key"] != "rootfs", d["key"]))
    nets.sort(key=lambda n: n["key"])
    features = dict(options("," + config.get("features", ""))[1]) if config.get("features") else {}
    return {
        "cores": int(config.get("cores") or (1 if kind == "lxc" else 1)),
        "sockets": int(config.get("sockets") or 1),
        "memory": int(config.get("memory") or 0),
        "swap": int(config.get("swap") or 0) if kind == "lxc" else None,
        "balloon": config.get("balloon"),
        "disks": disks,
        "nets": nets,
        "ostype": config.get("ostype", ""),
        "hostname": config.get("hostname") or config.get("name", ""),
        "onboot": str(config.get("onboot", "0")) == "1",
        "startup": config.get("startup", ""),
        "unprivileged": str(config.get("unprivileged", "0")) == "1" if kind == "lxc" else None,
        "features": features,
        "tags": [t for t in re.split(r"[;, ]+", config.get("tags", "")) if t],
        "description": config.get("description", ""),
        "nameserver": config.get("nameserver", ""),
        "agent": str(config.get("agent", "0")).split(",")[0] == "1" if kind == "qemu" else None,
        "raw": {k: v for k, v in config.items() if k not in HIDDEN_KEYS},
    }


def guest_ips(node: str, kind: str, vmid: int) -> list[dict]:
    """Current IP addresses (LXC: interfaces endpoint; VM: QEMU guest agent)."""
    out = []
    try:
        if kind == "lxc":
            for i in request(f"/nodes/{node}/lxc/{vmid}/interfaces") or []:
                if i.get("name") == "lo":
                    continue
                for key in ("inet", "inet6"):
                    for addr in str(i.get(key) or "").split():
                        if not addr.startswith("fe80"):
                            out.append({"interface": i.get("name", ""), "address": addr})
        else:
            data = request(f"/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces") or {}
            for i in data.get("result", []):
                if i.get("name") == "lo":
                    continue
                for a in i.get("ip-addresses") or []:
                    ip = a.get("ip-address", "")
                    if ip and not ip.startswith(("fe80", "127.")) and ip != "::1":
                        out.append({"interface": i.get("name", ""), "address": f"{ip}/{a.get('prefix', '')}"})
    except ProxmoxError:
        pass  # no guest agent / old Proxmox – addresses stay unknown
    return out


MASKED_CONF_KEYS = ("cipassword", "sshkeys")
MAX_CONF = 64 * 1024


def mask_conf(text: str) -> str:
    lines = []
    for line in text.splitlines():
        key = line.split(":", 1)[0].strip()
        lines.append(f"{key}: ••••••" if key in MASKED_CONF_KEYS and ":" in line else line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def conf_path(node: str, kind: str, vmid: int) -> str:
    return f"/etc/pve/nodes/{node}/{'lxc' if kind == 'lxc' else 'qemu-server'}/{vmid}.conf"


def conf_from_api(config: dict) -> str:
    """The file as Proxmox writes it: description as comment lines, then key: value."""
    lines = [f"#{line}" for line in str(config.get("description", "")).rstrip("\n").split("\n")
             if config.get("description")]
    for key in sorted(k for k in config if k not in ("description", "digest")):
        lines.append(f"{key}: {config[key]}")
    return mask_conf("\n".join(lines) + "\n")


def read_conf(node: str, kind: str, vmid: int, config: dict) -> dict:
    """The real .conf file when the agent runs on the Proxmox host, otherwise rebuilt from the API."""
    path = conf_path(node, kind, vmid)
    local = os.environ.get("XT_HOST_ROOT", "").rstrip("/") + path
    try:
        if os.path.getsize(local) <= MAX_CONF:
            with open(local, encoding="utf-8", errors="replace") as f:
                return {"path": path, "source": "file", "content": mask_conf(f.read())}
    except OSError:
        pass
    return {"path": path, "source": "api", "content": conf_from_api(config)}


def guest_details(g: dict) -> dict:
    node, kind, vmid = g["node"], g["type"], g["vmid"]
    out: dict = {"fetched_at": time.time()}
    try:
        raw = request(f"/nodes/{node}/{kind}/{vmid}/config") or {}
        out["config"] = parse_config(raw, kind)
        out["conf"] = read_conf(node, kind, vmid, raw)
    except ProxmoxError as error:
        out["error"] = str(error)
        return out
    if g.get("status") == "running":
        out["ips"] = guest_ips(node, kind, vmid)
    try:
        snaps = request(f"/nodes/{node}/{kind}/{vmid}/snapshot") or []
        out["snapshots"] = sorted(({"name": s.get("name", ""), "time": s.get("snaptime"),
                                    "description": (s.get("description") or "").strip(), "parent": s.get("parent", "")}
                                   for s in snaps if s.get("name") != "current"), key=lambda s: s["time"] or 0)
    except ProxmoxError:
        out["snapshots"] = None
    return out


def backups(storages: list[dict]) -> list[dict]:
    out, seen = [], set()
    for s in storages:
        if "backup" not in (s.get("content") or "") or s.get("status") != "available":
            continue
        shared = s.get("plugintype") in ("nfs", "cifs", "pbs", "cephfs", "rbd", "glusterfs")
        key = s["storage"] if shared else f"{s['node']}/{s['storage']}"
        if key in seen:  # shared storage: list it once
            continue
        seen.add(key)
        try:
            items = request(f"/nodes/{s['node']}/storage/{s['storage']}/content", data=None) or []
        except ProxmoxError:
            continue
        for b in items:
            if b.get("content") == "backup":
                out.append({"vmid": b.get("vmid"), "storage": s["storage"], "volid": b.get("volid", ""),
                            "time": b.get("ctime"), "size": b.get("size"), "notes": (b.get("notes") or "")[:200],
                            "protected": bool(b.get("protected"))})
    out.sort(key=lambda b: b["time"] or 0, reverse=True)
    return out[:500]


def local_updates() -> list[str] | None:
    """When the agent runs on the Proxmox host itself: upgradable packages from the local apt lists."""
    if not shutil.which("apt"):
        return None
    try:
        out = subprocess.run(["apt", "list", "--upgradable"], capture_output=True, text=True, timeout=60,
                             env={**os.environ, "LANG": "C"})
    except (OSError, subprocess.TimeoutExpired):
        return None
    return [line.split("/")[0] for line in out.stdout.splitlines() if "/" in line and "[upgradable" in line]


def node_details(node: str) -> dict:
    out: dict = {}
    try:
        status = request(f"/nodes/{node}/status") or {}
        out["pveversion"] = status.get("pveversion", "")
        out["kernel"] = status.get("kversion", "")
        cpu = status.get("cpuinfo") or {}
        out["cpu_model"] = cpu.get("model", "")
        out["boot_mode"] = (status.get("boot-info") or {}).get("mode", "")
    except ProxmoxError as error:
        out["error"] = str(error)
    try:
        version = request(f"/nodes/{node}/version") or {}
        out["version"] = version.get("version", "")
        out["release"] = version.get("release", "")
    except ProxmoxError:
        pass
    try:
        updates = request(f"/nodes/{node}/apt/update") or []
        out["updates"] = sorted(u.get("Package", "") for u in updates)
    except ProxmoxError:
        local = local_updates() if urllib.parse.urlparse(base_url()).hostname in ("127.0.0.1", "localhost", "::1") \
            else None
        out["updates"] = local  # None = unknown (token may not read apt and agent is not on the host)
    try:
        nets = request(f"/nodes/{node}/network") or []
        out["network"] = sorted(({"iface": n.get("iface", ""), "type": n.get("type", ""), "active": bool(n.get("active")),
                                  "autostart": bool(n.get("autostart")), "cidr": n.get("cidr", "") or n.get("address", ""),
                                  "cidr6": n.get("cidr6", ""), "gateway": n.get("gateway", ""),
                                  "ports": n.get("bridge_ports", "") or n.get("slaves", ""),
                                  "vlan_aware": bool(n.get("bridge_vlan_aware")), "vlan_id": n.get("vlan-id", ""),
                                  "comments": (n.get("comments") or "").strip()} for n in nets),
                                key=lambda n: (n["type"] not in ("bridge", "OVSBridge"), n["iface"]))
    except ProxmoxError:
        out["network"] = None
    return out


def details(overview: dict) -> dict:
    return {
        "fetched_at": time.time(),
        "guests": {f"{g['node']}/{g['vmid']}": guest_details(g) for g in overview.get("guests", [])},
        "backups": backups(overview.get("storage", [])),
        "nodes": {n["name"]: node_details(n["name"]) for n in overview.get("nodes", []) if n.get("status") == "online"},
    }


# --- Changes -------------------------------------------------------------------------------

POWER = ("start", "shutdown", "stop", "reboot")
TAGS = re.compile(r"^[a-z0-9_+.-]{1,40}$")


def check_guest(params: dict) -> tuple[str, str, int]:
    node, kind, vmid = str(params.get("node", "")), params.get("type"), params.get("vmid")
    if kind not in ("lxc", "qemu") or not str(vmid).isdigit() or not re.match(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,63}$", node):
        raise ValueError("Invalid Proxmox command")
    return node, kind, int(vmid)


def power(action: str, params: dict) -> None:
    if action not in POWER:
        raise ValueError("Invalid Proxmox command")
    node, kind, vmid = check_guest(params)
    try:
        request(f"/nodes/{node}/{kind}/{vmid}/status/{action}", method="POST", data={}, timeout=30)
    except ProxmoxError as error:
        hint = " – the API token needs the privilege VM.PowerMgmt" if ("401" in str(error) or "403" in str(error)) else ""
        raise ValueError(f"{error}{hint}") from None


def validate_changes(changes: dict, kind: str) -> dict:
    """Only these options can be changed – everything else is refused."""
    out: dict = {}
    for key, value in (changes or {}).items():
        if key == "cores":
            if not isinstance(value, int) or not 1 <= value <= 512:
                raise ValueError("cores: 1–512")
        elif key == "memory":
            if not isinstance(value, int) or not 16 <= value <= 4 * 1024 * 1024:
                raise ValueError("memory: 16 MB – 4 TB")
        elif key == "swap":
            if kind != "lxc" or not isinstance(value, int) or not 0 <= value <= 4 * 1024 * 1024:
                raise ValueError("swap: only for LXC, 0 – 4 TB")
        elif key == "onboot":
            if not isinstance(value, bool):
                raise ValueError("onboot: true/false")
            value = int(value)
        elif key == "description":
            if not isinstance(value, str) or len(value) > 8000:
                raise ValueError("description: up to 8000 characters")
        elif key == "tags":
            if not isinstance(value, list) or len(value) > 20 or not all(isinstance(t, str) and TAGS.match(t) for t in value):
                raise ValueError("tags: lowercase letters, digits, - _ . +")
            value = ";".join(value)
        else:
            raise ValueError(f"{key} cannot be changed here")
        out[key] = value
    if not out:
        raise ValueError("Nothing to change")
    return out


def change_config(params: dict) -> None:
    node, kind, vmid = check_guest(params)
    changes = validate_changes(params.get("changes") or {}, kind)
    data: dict = {k: v for k, v in changes.items() if v != ""}
    empty = [k for k, v in changes.items() if v == ""]
    if empty:
        data["delete"] = ",".join(empty)
    try:
        request(f"/nodes/{node}/{kind}/{vmid}/config", method="PUT", data=data, timeout=30)
    except ProxmoxError as error:
        hint = (" – the API token needs VM.Config.CPU, VM.Config.Memory and VM.Config.Options"
                if ("401" in str(error) or "403" in str(error)) else "")
        raise ValueError(f"{error}{hint}") from None


def resize_disk(params: dict) -> None:
    node, kind, vmid = check_guest(params)
    disk, add = str(params.get("disk", "")), params.get("add_gb")
    if not DISK_KEY.match(disk) or disk.startswith(("efidisk", "tpmstate")):
        raise ValueError("Invalid disk")
    if not isinstance(add, int) or not 1 <= add <= 4096:
        raise ValueError("Grow by 1–4096 GB")
    try:
        request(f"/nodes/{node}/{kind}/{vmid}/resize", method="PUT", data={"disk": disk, "size": f"+{add}G"},
                timeout=120)
    except ProxmoxError as error:
        hint = (" – the API token needs VM.Config.Disk and Datastore.AllocateSpace"
                if ("401" in str(error) or "403" in str(error)) else "")
        raise ValueError(f"{error}{hint}") from None
