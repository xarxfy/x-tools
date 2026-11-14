"""Import from Server-Info: IDs kept, secrets re-encrypted with the new key, idempotent."""

import json
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[2]


def write_server_info(src: Path, old: Fernet) -> None:
    enc = lambda value: old.encrypt(json.dumps(value).encode()).decode()  # noqa: E731
    (src / "services.json").write_text(json.dumps([
        {"id": "aaaaaaaaaaaa", "name": "Website", "domains": ["example.com"], "ports": [{"port": 3000, "label": "Web"}],
         "folder": "~/site", "type": "Docker Compose", "notes": ""},
        {"id": "bbbbbbbbbbbb", "name": "Git", "domains": [], "ports": [], "folder": "", "type": "", "notes": "x"},
    ]))
    (src / "customers.json").write_text(json.dumps([
        {"id": "cccccccccccc", "name": "ACME", "contact": "Jane", "email": "jane@example.com", "phone": "",
         "owner": "customer", "agreements": "Hosting", "notes": "", "services": ["aaaaaaaaaaaa", "unknown00000"]},
    ]))
    (src / "logins.json").write_text(json.dumps({
        "aaaaaaaaaaaa": {"n": 2, "data": enc([{"label": "Admin", "username": "root", "password": "s3cret"},
                                               {"label": "CI", "username": "ci", "password": "t0ken"}])},
    }))
    (src / "settings.json").write_text(json.dumps({
        "enabled": True, "delay": 3, "recovery": True, "base_url": "", "events": {"port": True},
        "telegram": {"enabled": True, "chat_id": "4242", "token": old.encrypt(b"123456:AAHtelegramtoken").decode()},
        "ntfy": {"enabled": False, "server": "https://ntfy.sh", "topic": "", "token": ""},
    }))
    (src / "agents.json").write_text(json.dumps([
        {"id": "dddddddddddd", "name": "Home", "hash": "ab" * 32, "created": 1794500000, "disabled": False},
    ]))


def run_import(dest: Path, src: Path, old_key: str) -> str:
    out = subprocess.run(
        [sys.executable, str(ROOT / "migrate" / "import_server_info.py"), "--source", str(src), "--old-key", old_key],
        capture_output=True, text=True, env={"XT_DATA_DIR": str(dest), "PATH": "/usr/bin:/bin"}, check=True,
    )
    return out.stdout


def test_import_server_info(tmp_path, monkeypatch):
    src, dest = tmp_path / "server-info", tmp_path / "x-tools"
    src.mkdir()
    old_key = Fernet.generate_key().decode()
    write_server_info(src, Fernet(old_key.encode()))

    output = run_import(dest, src, old_key)
    assert "credentials: 2" in output and "s3cret" not in output
    run_import(dest, src, old_key)  # second run must not duplicate anything

    monkeypatch.setenv("XT_DATA_DIR", str(dest))
    monkeypatch.setenv("XT_SECRET_KEY", "")
    from app.core import config, db, security
    config.get_settings.cache_clear()
    db.reset_engine()
    security.reset_fernet()
    from sqlalchemy import func, select
    from app.models import Agent, CredentialSet, Customer, Service, Setting

    with db.session_scope() as s:
        assert s.scalar(select(func.count()).select_from(Service)) == 2
        assert s.get(Service, "aaaaaaaaaaaa").customer_id == "cccccccccccc"
        assert s.get(Service, "bbbbbbbbbbbb").customer_id is None
        assert s.get(Customer, "cccccccccccc").email == "jane@example.com"
        creds = security.decrypt_json(s.get(CredentialSet, "aaaaaaaaaaaa").data)
        assert [c["password"] for c in creds] == ["s3cret", "t0ken"]
        assert s.get(CredentialSet, "aaaaaaaaaaaa").count == 2
        notif = s.get(Setting, "notifications").value
        assert security.decrypt_json(notif["telegram"]["token"]) == "123456:AAHtelegramtoken"
        assert notif["delay"] == 3
        assert s.get(Agent, "dddddddddddd").key_hash == "ab" * 32
        assert s.scalar(select(func.count()).select_from(Agent)) == 1

    raw = (dest / "x-tools.db").read_bytes()
    assert b"s3cret" not in raw and b"AAHtelegramtoken" not in raw
    db.reset_engine()
    config.get_settings.cache_clear()
