"""Backup and restore from the UI.

A backup contains the database and the secret key, encrypted with a passphrase
you choose (scrypt + Fernet). Without the passphrase the file is useless – and
with it, everything inside (credentials too) can be read, so keep it safe.
"""

import base64
import io
import json
import os
import sqlite3
import tempfile
import time
import zipfile
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import require
from app.core.audit import audit
from app.core import db as dbmod
from app.core import security
from app.core.config import VERSION, get_settings
from app.core.security import encrypt_json
from app.monitor import autobackup

router = APIRouter(prefix="/api/backup", tags=["backup"], dependencies=[Depends(require("admin"))])

MAGIC = b"XTB1"
MAX_BACKUP = 200 * 1024 * 1024


class BackupIn(BaseModel):
    passphrase: str = Field(min_length=10, max_length=256)


class RestoreIn(BaseModel):
    passphrase: str = Field(min_length=1, max_length=256)
    data: str = Field(min_length=10)  # base64 of the backup file


def _fernet(passphrase: str, salt: bytes) -> Fernet:
    key = Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(passphrase.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def create_backup(passphrase: str) -> bytes:
    settings = get_settings()
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = os.path.join(tmp, "x-tools.db")
        # Consistent copy of the live database (WAL included) via SQLite's backup API.
        src = sqlite3.connect(settings.data_dir / "x-tools.db")
        dst = sqlite3.connect(snapshot)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snapshot, "x-tools.db")
            z.writestr("secret.key", security.secret_key() + "\n")
            z.writestr("meta.json", json.dumps({"version": VERSION, "created_at": time.time()}))
    salt = os.urandom(16)
    return MAGIC + salt + _fernet(passphrase, salt).encrypt(buf.getvalue())


def read_backup(raw: bytes, passphrase: str) -> dict[str, bytes]:
    if not raw.startswith(MAGIC) or len(raw) < 40:
        raise HTTPException(422, "This is not an X-TOOLS backup")
    salt, token = raw[4:20], raw[20:]
    try:
        content = _fernet(passphrase, salt).decrypt(token)
    except InvalidToken:
        raise HTTPException(403, "Wrong passphrase") from None
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        names = set(z.namelist())
        if not {"x-tools.db", "secret.key", "meta.json"} <= names:
            raise HTTPException(422, "The backup is incomplete")
        files = {n: z.read(n) for n in ("x-tools.db", "secret.key", "meta.json")}
    if not files["x-tools.db"].startswith(b"SQLite format 3"):
        raise HTTPException(422, "The backup does not contain a database")
    return files


@router.post("")
def download_backup(body: BackupIn):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    audit("backup.downloaded")
    return Response(create_backup(body.passphrase), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="x-tools-backup-{stamp}.xtb"'})


@router.post("/restore", status_code=204)
def restore_backup(body: RestoreIn):
    try:
        raw = base64.b64decode(body.data, validate=True)
    except ValueError:
        raise HTTPException(422, "The file could not be read") from None
    if len(raw) > MAX_BACKUP:
        raise HTTPException(413, "The backup is too large")
    files = read_backup(raw, body.passphrase)
    from app.core.audit import current_request
    request = current_request.get()
    actor = getattr(getattr(request, "state", None), "user", None)
    actor_name = getattr(actor, "username", "")
    settings = get_settings()
    key = files["secret.key"].decode().strip()
    if settings.secret_key and settings.secret_key != key:
        raise HTTPException(409, "XT_SECRET_KEY is set to a different key. Set it to the key of the backup "
                                 "(or remove it) and try again.")
    data = settings.data_dir
    # Swap in the backup: close all connections, replace database and key, migrate.
    dbmod.reset_engine()
    for suffix in ("-wal", "-shm"):
        (data / f"x-tools.db{suffix}").unlink(missing_ok=True)
    tmp = data / "x-tools.db.restore"
    tmp.write_bytes(files["x-tools.db"])
    os.replace(tmp, data / "x-tools.db")
    if not settings.secret_key:
        key_tmp = data / "secret.key.restore"
        fd = os.open(key_tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key + "\n")
        os.replace(key_tmp, data / "secret.key")
    security.reset_fernet()
    dbmod.run_migrations()
    # Sessions in the restored database belong to the old installation's logins – start fresh.
    from sqlalchemy import delete

    from app.models import UserSession
    with dbmod.session_scope() as s:
        s.execute(delete(UserSession))
        s.commit()
    audit("backup.restored", "", f"meta: {files['meta.json'].decode()[:200]}", username=actor_name, user=False)
    return Response(status_code=204)


# --- automatic backups -----------------------------------------------------------------------


class LocationIn(BaseModel):
    id: str | None = Field(default=None, max_length=12)
    name: str = Field(min_length=1, max_length=60)
    type: str = Field(pattern="^(folder|webdav)$")
    path: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=300)
    username: str = Field(default="", max_length=120)
    password: str | None = Field(default=None, max_length=300)  # None: keep, "": remove


class AutoIn(BaseModel):
    enabled: bool
    frequency: str = Field(pattern="^(daily|weekly)$")
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekday: int = Field(default=0, ge=0, le=6)
    keep: int = Field(default=14, ge=1, le=365)
    passphrase: str | None = Field(default=None, min_length=10, max_length=256)  # None: keep
    locations: list[LocationIn] = Field(default_factory=list, max_length=5)


@router.get("/auto")
def get_auto():
    return autobackup.public(autobackup.load())


@router.put("/auto")
def put_auto(body: AutoIn):
    cfg = autobackup.load()
    old = {l["id"]: l for l in cfg["locations"]}
    locations = []
    for loc in body.locations:
        if loc.type == "folder":
            try:
                autobackup.check_folder(loc.path)
            except autobackup.LocationError as error:
                raise HTTPException(422, f"{loc.name}: {error}") from None
            item = {"type": "folder", "path": loc.path.rstrip("/") or "/"}
        else:
            if not loc.url.startswith(("https://", "http://")):
                raise HTTPException(422, f"{loc.name}: the WebDAV address must start with https://")
            previous = (old.get(loc.id or "") or {}).get("password", "")
            password = encrypt_json(loc.password) if loc.password else ("" if loc.password == "" else previous)
            item = {"type": "webdav", "url": loc.url.rstrip("/"), "username": loc.username, "password": password}
        locations.append({"id": loc.id if loc.id in old else autobackup.new_location_id(), "name": loc.name, **item})
    if body.enabled and not (body.passphrase or cfg["passphrase"]):
        raise HTTPException(422, "Automatic backups need a passphrase")
    if body.enabled and not locations:
        raise HTTPException(422, "Add at least one location")

    def change(data):
        data.update(enabled=body.enabled, frequency=body.frequency, time=body.time, weekday=body.weekday,
                    keep=body.keep, locations=locations)
        if body.passphrase:
            data["passphrase"] = encrypt_json(body.passphrase)
        return data
    from app.monitor import state
    state.update(autobackup.KEY, change, default=autobackup.defaults())
    audit("backup.auto_config", "", "on" if body.enabled else "off")
    return autobackup.public(autobackup.load())


@router.post("/auto/run")
def run_auto():
    cfg = autobackup.load()
    if not cfg["passphrase"] or not cfg["locations"]:
        raise HTTPException(422, "Set a passphrase and at least one location first")
    result = autobackup.run()
    audit("backup.auto_run", "", "ok" if result["ok"] else "failed")
    return autobackup.public(autobackup.load())
