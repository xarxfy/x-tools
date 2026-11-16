"""Global search: servers, containers, Proxmox guests, services, domains, customers, jobs, websites and tags."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.features import load as load_features
from app.collector.exchange import load_snapshot
from app.core.db import get_db
from app.models import Agent, Customer, Heartbeat, NetworkEntry, ServerGroup, Service, Site
from app.monitor.issues import all_containers

router = APIRouter(prefix="/api/search", tags=["search"], dependencies=[Depends(current_user)])

PER_TYPE = 6


class Matcher:
    """All words of the query must appear somewhere in the text of an entry; entries whose name matches rank first."""

    def __init__(self, query: str):
        self.words = [w for w in query.lower().split() if w]

    def score(self, title: str, *fields: object) -> int | None:
        name = title.lower()
        text = " ".join([name] + [str(f).lower() for f in fields if f])
        if not all(w in text for w in self.words):
            return None
        q = " ".join(self.words)
        if name == q:
            return 0
        if name.startswith(q):
            return 1
        return 2 if all(w in name for w in self.words) else 3


def search_all(db: Session, query: str) -> list[dict]:
    m = Matcher(query)
    found: dict[str, list[tuple[int, dict]]] = {}

    def add(kind: str, title: str, subtitle: str, link: str, *fields: object) -> None:
        s = m.score(title, subtitle, *fields)
        if s is not None:
            found.setdefault(kind, []).append((s, {"type": kind, "title": title, "subtitle": subtitle, "link": link}))

    groups = {g.id: g.name for g in db.scalars(select(ServerGroup))}
    tags: set[str] = set()
    for a in db.scalars(select(Agent).where(Agent.disabled.is_(False))):
        report = a.last_report or {}
        page = {"proxmox": "/proxmox", "linux": "/servers"}.get(a.kind, "/docker")
        link = f"/servers/{a.id}" if a.kind == "linux" else f"{page}#agent-{a.id}"
        group = groups.get(a.group_id or "", "")
        sub = " · ".join(x for x in (a.kind, group, ", ".join(f"#{t}" for t in a.tags or [])) if x)
        ips = [ad["ip"] for i in report.get("network") or [] if not i.get("virtual") for ad in i.get("addrs", [])]
        add("server", a.name, sub, link, report.get("hostname"), (report.get("linux") or {}).get("os"), a.notes, *ips, *(a.tags or []))
        tags.update(a.tags or [])
        for c in all_containers(report.get("docker")):
            add("container", c.get("name", ""), f"{a.name} · {c.get('image', '')}", f"/docker#agent-{a.id}", c.get("image"))
        for g in (report.get("proxmox") or {}).get("guests") or []:
            add("guest", g.get("name", ""), f"{a.name} · {str(g.get('type', '')).upper()} {g.get('vmid')}",
                f"/proxmox/{a.id}/{g.get('node')}/{g.get('vmid')}", g.get("vmid"), g.get("tags"))
    snap = load_snapshot()
    for c in all_containers(snap):
        add("container", c.get("name", ""), f"{c.get('image', '')}", "/docker#local", c.get("image"))
    for tag in sorted(tags):
        add("tag", f"#{tag}", "", f"/servers?tag={tag}")

    for s in db.scalars(select(Service)):
        ports = " ".join(f"{p.get('port')} {p.get('label', '')}" for p in s.ports or [])
        add("service", s.name, " · ".join(x for x in (s.host, s.folder, s.type) if x), f"/services?q={s.name}",
            ports, s.notes, *(s.domains or []))
        for d in s.domains or []:
            add("domain", d, s.name, f"/domains?q={d}")
    for e in db.scalars(select(NetworkEntry)):
        add("network", e.name, e.ip, "/servers?view=network", e.ip, e.notes)
    for j in db.scalars(select(Heartbeat)):
        add("job", j.name, "", "/monitoring")
    if load_features().customers:
        for c in db.scalars(select(Customer)):
            add("customer", c.name, c.contact or "", f"/customers/{c.id}", c.email, c.phone, c.owner, c.notes, c.agreements)
        for w in db.scalars(select(Site)):
            add("site", w.name, w.repo_url, f"/customers/{w.customer_id}" if w.customer_id else "/customers", w.branch)

    out: list[dict] = []
    for kind in ("server", "service", "container", "guest", "network", "domain", "customer", "site", "job", "tag"):
        items = sorted(found.get(kind, []), key=lambda x: (x[0], x[1]["title"].lower()))
        out += [i for _, i in items[:PER_TYPE]]
    return out


@router.get("")
def search(q: str = Query(min_length=1, max_length=100), db: Session = Depends(get_db)):
    return {"query": q, "results": search_all(db, q)}
