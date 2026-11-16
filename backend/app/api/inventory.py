"""Inventory (one row per server) and network overview (IP addresses of servers, Proxmox guests and your own entries)."""

import ipaddress
import time
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.agents import host_metrics, as_utc
from app.api.deps import current_user, require
from app.collector import linux
from app.collector.agent import AGENT_VERSION
from app.collector.exchange import load_snapshot
from app.core.audit import audit
from app.core.db import get_db
from app.models import Agent, NetworkEntry, ServerGroup
from app.monitor.eol import support

router = APIRouter(prefix="/api", tags=["inventory"], dependencies=[Depends(current_user)])

_local: dict = {"at": 0.0, "data": []}


def local_interfaces() -> list[dict]:
    """Interfaces of the machine X-TOOLS runs on (the web container shares the host's network)."""
    if time.time() - _local["at"] > 60:
        try:
            _local["data"] = linux.interfaces()
        except Exception:  # noqa: BLE001
            _local["data"] = []
        _local["at"] = time.time()
    return _local["data"]


def primary_ips(interfaces: list[dict]) -> list[str]:
    return [a["ip"] for i in interfaces if not i.get("virtual") for a in i.get("addrs", [])][:6]


# --- inventory ------------------------------------------------------------------------------------


@router.get("/inventory")
def inventory(db: Session = Depends(get_db)):
    groups = {g.id: g.name for g in db.scalars(select(ServerGroup))}
    rows = []
    for a in db.scalars(select(Agent).where(Agent.disabled.is_(False)).order_by(Agent.name)):
        report = a.last_report or {}
        lin = report.get("linux") or {}
        m = host_metrics(report)
        link = f"/servers/{a.id}" if a.kind == "linux" else f"{'/proxmox' if a.kind == 'proxmox' else '/docker'}#agent-{a.id}"
        rows.append({
            "id": a.id, "name": a.name, "kind": a.kind, "group": groups.get(a.group_id or "", ""), "tags": a.tags or [],
            "hostname": report.get("hostname", ""), "os": lin.get("os", ""), "kernel": lin.get("kernel", ""),
            "arch": lin.get("arch", ""), "support": support(lin.get("os_id", ""), lin.get("os_version", "")),
            "version": str(report.get("version", "")), "outdated": bool(report) and str(report.get("version", "")) != AGENT_VERSION,
            "uptime": m["uptime"], "updates": m["updates"], "reboot": m["reboot"],
            "last_report_at": as_utc(a.last_report_at), "ips": primary_ips(report.get("network") or []), "link": link,
        })
    snap = load_snapshot() or {}
    system = snap.get("system") or {}
    if system:
        rows.insert(0, {
            "id": "local", "name": system.get("hostname") or "X-TOOLS", "kind": "local", "group": "", "tags": [],
            "hostname": system.get("hostname", ""), "os": "", "kernel": "", "arch": "", "support": support("", ""),
            "version": "", "outdated": False, "uptime": system.get("uptime"), "updates": None, "reboot": False,
            "last_report_at": None, "ips": primary_ips(local_interfaces()), "link": "/docker#local",
        })
    return rows


# --- network ----------------------------------------------------------------------------------------


def usable(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_loopback or a.is_link_local or a.is_unspecified or a.is_multicast)


def network_of(ip: str, prefix) -> str:
    try:
        return str(ipaddress.ip_interface(f"{ip}/{prefix}").network) if prefix is not None else ""
    except ValueError:
        return ""


