"""Customers: contacts, contract data, tasks and agreements; services, servers and jobs are linked to a customer."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, permissions_of, require
from app.core.audit import audit
from app.core.db import get_db
from app.models import Agent, Customer, CustomerCategory, CustomerContact, CustomerTask, Heartbeat, Service
from app.schemas import CategoryIn, CustomerIn, CustomerOut, TaskIn

router = APIRouter(prefix="/api/customers", tags=["customers"], dependencies=[Depends(current_user)])

CONTRACT_WARN_DAYS = 60


def deadline_of(c: Customer) -> date | None:
    """The last day to give notice: the end of the contract minus the period of notice."""
    return c.contract_end - timedelta(days=c.notice_days or 0) if c.contract_end else None


def contract_out(c: Customer) -> dict:
    dl = deadline_of(c)
    return {"contract_end": c.contract_end.isoformat() if c.contract_end else None, "notice_days": c.notice_days,
            "support_hours": c.support_hours, "response_time": c.response_time,
            "deadline": dl.isoformat() if dl else None}


def task_out(t: CustomerTask) -> dict:
    return {"id": t.id, "title": t.title, "due": t.due.isoformat() if t.due else None, "done": t.done}


def to_out(c: Customer, contracts: bool = False) -> CustomerOut:
    tasks = sorted(c.tasks, key=lambda t: (t.done, t.due or date.max, t.created_at))
    return CustomerOut(
        id=c.id, name=c.name, owner=c.owner, agreements=c.agreements, notes=c.notes, category_id=c.category_id,
        service_ids=sorted(s.id for s in c.services), agent_ids=sorted(a.id for a in assigned(c, Agent)),
        job_ids=sorted(h.id for h in assigned(c, Heartbeat)),
        contacts=[{"id": p.id, "name": p.name, "role": p.role, "email": p.email, "phone": p.phone} for p in c.contacts],
        tasks=[task_out(t) for t in tasks], contract=contract_out(c) if contracts else None)


def assigned(c: Customer, model) -> list:
    from sqlalchemy.orm import object_session
    return list(object_session(c).scalars(select(model).where(model.customer_id == c.id)))


def can_contracts(user, db: Session) -> bool:
    return "customers.contracts" in permissions_of(user, db)


def get_customer(db: Session, cid: str) -> Customer:
    customer = db.get(Customer, cid)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    return customer


def link(db: Session, model, ids: list[str], customer: Customer, what: str) -> None:
    """Make exactly these rows belong to the customer (rows of another customer move here)."""
    wanted = set(ids)
    rows = list(db.scalars(select(model).where(model.id.in_(wanted)))) if wanted else []
    if len(rows) != len(wanted):
        raise HTTPException(422, f"Unknown {what}")
    for row in db.scalars(select(model).where(model.customer_id == customer.id)):
        if row.id not in wanted:
            row.customer_id = None
    for row in rows:
        row.customer_id = customer.id


def apply(customer: Customer, body: CustomerIn, db: Session, contracts: bool) -> None:
    for field in ("name", "owner", "agreements", "notes"):
        setattr(customer, field, getattr(body, field))
    if body.category_id and db.get(CustomerCategory, body.category_id) is None:
        raise HTTPException(422, "Unknown category")
    customer.category_id = body.category_id or None
    wanted = set(body.service_ids)
    services = list(db.scalars(select(Service).where(Service.id.in_(wanted)))) if wanted else []
    if len(services) != len(wanted):
        raise HTTPException(422, "Unknown service")
    customer.services = services  # services of another customer move to this one
    if body.contacts is not None:
        customer.contacts = [CustomerContact(name=p.name, role=p.role, email=p.email, phone=p.phone, position=i)
                             for i, p in enumerate(body.contacts)]
    if contracts and body.contract is not None:
        for field in ("contract_end", "notice_days", "support_hours", "response_time"):
            setattr(customer, field, getattr(body.contract, field))
    db.flush()
    link(db, Agent, body.agent_ids, customer, "server")
    link(db, Heartbeat, body.job_ids, customer, "job")


@router.get("", response_model=list[CustomerOut])
def list_customers(user=Depends(current_user), db: Session = Depends(get_db)):
    contracts = can_contracts(user, db)
    return [to_out(c, contracts) for c in db.scalars(select(Customer).order_by(Customer.name))]


@router.get("/{cid}", response_model=CustomerOut)
def read_customer(cid: str, user=Depends(current_user), db: Session = Depends(get_db)):
    return to_out(get_customer(db, cid), can_contracts(user, db))


@router.post("", response_model=CustomerOut, status_code=201, dependencies=[Depends(require("customers.edit"))])
def create_customer(body: CustomerIn, user=Depends(current_user), db: Session = Depends(get_db)):
    customer = Customer()
    db.add(customer)
    contracts = can_contracts(user, db)
    apply(customer, body, db, contracts)
    db.commit()
    audit("customer.created", customer.name)
    return to_out(customer, contracts)


@router.put("/{cid}", response_model=CustomerOut, dependencies=[Depends(require("customers.edit"))])
def update_customer(cid: str, body: CustomerIn, user=Depends(current_user), db: Session = Depends(get_db)):
    customer = get_customer(db, cid)
    contracts = can_contracts(user, db)
    apply(customer, body, db, contracts)
    db.commit()
    audit("customer.updated", customer.name)
    return to_out(customer, contracts)


# --- tasks ----------------------------------------------------------------------------------------------

tasks = APIRouter(prefix="/api", tags=["customers"], dependencies=[Depends(current_user), Depends(require("customers.edit"))])


@tasks.post("/customers/{cid}/tasks", status_code=201)
def create_task(cid: str, body: TaskIn, db: Session = Depends(get_db)):
    customer = get_customer(db, cid)
    task = CustomerTask(customer_id=customer.id, title=body.title, due=body.due, done=body.done)
    db.add(task)
    db.commit()
    audit("customer.task", customer.name, body.title)
    return task_out(task)


def get_task(db: Session, tid: str) -> CustomerTask:
    task = db.get(CustomerTask, tid)
    if task is None:
        raise HTTPException(404, "Task not found")
    return task


@tasks.put("/customer-tasks/{tid}")
def update_task(tid: str, body: TaskIn, db: Session = Depends(get_db)):
    task = get_task(db, tid)
    task.title, task.due, task.done = body.title, body.due, body.done
    db.commit()
    return task_out(task)


@tasks.delete("/customer-tasks/{tid}", status_code=204)
def delete_task(tid: str, db: Session = Depends(get_db)):
    db.delete(get_task(db, tid))
    db.commit()
    return Response(status_code=204)


@router.delete("/{cid}", status_code=204, dependencies=[Depends(require("customers.edit"))])
def delete_customer(cid: str, db: Session = Depends(get_db)):
    customer = get_customer(db, cid)
    db.delete(customer)  # services stay, customer_id becomes NULL
    db.commit()
    audit("customer.deleted", customer.name)
    return Response(status_code=204)


# --- categories (priority classes) ------------------------------------------------------------------

categories = APIRouter(prefix="/api/customer-categories", tags=["customers"], dependencies=[Depends(current_user)])


def category_out(c: CustomerCategory) -> dict:
    return {"id": c.id, "name": c.name, "position": c.position}


@categories.get("")
def list_categories(db: Session = Depends(get_db)):
    return [category_out(c) for c in db.scalars(select(CustomerCategory).order_by(CustomerCategory.position,
                                                                                    CustomerCategory.name))]


def unique_name(db: Session, name: str, own: str = "") -> None:
    for c in db.scalars(select(CustomerCategory)):
        if c.id != own and c.name.lower() == name.lower():
            raise HTTPException(409, "A category with this name already exists")


@categories.post("", status_code=201, dependencies=[Depends(require("customers.edit"))])
def create_category(body: CategoryIn, db: Session = Depends(get_db)):
    unique_name(db, body.name)
    last = db.scalars(select(CustomerCategory.position).order_by(CustomerCategory.position.desc())).first()
    category = CustomerCategory(name=body.name, position=(last + 1) if last is not None else 0)
    db.add(category)
    db.commit()
    audit("customer.category.created", category.name)
    return category_out(category)


class OrderIn(BaseModel):
    ids: list[str] = Field(max_length=100)


@categories.put("/order", dependencies=[Depends(require("customers.edit"))])
def order_categories(body: OrderIn, db: Session = Depends(get_db)):
    found = {c.id: c for c in db.scalars(select(CustomerCategory))}
    if set(body.ids) != set(found):
        raise HTTPException(422, "The list must contain every category exactly once")
    for position, cid in enumerate(body.ids):
        found[cid].position = position
    db.commit()
    return [category_out(found[cid]) for cid in body.ids]


@categories.put("/{cid}", dependencies=[Depends(require("customers.edit"))])
def rename_category(cid: str, body: CategoryIn, db: Session = Depends(get_db)):
    category = db.get(CustomerCategory, cid)
    if category is None:
        raise HTTPException(404, "Category not found")
    unique_name(db, body.name, cid)
    category.name = body.name
    db.commit()
    audit("customer.category.renamed", category.name)
    return category_out(category)


@categories.delete("/{cid}", status_code=204, dependencies=[Depends(require("customers.edit"))])
def delete_category(cid: str, db: Session = Depends(get_db)):
    category = db.get(CustomerCategory, cid)
    if category is None:
        raise HTTPException(404, "Category not found")
    for customer in db.scalars(select(Customer).where(Customer.category_id == cid)):
        customer.category_id = None  # customers stay, without a category
    db.delete(category)
    db.commit()
    audit("customer.category.deleted", category.name)
    return Response(status_code=204)
