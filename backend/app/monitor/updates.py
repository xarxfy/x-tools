"""Is a newer X-TOOLS version available? Asks the GitHub tags API once in a while (can be switched off)."""

import json
import re
import time
import urllib.error
import urllib.request

from app.core.config import VERSION, get_settings
from app.monitor import state

KEY = "update_check"
INTERVAL = 6 * 3600
TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z.-]+)?$")


def parse(tag: str):
    m = TAG.match(tag)
    if not m:
        return None
    # a pre-release (0.2.0-beta.1) is older than the release (0.2.0)
    return (int(m[1]), int(m[2]), int(m[3]), 0 if m[4] else 1, m[4] or "")


def newest(tags: list[str]) -> str | None:
    parsed = [(parse(t), t) for t in tags if parse(t)]
    return max(parsed)[1].lstrip("v") if parsed else None


def is_newer(latest: str | None, current: str = VERSION) -> bool:
    a, b = parse(latest or ""), parse(current)
    return bool(a and b and a > b)


def fetch_latest() -> str | None:
    s = get_settings()
    req = urllib.request.Request(f"{s.github_api}/repos/{s.update_repo}/tags?per_page=50",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "x-tools-update-check"})
    with urllib.request.urlopen(req, timeout=15) as res:
        return newest([t.get("name", "") for t in json.loads(res.read())])


def check() -> dict:
    result = {"checked_at": time.time(), "latest": None, "error": ""}
    try:
        result["latest"] = fetch_latest()
    except (urllib.error.URLError, OSError, ValueError) as error:
        result["error"] = f"{getattr(error, 'reason', error)}"[:200]
    state.save(KEY, result)
    return result


def check_if_due() -> None:
    if not get_settings().update_check:
        return
    last = state.load(KEY, {}) or {}
    if time.time() - last.get("checked_at", 0) > INTERVAL:
        check()


def info() -> dict:
    s = get_settings()
    last = state.load(KEY, {}) or {}
    latest = last.get("latest")
    return {"enabled": s.update_check, "current": VERSION, "latest": latest, "available": is_newer(latest),
            "checked_at": last.get("checked_at"), "error": last.get("error", ""),
            "url": f"https://github.com/{s.update_repo}/releases" }
