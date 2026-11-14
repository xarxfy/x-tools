"""The collector loop: snapshot of Docker + system, execution of queued commands."""

import http.client
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.collector import dockerapi
from app.collector.exchange import (
    COMMAND_ID, COMMAND_MAX_AGE, CONTAINER_NAME, STOP_TIMEOUT, ActionError, check_action, commands_dir,
    exchange_dir, write_json,
)
from app.collector.masking import mask_inline, mask_secrets, mask_url
from app.core.config import get_settings

MAX_FILE = 256 * 1024
MAX_DOCKERFILES = 8
SKIP_DIRS = {"node_modules", "vendor", "venv", ".venv", "__pycache__", "build", "dist"}
FAST_INTERVAL = 5
LOG_LINES_DEFAULT, LOG_LINES_MAX = 300, 1000
LOG_TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.\d+)?Z ")


# --- Paths ------------------------------------------------------------------------


def host_path(path: str) -> Path:
    """Where a host path is visible to this process (below XT_HOST_ROOT in a container)."""
    root = get_settings().host_root.rstrip("/")
    return Path(root + path) if root else Path(path)


def allowed(path: str) -> bool:
    """Only files below the configured compose roots are read."""
    norm = os.path.normpath(path)
    return any(norm == r or norm.startswith(r + "/") for r in get_settings().compose_root_list)


def display_path(path: str) -> str:
    home = get_settings().home_dir.rstrip("/")
    if home and path == home:
        return "~"
    if home and path.startswith(home + "/"):
        return "~/" + path[len(home) + 1:]
    return path


def read_text(path: str) -> tuple[str | None, str | None]:
    if not allowed(path):
        return None, "Outside the configured compose roots (XT_COMPOSE_ROOTS)"
    p = host_path(path)
    try:
        if p.stat().st_size > MAX_FILE:
            return None, "File is too large"
        return mask_secrets(p.read_text(encoding="utf-8", errors="replace")), None
    except FileNotFoundError:
        return None, "Not readable – is the folder mounted into the collector?"
    except PermissionError:
        return None, "No permission to read"
    except OSError as error:
        return None, str(error)


def is_dockerfile(name: str) -> bool:
    low = name.lower()
    return low == "dockerfile" or low.startswith("dockerfile.") or low.endswith(".dockerfile")


def find_dockerfiles(workdir: str) -> list[dict]:
    """Dockerfiles in the project folder (up to 3 levels deep, without node_modules etc.)."""
    if not allowed(workdir):
        return []
    base = host_path(workdir)
    found: list[dict] = []
    if not base.is_dir():
        return found
    for root, dirs, files in os.walk(base):
        depth = len(Path(root).relative_to(base).parts)
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")) if depth < 3 else []
        for name in sorted(files):
            if is_dockerfile(name):
                path = workdir.rstrip("/") + "/" + str((Path(root) / name).relative_to(base))
                content, error = read_text(path)
                found.append({"path": path, "content": content, "error": error})
        if len(found) >= MAX_DOCKERFILES:
            break
    return found[:MAX_DOCKERFILES]


