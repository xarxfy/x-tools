"""Files shared between the web process and the collector.

  snapshot.json            written by the collector
  commands/<id>.cmd.json   written by the web process
  commands/<id>.result.json written by the collector
"""

import json
import os
import re
import time
import uuid
from pathlib import Path

from app.core.config import get_settings

ACTIONS = ("start", "stop", "restart")
CONTAINER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
COMMAND_ID = re.compile(r"^[0-9a-f]{32}$")
STOP_TIMEOUT = 20  # seconds Docker gives a container to shut down
COMMAND_MAX_AGE = 120


class ActionError(ValueError):
    pass


def exchange_dir() -> Path:
    return get_settings().exchange_path


def commands_dir() -> Path:
    return exchange_dir() / "commands"


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def load_snapshot() -> dict | None:
    try:
        return json.loads((exchange_dir() / "snapshot.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        return {"error": f"Snapshot unreadable: {error}", "projects": [], "containers": [], "collected_at": 0}


def check_action(action: str, name: str) -> None:
    if action not in ACTIONS:
        raise ActionError("Unknown action")
    if not CONTAINER_NAME.match(name or ""):
        raise ActionError("Invalid container name")
    if name in get_settings().protected_list:
        raise ActionError(f"'{name}' is protected and cannot be controlled from here")


def known_containers(snap: dict | None) -> set[str]:
    snap = snap or {}
    names = {c["name"] for p in snap.get("projects", []) for c in p.get("containers", [])}
    return names | {c["name"] for c in snap.get("containers", [])}


def request(action: str, name: str, lines: int | None = None, timeout: float = STOP_TIMEOUT + 40) -> dict:
    """Web side: drop a command file and wait for the collector's result."""
    if action == "logs":  # reading logs is allowed for protected containers too
        if not CONTAINER_NAME.match(name or ""):
            raise ActionError("Invalid container name")
    else:
        check_action(action, name)
    if name not in known_containers(load_snapshot()):
        raise ActionError(f"Container '{name}' is not known")
    folder = commands_dir()
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.result.json"):  # clean up results nobody picked up
        if time.time() - old.stat().st_mtime > 600:
            old.unlink(missing_ok=True)
    cid = uuid.uuid4().hex
    cmd_file, result_file = folder / f"{cid}.cmd.json", folder / f"{cid}.result.json"
    write_json(cmd_file, {"action": action, "container": name, "lines": lines, "requested_at": time.time()})
    deadline = time.time() + timeout
    while time.time() < deadline:
        if result_file.exists():
            try:
                result = json.loads(result_file.read_text(encoding="utf-8"))
            except ValueError:
                time.sleep(0.2)
                continue
            result_file.unlink(missing_ok=True)
            return result
        time.sleep(0.3)
    cmd_file.unlink(missing_ok=True)
    raise TimeoutError("The collector does not answer – is the x-tools-collector container running?")