def collect(db: Session) -> list[dict]:
    items: list[dict] = []
    seen: set[tuple] = set()

    def add(ip: str, name: str, names: set[str], kind: str, source: str, link: str = "", iface: str = "", mac: str = "",
            prefix=None, virtual: bool = False, entry_id: str = "", notes: str = "") -> None:
        if not usable(ip):
            return
        ip = str(ipaddress.ip_address(ip))
        key = (ip, name.lower(), kind, iface)
        if key in seen:
            return
        seen.add(key)
        items.append({"ip": ip, "name": name, "names": sorted(n for n in names if n), "kind": kind, "source": source,
                      "link": link, "iface": iface, "mac": mac, "network": network_of(ip, prefix), "virtual": virtual,
                      "entry_id": entry_id, "notes": notes, "conflict": False})

    for a in db.scalars(select(Agent).where(Agent.disabled.is_(False))):
        report = a.last_report or {}
        page = "/proxmox" if a.kind == "proxmox" else "/docker"
        link = f"/servers/{a.id}" if a.kind == "linux" else f"{page}#agent-{a.id}"
        names = {a.name.lower(), str(report.get("hostname", "")).lower()}
        network = report.get("network")
        for i in network or []:
            for ad in i.get("addrs", []):
                add(ad["ip"], a.name, names, "server", a.name, link, i.get("name", ""), i.get("mac", ""), ad.get("prefix"),
                    bool(i.get("virtual")))
        px = report.get("proxmox") or {}
        details = px.get("details") or {}
        if network is None:  # agents older than version 8: the node addresses from the Proxmox network configuration
            for node in (details.get("nodes") or {}).values():
                for n in node.get("network") or []:
                    for cidr in (n.get("cidr"), n.get("cidr6")):
                        if cidr and "/" in cidr:
                            ip, _, prefix = cidr.partition("/")
                            add(ip, a.name, names, "server", a.name, link, n.get("iface", ""), "", int(prefix))
        for g in px.get("guests") or []:
            gd = (details.get("guests") or {}).get(f"{g.get('node')}/{g.get('vmid')}") or {}
            glink = f"/proxmox/{a.id}/{g.get('node')}/{g.get('vmid')}"
            gname = g.get("name") or str(g.get("vmid"))
            source = f"Proxmox {a.name}"
            for net in (gd.get("config") or {}).get("nets") or []:
                for cidr in (net.get("ip"), net.get("ip6")):
                    if cidr and "/" in cidr:
                        ip, _, prefix = cidr.partition("/")
                        add(ip, gname, {gname.lower()}, "guest", source, glink, net.get("name", ""), net.get("mac", ""), int(prefix))
            for ad in gd.get("ips") or []:
                add(ad.get("address", ""), gname, {gname.lower()}, "guest", source, glink, ad.get("interface", ""))

    system = (load_snapshot() or {}).get("system") or {}
    host = str(system.get("hostname", "")).lower()
    for i in local_interfaces():
        for ad in i.get("addrs", []):
            add(ad["ip"], system.get("hostname") or "X-TOOLS", {host, "x-tools"}, "server", "X-TOOLS", "/docker#local",
                i.get("name", ""), i.get("mac", ""), ad.get("prefix"), bool(i.get("virtual")))
    for e in db.scalars(select(NetworkEntry)):
        add(e.ip, e.name, {e.name.lower()}, "manual", "manual", iface="", entry_id=e.id, notes=e.notes)
    # a Proxmox guest that also runs an agent appears twice with the same address: keep the server row
    servers = {(it["ip"], n) for it in items if it["kind"] == "server" for n in it["names"]}
    items = [it for it in items if not (it["kind"] == "guest" and any((it["ip"], n) in servers for n in it["names"]))]
    return items


def mark_conflicts(items: list[dict]) -> list[dict]:
    """The same IP address on systems with different names (the names of one machine are matched, e.g. agent and guest)."""
    conflicts = []
    by_ip: dict[str, list[dict]] = {}
    for it in items:
        if not it["virtual"]:
            by_ip.setdefault(it["ip"], []).append(it)
    for ip, group in by_ip.items():
        clusters: list[set[str]] = []
        for it in group:
            names = set(it["names"]) or {it["name"].lower()}
            merged = [c for c in clusters if c & names]
            for c in merged:
                clusters.remove(c)
                names |= c
            clusters.append(names)
        if len(clusters) > 1:
            conflicts.append({"ip": ip, "names": sorted({it["name"] for it in group})})
            for it in group:
                it["conflict"] = True
    return conflicts


@router.get("/network")
def network(db: Session = Depends(get_db)):
    items = collect(db)
    conflicts = mark_conflicts(items)
    for it in items:
        it.pop("names", None)
    return {"items": items, "conflicts": sorted(conflicts, key=lambda c: c["ip"])}


class EntryIn(BaseModel):
    ip: str = Field(min_length=2, max_length=45)
    name: str = Field(min_length=1, max_length=80)
    notes: str = Field(default="", max_length=300)

    @field_validator("ip")
    @classmethod
    def valid_ip(cls, value: str) -> str:
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:
            raise ValueError("Not a valid IP address") from None

    @field_validator("name", "notes")
    @classmethod
    def strip(cls, value: str) -> str:
        return " ".join(value.split())


def entry_out(e: NetworkEntry) -> dict:
    return {"id": e.id, "ip": e.ip, "name": e.name, "notes": e.notes}


@router.post("/network/entries", status_code=201, dependencies=[Depends(require("network.edit"))])
def create_entry(body: EntryIn, db: Session = Depends(get_db)):
    entry = NetworkEntry(ip=body.ip, name=body.name, notes=body.notes)
    db.add(entry)
    db.commit()
    audit("network.entry.created", f"{entry.name} {entry.ip}")
    return entry_out(entry)


@router.put("/network/entries/{eid}", dependencies=[Depends(require("network.edit"))])
def update_entry(eid: str, body: EntryIn, db: Session = Depends(get_db)):
    entry = db.get(NetworkEntry, eid)
    if entry is None:
        raise HTTPException(404, "Entry not found")
    entry.ip, entry.name, entry.notes = body.ip, body.name, body.notes
    db.commit()
    audit("network.entry.updated", f"{entry.name} {entry.ip}")
    return entry_out(entry)


@router.delete("/network/entries/{eid}", status_code=204, dependencies=[Depends(require("network.edit"))])
def delete_entry(eid: str, db: Session = Depends(get_db)):
    entry = db.get(NetworkEntry, eid)
    if entry is None:
        raise HTTPException(404, "Entry not found")
    db.delete(entry)
    db.commit()
    audit("network.entry.deleted", f"{entry.name} {entry.ip}")
    return Response(status_code=204)
