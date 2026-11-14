"""History: problems over time (events) and host metrics (samples every few minutes)."""

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.collector.exchange import load_snapshot
from app.core.db import session_scope
from app.models import Agent, Event, Metric

SAMPLE_SECONDS = 300
KEEP_METRICS_DAYS = 30
KEEP_EVENTS_DAYS = 90
_last_sample = 0.0


def utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def record_events(issues: list[dict], now: datetime | None = None) -> None:
    """Open an event for every new issue, close events whose issue is gone."""
    now = now or datetime.now(timezone.utc)
    current = {i["key"]: i for i in issues if not i.get("manual")}
    with session_scope() as db:
        open_events = {e.key: e for e in db.scalars(select(Event).where(Event.ended_at.is_(None)))}
        for key, issue in current.items():
            event = open_events.get(key)
            if event is None:
                db.add(Event(key=key[:300], kind=issue["kind"], level=issue["level"], text=issue["text"][:500],
                             link=issue.get("link", "")[:200], started_at=now))
            elif issue["level"] == "down" and event.level != "down":
                event.level = "down"  # got worse while open
        for key, event in open_events.items():
            if key not in current:
                event.ended_at = now
        db.commit()


def _pct(used, total):
    return round(used / total * 100, 1) if used is not None and total else None


def _sample(system: dict) -> dict:
    load = system.get("load")
    return {"load": round(load[0] / max(1, system.get("cpus") or 1) * 100, 1) if load else None,
            "mem": _pct(system.get("mem_used"), system.get("mem_total")),
            "disk": _pct(system.get("disk_used"), system.get("disk_total"))}


def record_metrics(force: bool = False) -> None:
    """One sample per source every SAMPLE_SECONDS; old rows are removed."""
    global _last_sample
    if not force and time.time() - _last_sample < SAMPLE_SECONDS - 10:
        return
    _last_sample = time.time()
    now = datetime.now(timezone.utc)
    rows = []
    snap = load_snapshot()
    if snap and snap.get("system") and time.time() - (snap.get("collected_at") or 0) < 600:
        rows.append(Metric(source="local", ts=now, **_sample(snap["system"])))
    with session_scope() as db:
        for agent in db.scalars(select(Agent).where(Agent.disabled.is_(False))):
            received = utc(agent.last_report_at)
            if agent.last_report and received and (now - received).total_seconds() < 600:
                system = agent.last_report.get("system") or {}
                if system:
                    rows.append(Metric(source=agent.id, ts=now, **_sample(system)))
        db.add_all(rows)
        db.execute(delete(Metric).where(Metric.ts < now - timedelta(days=KEEP_METRICS_DAYS)))
        db.execute(delete(Event).where(Event.ended_at < now - timedelta(days=KEEP_EVENTS_DAYS)))
        db.commit()


def uptime(service_ids: list[str], days: int = 7) -> dict[str, float]:
    """Share of time without port problems per service over the last days (%)."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    total = (now - start).total_seconds()
    down: dict[str, float] = {sid: 0.0 for sid in service_ids}
    with session_scope() as db:
        events = db.scalars(select(Event).where(Event.kind == "port",
                                                (Event.ended_at.is_(None)) | (Event.ended_at > start)))
        intervals: dict[str, list[tuple[datetime, datetime]]] = {}
        for e in events:
            sid = e.key.split(":")[1] if e.key.count(":") >= 2 else ""
            if sid in down:
                a, b = max(utc(e.started_at), start), utc(e.ended_at) or now
                if b > a:
                    intervals.setdefault(sid, []).append((a, b))
    for sid, spans in intervals.items():  # merge overlapping port outages of one service
        spans.sort()
        merged: list[list[datetime]] = []
        for a, b in spans:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        down[sid] = sum((b - a).total_seconds() for a, b in merged)
    return {sid: round(max(0.0, 100 - d / total * 100), 2) for sid, d in down.items()}
