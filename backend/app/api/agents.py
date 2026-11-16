"""Agents: other servers that report their state (outbound only, never receive commands)."""

import hmac
import json
import secrets
import time
from datetime import datetime, timezone

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.agent_install import InstallOptions, bundle_response, create_install, install_script
from app.api.deps import current_user, require
from app.api.organize import check_tags
from app.core.palette import COLOR_PATTERN
from app.core.audit import audit
from app.collector.agent import AGENT_VERSION
from app.core.db import get_db
from app.core.security import decrypt_json, encrypt_json, token_hash
from app.models import Agent, ServerGroup

router = APIRouter(prefix="/api/agents", tags=["agents"], dependencies=[Depends(current_user)])
report_router = APIRouter(prefix="/api/agent", tags=["agents"])

MAX_REPORT = 5 * 1024 * 1024
MIN_INTERVAL = 5  # seconds between two reports of one agent


class AgentIn(InstallOptions):
    name: str = Field(min_length=1, max_length=60)


class AgentUpdate(BaseModel):
    disabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=60)
    kind: str | None = Field(default=None, pattern="^(proxmox|docker|linux)$")


def as_utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def host_metrics(report: dict) -> dict:
    """Load, memory and disk in percent, pending updates and reboot flag – for lists."""
    system, linux = report.get("system") or {}, report.get("linux") or {}
    load = system.get("load")
    return {
        "load": round(load[0] / max(1, system.get("cpus") or 1) * 100) if load else None,
        "mem": round(system["mem_used"] / system["mem_total"] * 100) if system.get("mem_total") else None,
        "disk": round(system["disk_used"] / system["disk_total"] * 100) if system.get("disk_total") else None,
        "updates": len(linux["updates"]) if linux.get("updates") is not None else None,
        "reboot": bool(linux.get("reboot_required")),
        "os": linux.get("os", ""),
        "uptime": system.get("uptime"),
    }


def summary(a: Agent) -> dict:
    report = a.last_report or {}
    return {**host_metrics(report), "id": a.id, "name": a.name, "kind": a.kind, "disabled": a.disabled, "created_at": as_utc(a.created_at),
            "last_report_at": as_utc(a.last_report_at), "hostname": report.get("hostname", ""),
            "version": report.get("version", ""),
            "has_docker": bool(report.get("docker")), "has_proxmox": bool(report.get("proxmox")),
            "has_linux": bool(report.get("linux")),
            "outdated": bool(report) and str(report.get("version", "")) != AGENT_VERSION,
            "control": bool(report.get("control")),
            "group_id": a.group_id, "tags": a.tags or [], "notes": a.notes or "",
            "latest_version": AGENT_VERSION}


def get_agent(db: Session, aid: str) -> Agent:
    agent = db.get(Agent, aid)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    return agent


@router.get("")
def list_agents(db: Session = Depends(get_db)):
    return [summary(a) for a in db.scalars(select(Agent).order_by(Agent.name))]


@router.get("/keys", dependencies=[Depends(require("servers.manage"))])
def key_inventory(db: Session = Depends(get_db)):
    """Which SSH key (fingerprint) has access to which server and user – from the reports of the Linux agents."""
    keys: dict[str, dict] = {}
    for a in db.scalars(select(Agent).where(Agent.disabled.is_(False)).order_by(Agent.name)):
        report = a.last_report or {}
        for u in (report.get("linux") or {}).get("users") or []:
            for k in u.get("keys") or []:
                entry = keys.setdefault(k.get("fingerprint", ""), {"fingerprint": k.get("fingerprint", ""),
                                                                   "type": k.get("type", ""), "comments": [],
                                                                   "installs": []})
                comment = k.get("comment", "")
                if comment and comment not in entry["comments"]:
                    entry["comments"].append(comment)
                entry["installs"].append({"agent_id": a.id, "agent": a.name, "user": u.get("name", ""),
                                          "control": bool(report.get("control")), "options": bool(k.get("options"))})
    return sorted((k for k in keys.values() if k["fingerprint"]), key=lambda k: (-len(k["installs"]), k["fingerprint"]))


@router.get("/{aid}")
def read_agent(aid: str, db: Session = Depends(get_db)):
    agent = get_agent(db, aid)
    return {**summary(agent), "report": agent.last_report}