def git_info(workdir: str) -> dict | None:
    """Branch, last commit and uncommitted changes of a project folder (read-only)."""
    if not allowed(workdir):
        return None
    path = host_path(workdir)
    if not (path / ".git").exists():
        return None

    def git(*args):
        out = subprocess.run(["git", "--no-optional-locks", "-c", f"safe.directory={path}", "-C", str(path), *args],
                             capture_output=True, text=True, timeout=10,
                             env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        if out.returncode != 0:
            raise OSError(out.stderr.strip() or "git error")
        return out.stdout.strip()

    try:
        sha, subject, author, ts = git("log", "-1", "--format=%h%x1f%s%x1f%an%x1f%ct").split("\x1f")
        info = {"commit": sha, "subject": subject, "author": author, "time": int(ts),
                "branch": git("rev-parse", "--abbrev-ref", "HEAD")}
        try:
            info["remote"] = mask_url(git("config", "--get", "remote.origin.url"))
        except OSError:
            info["remote"] = ""
        info["dirty"] = len([l for l in git("status", "--porcelain", "--untracked-files=no").splitlines() if l])
        return info
    except subprocess.TimeoutExpired:
        return {"error": "git does not answer"}
    except (OSError, ValueError) as error:
        return {"error": str(error)[:200]}


# --- Snapshot ---------------------------------------------------------------------


def system_info() -> dict:
    """Host metrics. /proc inside a container shows the host's values."""
    info: dict = {"cpus": os.cpu_count() or 1}
    try:
        info["uptime"] = float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        pass
    try:
        info["load"] = [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]]
    except (OSError, ValueError):
        pass
    try:
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, value = line.partition(":")
            mem[key] = int(value.split()[0]) * 1024
        info["mem_total"] = mem["MemTotal"]
        info["mem_used"] = mem["MemTotal"] - mem.get("MemAvailable", mem.get("MemFree", 0))
    except (OSError, ValueError, KeyError, IndexError):
        pass
    roots = get_settings().compose_root_list
    for candidate in [host_path(r) for r in roots] + [Path("/")]:
        try:
            st = os.statvfs(candidate)
        except OSError:
            continue
        used = (st.f_blocks - st.f_bfree) * st.f_frsize
        info["disk_used"], info["disk_total"] = used, used + st.f_bavail * st.f_frsize  # like df
        break
    try:
        info["hostname"] = host_path("/etc/hostname").read_text().strip()[:100]
    except OSError:
        pass
    return info


def container_info(c: dict) -> dict:
    labels = c.get("Labels") or {}
    ports = set()
    for p in c.get("Ports") or []:
        if p.get("PublicPort"):
            ip = p.get("IP") or ""
            ports.add((p["PublicPort"], p.get("PrivatePort"), p.get("Type", "tcp"),
                       "" if ip in ("", "0.0.0.0", "::") else ip))
    status = c.get("Status", "")
    health = re.search(r"\((healthy|unhealthy|health: starting)\)", status)
    return {
        "name": (c.get("Names") or ["?"])[0].lstrip("/"),
        "image": c.get("Image", ""),
        "state": c.get("State", ""),
        "health": health.group(1) if health else "",
        "status": status,
        "service": labels.get("com.docker.compose.service", ""),
        "ports": [{"public": a, "private": b, "proto": t, "ip": ip} for a, b, t, ip in sorted(ports)],
        "created": c.get("Created", 0),
    }


def collect_snapshot() -> dict:
    snap = {"collected_at": time.time(), "error": None, "docker": "", "system": system_info(), "projects": [],
            "containers": []}
    try:
        version = dockerapi.get("/version")
        containers = dockerapi.get("/containers/json?all=1")
    except (OSError, ValueError, http.client.HTTPException) as error:
        snap["error"] = f"Docker not reachable: {error}"
        return snap
    snap["docker"] = version.get("Version", "")
    projects: dict[str, dict] = {}
    for c in containers:
        labels = c.get("Labels") or {}
        name = labels.get("com.docker.compose.project")
        info = container_info(c)
        if not name:
            snap["containers"].append(info)
            continue
        p = projects.setdefault(name, {
            "name": name,
            "working_dir": labels.get("com.docker.compose.project.working_dir", ""),
            "config_files": [f for f in labels.get("com.docker.compose.project.config_files", "").split(",") if f],
            "containers": [],
        })
        p["containers"].append(info)
    for p in projects.values():
        wd = p["working_dir"]
        p["folder"] = display_path(wd) if wd else ""
        p["compose"] = [{"path": f, **dict(zip(("content", "error"), read_text(f)))} for f in p["config_files"]]
        p["dockerfiles"] = find_dockerfiles(wd) if wd else []
        p["git"] = git_info(wd) if wd else None
        p["containers"].sort(key=lambda c: c["name"])
    snap["projects"] = sorted(projects.values(), key=lambda p: p["name"].lower())
    snap["containers"].sort(key=lambda c: c["name"])
    return snap


# --- Commands ---------------------------------------------------------------------


