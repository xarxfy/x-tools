"""Commands for agents (start/stop containers, Proxmox guests and systemd services, logs, reboot).

Agents stay outbound-only: an agent with control switched on (XT_AGENT_CONTROL=1,
set by the install command) long-polls GET /api/agent/commands and posts the
result back. X-TOOLS keeps the queue in memory; commands expire after a minute.
Operators trigger commands through POST /api/agents/{id}/action.
"""

import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require
from app.collector.linux import PROTECTED as PROTECTED_UNITS
from app.collector.proxmox import DISK_KEY, validate_changes
from app.core.audit import audit
from app.core.db import get_db
from app.models import Agent

COMMAND_TTL = 60
WAIT_RESULT = 75
ACTIONS = {"docker.start", "docker.stop", "docker.restart", "docker.logs",
           "proxmox.start", "proxmox.shutdown", "proxmox.stop", "proxmox.reboot", "proxmox.config", "proxmox.resize",
           "systemd.start", "systemd.stop", "systemd.restart", "systemd.logs", "system.reboot"}


class Queue:
    def __init__(self):
        self.cond = threading.Condition()
        self.pending: dict[str, list[dict]] = {}   # agent id → commands not yet fetched
        self.results: dict[str, dict] = {}         # command id → result

    def add(self, agent_id: str, command: dict) -> None:
        with self.cond:
            self.pending.setdefault(agent_id, []).append(command)
            self.cond.notify_all()

    def take(self, agent_id: str, wait: float) -> list[dict]:
        deadline = time.time() + wait
        with self.cond:
            while True:
                now = time.time()
                items = [c for c in self.pending.pop(agent_id, []) if c["expires_at"] > now]
                if items or now >= deadline:
                    return items
                self.cond.wait(deadline - now)

    def finish(self, command_id: str, result: dict) -> None:
        with self.cond:
            self.results[command_id] = result
            self.cond.notify_all()

    def wait_result(self, command_id: str, wait: float) -> dict | None:
        deadline = time.time() + wait
        with self.cond:
            while command_id not in self.results:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self.cond.wait(remaining)
            return self.results.pop(command_id)

    def drop(self, agent_id: str, command_id: str) -> None:
        with self.cond:
            self.pending[agent_id] = [c for c in self.pending.get(agent_id, []) if c["id"] != command_id]
            self.results.pop(command_id, None)


queue = Queue()
router = APIRouter(prefix="/api/agents", tags=["agents"])


class ActionIn(BaseModel):
    action: str = Field(max_length=30)
    target: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.@:-]*$")
    node: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9.-]*$")
    type: str = Field(default="", pattern="^(|lxc|qemu)$")
    lines: int = Field(default=300, ge=10, le=1000)
    changes: dict = Field(default_factory=dict)  # proxmox.config
    disk: str = Field(default="", max_length=20)  # proxmox.resize
    add_gb: int = Field(default=0, ge=0, le=4096)


@router.post("/{aid}/action", dependencies=[Depends(require("operator"))])
def agent_action(aid: str, body: ActionIn, db: Session = Depends(get_db)):
    agent = db.get(Agent, aid)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    if body.action not in ACTIONS:
        raise HTTPException(422, "Unknown action")
    report = agent.last_report or {}
    if agent.disabled or not report.get("control"):
        raise HTTPException(409, "Control is not switched on for this agent – create a new install command with "
                                 "“Allow control”")
    if body.action.startswith("proxmox."):
        if not report.get("proxmox") or not body.node or not body.type or not body.target.isdigit():
            raise HTTPException(422, "Proxmox guest needed (node, type, ID)")
        guests = {(str(g.get("vmid")), g.get("node")) for g in (report.get("proxmox") or {}).get("guests") or []}
        if (body.target, body.node) not in guests:
            raise HTTPException(422, "Unknown guest")
        params = {"node": body.node, "type": body.type}
        what = f"{agent.name}: {body.type.upper()} {body.target}"
        detail = ""
        if body.action == "proxmox.config":
            try:
                validate_changes(body.changes, body.type)
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
            params["changes"] = body.changes
            detail = ", ".join(f"{k}={'…' if k == 'description' else v}" for k, v in body.changes.items())
        elif body.action == "proxmox.resize":
            if not DISK_KEY.match(body.disk) or body.disk.startswith(("efidisk", "tpmstate")) or not body.add_gb:
                raise HTTPException(422, "Disk and size needed")
            params.update(disk=body.disk, add_gb=body.add_gb)
            detail = f"{body.disk} +{body.add_gb} GB"
    elif body.action.startswith("systemd.") or body.action == "system.reboot":
        linux = report.get("linux")
        if not linux:
            raise HTTPException(422, "This agent does not report a Linux server (create the install command for "
                                     "the kind “Linux server”)")
        params = {"lines": body.lines}
        if body.action == "system.reboot":
            if body.target != "host":
                raise HTTPException(422, "Unknown target")
            what = f"{agent.name}: reboot"
        else:
            if body.target not in {s.get("name") for s in linux.get("services") or []}:
                raise HTTPException(422, "Unknown service")
            if body.target in PROTECTED_UNITS and not body.action.endswith(".logs"):
                raise HTTPException(422, f"{body.target} cannot be controlled from X-TOOLS")
            what = f"{agent.name}: {body.target}"
        detail = ""
    else:
        names = {c.get("name") for p in (report.get("docker") or {}).get("projects", []) for c in p.get("containers", [])}
        names |= {c.get("name") for c in (report.get("docker") or {}).get("containers", [])}
        if body.target not in names:
            raise HTTPException(422, "Unknown container")
        params = {"lines": body.lines}
        what = f"{agent.name}: {body.target}"
        detail = ""
    command = {"id": secrets.token_hex(12), "action": body.action, "target": body.target, "params": params,
               "expires_at": time.time() + COMMAND_TTL}
    queue.add(agent.id, command)
    result = queue.wait_result(command["id"], WAIT_RESULT)
    if result is None:
        queue.drop(agent.id, command["id"])
        audit(body.action, what, "no answer from the agent")
        raise HTTPException(504, "The agent did not answer – is it running (and on version 3 or newer)?")
    audit(body.action, what, detail if result.get("ok") else f"{detail} failed: {result.get('error', '')}".strip())
    if not result.get("ok"):
        raise HTTPException(502, result.get("error") or "The action failed")
    return result


# --- agent side (key authentication, see agents.agent_for_key) ---------------------------

agent_router = APIRouter(prefix="/api/agent", tags=["agents"])


def _agent(request: Request, db: Session) -> Agent:
    from app.api.agents import agent_for_key
    agent = agent_for_key(db, request.headers.get("x-agent-key", ""))
    if agent is None:
        raise HTTPException(401, "Unknown agent key")
    if agent.disabled:
        raise HTTPException(403, "Agent is disabled")
    return agent


@agent_router.get("/commands")
def poll_commands(request: Request, wait: int = Query(25, ge=0, le=30), db: Session = Depends(get_db)):
    agent_id = _agent(request, db).id
    db.close()  # do not hold a database connection while waiting
    return [{k: c[k] for k in ("id", "action", "target", "params")} for c in queue.take(agent_id, wait)]


class ResultIn(BaseModel):
    ok: bool
    error: str = Field(default="", max_length=500)
    logs: str = Field(default="", max_length=500_000)


@agent_router.post("/commands/{command_id}")
def command_result(command_id: str, body: ResultIn, request: Request, db: Session = Depends(get_db)):
    _agent(request, db)
    queue.finish(command_id, body.model_dump())
    return {"ok": True}
