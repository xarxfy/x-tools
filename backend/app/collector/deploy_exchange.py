"""Web side of the deployer: queue jobs and read their status (files in <exchange>/deploy).

  deploy/jobs/<id>.json      written here, read and deleted by the deployer (may contain a token)
  deploy/status/<site>.json  written by the deployer: state, log, commit
  deploy/alive               touched by the deployer every few seconds
"""

import json
import re
import time
import uuid
from pathlib import Path

from app.collector.exchange import exchange_dir, write_json

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,98}$")
COMPOSE_FILE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,98}$")
ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
REPO_URL = re.compile(r"^https?://[A-Za-z0-9.-]+(:\d{1,5})?/[A-Za-z0-9_./~%+-]+$")
ACTIONS = ("deploy", "stop", "remove")
ALIVE_MAX_AGE = 30
RUNNING_MAX_AGE = 20 * 60


def deploy_dir() -> Path:
    return exchange_dir() / "deploy"


def alive() -> bool:
    try:
        return time.time() - (deploy_dir() / "alive").stat().st_mtime < ALIVE_MAX_AGE
    except OSError:
        return False


def status(site_id: str) -> dict:
    try:
        data = json.loads((deploy_dir() / "status" / f"{site_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "none"}
    if data.get("state") == "running" and time.time() - data.get("updated", 0) > RUNNING_MAX_AGE:
        data["state"] = "failed"  # the deployer died in the middle of a job
    return data


def submit(action: str, site, token: str, env: dict[str, str], purge: bool = False) -> None:
    """Queue a job. ``site`` is a models.Site; the deployer validates everything again."""
    if action not in ACTIONS:
        raise ValueError("Unknown action")
    if status(site.id).get("state") in ("queued", "running"):
        raise RuntimeError("A job for this website is already running")
    job = {"action": action, "site_id": site.id, "slug": site.slug, "repo_url": site.repo_url, "branch": site.branch,
           "compose_file": site.compose_file, "port": site.port, "token": token, "env": env, "purge": purge}
    write_json(deploy_dir() / "status" / f"{site.id}.json",
               {"state": "queued", "action": action, "started": time.time(), "updated": time.time(), "log": ""})
    write_json(deploy_dir() / "jobs" / f"{uuid.uuid4().hex}.json", job)