def docker_action(action: str, name: str) -> None:
    check_action(action, name)
    names = {n.lstrip("/") for c in dockerapi.get("/containers/json?all=1") for n in c.get("Names") or []}
    if name not in names:
        raise ActionError(f"Container '{name}' does not exist")
    query = f"?t={STOP_TIMEOUT}" if action in ("stop", "restart") else ""
    status, body = dockerapi.post(f"/containers/{name}/{action}{query}", timeout=STOP_TIMEOUT + 30)
    if status not in (204, 304):  # 304 = already started/stopped
        try:
            message = json.loads(body).get("message", "")
        except ValueError:
            message = ""
        raise OSError(f"Docker answered HTTP {status}{': ' + message if message else ''}")


def demux(raw: bytes) -> bytes:
    """Without a TTY Docker sends frames: 8 byte header (stream, 0, 0, 0, size) + payload."""
    chunks, i = [], 0
    while i + 8 <= len(raw):
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        chunks.append(raw[i + 8:i + 8 + size])
        i += 8 + size
    return b"".join(chunks)


def format_logs(raw: bytes, tz: ZoneInfo) -> str:
    out = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        m = LOG_TS.match(line)
        if m:
            stamp = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            line = stamp.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S") + "  " + line[m.end():]
        out.append(line)
    return mask_inline("\n".join(out))[-400_000:]


def docker_logs(name: str, lines) -> str:
    """Last lines (stdout + stderr) of a container, local time, secrets masked."""
    if not CONTAINER_NAME.match(name or ""):
        raise ActionError("Invalid container name")
    lines = max(10, min(LOG_LINES_MAX, int(lines or LOG_LINES_DEFAULT)))
    tty = (dockerapi.get(f"/containers/{name}/json").get("Config") or {}).get("Tty", False)
    raw = dockerapi.get_raw(f"/containers/{name}/logs?stdout=1&stderr=1&timestamps=1&tail={lines}", timeout=30)
    return format_logs(raw if tty else demux(raw), ZoneInfo(get_settings().timezone))


def take_commands() -> list[tuple[str, dict, bool]]:
    """Execute pending commands; returns [(id, result, changed_something)]."""
    results = []
    for f in sorted(commands_dir().glob("*.cmd.json")):
        cid = f.name.removesuffix(".cmd.json")
        try:
            cmd = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cmd = {}
        f.unlink(missing_ok=True)
        if not COMMAND_ID.match(cid):
            continue
        result: dict = {"ok": False, "error": None}
        action = cmd.get("action")
        if time.time() - float(cmd.get("requested_at") or 0) > COMMAND_MAX_AGE:
            result["error"] = "Command expired"
        else:
            try:
                if action == "logs":
                    result["logs"] = docker_logs(cmd.get("container"), cmd.get("lines"))
                else:
                    docker_action(action, cmd.get("container"))
                result["ok"] = True
            except (ValueError, OSError, http.client.HTTPException) as error:
                result["error"] = str(error)
        if action != "logs":
            print(f"{action} {cmd.get('container')}: {'ok' if result['ok'] else result['error']}", flush=True)
        results.append((cid, result, action != "logs"))
    return results


def in_transition(snap: dict) -> bool:
    containers = [c for p in snap.get("projects", []) for c in p["containers"]] + snap.get("containers", [])
    return any(c.get("state") in ("created", "restarting") or c.get("health") == "health: starting"
               for c in containers)


def run() -> None:
    interval = get_settings().collect_interval
    commands_dir().mkdir(parents=True, exist_ok=True)
    print(f"X-TOOLS collector: every {interval}s → {exchange_dir()}", flush=True)
    started, next_snapshot = time.time(), 0.0
    while True:
        results = []
        try:
            results = take_commands()
        except OSError as error:
            print(f"Cannot read commands: {error}", flush=True)
        if any(changed for _, _, changed in results) or time.time() >= next_snapshot:
            # Write the new state first, then the result – the UI reloads right after.
            snap = collect_snapshot()
            try:
                write_json(exchange_dir() / "snapshot.json", snap)
            except OSError as error:
                print(f"Cannot write snapshot: {error}", flush=True)
            if snap["error"]:
                print(snap["error"], flush=True)
            fast = time.time() - started < 30 or in_transition(snap)
            next_snapshot = time.time() + (FAST_INTERVAL if fast else interval)
        for cid, result, _ in results:
            try:
                write_json(commands_dir() / f"{cid}.result.json", result)
            except OSError as error:
                print(f"Cannot write result: {error}", flush=True)
        time.sleep(1)
