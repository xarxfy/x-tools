"""PDF reports: an overall report (servers, services) or one for a customer. Never contains credentials or notes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.inventory import inventory
from app.core.audit import audit
from app.core.db import get_db
from app.core.pdf import Document
from app.models import Customer, CustomerCategory, Service

router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(current_user)])

TEXT = {
    "en": {
        "title": "Server and service report", "customer": "Customer report", "created": "Created", "servers": "Servers",
        "services": "Services and domains", "name": "Name", "kind": "Type", "group": "Group", "system": "System",
        "ips": "IP addresses", "updates": "Updates", "uptime": "Uptime", "host": "Host", "domains": "Domains",
        "ports": "Ports", "folder": "Folder", "type": "Kind", "category": "Category", "contact": "Contact",
        "email": "E-mail", "phone": "Phone", "domain_owner": "Domain owner", "agreements": "Agreements",
        "none": "Nothing to show.", "page": "Page", "customers": "Customer", "all": "All customers",
        "servers_of": "Servers of this customer's services", "days": "d", "reboot": "reboot needed",
        "summary": "{servers} servers, {services} services",
        "kinds": {"linux": "Linux", "proxmox": "Proxmox", "docker": "Docker", "local": "This server"},
    },
    "de": {
        "title": "Server- und Dienste-Bericht", "customer": "Kundenbericht", "created": "Erstellt", "servers": "Server",
        "services": "Dienste und Domains", "name": "Name", "kind": "Art", "group": "Gruppe", "system": "System",
        "ips": "IP-Adressen", "updates": "Updates", "uptime": "Laufzeit", "host": "Host", "domains": "Domains",
        "ports": "Ports", "folder": "Ordner", "type": "Art", "category": "Kategorie", "contact": "Kontakt",
        "email": "E-Mail", "phone": "Telefon", "domain_owner": "Domain-Inhaber", "agreements": "Vereinbarungen",
        "none": "Nichts anzuzeigen.", "page": "Seite", "customers": "Kunde", "all": "Alle Kunden",
        "servers_of": "Server der Dienste dieses Kunden", "days": "T", "reboot": "Neustart nötig",
        "summary": "{servers} Server, {services} Dienste",
        "kinds": {"linux": "Linux", "proxmox": "Proxmox", "docker": "Docker", "local": "Dieser Server"},
    },
}


def uptime(seconds) -> str:
    return "" if seconds is None else f"{int(seconds // 86400)} d"


def server_rows(rows: list[dict], tx: dict) -> list[list[str]]:
    out = []
    for r in rows:
        updates = "" if r["updates"] is None else str(r["updates"])
        if r["reboot"]:
            updates = f"{updates} ({tx['reboot']})".strip()
        system = " / ".join(x for x in (r["os"], r["kernel"]) if x)
        out.append([r["name"], tx["kinds"].get(r["kind"], r["kind"]), r["group"], system, ", ".join(r["ips"]),
                    updates, uptime(r["uptime"])])
    return out


def service_rows(items: list[Service]) -> list[list[str]]:
    return [[s.name, s.host, "\n".join(s.domains or []),
             ", ".join(f"{p['port']}" + (f" {p['label']}" if p.get("label") else "") for p in (s.ports or [])),
             s.type, s.folder] for s in items]


@router.get("/pdf")
def pdf_report(customer: str | None = Query(default=None, max_length=12), servers: bool = True, services: bool = True,
               lang: str = Query(default="en", pattern="^(en|de)$"), db: Session = Depends(get_db)):
    if not servers and not services:
        raise HTTPException(422, "Choose at least one section")
    tx = TEXT[lang]
    now = datetime.now(timezone.utc).astimezone()
    stamp = now.strftime("%d.%m.%Y %H:%M" if lang == "de" else "%Y-%m-%d %H:%M")
    query = select(Service).order_by(Service.name)
    cust = None
    if customer:
        cust = db.get(Customer, customer)
        if cust is None:
            raise HTTPException(404, "Customer not found")
        query = query.where(Service.customer_id == cust.id)
    service_list = list(db.scalars(query))
    inv = inventory(db)
    if cust:  # only the servers the customer's services run on
        hosts = {s.host.strip().lower() for s in service_list if s.host}
        inv = [r for r in inv if r["name"].lower() in hosts or r["hostname"].lower() in hosts
               or any(ip.lower() in hosts for ip in r["ips"])]

    doc = Document(tx["customer"] if cust else tx["title"], f"X-TOOLS · {tx['created']} {stamp}", tx["page"])
    doc.heading(f"{tx['customer']}: {cust.name}" if cust else tx["title"], 20)
    doc.paragraph(f"{tx['created']}: {stamp}")
    doc.space(6)
    if cust:
        category = db.get(CustomerCategory, cust.category_id) if cust.category_id else None
        doc.facts([(tx["category"], category.name if category else ""), (tx["contact"], cust.contact),
                   (tx["email"], cust.email), (tx["phone"], cust.phone), (tx["domain_owner"], cust.owner),
                   (tx["agreements"], cust.agreements)])
    else:
        doc.paragraph(tx["summary"].format(servers=len(inv) if servers else 0, services=len(service_list) if services else 0))
    if servers:
        doc.space(10)
        doc.heading(tx["servers_of"] if cust else tx["servers"])
        doc.space(4)
        if inv:
            doc.table([tx["name"], tx["kind"], tx["group"], tx["system"], tx["ips"], tx["updates"], tx["uptime"]],
                      server_rows(inv, tx), [1.3, 0.8, 0.8, 2.2, 1.7, 1.0, 0.7])
        else:
            doc.paragraph(tx["none"])
    if services:
        doc.space(10)
        doc.heading(tx["services"])
        doc.space(4)
        if service_list:
            doc.table([tx["name"], tx["host"], tx["domains"], tx["ports"], tx["type"], tx["folder"]],
                      service_rows(service_list), [1.3, 1.2, 2.0, 1.2, 0.9, 1.3])
        else:
            doc.paragraph(tx["none"])
    audit("report.pdf", cust.name if cust else "all", f"servers={servers} services={services}")
    name = "x-tools-report" + (f"-{''.join(c if c.isascii() and c.isalnum() else '-' for c in cust.name.lower())[:30]}" if cust else "")
    return Response(doc.render(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}-{now:%Y%m%d}.pdf"',
                             "Cache-Control": "no-store"})
