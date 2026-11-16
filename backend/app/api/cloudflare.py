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


class WriteIn(BaseModel):
    allow_write: bool


HOST = r"^(\*\.)?([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$"


class RecordIn(BaseModel):
    zone_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9]+$")
    type: str = Field(pattern="^(A|AAAA|CNAME|TXT)$")
    name: str = Field(min_length=1, max_length=253)
    content: str = Field(min_length=1, max_length=2048)
    proxied: bool = False
    ttl: int = Field(default=1, ge=1, le=86400)


class RouteIn(BaseModel):
    tunnel_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-f0-9-]+$")
    hostname: str = Field(min_length=3, max_length=253, pattern=HOST)
    service: str = Field(default="", max_length=300, pattern=r"^(https?|tcp|ssh|rdp|unix)://[^\s]+$|^http_status:\d{3}$|^$")
    dns: bool = True


def writable():
    if not cf.allow_write():
        raise HTTPException(409, "Changes at Cloudflare are not allowed – an admin can allow them under "
                                 "Settings → Cloudflare")


def run(fn, *args):
    try:
        fn(*args)
    except cf.CloudflareError as error:
        cf.refresh()
        raise HTTPException(424, str(error)) from None


def service_rows(db: Session) -> list[dict]:
    return [{"id": s.id, "name": s.name, "host": s.host, "domains": list(s.domains or []), "ports": list(s.ports or [])}
            for s in db.scalars(select(Service))]


@router.get("")
def overview(db: Session = Depends(get_db)):
    snap = cf.load_snapshot()
    return {"configured": cf.configured(), "allow_write": cf.allow_write(), "snapshot": snap,
            "hosts": cf.analyse(snap, service_rows(db)) if snap else []}


@router.post("/refresh", dependencies=[Depends(require("cloudflare.edit"))])
def refresh(db: Session = Depends(get_db)):
    if not cf.configured():
        raise HTTPException(409, "Cloudflare is not set up")
    snap = cf.refresh()
    return {"configured": True, "allow_write": cf.allow_write(), "snapshot": snap,
            "hosts": cf.analyse(snap, service_rows(db))}


@router.get("/settings", dependencies=[Depends(require("admin.settings"))])
def get_settings_():
    snap = cf.load_snapshot() or {}
    return {"configured": cf.configured(), "allow_write": cf.allow_write(), "fetched_at": snap.get("fetched_at"),
            "errors": snap.get("errors", {}),
            "zones": len(snap.get("zones", [])), "tunnels": len(snap.get("tunnels", [])),
            "access_apps": len(snap.get("access_apps", []))}


@router.put("/settings", dependencies=[Depends(require("admin.settings"))])
def put_settings(body: TokenIn):
    try:
        cf.verify(body.token)
    except cf.CloudflareError as error:
        raise HTTPException(422, f"The token does not work: {error}") from None
    cf.save_token(body.token)
    audit("settings.cloudflare", "", "token saved")
    snap = cf.refresh() or {}
    return {"configured": True, "errors": snap.get("errors", {}), "zones": len(snap.get("zones", []))}


@router.delete("/settings", status_code=204, dependencies=[Depends(require("admin.settings"))])
def delete_settings():
    cf.remove()
    audit("settings.cloudflare", "", "token removed")
    return Response(status_code=204)


@router.put("/settings/write", dependencies=[Depends(require("admin.settings"))])
def put_write(body: WriteIn):
    if not cf.configured():
        raise HTTPException(409, "Store a token first")
    cf.set_allow_write(body.allow_write)
    audit("settings.cloudflare", "", "changes allowed" if body.allow_write else "read-only")
    return {"allow_write": cf.allow_write()}


OPERATOR = [Depends(require("cloudflare.edit"))]


@router.post("/dns", dependencies=OPERATOR)
def create_record(body: RecordIn):
    writable()
    run(cf.save_record, body.zone_id, body.model_dump())
    audit("cloudflare.dns_created", body.name, f"{body.type} {body.content[:100]}")
    cf.refresh()
    return {"ok": True}


@router.put("/dns/{record_id}", dependencies=OPERATOR)
def update_record(record_id: str, body: RecordIn):
    writable()
    run(cf.save_record, body.zone_id, body.model_dump(), record_id)
    audit("cloudflare.dns_updated", body.name, f"{body.type} {body.content[:100]}")
    cf.refresh()
    return {"ok": True}


@router.delete("/dns/{zone_id}/{record_id}", status_code=204, dependencies=OPERATOR)
def remove_record(zone_id: str, record_id: str):
    writable()
    snap = cf.load_snapshot() or {}
    name = next((r["name"] for z in snap.get("zones", []) for r in z["records"] if r.get("id") == record_id), record_id)
    run(cf.delete_record, zone_id, record_id)
    audit("cloudflare.dns_deleted", name)
    cf.refresh()
    return Response(status_code=204)


@router.post("/routes", dependencies=OPERATOR)
def save_route(body: RouteIn):
    writable()
    if not body.service:
        raise HTTPException(422, "service: e.g. http://localhost:8080")
    run(cf.save_route, body.tunnel_id, body.hostname, body.service, body.dns)
    audit("cloudflare.route_saved", body.hostname, f"→ {body.service}{' + DNS' if body.dns else ''}")
    cf.refresh()
    return {"ok": True}


@router.post("/routes/delete", dependencies=OPERATOR)
def remove_route(body: RouteIn):
    writable()
    run(cf.delete_route, body.tunnel_id, body.hostname, body.dns)
    audit("cloudflare.route_deleted", body.hostname, "with DNS record" if body.dns else "")
    cf.refresh()
    return {"ok": True}
