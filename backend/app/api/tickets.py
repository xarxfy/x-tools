"""Tickets of customers and the history (journal) of a customer: comments, status changes and free notes."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.core.audit import audit
from app.core.db import get_db
from app.models import Agent, Customer, JournalEntry, Service, Ticket, User, utcnow
from app.schemas import strip

router = APIRouter(prefix="/api", tags=["tickets"], dependencies=[Depends(current_user)])

STATUSES = ("open", "progress", "waiting", "done")
PRIORITIES = ("low", "normal", "high", "urgent")
PRIORITY_RANK = {p: i for i, p in enumerate(reversed(PRIORITIES))}  # urgent first


class TicketIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    status: str = "open"
    priority: str = "normal"
    due: date | None = None
    assignee_id: int | None = None
    service_id: str | None = Field(default=None, max_length=12)
    agent_id: str | None = Field(default=None, max_length=12)

    _strip = field_validator("title", "description", mode="before")(strip)

    @field_validator("status")
    @classmethod
    def known_status(cls, v: str) -> str:
        if v not in STATUSES:
            raise ValueError("Unknown status")
        return v

    @field_validator("priority")
    @classmethod
    def known_priority(cls, v: str) -> str:
        if v not in PRIORITIES:
            raise ValueError("Unknown priority")
        return v


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=10000)

    _strip = field_validator("text", mode="before")(strip)


def utc(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    return (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)).isoformat()


def ticket_out(t: Ticket) -> dict:
    return {"id": t.id, "number": t.number, "customer_id": t.customer_id, "customer": t.customer.name, "title": t.title,
            "description": t.description, "status": t.status, "priority": t.priority,
            "due": t.due.isoformat() if t.due else None, "assignee_id": t.assignee_id,
            "assignee": t.assignee.username if t.assignee else None, "service_id": t.service_id, "agent_id": t.agent_id,
            "created_by": t.created_by, "created_at": utc(t.created_at), "updated_at": utc(t.updated_at),
            "closed_at": utc(t.closed_at)}


def entry_out(e: JournalEntry) -> dict:
    return {"id": e.id, "ticket_id": e.ticket_id, "ticket": e.ticket.number if e.ticket else None,
            "ticket_title": e.ticket.title if e.ticket else None, "kind": e.kind, "text": e.text, "author": e.author,
            "created_at": utc(e.created_at)}


def get_ticket(db: Session, tid: str) -> Ticket:
    t = db.get(Ticket, tid)
    if t is None:
        raise HTTPException(404, "Ticket not found")
    return t


def check_links(db: Session, body: TicketIn, customer: Customer) -> None:
    if body.assignee_id is not None:
        u = db.get(User, body.assignee_id)
        if u is None or u.disabled:
            raise HTTPException(422, "Unknown user")
    if body.service_id and db.get(Service, body.service_id) is None:
        raise HTTPException(422, "Unknown service")
    if body.agent_id and db.get(Agent, body.agent_id) is None:
        raise HTTPException(422, "Unknown server")


def log(db: Session, ticket: Ticket, kind: str, text: str, author: str) -> None:
    db.add(JournalEntry(customer_id=ticket.customer_id, ticket_id=ticket.id, kind=kind, text=text, author=author))


@router.get("/tickets/assignees")
def assignees(db: Session = Depends(get_db)):
    """Users a ticket can be assigned to (name only, for everyone who may see tickets)."""
    return [{"id": u.id, "username": u.username} for u in db.scalars(select(User).where(User.disabled.is_(False)).order_by(User.username))]


@router.get("/tickets")
def list_tickets(status: str = Query(default="open", pattern="^(open|all|done)$"), customer: str | None = Query(default=None, max_length=12),
                 db: Session = Depends(get_db)):
    q = select(Ticket)
    if status == "open":
        q = q.where(Ticket.status != "done")
    elif status == "done":
        q = q.where(Ticket.status == "done")
    if customer:
        q = q.where(Ticket.customer_id == customer)
    rows = list(db.scalars(q))
    rows.sort(key=lambda t: (t.status == "done", PRIORITY_RANK[t.priority], t.due or date.max, -t.number))
    return [ticket_out(t) for t in rows]


@router.get("/tickets/{tid}")
def read_ticket(tid: str, db: Session = Depends(get_db)):
    t = get_ticket(db, tid)
    return {**ticket_out(t), "entries": [entry_out(e) for e in t.entries]}


@router.post("/customers/{cid}/tickets", status_code=201, dependencies=[Depends(require("tickets.edit"))])
def create_ticket(cid: str, body: TicketIn, user=Depends(current_user), db: Session = Depends(get_db)):
    customer = db.get(Customer, cid)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    check_links(db, body, customer)
    number = (db.scalar(select(func.max(Ticket.number))) or 0) + 1
    t = Ticket(number=number, customer_id=cid, created_by=user.username, **body.model_dump())
    if t.status == "done":
        t.closed_at = utcnow()
    db.add(t)
    db.flush()
    log(db, t, "event", "created", user.username)
    db.commit()
    audit("ticket.created", f"#{t.number} {customer.name}", t.title)
    return ticket_out(t)


@router.put("/tickets/{tid}", dependencies=[Depends(require("tickets.edit"))])
def update_ticket(tid: str, body: TicketIn, user=Depends(current_user), db: Session = Depends(get_db)):
    t = get_ticket(db, tid)
    check_links(db, body, t.customer)
    changes = []
    if body.status != t.status:
        changes.append(f"status:{t.status}>{body.status}")
        t.closed_at = utcnow() if body.status == "done" else None
    if body.priority != t.priority:
        changes.append(f"priority:{t.priority}>{body.priority}")
    if body.assignee_id != t.assignee_id:
        other = db.get(User, body.assignee_id) if body.assignee_id else None
        changes.append(f"assignee:{other.username if other else '-'}")
    for field, value in body.model_dump().items():
        setattr(t, field, value)
    t.updated_at = utcnow()
    for c in changes:
        log(db, t, "event", c, user.username)
    db.commit()
    audit("ticket.updated", f"#{t.number}", ", ".join(changes) or t.title)
    return ticket_out(t)


@router.delete("/tickets/{tid}", status_code=204, dependencies=[Depends(require("tickets.edit"))])
def delete_ticket(tid: str, db: Session = Depends(get_db)):
    t = get_ticket(db, tid)
    number, name = t.number, t.customer.name
    db.delete(t)
    db.commit()
    audit("ticket.deleted", f"#{number} {name}")
    return Response(status_code=204)


@router.post("/tickets/{tid}/comments", status_code=201, dependencies=[Depends(require("tickets.edit"))])
def comment(tid: str, body: NoteIn, user=Depends(current_user), db: Session = Depends(get_db)):
    t = get_ticket(db, tid)
    e = JournalEntry(customer_id=t.customer_id, ticket_id=t.id, kind="note", text=body.text, author=user.username)
    db.add(e)
    t.updated_at = utcnow()
    db.commit()
    return entry_out(e)


# --- the history of a customer --------------------------------------------------------------------------


@router.get("/customers/{cid}/journal")
def journal(cid: str, q: str = Query(default="", max_length=100), db: Session = Depends(get_db)):
    if db.get(Customer, cid) is None:
        raise HTTPException(404, "Customer not found")
    query = select(JournalEntry).where(JournalEntry.customer_id == cid)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.where(JournalEntry.text.ilike(like))
    return [entry_out(e) for e in db.scalars(query.order_by(JournalEntry.created_at.desc()).limit(500))]


@router.post("/customers/{cid}/journal", status_code=201, dependencies=[Depends(require("customers.edit"))])
def add_note(cid: str, body: NoteIn, user=Depends(current_user), db: Session = Depends(get_db)):
    if db.get(Customer, cid) is None:
        raise HTTPException(404, "Customer not found")
    e = JournalEntry(customer_id=cid, kind="note", text=body.text, author=user.username)
    db.add(e)
    db.commit()
    return entry_out(e)


@router.delete("/journal/{eid}", status_code=204, dependencies=[Depends(require("customers.edit"))])
def delete_entry(eid: str, db: Session = Depends(get_db)):
    e = db.get(JournalEntry, eid)
    if e is None or e.kind == "event":
        raise HTTPException(404, "Entry not found")
    db.delete(e)
    db.commit()
    return Response(status_code=204)
