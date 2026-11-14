"""Import data from Server-Info (the predecessor of X-TOOLS).

Reads the JSON files of a Server-Info installation and writes them into the
X-TOOLS database configured via XT_DATA_DIR / XT_SECRET_KEY:

  services.json   → services (IDs kept)
  customers.json  → customers, and links services to their customer
  logins.json     → credentials (decrypted with the old key, re-encrypted with the new one)
  settings.json   → notification settings (tokens re-encrypted)
  agents.json     → agents (key hash kept, so existing agents keep working)

Usage (from the repository root, backend installed or on PYTHONPATH):

  XT_DATA_DIR=/path/to/x-tools-data python migrate/import_server_info.py \\
      --source ~/server-info/data --old-env ~/server-info/.env

Existing rows with the same ID are updated; nothing else is deleted.
Secrets are never printed.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from cryptography.fernet import Fernet, InvalidToken  # noqa: E402

from app.core.db import run_migrations, session_scope  # noqa: E402
from app.core.security import encrypt_json  # noqa: E402
from app.models import Agent, CredentialSet, Customer, Service, Setting  # noqa: E402


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def old_key_from_env(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("INFO_SECRET_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"INFO_SECRET_KEY not found in {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help="Server-Info data directory")
    key = parser.add_mutually_exclusive_group()
    key.add_argument("--old-env", type=Path, help="Server-Info .env (to read INFO_SECRET_KEY)")
    key.add_argument("--old-key", help="Server-Info INFO_SECRET_KEY")
    args = parser.parse_args()

    old_key = args.old_key or (old_key_from_env(args.old_env) if args.old_env else "")
    old = Fernet(old_key.encode()) if old_key else None

    def old_decrypt(token: str):
        if old is None:
            raise SystemExit("Encrypted data found – pass --old-env or --old-key")
        try:
            return json.loads(old.decrypt(token.encode()))
        except InvalidToken:
            raise SystemExit("Cannot decrypt Server-Info data – wrong old key?") from None

    run_migrations()
    src = args.source
    counts = {}
    with session_scope() as db:
        # Services
        services = read_json(src / "services.json", [])
        for s in services:
            if not s.get("id"):
                continue
            db.merge(Service(
                id=s["id"], name=s.get("name", "")[:80], ports=s.get("ports") or [], domains=s.get("domains") or [],
                folder=s.get("folder", ""), type=s.get("type", ""), notes=s.get("notes", ""),
            ))
        db.flush()
        counts["services"] = len(services)

        # Customers (+ service links)
        customers = read_json(src / "customers.json", [])
        service_ids = {s["id"] for s in services if s.get("id")}
        for c in customers:
            db.merge(Customer(
                id=c["id"], name=c.get("name", "")[:80], contact=c.get("contact", ""), email=c.get("email", ""),
                phone=c.get("phone", ""), owner=c.get("owner", ""), agreements=c.get("agreements", ""),
                notes=c.get("notes", ""),
            ))
            db.flush()
            for sid in c.get("services", []):
                if sid in service_ids:
                    db.get(Service, sid).customer_id = c["id"]
        counts["customers"] = len(customers)

        # Credentials: old key → new key
        logins = read_json(src / "logins.json", {})
        moved = 0
        for sid, entry in logins.items():
            if sid not in service_ids or not isinstance(entry, dict) or not entry.get("data"):
                continue
            items = old_decrypt(entry["data"])
            db.merge(CredentialSet(service_id=sid, count=len(items), data=encrypt_json(items)))
            moved += len(items)
        counts["credentials"] = moved

        # Notification settings: tokens old key → new key
        settings = read_json(src / "settings.json", None)
        if settings:
            for channel in ("telegram", "ntfy"):
                cfg = settings.get(channel) or {}
                token = cfg.get("token") or ""
                cfg["token"] = encrypt_json(old.decrypt(token.encode()).decode()) if token and old else ""
                if token and old is None:
                    raise SystemExit("Encrypted tokens found – pass --old-env or --old-key")
            db.merge(Setting(key="notifications", value=settings))
            counts["notification settings"] = 1

        # Agents: keep the key hash so existing agents keep reporting
        agents = read_json(src / "agents.json", [])
        for a in agents:
            created = datetime.fromtimestamp(a.get("created", 0) or 0, timezone.utc)
            db.merge(Agent(id=a["id"], name=a["name"][:60], key_hash=a["hash"], disabled=bool(a.get("disabled")),
                           created_at=created))
        counts["agents"] = len(agents)

        db.commit()

    for name, n in counts.items():
        print(f"  {name}: {n}")
    print("Import finished.")


if __name__ == "__main__":
    main()