@router.post("", status_code=201, dependencies=[Depends(require("agents.manage"))])
def create_agent(body: AgentIn, request: Request, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name is missing")
    if any(a.name.lower() == name.lower() for a in db.scalars(select(Agent))):
        raise HTTPException(409, "An agent with this name already exists")
    key = secrets.token_urlsafe(32)
    opts = InstallOptions(**body.model_dump(exclude={"name"}))
    agent = Agent(name=name, kind=body.kind, key_hash=token_hash(key), install_options=encrypt_json(opts.model_dump()))
    db.add(agent)
    db.commit()
    # The key is shown exactly once; only its hash is stored.
    audit("agent.created", agent.name, agent.kind)
    return {**summary(agent), "key": key, "install": create_install(request, agent.id, key, opts)}


SECRET_FIELDS = ("proxmox_token_secret", "cf_client_secret")


def stored_options(agent: Agent) -> dict:
    if not agent.install_options:
        return {}
    try:
        return decrypt_json(agent.install_options)
    except InvalidToken:
        return {}


@router.get("/{aid}/install-options", dependencies=[Depends(require("agents.manage"))])
def install_options(aid: str, db: Session = Depends(get_db)):
    """Options of the last install command for prefilling – secrets are never sent back, only whether one is stored."""
    agent = get_agent(db, aid)
    opts = stored_options(agent)
    out = {k: v for k, v in opts.items() if k not in SECRET_FIELDS}
    out.update({f"has_{k}": bool(opts.get(k)) for k in SECRET_FIELDS})
    out.setdefault("kind", agent.kind)
    return out


@router.post("/{aid}/install", dependencies=[Depends(require("agents.manage"))])
def new_install(aid: str, request: Request, body: dict = Body(...), db: Session = Depends(get_db)):
    """New install command (e.g. to reinstall or add Proxmox later). Replaces the agent key.
    Empty secret fields keep the stored secrets of the last install command."""
    agent = get_agent(db, aid)
    stored = stored_options(agent)
    merged = {**body}
    for field in SECRET_FIELDS:
        if not str(merged.get(field) or "").strip() and stored.get(field):
            merged[field] = stored[field]
    try:
        body = InstallOptions(**merged)
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from None
    key = secrets.token_urlsafe(32)
    agent.key_hash = token_hash(key)
    agent.kind = body.kind
    agent.install_options = encrypt_json(body.model_dump())
    db.commit()
    audit("agent.install_command", agent.name, f"{agent.kind}, new key")
    return {"key": key, "install": create_install(request, agent.id, key, body)}


class MetaIn(BaseModel):
    group_id: str | None = Field(default=None, max_length=12)
    tags: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=5000)  # None keeps the stored notes


@router.put("/{aid}/meta", dependencies=[Depends(require("servers.organize"))])
def update_meta(aid: str, body: MetaIn, db: Session = Depends(get_db)):
    """Group (one) and tags (any number, from the central list) of a server."""
    agent = get_agent(db, aid)
    if body.group_id and db.get(ServerGroup, body.group_id) is None:
        raise HTTPException(422, "Unknown group")
    agent.group_id = body.group_id or None
    agent.tags = check_tags(db, body.tags)
    if body.notes is not None:
        agent.notes = body.notes.strip()
    db.commit()
    audit("agent.meta", agent.name, ", ".join(agent.tags))
    return summary(agent)


# --- server groups --------------------------------------------------------------------------------

groups_router = APIRouter(prefix="/api/server-groups", tags=["agents"], dependencies=[Depends(current_user)])


def group_out(g: ServerGroup) -> dict:
    return {"id": g.id, "name": g.name, "position": g.position, "color": g.color}


def unique_group(db: Session, name: str, own: str = "") -> None:
    if any(g.id != own and g.name.lower() == name.lower() for g in db.scalars(select(ServerGroup))):
        raise HTTPException(409, "A group with this name already exists")


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str = Field(default="gray", pattern=COLOR_PATTERN)


class GroupOrder(BaseModel):
    ids: list[str] = Field(max_length=100)


@groups_router.get("")
def list_groups(db: Session = Depends(get_db)):
    return [group_out(g) for g in db.scalars(select(ServerGroup).order_by(ServerGroup.position, ServerGroup.name))]


