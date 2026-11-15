"""Automatic backups: a schedule (the job) and locations (where the encrypted files go).

The backup itself is the one from Settings → Backup (database + secret key, encrypted with a passphrase). The
passphrase is stored encrypted with the instance's secret key so the job can run unattended.
Locations: a folder (the last N files are kept) or WebDAV (e.g. Nextcloud; upload only).
"""

import base64
import re
import secrets
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.security import decrypt_json, encrypt_json
from app.monitor import state

KEY = "backup_auto"
KEEP_DEFAULT = 14
FILE_RE = re.compile(r"^x-tools-\d{8}-\d{6}\.xtb$")


def defaults() -> dict:
    return {"enabled": False, "frequency": "daily", "time": "03:00", "weekday": 0, "keep": KEEP_DEFAULT,
            "passphrase": "", "locations": [], "last": None}


def load() -> dict:
    data = defaults()
    data.update(state.load(KEY, {}) or {})
    return data


def default_folder() -> str:
    return str(get_settings().data_dir / "backups")


# --- schedule ---------------------------------------------------------------------------


def last_due(cfg: dict, now: datetime) -> datetime:
    """The most recent moment the schedule says a backup should have run."""
    hh, mm = (int(x) for x in cfg["time"].split(":"))
    local = now.astimezone(ZoneInfo(get_settings().timezone))
    due = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if cfg["frequency"] == "weekly":
        due -= timedelta(days=(due.weekday() - int(cfg["weekday"])) % 7)
    if due > local:
        due -= timedelta(days=7 if cfg["frequency"] == "weekly" else 1)
    return due


def period_hours(cfg: dict) -> int:
    return 24 * 7 if cfg["frequency"] == "weekly" else 24


def is_due(cfg: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if not cfg["enabled"] or not cfg["passphrase"] or not cfg["locations"]:
        return False
    last = (cfg.get("last") or {}).get("at")
    return last is None or datetime.fromtimestamp(last, timezone.utc) < last_due(cfg, now)


def problem() -> str:
    """Text for the problem list, or empty."""
    cfg = load()
    if not cfg["enabled"]:
        return ""
    last = cfg.get("last")
    if not last:
        return ""
    if not last.get("ok"):
        errors = "; ".join(f"{r['name']}: {r['error']}" for r in last.get("results", []) if not r.get("ok"))
        return f"Automatic backup failed ({errors[:200] or 'see Settings → Backup'})"
    if time.time() - last["at"] > (period_hours(cfg) * 2 + 24) * 3600:
        return "No automatic backup has run for a long time"
    return ""


# --- locations --------------------------------------------------------------------------


class LocationError(Exception):
    pass


def check_folder(path: str) -> Path:
    if not path.startswith("/") or ".." in Path(path).parts or len(path) > 200:
        raise LocationError("Use an absolute folder path")
    return Path(path)


def write_folder(loc: dict, name: str, blob: bytes, keep: int) -> None:
    folder = check_folder(loc["path"])
    try:
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        tmp = folder / (name + ".part")
        tmp.write_bytes(blob)
        tmp.replace(target)
        files = sorted(p for p in folder.iterdir() if FILE_RE.match(p.name))
        for old in files[:-keep] if keep > 0 else []:
            old.unlink(missing_ok=True)
    except OSError as error:
        raise LocationError(f"{error.strerror or error} – is the folder mounted into the container and writable?") from None


def write_webdav(loc: dict, name: str, blob: bytes) -> None:
    url = loc["url"].rstrip("/") + "/" + name
    password = decrypt_json(loc["password"]) if loc.get("password") else ""
    req = urllib.request.Request(url, data=blob, method="PUT", headers={"Content-Type": "application/octet-stream"})
    if loc.get("username"):
        token = base64.b64encode(f"{loc['username']}:{password}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            if res.status >= 300:
                raise LocationError(f"HTTP {res.status}")
    except urllib.error.HTTPError as error:
        raise LocationError(f"HTTP {error.code} – check address, folder and login") from None
    except (urllib.error.URLError, OSError) as error:
        raise LocationError(f"not reachable ({getattr(error, 'reason', error)})") from None


def run(now: datetime | None = None) -> dict:
    """Make one backup and write it to all locations. Returns the result (also stored as 'last')."""
    from app.api.backup import create_backup
    cfg = load()
    now = now or datetime.now(timezone.utc)
    results = []
    if not cfg["passphrase"]:
        results.append({"name": "-", "ok": False, "error": "No passphrase set"})
    elif not cfg["locations"]:
        results.append({"name": "-", "ok": False, "error": "No location set"})
    else:
        try:
            blob = create_backup(decrypt_json(cfg["passphrase"]))
        except Exception as error:  # noqa: BLE001
            blob, results = None, [{"name": "-", "ok": False, "error": f"Backup failed: {error}"[:300]}]
        name = f"x-tools-{now.strftime('%Y%m%d-%H%M%S')}.xtb"
        for loc in cfg["locations"] if blob else []:
            try:
                if loc["type"] == "folder":
                    write_folder(loc, name, blob, int(cfg["keep"]))
                else:
                    write_webdav(loc, name, blob)
                results.append({"name": loc["name"], "ok": True, "size": len(blob)})
            except LocationError as error:
                results.append({"name": loc["name"], "ok": False, "error": str(error)[:300]})
    last = {"at": now.timestamp(), "ok": bool(results) and all(r["ok"] for r in results), "results": results}

    def save(data):
        data["last"] = last
        return data
    state.update(KEY, save, default=defaults())
    return last


def run_if_due() -> None:
    if is_due(load()):
        run()


# --- configuration (API side) ---------------------------------------------------------------


def public(cfg: dict) -> dict:
    out = {k: cfg[k] for k in ("enabled", "frequency", "time", "weekday", "keep", "last")}
    out["has_passphrase"] = bool(cfg["passphrase"])
    out["default_folder"] = default_folder()
    out["locations"] = [{"id": l["id"], "name": l["name"], "type": l["type"], "path": l.get("path", ""),
                         "url": l.get("url", ""), "username": l.get("username", ""),
                         "has_password": bool(l.get("password"))} for l in cfg["locations"]]
    return out


def new_location_id() -> str:
    return secrets.token_hex(4)


