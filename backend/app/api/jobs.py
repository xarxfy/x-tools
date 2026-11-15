"""Jobs: heartbeat monitors. A cron job or backup script calls its secret address when it has run."""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.core.audit import audit
from app.core.config import get_settings
from app.core.db import get_db
from app.models import Heartbeat
from app.monitor.jobs import job_state, utc
from app.schemas import strip

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(current_user)])
ping_router = APIRouter(prefix="/api/heartbeat", tags=["jobs"])


class JobIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    interval_minutes: int = Field(ge=1, le=60 * 24 * 366)
    grace_minutes: int = Field(default=30, ge=0, le=60 * 24 * 31)
    paused: bool = False

    _strip = field_validator("name", mode="before")(strip)


def out(h: Heartbeat, show_token: bool) -> dict:
    return {"id": h.id, "name": h.name, "interval_minutes": h.interval_minutes, "grace_minutes": h.grace_minutes,
            "paused": h.paused, "state": job_state(h), "last_ping_at": utc(h.last_ping_at),
            "last_ok_at": utc(h.last_ok_at), "last_status": h.last_status,
            # the ping address is a secret: viewers do not get it
            "token": h.token if show_token else None}


def get_job(db: Session, jid: str) -> Heartbeat:
    h = db.get(Heartbeat, jid)
    if h is None:
        raise HTTPException(404, "Job not found")
    return h


@router.get("")
def list_jobs(user=Depends(current_user), db: Session = Depends(get_db)):
    can = user.role in ("operator", "admin")
    return [out(h, can) for h in db.scalars(select(Heartbeat).order_by(Heartbeat.name))]


@router.post("", status_code=201, dependencies=[Depends(require("operator"))])
def create_job(body: JobIn, db: Session = Depends(get_db)):
    h = Heartbeat(token=secrets.token_urlsafe(24), **body.model_dump())
    db.add(h)
    db.commit()
    audit("job.created", h.name)
    return out(h, True)


@router.put("/{jid}", dependencies=[Depends(require("operator"))])
def update_job(jid: str, body: JobIn, db: Session = Depends(get_db)):
    h = get_job(db, jid)
    for k, v in body.model_dump().items():
        setattr(h, k, v)
    db.commit()
    audit("job.updated", h.name)
    return out(h, True)


@router.post("/{jid}/new-token", dependencies=[Depends(require("operator"))])
def new_token(jid: str, db: Session = Depends(get_db)):
    h = get_job(db, jid)
    h.token = secrets.token_urlsafe(24)
    db.commit()
    audit("job.new_token", h.name)
    return out(h, True)


@router.delete("/{jid}", status_code=204, dependencies=[Depends(require("operator"))])
def delete_job(jid: str, db: Session = Depends(get_db)):
    h = get_job(db, jid)
    name = h.name
    db.delete(h)
    db.commit()
    audit("job.deleted", name)
    return Response(status_code=204)


# --- the ping (no login: the address itself is the secret) -----------------------------------------


def record(token: str, status: str, db: Session) -> dict:
    h = db.scalar(select(Heartbeat).where(Heartbeat.token == token)) if 20 <= len(token) <= 48 else None
    if h is None:
        raise HTTPException(404, "Unknown job")
    now = datetime.now(timezone.utc)
    h.last_ping_at, h.last_status = now, status
    if status == "ok":
        h.last_ok_at = now
    db.commit()
    return {"ok": True, "job": h.name}


@ping_router.api_route("/{token}", methods=["GET", "POST", "HEAD"])
def ping_ok(token: str, db: Session = Depends(get_db)):
    return record(token, "ok", db)


@ping_router.api_route("/{token}/start", methods=["GET", "POST", "HEAD"])
def ping_start(token: str, db: Session = Depends(get_db)):
    return record(token, "start", db)


@ping_router.api_route("/{token}/fail", methods=["GET", "POST", "HEAD"])
def ping_fail(token: str, db: Session = Depends(get_db)):
    return record(token, "fail", db)


def base_url() -> str:
    return get_settings().base_url