@groups_router.post("", status_code=201, dependencies=[Depends(require("admin.organize"))])
def create_group(body: GroupIn, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name is missing")
    unique_group(db, name)
    last = db.scalars(select(ServerGroup.position).order_by(ServerGroup.position.desc())).first()
    group = ServerGroup(name=name, color=body.color, position=(last + 1) if last is not None else 0)
    db.add(group)
    db.commit()
    audit("servergroup.created", name)
    return group_out(group)


@groups_router.put("/order", dependencies=[Depends(require("admin.organize"))])
def order_groups(body: GroupOrder, db: Session = Depends(get_db)):
    found = {g.id: g for g in db.scalars(select(ServerGroup))}
    if set(body.ids) != set(found) or len(body.ids) != len(found):
        raise HTTPException(422, "The list must contain every group exactly once")
    for position, gid in enumerate(body.ids):
        found[gid].position = position
    db.commit()
    return [group_out(found[gid]) for gid in body.ids]


@groups_router.put("/{gid}", dependencies=[Depends(require("admin.organize"))])
def rename_group(gid: str, body: GroupIn, db: Session = Depends(get_db)):
    group = db.get(ServerGroup, gid)
    if group is None:
        raise HTTPException(404, "Group not found")
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name is missing")
    unique_group(db, name, gid)
    group.name, group.color = name, body.color
    db.commit()
    audit("servergroup.renamed", name)
    return group_out(group)


@groups_router.delete("/{gid}", status_code=204, dependencies=[Depends(require("admin.organize"))])
def delete_group(gid: str, db: Session = Depends(get_db)):
    group = db.get(ServerGroup, gid)
    if group is None:
        raise HTTPException(404, "Group not found")
    for agent in db.scalars(select(Agent).where(Agent.group_id == gid)):
        agent.group_id = None  # the servers stay, without a group
    db.delete(group)
    db.commit()
    audit("servergroup.deleted", group.name)
    return Response(status_code=204)


@router.put("/{aid}", dependencies=[Depends(require("agents.manage"))])
def update_agent(aid: str, body: AgentUpdate, db: Session = Depends(get_db)):
    agent = get_agent(db, aid)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(422, "Name is missing")
        if any(a.id != aid and a.name.lower() == name.lower() for a in db.scalars(select(Agent))):
            raise HTTPException(409, "An agent with this name already exists")
        agent.name = name
    if body.kind is not None:
        agent.kind = body.kind
    old_name = agent.name
    if body.disabled is not None:
        agent.disabled = body.disabled
    db.commit()
    changes = [f"renamed from {old_name}" if body.name is not None and old_name != agent.name else "",
               "disabled" if body.disabled else "enabled" if body.disabled is False else ""]
    audit("agent.updated", agent.name, ", ".join(c for c in changes if c))
    return summary(agent)


@router.delete("/{aid}", status_code=204, dependencies=[Depends(require("agents.manage"))])
def delete_agent(aid: str, db: Session = Depends(get_db)):
    agent = get_agent(db, aid)
    db.delete(agent)
    db.commit()
    audit("agent.deleted", agent.name)
    return Response(status_code=204)


# --- Reports ------------------------------------------------------------------------

RENAMES = {"collectedAt": "collected_at", "workingDir": "working_dir", "configFiles": "config_files",
           "sentAt": "sent_at"}


def normalize(value):
    """Accept reports of the Server-Info agent (camelCase keys) as well."""
    if isinstance(value, dict):
        return {RENAMES.get(k, k): normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def agent_for_key(db: Session, key: str) -> Agent | None:
    if not 0 < len(key) <= 200:
        return None
    digest = token_hash(key)
    return next((a for a in db.scalars(select(Agent)) if hmac.compare_digest(a.key_hash, digest)), None)


@report_router.get("/install/{token}", include_in_schema=False)
def agent_install_script(token: str, request: Request):
    """Install script for one agent. Public, but only with a valid one-time token."""
    return install_script(request, token)


@report_router.get("/bundle", include_in_schema=False)
def agent_bundle_download(request: Request, db: Session = Depends(get_db)):
    """The standalone agent (Python zipapp) – only for a known agent key."""
    agent = agent_for_key(db, request.headers.get("x-agent-key", ""))
    if agent is None or agent.disabled:
        raise HTTPException(401, "Unknown agent key")
    return bundle_response()


@report_router.post("/report")
async def agent_report(request: Request, db: Session = Depends(get_db)):
    """Report of an agent. No session login – authenticated by the agent key (X-Agent-Key)."""
    agent = agent_for_key(db, request.headers.get("x-agent-key", ""))
    if agent is None:
        raise HTTPException(401, "Unknown agent key")
    if agent.disabled:
        raise HTTPException(403, "Agent is disabled")
    length = int(request.headers.get("content-length") or 0)
    if not 0 < length <= MAX_REPORT:
        raise HTTPException(413, "Report too large")
    last = as_utc(agent.last_report_at)
    if last and time.time() - last.timestamp() < MIN_INTERVAL:
        raise HTTPException(429, "Too many reports")
    try:
        report = json.loads((await request.body())[:MAX_REPORT])
    except ValueError:
        raise HTTPException(400, "Report must be JSON") from None
    if not isinstance(report, dict):
        raise HTTPException(400, "Report must be a JSON object")
    agent.last_report = normalize(report)
    agent.last_report_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
