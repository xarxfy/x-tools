"""History API: recent problems, uptime per service, metric curves."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.db import get_db
from app.models import Event, Metric, Service
from app.monitor.history import uptime, utc

router = APIRouter(prefix="/api/history", tags=["history"], dependencies=[Depends(current_user)])
MAX_POINTS = 300


@router.get("/events")
def events(days: int = Query(7, ge=1, le=90), limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.scalars(select(Event).where((Event.ended_at.is_(None)) | (Event.started_at >= since)
                                          | (Event.ended_at >= since))
                      .order_by(Event.started_at.desc()).limit(limit))
    return [{"id": e.id, "key": e.key, "kind": e.kind, "level": e.level, "text": e.text, "link": e.link,
             "started_at": utc(e.started_at), "ended_at": utc(e.ended_at)} for e in rows]


@router.get("/uptime")
def service_uptime(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)):
    ids = [s.id for s in db.scalars(select(Service)) if s.ports]
    return uptime(ids, days)


@router.get("/metrics")
def metrics(source: str = Query("local", max_length=20), hours: int = Query(24, ge=1, le=24 * 30),
            db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = list(db.scalars(select(Metric).where(Metric.source == source, Metric.ts >= since).order_by(Metric.ts)))
    step = max(1, len(rows) // MAX_POINTS)  # thin out long ranges
    return [{"ts": utc(m.ts), "load": m.load, "mem": m.mem, "disk": m.disk} for m in rows[::step]]
