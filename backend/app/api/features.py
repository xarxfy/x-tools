"""Optional areas that can be switched on and off (e.g. customers for people who host nothing for others)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import current_user
from app.core.db import session_scope
from app.models import Customer
from app.monitor import state

router = APIRouter(prefix="/api/features", tags=["features"], dependencies=[Depends(current_user)])
KEY = "features"


class Features(BaseModel):
    customers: bool


def load() -> Features:
    stored = state.load(KEY, {}) or {}
    if "customers" not in stored:
        # Not decided yet: on when customers exist (e.g. after an import), otherwise off.
        with session_scope() as db:
            stored["customers"] = (db.scalar(select(func.count()).select_from(Customer)) or 0) > 0
    return Features(**stored)


@router.get("", response_model=Features)
def get_features():
    return load()


@router.put("", response_model=Features)
def put_features(body: Features):
    state.save(KEY, body.model_dump())
    return body
