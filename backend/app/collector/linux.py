"""Generic Linux server: systemd services, listening ports, disks, updates, reboot.

Used by the agent (kind "linux"). Everything is read from /proc, systemd and the local package cache – the agent
needs no extra credentials. Control is limited to start/stop/restart of systemd services, their logs and a reboot.
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from app.collector.proxmox import local_updates

UNIT = re.compile(r"^[A-Za-z0-9:_.@-]{1,120}\.service$")
VERBS = ("start", "stop", "restart", "logs")
# The agent itself: stopping or restarting it from within would cut off the answer.
PROTECTED = {"x-tools-agent.service"}
MAX_SERVICES = 400
REAL_FS = {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "f2fs", "vfat", "exfat", "ntfs", "ntfs3", "reiserfs", "jfs"}
LOG_LINES_MAX = 1000


def run(args: list[str], timeout: float = 20) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, env={**os.environ, "LANG": "C"})


# --- services -----------------------------------------------------------------------


def services() -> list[dict] | None:
    """Service units with state; None when systemd is not available."""
    if not shutil.which("systemctl"):
        return None
    try:
        listed = run(["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain", "--no-pager"])
        files = run(["systemctl", "list-unit-files", "--type=service", "--no-legend", "--no-pager"])
    except (OSError, subprocess.TimeoutExpired):
        return None
    if listed.returncode != 0:
        return None
    enabled = {}
    for line in files.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            enabled[parts[0]] = parts[1]
    out = []
    for line in listed.stdout.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4 or not UNIT.match(parts[0]):
            continue
        name, load, active, sub = parts[:4]
        if load == "not-found":
            continue
        out.append({"name": name, "active": active, "sub": sub, "enabled": enabled.get(name, ""),
                    "description": (parts[4] if len(parts) > 4 else "")[:120]})
    # Failed and running ones first; the rest (inactive, static helpers) only when enabled.
    out = [s for s in out if s["active"] in ("active", "failed", "activating", "reloading")
           or s["enabled"] == "enabled"]
    out.sort(key=lambda s: (s["active"] != "failed", s["name"]))
    return out[:MAX_SERVICES]


# --- ports --------------------------------------------------------------------------


def _hex_addr(value: str) -> str:
    host = value.rsplit(":", 1)[0]
    if len(host) == 8:  # IPv4, little endian
        return ".".join(str(int(host[i:i + 2], 16)) for i in (6, 4, 2, 0))
    return "::" if set(host) <= {"0"} else "[ipv6]"


def _socket_owners() -> dict[str, str]:
    owners: dict[str, str] = {}
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            name = (proc / "comm").read_text().strip()
            for fd in (proc / "fd").iterdir():
                target = os.readlink(fd)
                if target.startswith("socket:["):
                    owners.setdefault(target[8:-1], name)
        except OSError:
            continue
    return owners


def ports() -> list[dict]:
    found: dict[tuple, dict] = {}
    owners: dict[str, str] | None = None
    for proto, path in (("tcp", "/proc/net/tcp"), ("tcp", "/proc/net/tcp6"), ("udp", "/proc/net/udp"),
                        ("udp", "/proc/net/udp6")):
        try:
            lines = Path(path).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            f = line.split()
            if len(f) < 10:
                continue
            # tcp: state 0A = LISTEN; udp has no listen state, 07 = bound
            if f[3] != ("0A" if proto == "tcp" else "07"):
                continue
            try:
                port = int(f[1].rsplit(":", 1)[1], 16)
            except ValueError:
                continue
            if proto == "udp" and port < 1:
                continue
            if owners is None:
                owners = _socket_owners()
            addr = _hex_addr(f[1])
            found.setdefault((proto, port, addr), {"port": port, "proto": proto, "address": addr,
                                                    "process": owners.get(f[9], "")})
    return sorted(found.values(), key=lambda p: (p["proto"], p["port"]))[:300]


# --- disks, os, updates -------------------------------------------------------------


def disks() -> list[dict]:
    out, seen = [], set()
    try:
        mounts = Path("/proc/mounts").read_text().splitlines()
    except OSError:
        return out
    for line in mounts:
        dev, mount, fstype = (line.split() + ["", "", ""])[:3]
        mount = mount.replace("\\040", " ")
        if fstype not in REAL_FS or dev in seen or mount.startswith(("/var/lib/docker", "/snap")):
            continue
        seen.add(dev)
        try:
            st = os.statvfs(mount)
        except OSError:
            continue
        total = st.f_blocks * st.f_frsize
        if not total:
            continue
        used = (st.f_blocks - st.f_bfree) * st.f_frsize
        out.append({"mount": mount, "fstype": fstype, "used": used, "total": used + st.f_bavail * st.f_frsize})
    return sorted(out, key=lambda d: d["mount"])[:20]


def os_release() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            key, _, value = line.partition("=")
            if key in ("PRETTY_NAME", "ID", "VERSION_ID"):
                out[key] = value.strip().strip('"')[:100]
    except OSError:
        pass
    return out


def os_name() -> str:
    return os_release().get("PRETTY_NAME", "")


# --- network interfaces ---------------------------------------------------------------

VIRTUAL_IFACE = re.compile(r"^(veth|docker|br-|virbr|tap|fwbr|fwpr|fwln|cali|flannel|cni|tun|vxlan|kube)")


def _iface(name: str, mac: str, state: str, addrs: list[dict]) -> dict:
    return {"name": name, "mac": mac, "state": state, "virtual": bool(VIRTUAL_IFACE.match(name)), "addrs": addrs}


def _interfaces_ip() -> list[dict] | None:
    if not shutil.which("ip"):
        return None
    try:
        out = run(["ip", "-j", "addr", "show"], timeout=5)
        data = json.loads(out.stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    result = []
    for ifc in data:
        name = ifc.get("ifname", "")
        if not name or name == "lo":
            continue
        addrs = [{"ip": a["local"], "prefix": a.get("prefixlen")} for a in ifc.get("addr_info") or []
                 if a.get("local") and a.get("scope") == "global" and not a["local"].startswith("169.254.")]
        result.append(_iface(name, ifc.get("address", ""), ifc.get("operstate", "").lower(), addrs))
    return result


def _interfaces_proc() -> list[dict]:
    """Without iproute2: one IPv4 address per interface (ioctl) and the IPv6 ones from /proc."""
    import fcntl
    import ipaddress
    import socket
    import struct
    v6: dict[str, list[dict]] = {}
    try:
        for line in Path("/proc/net/if_inet6").read_text().splitlines():
            raw, _, prefix, scope, _, name = line.split()
            if scope == "00":  # global scope
                addr = ipaddress.IPv6Address(bytes.fromhex(raw))
                v6.setdefault(name, []).append({"ip": str(addr), "prefix": int(prefix, 16)})
    except (OSError, ValueError):
        pass
    result = []
    for _, name in socket.if_nameindex():
        if name == "lo":
            continue
        addrs = list(v6.get(name, []))
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                packed = struct.pack("256s", name.encode()[:15])
                ip = socket.inet_ntoa(fcntl.ioctl(sock.fileno(), 0x8915, packed)[20:24])  # SIOCGIFADDR
                mask = socket.inet_ntoa(fcntl.ioctl(sock.fileno(), 0x891B, packed)[20:24])  # SIOCGIFNETMASK
            if not ip.startswith("169.254."):
                addrs.insert(0, {"ip": ip, "prefix": ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen})
        except OSError:
            pass
        try:
            mac = Path(f"/sys/class/net/{name}/address").read_text().strip()
            state = Path(f"/sys/class/net/{name}/operstate").read_text().strip()
        except OSError:
            mac, state = "", ""
        result.append(_iface(name, mac, state, addrs))
    return result


def interfaces() -> list[dict]:
    """Network interfaces with their global IP addresses (loopback and link-local ones left out)."""
    found = _interfaces_ip()
    if found is None:
        found = _interfaces_proc()
    return [i for i in found if i["addrs"]][:40]


def dnf_updates() -> list[str] | None:
    exe = shutil.which("dnf") or shutil.which("yum")
    if not exe:
        return None
    try:
        out = run([exe, "-C", "-q", "check-update"], timeout=60)  # -C: cache only, nothing is written
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode not in (0, 100):
        return None
    return [l.split()[0].rsplit(".", 1)[0] for l in out.stdout.splitlines()
            if len(l.split()) == 3 and "." in l.split()[0]]


def details() -> dict:
    """Slow-changing facts: OS, kernel, pending updates, reboot flag."""
    updates = local_updates()
    if updates is None:
        updates = dnf_updates()
    uname = os.uname()
    rel = os_release()
    return {"os": rel.get("PRETTY_NAME", ""), "os_id": rel.get("ID", ""), "os_version": rel.get("VERSION_ID", ""), "kernel": uname.release, "arch": uname.machine, "updates": updates,
            "reboot_required": Path("/var/run/reboot-required").exists() or Path("/run/reboot-required").exists(),
            "fetched_at": time.time()}


# --- commands -----------------------------------------------------------------------


def service_action(verb: str, unit: str, lines: int | None = None) -> dict:
    if verb not in VERBS:
        raise ValueError("Unknown action")
    if not UNIT.match(unit or ""):
        raise ValueError("Invalid service name")
    if verb == "logs":
        n = max(10, min(int(lines or 300), LOG_LINES_MAX))
        out = run(["journalctl", "-u", unit, "-n", str(n), "--no-pager", "-o", "short-iso"], timeout=30)
        return {"ok": True, "logs": out.stdout or out.stderr}
    if unit in PROTECTED:
        raise ValueError(f"{unit} cannot be controlled from X-TOOLS")
    out = run(["systemctl", verb, unit], timeout=120)
    if out.returncode != 0:
        raise ValueError((out.stderr or out.stdout or f"systemctl {verb} failed").strip()[:300])
    return {"ok": True}


def reboot() -> dict:
    out = run(["systemctl", "reboot"], timeout=30)
    if out.returncode != 0:
        raise ValueError((out.stderr or out.stdout or "reboot failed").strip()[:300])
    return {"ok": True}
