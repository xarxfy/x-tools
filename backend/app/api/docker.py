"""Servers and Docker: snapshot of the collector, container actions and logs."""

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.core.audit import audit
from app.collector.exchange import ActionError, load_snapshot, request
from app.core.config import get_settings
from app.core.db import get_db
from app.models import Service
from app.monitor.issues import mark_manual

router = APIRouter(prefix="/api/docker", tags=["docker"], dependencies=[Depends(current_user)])


def stale_after() -> int:
    return max(300, 5 * get_settings().collect_interval)


def norm_folder(folder: str | None) -> str:
    return (folder or "").strip().rstrip("/")


@router.get("")
def snapshot(db: Session = Depends(get_db)):
    """Latest collector snapshot plus what the UI needs to show it."""
    snap = load_snapshot()
    services = {norm_folder(s.folder): {"id": s.id, "name": s.name} for s in db.scalars(select(Service)) if s.folder}
    if snap:
        for p in snap.get("projects", []):
            p["service"] = services.get(norm_folder(p.get("folder")))
    age = time.time() - (snap or {}).get("collected_at", 0)
    return {"snapshot": snap, "stale": snap is not None and age > stale_after(),
            "protected": get_settings().protected_list}


class ActionIn(BaseModel):
    action: str = Field(pattern="^(start|stop|restart)$")
    container: str = Field(max_length=128)


class LogsIn(BaseModel):
    container: str = Field(max_length=128)
    lines: int = Field(default=300, ge=10, le=1000)


def run(action: str, container: str, lines: int | None = None) -> dict:
    try:
        result = request(action, container, lines)
    except ActionError as error:
        raise HTTPException(422, str(error)) from None
    except TimeoutError as error:
        raise HTTPException(504, str(error)) from None
    if not result.get("ok"):
        raise HTTPException(502, result.get("error") or "Action failed")
    return result


@router.post("/action", dependencies=[Depends(require("operator"))])
def container_action(body: ActionIn):
    try:
        run(body.action, body.container)
    except HTTPException as error:
        audit(f"container.{body.action}", body.container, f"failed: {error.detail}")
        raise
    audit(f"container.{body.action}", body.container)
    mark_manual(body.container, stopped=body.action == "stop")
    return {"ok": True}


@router.post("/logs", dependencies=[Depends(require("operator"))])
def container_logs(body: LogsIn):
    logs = run("logs", body.container, body.lines).get("logs", "")
    audit("container.logs", body.container)
    return {"logs": logs}
