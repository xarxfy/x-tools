"""Everything that currently needs attention.

Each issue has a stable key (so notifications are sent once per problem), a
kind (matches the notification event switches), a level and a link into the UI.
"""

import time
from datetime import timezone

from sqlalchemy import select

from app.collector.exchange import load_snapshot
from app.core.config import get_settings
from app.core.db import session_scope
from app.models import Agent, Customer, Service
from app.monitor import sites, state
from app.monitor.ports import port_key, port_status

ALERT_STATE = "alert_state"
AGENT_STALE = 300  # seconds without a report


def container_state(c: dict) -> tuple[str, str]:
    if c.get("state") == "running":
        if c.get("health") == "unhealthy":
            return "warn", "unhealthy"
        if c.get("health") == "health: starting":
            return "warn", "starting"
        return "up", "running"
    if c.get("state") in ("restarting", "paused", "created"):
        return "warn", c["state"]
    return "down", "stopped"


def all_containers(snap: dict | None) -> list[dict]:
    if not snap:
        return []
    return [c for p in snap.get("projects", []) for c in p.get("containers", [])] + list(snap.get("containers", []))


def ago(ts) -> str:
    seconds = max(0, int(time.time() - (ts or 0)))
    if seconds < 90:
        return "just now"
    if seconds < 3600:
        return f"{round(seconds / 60)} min ago"
    if seconds < 86400:
        return f"{round(seconds / 3600)} h ago"
    return f"{round(seconds / 86400)} days ago"


def manual_stops() -> set[str]:
    return set((state.load(ALERT_STATE, {}) or {}).get("manual", []))


def mark_manual(name: str, stopped: bool) -> None:
    """Containers stopped on purpose through the UI are not reported as problems."""
    def change(data):
        manual = set(data.get("manual", []))
        (manual.add if stopped else manual.discard)(name)
        data["manual"] = sorted(manual)
        return data
    state.update(ALERT_STATE, change)


def system_issues(add, sysinfo: dict, prefix: str, name: str, link: str) -> None:
    if sysinfo.get("disk_total"):
        pct = sysinfo["disk_used"] / sysinfo["disk_total"] * 100
        if pct >= 80:
            add(f"{prefix}disk", "system", "down" if pct >= 90 else "warn", f"{name}disk {pct:.0f} % full", link)
    if sysinfo.get("mem_total") and sysinfo.get("mem_used", 0) / sysinfo["mem_total"] >= 0.9:
        add(f"{prefix}mem", "system", "warn",
            f"{name}memory {sysinfo['mem_used'] / sysinfo['mem_total'] * 100:.0f} % used", link)


def find_issues(ports: dict[int, bool] | None = None) -> list[dict]:
    issues: list[dict] = []

    def add(key, kind, level, text, link, **extra):
        issues.append({"key": key, "kind": kind, "level": level, "text": text, "link": link, **extra})

    with session_scope() as db:
        services = [(s.id, s.name, s.host, list(s.ports or [])) for s in db.scalars(select(Service))]
        agents = [(a.id, a.name, a.last_report, a.last_report_at) for a in db.scalars(select(Agent))
                  if not a.disabled]
        customer_sites = [(c.id, c.name, d) for c in db.scalars(select(Customer)) for s in c.services
                          for d in (s.domains or [])]

    # Ports
    if ports is None:
        ports = port_status((host, p["port"]) for _, _, host, ps in services for p in ps)
    for sid, name, host, ps in services:
        for p in ps:
            if not ports.get(port_key(host, p["port"])):
                label = f" ({p['label']})" if p.get("label") else ""
                where = f" on {host}" if host else ""
                add(f"port:{sid}:{p['port']}", "port", "down",
                    f"{name}: port {p['port']}{label}{where} does not answer", "/services")

    # This server: Docker + system
    snap = load_snapshot()
    docker_link = "/servers/local?tab=docker"
    if snap is None:
        add("docker:none", "docker", "warn", "No Docker data yet – is x-tools-collector running?", docker_link)
    elif snap.get("error"):
        add("docker:error", "docker", "down", snap["error"], docker_link)
    else:
        if time.time() - (snap.get("collected_at") or 0) > max(300, 5 * get_settings().collect_interval):
            add("docker:stale", "docker", "warn", f"Docker data is outdated (last update {ago(snap.get('collected_at'))})",
                docker_link)
        manual = manual_stops()
        for c in all_containers(snap):
            level, label = container_state(c)
            if level == "up":
                continue
            if c.get("state") == "exited" and c["name"] in manual:
                add(f"container:{c['name']}", "container", "warn", f"Container {c['name']}: stopped by you",
                    docker_link, manual=True)
            else:
                add(f"container:{c['name']}", "container", level, f"Container {c['name']}: {label}", docker_link)
    if snap:
        system_issues(add, snap.get("system") or {}, "", "This server: ", "/servers/local")

    # Agents
    for aid, name, report, received in agents:
        link = f"/servers/{aid}"
        if report is None or received is None:
            add(f"agent:{aid}", "agent", "warn", f"Server '{name}' has never reported", link)
            continue
        received_ts = (received if received.tzinfo else received.replace(tzinfo=timezone.utc)).timestamp()
        if time.time() - received_ts > AGENT_STALE:
            add(f"agent:{aid}", "agent", "down", f"Server '{name}' does not report (last {ago(received_ts)})", link)
            continue
        try:
            if (report.get("proxmox") or {}).get("error"):
                add(f"agent:{aid}:proxmox", "agent", "warn", f"{name}: {report['proxmox']['error']}", link)
            for c in all_containers(report.get("docker")):
                level, label = container_state(c)
                if level != "up":
                    add(f"container:{aid}:{c['name']}", "container", level, f"{name}: container {c['name']}: {label}",
                        link)
            system_issues(add, report.get("system") or {}, f"{aid}:", f"{name}: ", link)
        except (KeyError, TypeError, AttributeError) as error:
            add(f"agent:{aid}:broken", "agent", "warn", f"{name}: report cannot be read ({error})", link)

    # Customer websites
    from app.api.features import load as features
    checks = sites.load_results() if features().customers else {}
    seen = set()
    for cid, cname, domain in customer_sites:
        ch = checks.get(domain)
        if domain in seen or not ch or ch.get("level") not in ("down", "warn"):
            continue
        seen.add(domain)
        add(f"site:{domain}", "site", ch["level"], f"{domain} ({cname}): {ch.get('label', '')}", f"/customers/{cid}")

    issues.sort(key=lambda i: (i.get("manual", False), i["level"] != "down"))
    return issues
