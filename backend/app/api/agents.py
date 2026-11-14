"""Agents: other servers that report their state (outbound only, never receive commands)."""

import hmac
import json
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.agent_install import InstallOptions, bundle_response, create_install, install_script
from app.api.deps import current_user
from app.collector.agent import AGENT_VERSION
from app.core.db import get_db
from app.core.security import token_hash
from app.models import Agent

router = APIRouter(prefix="/api/agents", tags=["agents"], dependencies=[Depends(current_user)])
report_router = APIRouter(prefix="/api/agent", tags=["agents"])

MAX_REPORT = 5 * 1024 * 1024
MIN_INTERVAL = 5  # seconds between two reports of one agent


class AgentIn(InstallOptions):
    name: str = Field(min_length=1, max_length=60)


class AgentUpdate(BaseModel):
    disabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=60)
    kind: str | None = Field(default=None, pattern="^(proxmox|docker)$")


def as_utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def summary(a: Agent) -> dict:
    report = a.last_report or {}
    return {"id": a.id, "name": a.name, "kind": a.kind, "disabled": a.disabled, "created_at": as_utc(a.created_at),
            "last_report_at": as_utc(a.last_report_at), "hostname": report.get("hostname", ""),
            "version": report.get("version", ""),
            "has_docker": bool(report.get("docker")), "has_proxmox": bool(report.get("proxmox")),
            "outdated": bool(report) and str(report.get("version", "")) != AGENT_VERSION,
            "latest_version": AGENT_VERSION}


def get_agent(db: Session, aid: str) -> Agent:
    agent = db.get(Agent, aid)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    return agent


@router.get("")
def list_agents(db: Session = Depends(get_db)):
    return [summary(a) for a in db.scalars(select(Agent).order_by(Agent.name))]


@router.get("/{aid}")
def read_agent(aid: str, db: Session = Depends(get_db)):
    agent = get_agent(db, aid)
    return {**summary(agent), "report": agent.last_report}


@router.post("", status_code=201)
def create_agent(body: AgentIn, request: Request, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name is missing")
    if any(a.name.lower() == name.lower() for a in db.scalars(select(Agent))):
        raise HTTPException(409, "An agent with this name already exists")
    key = secrets.token_urlsafe(32)
    agent = Agent(name=name, kind=body.kind, key_hash=token_hash(key))
    db.add(agent)
    db.commit()
    # The key is shown exactly once; only its hash is stored.
    opts = InstallOptions(**body.model_dump(exclude={"name"}))
    return {**summary(agent), "key": key, "install": create_install(request, agent.id, key, opts)}


@router.post("/{aid}/install")
def new_install(aid: str, body: InstallOptions, request: Request, db: Session = Depends(get_db)):
    """New install command (e.g. to reinstall or add Proxmox later). Replaces the agent key."""
    agent = get_agent(db, aid)
    key = secrets.token_urlsafe(32)
    agent.key_hash = token_hash(key)
    agent.kind = body.kind
    db.commit()
    return {"key": key, "install": create_install(request, agent.id, key, body)}


@router.put("/{aid}")
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
    if body.disabled is not None:
        agent.disabled = body.disabled
    db.commit()
    return summary(agent)


@router.delete("/{aid}", status_code=204)
def delete_agent(aid: str, db: Session = Depends(get_db)):
    db.delete(get_agent(db, aid))
    db.commit()
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
