"""Services (what runs where), their port status and their encrypted credentials."""

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.core.audit import audit
from app.core.db import get_db
from app.core.security import decrypt_json, encrypt_json
from app.models import CredentialSet, Customer, Service
from app.monitor.ports import port_status as check_ports
from app.schemas import Credential, ServiceIn, ServiceOut

router = APIRouter(prefix="/api/services", tags=["services"], dependencies=[Depends(current_user)])

MAX_CREDENTIALS = 20


def to_out(s: Service) -> ServiceOut:
    return ServiceOut(id=s.id, name=s.name, host=s.host, domains=s.domains or [], ports=s.ports or [], folder=s.folder,
                      type=s.type, notes=s.notes, customer_id=s.customer_id,
                      customer_name=s.customer.name if s.customer else None,
                      credential_count=s.credentials.count if s.credentials else 0, checklist=s.checklist or [])


def get_service(db: Session, sid: str) -> Service:
    service = db.get(Service, sid)
    if service is None:
        raise HTTPException(404, "Service not found")
    return service


def apply(service: Service, body: ServiceIn, db: Session) -> None:
    if body.customer_id and db.get(Customer, body.customer_id) is None:
        raise HTTPException(422, "Customer not found")
    service.name, service.domains, service.folder, service.host = body.name, body.domains, body.folder, body.host
    service.ports = [p.model_dump() for p in body.ports]
    service.type, service.notes, service.customer_id = body.type, body.notes, body.customer_id
    if body.checklist is not None:
        service.checklist = [item.model_dump() for item in body.checklist]


@router.get("", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return [to_out(s) for s in db.scalars(select(Service).order_by(Service.name))]


@router.post("", response_model=ServiceOut, status_code=201, dependencies=[Depends(require("services.edit"))])
def create_service(body: ServiceIn, db: Session = Depends(get_db)):
    service = Service()
    apply(service, body, db)
    db.add(service)
    db.commit()
    audit("service.created", service.name)
    return to_out(service)


@router.put("/{sid}", response_model=ServiceOut, dependencies=[Depends(require("services.edit"))])
def update_service(sid: str, body: ServiceIn, db: Session = Depends(get_db)):
    service = get_service(db, sid)
    apply(service, body, db)
    db.commit()
    audit("service.updated", service.name)
    return to_out(service)


@router.delete("/{sid}", status_code=204, dependencies=[Depends(require("services.edit"))])
def delete_service(sid: str, db: Session = Depends(get_db)):
    service = get_service(db, sid)
    db.delete(service)
    db.commit()
    audit("service.deleted", service.name)
    return Response(status_code=204)


# --- Port status ---------------------------------------------------------------


@router.get("/ports", response_model=dict[str, bool])
def port_status(db: Session = Depends(get_db)):
    """Whether each port used by a service answers on the check host."""
    return check_ports((s.host, p["port"]) for s in db.scalars(select(Service)) for p in (s.ports or []))


# --- Credentials ----------------------------------------------------------------


@router.get("/{sid}/credentials", response_model=list[Credential], dependencies=[Depends(require("credentials.manage"))])
def get_credentials(sid: str, db: Session = Depends(get_db)):
    service = get_service(db, sid)
    if not service.credentials:
        return []
    audit("credentials.viewed", service.name)
    try:
        return decrypt_json(service.credentials.data)
    except InvalidToken:
        raise HTTPException(500, "Credentials cannot be decrypted – was the secret key changed?") from None


@router.put("/{sid}/credentials", response_model=list[Credential], dependencies=[Depends(require("credentials.manage"))])
def set_credentials(sid: str, body: list[Credential], db: Session = Depends(get_db)):
    service = get_service(db, sid)
    items = [c.model_dump() for c in body if any(c.model_dump().values())]
    if len(items) > MAX_CREDENTIALS:
        raise HTTPException(422, f"At most {MAX_CREDENTIALS} credentials per service")
    if items:
        if service.credentials:
            service.credentials.data, service.credentials.count = encrypt_json(items), len(items)
        else:
            service.credentials = CredentialSet(data=encrypt_json(items), count=len(items))
    elif service.credentials:
        db.delete(service.credentials)
    db.commit()
    audit("credentials.changed", service.name, f"{len(items)} login(s)")
    return items
