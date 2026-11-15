"""Maintenance windows: alerts for a part of the system are paused for a while.

A window has a scope: everything, this server (local Docker), one agent/service/job, or all of a customer.
Problems stay visible (marked as paused) but nothing is sent, and no "back to normal" message follows.
"""

import secrets
import time

from sqlalchemy import select

from app.core.db import session_scope
from app.models import Customer
from app.monitor import state

KEY = "maintenance"
SCOPES = ("all", "local", "agent", "service", "job", "customer")
MAX_MINUTES = 7 * 24 * 60


def active(now: float | None = None) -> list[dict]:
    now = now or time.time()
    return [w for w in state.load(KEY, []) or [] if w["until"] > now]


def add(scope: str, target: str, label: str, minutes: int, reason: str, user: str) -> dict:
    now = time.time()
    window = {"id": secrets.token_hex(6), "scope": scope, "target": target, "label": label, "reason": reason,
              "until": now + minutes * 60, "created_at": now, "created_by": user}

    def change(data):
        data = data if isinstance(data, list) else []
        return [w for w in data if w["until"] > now - 3600] + [window]
    state.update(KEY, change, default=[])
    return window


def end(window_id: str) -> bool:
    found = []

    def change(data):
        data = data if isinstance(data, list) else []
        for w in data:
            if w["id"] == window_id and w["until"] > time.time():
                found.append(w)
                w["until"] = time.time()
        return data
    state.update(KEY, change, default=[])
    return bool(found)


def _customer_parts(customer_id: str) -> tuple[set[str], set[str]]:
    with session_scope() as db:
        customer = db.scalar(select(Customer).where(Customer.id == customer_id))
        if customer is None:
            return set(), set()
        return ({s.id for s in customer.services}, {d for s in customer.services for d in (s.domains or [])})


def silenced_keys(issues: list[dict], now: float | None = None) -> set[str]:
    """Keys of the issues that are covered by an active window."""
    windows = active(now)
    if not windows:
        return set()
    customers = {w["target"]: _customer_parts(w["target"]) for w in windows if w["scope"] == "customer"}
    out = set()
    for issue in issues:
        key = issue["key"]
        parts = key.split(":")
        for w in windows:
            scope, target = w["scope"], w["target"]
            if scope == "all":
                hit = True
            elif scope == "local":
                # local Docker and local system metrics: keys without an agent id
                hit = key in ("disk", "mem") or key.startswith("docker:") or (parts[0] == "container" and len(parts) == 2)
            elif scope in ("agent", "service", "job"):
                hit = target in parts[1:] or parts[0] == target
            else:
                services, domains = customers.get(target, (set(), set()))
                hit = any(p in services for p in parts[1:]) or (parts[0] == "site" and key[5:] in domains)
            if hit:
                out.add(key)
                break
    return out
