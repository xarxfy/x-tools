"""Maintenance windows: pause alerts for a part of the system."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.core.audit import audit
from app.core.db import get_db
from app.models import Agent, Customer, Heartbeat, Service
from app.monitor import maintenance

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"], dependencies=[Depends(current_user)])


class WindowIn(BaseModel):
    scope: str = Field(pattern="^(all|local|agent|service|job|customer)$")
    target: str = Field(default="", max_length=12)
    minutes: int = Field(ge=1, le=maintenance.MAX_MINUTES)
    reason: str = Field(default="", max_length=200)


@router.get("")
def list_windows():
    return maintenance.active()


@router.post("", status_code=201, dependencies=[Depends(require("operator"))])
def create_window(body: WindowIn, request: Request, db: Session = Depends(get_db)):
    models = {"agent": Agent, "service": Service, "job": Heartbeat, "customer": Customer}
    if body.scope in models:
        obj = db.get(models[body.scope], body.target)
        if obj is None:
            raise HTTPException(422, "Unknown target")
        label = obj.name
    else:
        label = {"all": "Everything", "local": "This server"}[body.scope]
    window = maintenance.add(body.scope, body.target, label, body.minutes, body.reason.strip(),
                             getattr(request.state, "user", None).username)
    audit("maintenance.start", label, f"{body.minutes} min" + (f": {body.reason}" if body.reason else ""))
    return window


@router.delete("/{wid}", status_code=204, dependencies=[Depends(require("operator"))])
def end_window(wid: str):
    if not maintenance.end(wid):
        raise HTTPException(404, "Window not found or already over")
    audit("maintenance.end", wid)
