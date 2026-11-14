"""Agent mode (``x-tools agent``): runs on another server and reports to X-TOOLS.

Collects Docker (if the socket is mounted), host metrics and optionally Proxmox,
and POSTs them every minute to <XT_AGENT_URL>/api/agent/report. Outbound HTTPS
only – the agent never receives commands. Secrets in files are masked before
anything leaves the machine.

Environment:
  XT_AGENT_URL, XT_AGENT_KEY            where to report, key from Settings → Agents
  XT_AGENT_INTERVAL                     seconds (default 60, min 30)
  CF_ACCESS_CLIENT_ID/_SECRET           optional Cloudflare Access service token
  PROXMOX_URL, PROXMOX_TOKEN_ID, PROXMOX_TOKEN_SECRET, PROXMOX_VERIFY_TLS (0/1)
"""

import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request

from app.collector.collector import collect_snapshot, host_path, system_info
from app.core.config import get_settings
from app.monitor.notify import post_json

AGENT_VERSION = "2"


def proxmox_info() -> dict | None:
    """Nodes, guests (LXC/VM) and storage via the Proxmox API – read-only (role PVEAuditor is enough)."""
    url = os.environ.get("PROXMOX_URL", "").rstrip("/")
    if not url:
        return None
    token_id = os.environ.get("PROXMOX_TOKEN_ID", "")
    token_secret = os.environ.get("PROXMOX_TOKEN_SECRET", "")
    ctx = ssl.create_default_context()
    if os.environ.get("PROXMOX_VERIFY_TLS", "0") == "0":  # Proxmox usually has a self-signed certificate
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url + "/api2/json/cluster/resources",
                                 headers={"Authorization": f"PVEAPIToken={token_id}={token_secret}"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as res:
            data = json.loads(res.read()).get("data") or []
    except urllib.error.HTTPError as error:
        return {"error": f"Proxmox API: HTTP {error.code} – check token and permissions"}
    except (urllib.error.URLError, OSError, ValueError) as error:
        return {"error": f"Proxmox API not reachable: {getattr(error, 'reason', error)}"}
    keys = ("cpu", "maxcpu", "mem", "maxmem", "disk", "maxdisk", "uptime")
    nodes = [{"name": r.get("node", ""), "status": r.get("status", ""), **{k: r.get(k, 0) for k in keys}}
             for r in data if r.get("type") == "node"]
    guests = [{"vmid": r.get("vmid"), "name": r.get("name", ""), "type": r.get("type"), "status": r.get("status", ""),
               "node": r.get("node", ""), **{k: r.get(k, 0) for k in keys}}
              for r in data if r.get("type") in ("lxc", "qemu") and not r.get("template")]
    storage = [{"storage": r.get("storage", ""), "node": r.get("node", ""), "status": r.get("status", ""),
                "disk": r.get("disk", 0), "maxdisk": r.get("maxdisk", 0)}
               for r in data if r.get("type") == "storage" and r.get("maxdisk")]
    return {"nodes": sorted(nodes, key=lambda n: n["name"]),
            "guests": sorted(guests, key=lambda g: g["vmid"] or 0),
            "storage": sorted(storage, key=lambda s: (s["node"], s["storage"]))}


def hostname() -> str:
    try:
        return host_path("/etc/hostname").read_text().strip() or socket.gethostname()
    except OSError:
        return socket.gethostname()


def build_report() -> dict:
    has_docker = os.path.exists(get_settings().docker_socket)
    docker = collect_snapshot() if has_docker else None
    return {"version": AGENT_VERSION, "hostname": hostname(), "sent_at": time.time(),
            "system": (docker or {}).get("system") or system_info(), "docker": docker, "proxmox": proxmox_info()}


def run() -> None:
    url = os.environ.get("XT_AGENT_URL", "").rstrip("/")
    key = os.environ.get("XT_AGENT_KEY", "")
    if not url or not key:
        sys.exit("XT_AGENT_URL and XT_AGENT_KEY must be set (see deploy/agent/.env.example)")
    interval = max(30, int(os.environ.get("XT_AGENT_INTERVAL", "60")))
    headers = {"X-Agent-Key": key}
    if os.environ.get("CF_ACCESS_CLIENT_ID"):
        headers["CF-Access-Client-Id"] = os.environ["CF_ACCESS_CLIENT_ID"]
        headers["CF-Access-Client-Secret"] = os.environ.get("CF_ACCESS_CLIENT_SECRET", "")
    print(f"X-TOOLS agent: reporting every {interval}s to {url} "
          f"(Docker: {'yes' if os.path.exists(get_settings().docker_socket) else 'no'}, "
          f"Proxmox: {'yes' if os.environ.get('PROXMOX_URL') else 'no'})", flush=True)
    failures = 0
    while True:
        try:
            post_json(url + "/api/agent/report", build_report(), headers)
            if failures:
                print("Reporting works again", flush=True)
            failures = 0
        except (OSError, ValueError) as error:
            failures += 1
            if failures in (1, 5) or failures % 60 == 0:  # do not flood the log
                hint = ""
                if isinstance(error, ValueError) or "403" in str(error):
                    hint = (" – probably Cloudflare Access blocks the agent: check the service token and the "
                            "Access rule for /api/agent/report")
                if isinstance(error, ValueError):
                    error = "answer was not JSON (login page?)"
                print(f"Report failed ({failures}×): {error}{hint}", flush=True)
        time.sleep(interval)
