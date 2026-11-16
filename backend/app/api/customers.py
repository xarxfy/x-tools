"""Customers: contacts and agreements for hosted sites; services are linked to a customer."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.core.audit import audit
from app.core.db import get_db
from app.models import Customer, CustomerCategory, Service
from app.schemas import CategoryIn, CustomerIn, CustomerOut

router = APIRouter(prefix="/api/customers", tags=["customers"], dependencies=[Depends(current_user)])


def to_out(c: Customer) -> CustomerOut:
    return CustomerOut(id=c.id, name=c.name, contact=c.contact, email=c.email, phone=c.phone, owner=c.owner,
                       agreements=c.agreements, notes=c.notes, category_id=c.category_id, service_ids=sorted(s.id for s in c.services))


def get_customer(db: Session, cid: str) -> Customer:
    customer = db.get(Customer, cid)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    return customer


def apply(customer: Customer, body: CustomerIn, db: Session) -> None:
    for field in ("name", "contact", "email", "phone", "owner", "agreements", "notes"):
        setattr(customer, field, getattr(body, field))
    if body.category_id and db.get(CustomerCategory, body.category_id) is None:
        raise HTTPException(422, "Unknown category")
    customer.category_id = body.category_id or None
    wanted = set(body.service_ids)
    services = list(db.scalars(select(Service).where(Service.id.in_(wanted)))) if wanted else []
    if len(services) != len(wanted):
        raise HTTPException(422, "Unknown service")
    customer.services = services  # services of another customer move to this one


@router.get("", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db)):
    return [to_out(c) for c in db.scalars(select(Customer).order_by(Customer.name))]


@router.get("/{cid}", response_model=CustomerOut)
def read_customer(cid: str, db: Session = Depends(get_db)):
    return to_out(get_customer(db, cid))


@router.post("", response_model=CustomerOut, status_code=201, dependencies=[Depends(require("customers.edit"))])
def create_customer(body: CustomerIn, db: Session = Depends(get_db)):
    customer = Customer()
    db.add(customer)
    apply(customer, body, db)
    db.commit()
    audit("customer.created", customer.name)
    return to_out(customer)


@router.put("/{cid}", response_model=CustomerOut, dependencies=[Depends(require("customers.edit"))])
def update_customer(cid: str, body: CustomerIn, db: Session = Depends(get_db)):
    customer = get_customer(db, cid)
    apply(customer, body, db)
    db.commit()
    audit("customer.updated", customer.name)
    return to_out(customer)


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
