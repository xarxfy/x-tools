"""Agent mode (``x-tools agent``): runs on another server and reports to X-TOOLS.

Collects Docker (if the socket is mounted), host metrics and optionally Proxmox,
and POSTs them every minute to <XT_AGENT_URL>/api/agent/report. Outbound HTTPS
only – the agent never receives commands. Secrets in files are masked before
anything leaves the machine.

Environment:
  XT_AGENT_URL, XT_AGENT_KEY            where to report, key from Settings → Agents
  XT_AGENT_INTERVAL                     seconds (default 60, min 30)
  XT_AGENT_CONTROL                      1 = accept commands from X-TOOLS (start/stop containers and
                                        Proxmox guests, read logs). Off by default.
  CF_ACCESS_CLIENT_ID/_SECRET           optional Cloudflare Access service token
  PROXMOX_URL, PROXMOX_TOKEN_ID, PROXMOX_TOKEN_SECRET, PROXMOX_VERIFY_TLS (0/1)
"""

import json
import os
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request

from app.collector.collector import collect_snapshot, host_path, system_info
from app.core.config import get_settings
from app.collector.httpjson import post_json

AGENT_VERSION = "3"


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


def _proxmox_ctx():
    ctx = ssl.create_default_context()
    if os.environ.get("PROXMOX_VERIFY_TLS", "0") == "0":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


PROXMOX_ACTIONS = ("start", "shutdown", "stop", "reboot")
DOCKER_ACTIONS = ("start", "stop", "restart", "logs")


def proxmox_action(action: str, params: dict) -> None:
    """Power action for one guest. The API token needs VM.PowerMgmt for this."""
    url = os.environ.get("PROXMOX_URL", "").rstrip("/")
    if not url:
        raise ValueError("Proxmox is not configured on this agent")
    node, kind, vmid = str(params.get("node", "")), params.get("type"), params.get("vmid")
    if action not in PROXMOX_ACTIONS or kind not in ("lxc", "qemu") or not str(vmid).isdigit() \
            or not node.replace("-", "").replace(".", "").isalnum():
        raise ValueError("Invalid Proxmox command")
    token = f"PVEAPIToken={os.environ.get('PROXMOX_TOKEN_ID', '')}={os.environ.get('PROXMOX_TOKEN_SECRET', '')}"
    req = urllib.request.Request(f"{url}/api2/json/nodes/{node}/{kind}/{int(vmid)}/status/{action}", data=b"",
                                 method="POST", headers={"Authorization": token})
    try:
        with urllib.request.urlopen(req, timeout=30, context=_proxmox_ctx()):
            pass
    except urllib.error.HTTPError as error:
        hint = " – the API token needs the privilege VM.PowerMgmt" if error.code in (401, 403) else ""
        raise OSError(f"Proxmox API: HTTP {error.code}{hint}") from None
    except (urllib.error.URLError, OSError) as error:
        raise OSError(f"Proxmox API not reachable: {getattr(error, 'reason', error)}") from None


def execute(command: dict) -> dict:
    """Run one command from X-TOOLS – only the fixed set of actions is possible."""
    from app.collector.collector import docker_action, docker_logs
    action, target, params = command.get("action", ""), str(command.get("target", "")), command.get("params") or {}
    try:
        area, _, verb = action.partition(".")
        if area == "docker" and verb in DOCKER_ACTIONS:
            if os.environ.get("XT_AGENT_DOCKER", "1") == "0":
                raise ValueError("Docker is not enabled on this agent")
            if verb == "logs":
                return {"ok": True, "logs": docker_logs(target, params.get("lines"))}
            docker_action(verb, target)
        elif area == "proxmox" and verb in PROXMOX_ACTIONS:
            proxmox_action(verb, {**params, "vmid": target})
        else:
            raise ValueError("Unknown command")
        return {"ok": True}
    except (ValueError, OSError) as error:
        return {"ok": False, "error": str(error)[:300]}


def get_json(url: str, headers: dict, timeout: float) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "x-tools", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read() or b"null")
    except urllib.error.HTTPError as error:
        raise OSError(f"HTTP {error.code}") from None
    except urllib.error.URLError as error:
        raise OSError(f"not reachable ({error.reason})") from None


def command_loop(url: str, headers: dict, report_now) -> None:
    """Long-poll X-TOOLS for commands (outbound only) and send the results back."""
    while True:
        try:
            commands = get_json(url + "/api/agent/commands?wait=25", headers, timeout=40) or []
            for command in commands:
                result = execute(command)
                print(f"Command {command.get('action')} {command.get('target')}: "
                      f"{'ok' if result['ok'] else result.get('error')}", flush=True)
                post_json(f"{url}/api/agent/commands/{command['id']}", result, headers, timeout=60)
                if result["ok"] and not command.get("action", "").endswith(".logs"):
                    report_now.set()  # show the new state soon
        except (OSError, ValueError) as error:
            print(f"Command polling failed: {error}", flush=True)
            time.sleep(15)


def hostname() -> str:
    try:
        return host_path("/etc/hostname").read_text().strip() or socket.gethostname()
    except OSError:
        return socket.gethostname()


def build_report() -> dict:
    has_docker = os.environ.get("XT_AGENT_DOCKER", "1") != "0" and os.path.exists(get_settings().docker_socket)
    docker = collect_snapshot() if has_docker else None
    return {"version": AGENT_VERSION, "hostname": hostname(), "sent_at": time.time(),
            "control": os.environ.get("XT_AGENT_CONTROL", "0") == "1",
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
    control = os.environ.get("XT_AGENT_CONTROL", "0") == "1"
    print(f"X-TOOLS agent: reporting every {interval}s to {url} "
          f"(Docker: {'yes' if os.path.exists(get_settings().docker_socket) else 'no'}, "
          f"Proxmox: {'yes' if os.environ.get('PROXMOX_URL') else 'no'}, "
          f"control: {'on' if control else 'off'})", flush=True)
    report_now = threading.Event()
    if control:
        threading.Thread(target=command_loop, args=(url, headers, report_now), daemon=True).start()
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
        report_now.wait(interval)
        if report_now.is_set():
            report_now.clear()
            time.sleep(3)  # give Docker/Proxmox a moment to change state
