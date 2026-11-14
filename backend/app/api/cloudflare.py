"""Cloudflare (read-only): settings, snapshot and analysis."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.core.audit import audit
from app.core.db import get_db
from app.integrations import cloudflare as cf
from app.models import Service

router = APIRouter(prefix="/api/cloudflare", tags=["cloudflare"], dependencies=[Depends(current_user)])


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200, pattern=r"^[A-Za-z0-9_\-]+$")


def service_rows(db: Session) -> list[dict]:
    return [{"id": s.id, "name": s.name, "host": s.host, "domains": list(s.domains or []), "ports": list(s.ports or [])}
            for s in db.scalars(select(Service))]


@router.get("")
def overview(db: Session = Depends(get_db)):
    snap = cf.load_snapshot()
    return {"configured": cf.configured(), "snapshot": snap,
            "hosts": cf.analyse(snap, service_rows(db)) if snap else []}


@router.post("/refresh", dependencies=[Depends(require("operator"))])
def refresh(db: Session = Depends(get_db)):
    if not cf.configured():
        raise HTTPException(409, "Cloudflare is not set up")
    snap = cf.refresh()
    return {"configured": True, "snapshot": snap, "hosts": cf.analyse(snap, service_rows(db))}


@router.get("/settings", dependencies=[Depends(require("admin"))])
def get_settings_():
    snap = cf.load_snapshot() or {}
    return {"configured": cf.configured(), "fetched_at": snap.get("fetched_at"), "errors": snap.get("errors", {}),
            "zones": len(snap.get("zones", [])), "tunnels": len(snap.get("tunnels", [])),
            "access_apps": len(snap.get("access_apps", []))}


@router.put("/settings", dependencies=[Depends(require("admin"))])
def put_settings(body: TokenIn):
    try:
        cf.verify(body.token)
    except cf.CloudflareError as error:
        raise HTTPException(422, f"The token does not work: {error}") from None
    cf.save_token(body.token)
    audit("settings.cloudflare", "", "token saved")
    snap = cf.refresh() or {}
    return {"configured": True, "errors": snap.get("errors", {}), "zones": len(snap.get("zones", []))}


@router.delete("/settings", status_code=204, dependencies=[Depends(require("admin"))])
def delete_settings():
    cf.remove()
    audit("settings.cloudflare", "", "token removed")
    return Response(status_code=204)
