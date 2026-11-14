"""Overview (current issues), notification settings and website checks."""

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.collector.exchange import load_snapshot
from app.core.config import VERSION, get_settings
from app.core.db import get_db
from app.models import Agent, Customer, Service
from app.monitor import notify, sites, state
from app.monitor.issues import ALERT_STATE, all_containers, container_state, find_issues

router = APIRouter(prefix="/api", tags=["monitor"], dependencies=[Depends(current_user)])


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    issues = find_issues()
    snap = load_snapshot()
    containers = all_containers(snap)
    agents = list(db.scalars(select(Agent).where(Agent.disabled.is_(False))))
    count = lambda model: db.scalar(select(func.count()).select_from(model)) or 0  # noqa: E731
    checks = sites.load_results()
    return {
        "issues": issues,
        "counts": {
            "services": count(Service),
            "customers": count(Customer),
            "servers": 1 + len(agents),
            "containers": len(containers),
            "containers_running": sum(container_state(c)[0] == "up" for c in containers),
            "sites": len(checks),
            "sites_up": sum(1 for c in checks.values() if c.get("level") == "up"),
        },
        "system": (snap or {}).get("system"),
        "notifications": bool(notify.active_channels(notify.load())),
    }


# --- Notifications ------------------------------------------------------------------


@router.get("/settings/notifications")
def get_notifications():
    data = notify.public(notify.load())
    data["last"] = (state.load(ALERT_STATE, {}) or {}).get("last")
    data["base_url"] = get_settings().base_url
    return data


@router.put("/settings/notifications")
def put_notifications(body: dict):
    try:
        return notify.public(notify.save(body))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


class TestIn(BaseModel):
    channel: str


@router.post("/settings/notifications/test")
def test_notification(body: TestIn):
    if body.channel not in ("telegram", "ntfy"):
        raise HTTPException(422, "Unknown channel")
    settings = notify.load()
    cfg = settings[body.channel]
    if body.channel == "telegram" and not (cfg["token"] and cfg["chat_id"]):
        raise HTTPException(422, "Save bot token and chat ID first")
    if body.channel == "ntfy" and not cfg["topic"]:
        raise HTTPException(422, "Save a topic first")
    result = notify.notify(settings, "🔔 X-TOOLS: test", "Notifications work.", "info", only=[body.channel])
    if result[body.channel]:
        raise HTTPException(502, result[body.channel])
    return {"ok": True}


# --- Website checks -------------------------------------------------------------------


@router.get("/sitechecks")
def get_sitechecks():
    return sites.load_results()


class SiteCheckIn(BaseModel):
    customer_id: str | None = None


@router.post("/sitechecks")
def run_sitechecks(body: SiteCheckIn, db: Session = Depends(get_db)):
    """Check now – the domains of one customer, or all customer domains."""
    if body.customer_id:
        customer = db.get(Customer, body.customer_id)
        if customer is None:
            raise HTTPException(404, "Customer not found")
        domains = sorted({d for s in customer.services for d in (s.domains or [])})
    else:
        domains = None
    db.close()  # checks can take a while; do not hold the session
    sites.run_checks(domains)
    return sites.load_results()


@router.get("/about")
def about():
    s = get_settings()
    snap = load_snapshot()
    return {"version": VERSION, "base_url": s.base_url, "timezone": s.timezone, "data_dir": str(s.data_dir),
            "secret_key_from_env": bool(s.secret_key), "compose_roots": s.compose_root_list,
            "protected": s.protected_list, "collector_seen": (snap or {}).get("collected_at"),
            "now": time.time()}
