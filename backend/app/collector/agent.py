"""Agent mode (``x-tools agent``): runs on another server and reports to X-TOOLS.

Collects Docker (if the socket is mounted), host metrics and optionally Proxmox,
and POSTs them every minute to <XT_AGENT_URL>/api/agent/report. Outbound HTTPS
only – the agent never receives commands. Secrets in files are masked before
anything leaves the machine.

Environment:
  XT_AGENT_URL, XT_AGENT_KEY            where to report, key from Settings → Agents
  XT_AGENT_INTERVAL                     seconds (default 60, min 30)
  XT_AGENT_CONTROL                      1 = accept commands from X-TOOLS (start/stop containers, Proxmox
                                        guests and systemd services, read logs, reboot; on Linux servers also
                                        install updates, manage users/SSH keys and the ufw firewall). Off by default.
  XT_AGENT_LINUX                        1 = report systemd services, ports, disks and updates of this server
  XT_AGENT_DOCKER                       0 = ignore Docker even if the socket exists
  CF_ACCESS_CLIENT_ID/_SECRET           optional Cloudflare Access service token
  PROXMOX_URL, PROXMOX_TOKEN_ID, PROXMOX_TOKEN_SECRET, PROXMOX_VERIFY_TLS (0/1)
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from app.collector import linux, linux_admin, proxmox
from app.collector.collector import collect_snapshot, host_path, system_info
from app.core.config import get_settings
from app.collector.httpjson import post_json

AGENT_VERSION = "8"


DETAILS_INTERVAL = max(120, int(os.environ.get("XT_PROXMOX_DETAILS_INTERVAL", "600")))
_details: dict = {"data": None, "at": 0.0, "due": True}


def proxmox_info() -> dict | None:
    """Overview every report; configuration details every few minutes (and right after changes)."""
    overview = proxmox.info()
    if not overview or overview.get("error"):
        return overview
    if _details["due"] or time.time() - _details["at"] > DETAILS_INTERVAL:
        try:
            _details["data"] = proxmox.details(overview)
        except Exception as error:  # noqa: BLE001 – details must never stop the report
            _details["data"] = {"error": str(error)[:300], "fetched_at": time.time()}
        _details["at"], _details["due"] = time.time(), False
    return {**overview, "details": _details["data"]}


LINUX_DETAILS_INTERVAL = max(120, int(os.environ.get("XT_LINUX_DETAILS_INTERVAL", "600")))
_linux: dict = {"data": None, "at": 0.0, "dirty": set()}
_fast = threading.Event()  # set after an administration action: report at once, without waiting


def _read_part(data: dict, key: str) -> None:
    fn = linux_admin.users if key == "users" else linux_admin.ufw_status
    try:
        data[key] = fn()
    except Exception as error:  # noqa: BLE001
        data[key] = None if key == "users" else {"installed": True, "error": str(error)[:200]}


def linux_info() -> dict | None:
    """Services, ports and disks every report; OS and update information every few minutes."""
    if os.environ.get("XT_AGENT_LINUX", "0") != "1":
        return None
    job = linux_admin.update_job()
    finished = bool(job and job["finished"] and job["finished"] > _linux["at"])  # new package state after an update
    if _linux["data"] is None or finished or time.time() - _linux["at"] > LINUX_DETAILS_INTERVAL:
        try:
            _linux["data"] = linux.details()
            _read_part(_linux["data"], "users")
            _read_part(_linux["data"], "firewall")
        except Exception as error:  # noqa: BLE001 – must never stop the report
            _linux["data"] = {"error": str(error)[:300], "fetched_at": time.time()}
        _linux["at"] = time.time()
        _linux["dirty"].clear()
    while _linux["dirty"]:  # after an action only the changed part is read again (fast)
        _read_part(_linux["data"], _linux["dirty"].pop())
    out = {**_linux["data"], "collected_at": time.time(), "update_job": job}
    for key, fn in (("services", linux.services), ("ports", linux.ports), ("disks", linux.disks)):
        try:
            out[key] = fn()
        except Exception as error:  # noqa: BLE001
            out[key] = None
            out["error"] = str(error)[:300]
    return out


DOCKER_ACTIONS = ("start", "stop", "restart", "logs")


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
        elif area == "proxmox" and verb in proxmox.POWER:
            proxmox.power(verb, {**params, "vmid": target})
            _details["due"] = True
        elif area == "systemd" and verb in linux.VERBS:
            if os.environ.get("XT_AGENT_LINUX", "0") != "1":
                raise ValueError("Linux server mode is not enabled on this agent")
            result = linux.service_action(verb, target, params.get("lines"))
            return result
        elif action in linux_admin.ACTIONS:
            if os.environ.get("XT_AGENT_LINUX", "0") != "1":
                raise ValueError("Linux server mode is not enabled on this agent")
            result = linux_admin.admin_action(action, target, params)
            if action != "system.update":  # the update refreshes everything itself when it is done
                _linux["dirty"].update(("users", "firewall"))
                _fast.set()
            return result
        elif action == "system.reboot":
            if os.environ.get("XT_AGENT_LINUX", "0") != "1":
                raise ValueError("Linux server mode is not enabled on this agent")
            return linux.reboot()
        elif action == "proxmox.config":
            proxmox.change_config({**params, "vmid": target})
            _details["due"] = True
        elif action == "proxmox.resize":
            proxmox.resize_disk({**params, "vmid": target})
            _details["due"] = True
        else:
            raise ValueError("Unknown command")
        return {"ok": True}
    except (ValueError, OSError, subprocess.SubprocessError) as error:  # AdminError is a ValueError
        return {"ok": False, "error": str(error)[:480]}


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


_network: dict = {"data": [], "at": 0.0}


def network_info() -> list[dict]:
    """Interfaces and IP addresses of this machine (every few minutes; every kind of agent reports them)."""
    if time.time() - _network["at"] > LINUX_DETAILS_INTERVAL or not _network["at"]:
        try:
            _network["data"] = linux.interfaces()
        except Exception:  # noqa: BLE001 – must never stop the report
            _network["data"] = []
        _network["at"] = time.time()
    return _network["data"]


def build_report() -> dict:
    has_docker = os.environ.get("XT_AGENT_DOCKER", "1") != "0" and os.path.exists(get_settings().docker_socket)
    docker = collect_snapshot() if has_docker else None
    return {"version": AGENT_VERSION, "hostname": hostname(), "sent_at": time.time(),
            "control": os.environ.get("XT_AGENT_CONTROL", "0") == "1",
            "system": (docker or {}).get("system") or system_info(), "docker": docker, "proxmox": proxmox_info(),
            "linux": linux_info(), "network": network_info()}


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
          f"(Docker: {'yes' if os.environ.get('XT_AGENT_DOCKER', '1') != '0' and os.path.exists(get_settings().docker_socket) else 'no'}, "
          f"Proxmox: {'yes' if os.environ.get('PROXMOX_URL') else 'no'}, "
          f"Linux: {'yes' if os.environ.get('XT_AGENT_LINUX') == '1' else 'no'}, "
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
        # while an update runs, report more often so that X-TOOLS shows its log almost live
        report_now.wait(10 if (linux_admin.update_job() or {}).get("state") == "running" else interval)
        if report_now.is_set():
            report_now.clear()
            time.sleep(0 if _fast.is_set() else 3)  # give Docker/Proxmox a moment to change state
            _fast.clear()
