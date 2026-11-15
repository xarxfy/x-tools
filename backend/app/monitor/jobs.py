"""Heartbeat monitors: state of a job from its last pings."""

from datetime import datetime, timezone


def utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def job_state(h, now: datetime | None = None) -> str:
    """paused | waiting | ok | late | fail"""
    now = now or datetime.now(timezone.utc)
    if h.paused:
        return "paused"
    if h.last_status == "fail":
        return "fail"
    last_ok, created = utc(h.last_ok_at), utc(h.created_at)
    reference = last_ok or created
    late = (now - reference).total_seconds() > (h.interval_minutes + h.grace_minutes) * 60
    if late:
        return "late"
    return "ok" if last_ok else "waiting"
