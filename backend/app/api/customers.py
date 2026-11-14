"""Customers: contacts and agreements for hosted sites; services are linked to a customer."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.db import get_db
from app.models import Customer, Service
from app.schemas import CustomerIn, CustomerOut

router = APIRouter(prefix="/api/customers", tags=["customers"], dependencies=[Depends(current_user)])


def to_out(c: Customer) -> CustomerOut:
    return CustomerOut(id=c.id, name=c.name, contact=c.contact, email=c.email, phone=c.phone, owner=c.owner,
                       agreements=c.agreements, notes=c.notes, service_ids=sorted(s.id for s in c.services))


def get_customer(db: Session, cid: str) -> Customer:
    customer = db.get(Customer, cid)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    return customer


def apply(customer: Customer, body: CustomerIn, db: Session) -> None:
    for field in ("name", "contact", "email", "phone", "owner", "agreements", "notes"):
        setattr(customer, field, getattr(body, field))
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


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, db: Session = Depends(get_db)):
    customer = Customer()
    db.add(customer)
    apply(customer, body, db)
    db.commit()
    return to_out(customer)


@router.put("/{cid}", response_model=CustomerOut)
def update_customer(cid: str, body: CustomerIn, db: Session = Depends(get_db)):
    customer = get_customer(db, cid)
    apply(customer, body, db)
    db.commit()
    return to_out(customer)


@router.delete("/{cid}", status_code=204)
def delete_customer(cid: str, db: Session = Depends(get_db)):
    db.delete(get_customer(db, cid))  # services stay, customer_id becomes NULL
    db.commit()
    return Response(status_code=204)
