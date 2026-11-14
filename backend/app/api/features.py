"""Optional areas that can be switched on and off (e.g. customers for people who host nothing for others)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import current_user, require
from app.core.audit import audit
from app.core.db import session_scope
from app.models import Customer
from app.monitor import state

router = APIRouter(prefix="/api/features", tags=["features"], dependencies=[Depends(current_user)])
KEY = "features"


class Features(BaseModel):
    customers: bool
    cloudflare: bool = False  # read-only: on when a Cloudflare token is stored


def load() -> Features:
    stored = state.load(KEY, {}) or {}
    if "customers" not in stored:
        # Not decided yet: on when customers exist (e.g. after an import), otherwise off.
        with session_scope() as db:
            stored["customers"] = (db.scalar(select(func.count()).select_from(Customer)) or 0) > 0
    from app.integrations import cloudflare
    return Features(customers=stored["customers"], cloudflare=cloudflare.configured())


@router.get("", response_model=Features)
def get_features():
    return load()


@router.put("", response_model=Features, dependencies=[Depends(require("admin"))])
def put_features(body: Features):
    state.save(KEY, {"customers": body.customers})
    audit("settings.features", "", f"customers={'on' if body.customers else 'off'}")
    return body
