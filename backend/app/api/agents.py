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

from app.api.deps import current_user
from app.core.db import get_db
from app.core.security import token_hash
from app.models import Agent

router = APIRouter(prefix="/api/agents", tags=["agents"], dependencies=[Depends(current_user)])
report_router = APIRouter(prefix="/api/agent", tags=["agents"])

MAX_REPORT = 5 * 1024 * 1024
MIN_INTERVAL = 5  # seconds between two reports of one agent


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class AgentUpdate(BaseModel):
    disabled: bool


def as_utc(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def summary(a: Agent) -> dict:
    report = a.last_report or {}
    return {"id": a.id, "name": a.name, "disabled": a.disabled, "created_at": as_utc(a.created_at),
            "last_report_at": as_utc(a.last_report_at), "hostname": report.get("hostname", ""),
            "version": report.get("version", "")}


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
def create_agent(body: AgentIn, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name is missing")
    if any(a.name.lower() == name.lower() for a in db.scalars(select(Agent))):
        raise HTTPException(409, "An agent with this name already exists")
    key = secrets.token_urlsafe(32)
    agent = Agent(name=name, key_hash=token_hash(key))
    db.add(agent)
    db.commit()
    # The key is shown exactly once; only its hash is stored.
    return {**summary(agent), "key": key}


@router.put("/{aid}")
def update_agent(aid: str, body: AgentUpdate, db: Session = Depends(get_db)):
    agent = get_agent(db, aid)
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


@report_router.post("/report")
async def agent_report(request: Request, db: Session = Depends(get_db)):
    """Report of an agent. No session login – authenticated by the agent key (X-Agent-Key)."""
    key = request.headers.get("x-agent-key", "")
    agent = None
    if 0 < len(key) <= 200:
        digest = token_hash(key)
        agent = next((a for a in db.scalars(select(Agent)) if hmac.compare_digest(a.key_hash, digest)), None)
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
