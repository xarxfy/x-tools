"""Cloudflare, read-only: zones, DNS records, tunnels with their routes, Access applications.

The API token (needs only read permissions, see docs/cloudflare.md) is stored
encrypted. A snapshot is fetched every 10 minutes and compared with the
services in X-TOOLS: which domain points where, does the tunnel route go to
the port of the service, is the domain protected by Access?
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.fernet import InvalidToken

from app.core.config import get_settings
from app.core.security import decrypt_json, encrypt_json
from app.monitor import state

SETTINGS_KEY = "cloudflare"
SNAPSHOT_KEY = "cloudflare_snapshot"
REFRESH_SECONDS = 600
TUNNEL_SUFFIX = ".cfargotunnel.com"


class CloudflareError(Exception):
    pass


# --- Settings ---------------------------------------------------------------------


def load_settings() -> dict:
    return state.load(SETTINGS_KEY, {}) or {}


def token() -> str:
    enc = load_settings().get("token")
    if not enc:
        return ""
    try:
        return decrypt_json(enc)
    except InvalidToken:
        return ""


def configured() -> bool:
    return bool(load_settings().get("token"))


def save_token(value: str) -> None:
    state.save(SETTINGS_KEY, {**load_settings(), "token": encrypt_json(value), "saved_at": time.time()})


def allow_write() -> bool:
    return configured() and bool(load_settings().get("allow_write"))


def set_allow_write(value: bool) -> None:
    state.save(SETTINGS_KEY, {**load_settings(), "allow_write": bool(value)})


def remove() -> None:
    state.save(SETTINGS_KEY, {})
    state.save(SNAPSHOT_KEY, {})


# --- API ----------------------------------------------------------------------------


def api(path: str, tok: str, params: dict | None = None, method: str = "GET", body: dict | None = None):
    base = get_settings().cloudflare_api.rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                                          "User-Agent": "x-tools"})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            data = json.loads(res.read())
    except urllib.error.HTTPError as error:
        try:
            data = json.loads(error.read())
            message = "; ".join(e.get("message", "") for e in data.get("errors", [])) or f"HTTP {error.code}"
        except (ValueError, AttributeError):
            message = f"HTTP {error.code}"
        if error.code in (401, 403):
            message = f"no permission ({message})"
        raise CloudflareError(message) from None
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise CloudflareError(f"Cloudflare not reachable: {getattr(error, 'reason', error)}") from None
    if not data.get("success", False):
        raise CloudflareError("; ".join(e.get("message", "") for e in data.get("errors", [])) or "request failed")
    return data


def api_all(path: str, tok: str, params: dict | None = None, per_page: int = 100) -> list:
    out, page = [], 1
    while True:
        data = api(path, tok, {**(params or {}), "page": page, "per_page": per_page})
        out.extend(data.get("result") or [])
        info = data.get("result_info") or {}
        if page >= int(info.get("total_pages") or 1) or page >= 50:
            return out
        page += 1


def verify(tok: str) -> None:
    """Raises CloudflareError if the token does not work at all (zones must be readable)."""
    api("/zones", tok, {"per_page": 5})


def fetch(tok: str) -> dict:
    snap: dict = {"fetched_at": time.time(), "errors": {}, "zones": [], "tunnels": [], "access_apps": []}
    try:
        zones = api_all("/zones", tok, per_page=50)
    except CloudflareError as error:
        snap["errors"]["zones"] = str(error)
        return snap
    accounts = {}
    for z in zones:
        acc = z.get("account") or {}
        if acc.get("id"):
            accounts[acc["id"]] = acc.get("name", "")
        zone = {"id": z["id"], "name": z["name"], "status": z.get("status", ""), "records": []}
        try:
            records = api_all(f"/zones/{z['id']}/dns_records", tok, per_page=500)
            zone["records"] = [{"id": r.get("id", ""), "type": r.get("type"), "name": r.get("name"),
                                "content": r.get("content", ""),
                                "proxied": bool(r.get("proxied")), "ttl": r.get("ttl")} for r in records
                               if r.get("type") in ("A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA")]
        except CloudflareError as error:
            snap["errors"][f"dns:{z['name']}"] = str(error)
        snap["zones"].append(zone)
    snap["accounts"] = [{"id": i, "name": n} for i, n in accounts.items()]

    for account_id in accounts:
        try:
            tunnels = api_all(f"/accounts/{account_id}/cfd_tunnel", tok, {"is_deleted": "false"}, per_page=50)
        except CloudflareError as error:
            snap["errors"]["tunnels"] = str(error)
            tunnels = []
        for tn in tunnels:
            tunnel = {"id": tn["id"], "account_id": account_id, "name": tn.get("name", ""), "status": tn.get("status", ""),
                      "connections": len(tn.get("connections") or []), "remote_config": bool(tn.get("remote_config")),
                      "ingress": None}
            if tunnel["remote_config"]:
                try:
                    cfg = api(f"/accounts/{account_id}/cfd_tunnel/{tn['id']}/configurations", tok)
                    ingress = ((cfg.get("result") or {}).get("config") or {}).get("ingress") or []
                    tunnel["ingress"] = [{"hostname": i.get("hostname", ""), "service": i.get("service", ""),
                                          "path": i.get("path", "")} for i in ingress if i.get("hostname")]
                except CloudflareError as error:
                    snap["errors"][f"tunnel:{tunnel['name']}"] = str(error)
            snap["tunnels"].append(tunnel)
        try:
            apps = api_all(f"/accounts/{account_id}/access/apps", tok, per_page=100)
            for a in apps:
                domains = set(a.get("self_hosted_domains") or [])
                if a.get("domain"):
                    domains.add(a["domain"])
                domains |= {d.get("uri", "") for d in a.get("destinations") or [] if d.get("uri")}
                snap["access_apps"].append({"name": a.get("name", ""), "type": a.get("type", ""),
                                            "domains": sorted(d for d in domains if d)})
        except CloudflareError as error:
            snap["errors"]["access"] = str(error)
    return snap


def refresh() -> dict | None:
    tok = token()
    if not tok:
        return None
    snap = fetch(tok)
    state.save(SNAPSHOT_KEY, snap)
    return snap


def load_snapshot() -> dict | None:
    snap = state.load(SNAPSHOT_KEY, None)
    return snap if snap else None


def refresh_if_due() -> None:
    if not configured():
        return
    snap = load_snapshot()
    if not snap or time.time() - snap.get("fetched_at", 0) > REFRESH_SECONDS:
        refresh()


# --- Analysis -------------------------------------------------------------------------

LOCAL_SERVICE = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(:(\d+))?", re.I)


def _host_of(uri: str) -> str:
    return uri.split("/")[0].lower()


def analyse(snap: dict, services: list[dict]) -> list[dict]:
    """One row per hostname that appears in DNS, a tunnel route or a service."""
    rows: dict[str, dict] = {}

    def row(host: str) -> dict:
        host = host.lower().rstrip(".")
        return rows.setdefault(host, {"hostname": host, "dns": None, "tunnel": None, "route": None, "access": [],
                                      "service": None, "zone": None, "problems": []})

    zones = sorted((z["name"] for z in snap.get("zones", [])), key=len, reverse=True)
    for z in snap.get("zones", []):
        for r in z.get("records", []):
            if r["type"] in ("A", "AAAA", "CNAME"):
                rw = row(r["name"])
                rw["zone"] = z["name"]
                rw["dns"] = {"type": r["type"], "content": r["content"], "proxied": r["proxied"]}
    tunnels_by_id = {t["id"]: t for t in snap.get("tunnels", [])}
    for t in snap.get("tunnels", []):
        for ing in t.get("ingress") or []:
            if ing.get("hostname") and not ing["hostname"].startswith("*"):
                rw = row(ing["hostname"])
                rw["route"] = {"tunnel": t["name"], "tunnel_id": t["id"], "service": ing["service"],
                               "path": ing.get("path", ""), "status": t["status"]}
    for s in services:
        for d in s["domains"]:
            host = d.split(":")[0]
            rw = row(host)
            rw["service"] = {"id": s["id"], "name": s["name"], "ports": [p["port"] for p in s["ports"]],
                             "host": s.get("host", "")}
    for app in snap.get("access_apps", []):
        for d in app["domains"]:
            host = _host_of(d)
            if host in rows:
                path = d[len(host):] or "/"
                rows[host]["access"].append({"name": app["name"], "path": path})

    for host, rw in rows.items():
        if rw["zone"] is None:
            rw["zone"] = next((z for z in zones if host == z or host.endswith("." + z)), None)
        dns, route, svc = rw["dns"], rw["route"], rw["service"]
        if dns and dns["type"] == "CNAME" and dns["content"].endswith(TUNNEL_SUFFIX):
            tid = dns["content"][: -len(TUNNEL_SUFFIX)]
            tunnel = tunnels_by_id.get(tid)
            rw["tunnel"] = {"id": tid, "name": tunnel["name"] if tunnel else "", "status": tunnel["status"] if tunnel else ""}
            if tunnel is None:
                rw["problems"].append("DNS points to a tunnel that does not exist (any more)")
            elif tunnel["ingress"] is not None and not route:
                rw["problems"].append(f"Tunnel “{tunnel['name']}” has no route for this hostname")
            elif route and route["tunnel_id"] != tid:
                rw["problems"].append(f"Route is in tunnel “{route['tunnel']}”, but DNS points to “{tunnel['name']}”")
        elif route and dns:
            rw["problems"].append("Tunnel route exists, but DNS does not point to the tunnel")
        elif route and not dns and rw["zone"]:
            rw["problems"].append("Tunnel route exists, but there is no DNS record")
        if svc and not dns and rw["zone"]:
            rw["problems"].append("Domain of a service without DNS record")
        if svc and route:
            m = LOCAL_SERVICE.match(route["service"])
            if m and m.group(3) and svc["ports"] and int(m.group(3)) not in svc["ports"] and not svc["host"]:
                rw["problems"].append(f"Route goes to port {m.group(3)}, the service uses "
                                      f"{', '.join(map(str, svc['ports']))}")
    # Domains of services that are not in a zone of this Cloudflare account are not Cloudflare's business.
    shown = [r for r in rows.values() if r["zone"] or r["route"]]
    return sorted(shown, key=lambda r: (r["zone"] or "~", r["hostname"]))


def issues(services: list[dict]) -> list[dict]:
    """For the overview: unhealthy tunnels and configuration problems of service domains."""
    snap = load_snapshot()
    if not snap:
        return []
    out = []
    for t in snap.get("tunnels", []):
        if t["status"] in ("down", "degraded"):
            out.append({"key": f"cloudflare:tunnel:{t['id']}", "kind": "cloudflare",
                        "level": "down" if t["status"] == "down" else "warn",
                        "text": f"Cloudflare Tunnel “{t['name']}” is {t['status']}", "link": "/cloudflare?tab=tunnels"})
    for rw in analyse(snap, services):
        if rw["service"] and rw["problems"]:
            out.append({"key": f"cloudflare:host:{rw['hostname']}", "kind": "cloudflare", "level": "warn",
                        "text": f"{rw['hostname']}: {rw['problems'][0]}", "link": "/cloudflare"})
    return out


# --- Changes (only when an admin allowed them; the token needs edit permissions) ---------

EDITABLE_TYPES = ("A", "AAAA", "CNAME", "TXT")


def _zone(snap: dict, zone_id: str) -> dict:
    zone = next((z for z in snap.get("zones", []) if z["id"] == zone_id), None)
    if zone is None:
        raise CloudflareError("Unknown zone")
    return zone


def _tunnel(snap: dict, tunnel_id: str) -> dict:
    tunnel = next((t for t in snap.get("tunnels", []) if t["id"] == tunnel_id), None)
    if tunnel is None:
        raise CloudflareError("Unknown tunnel")
    if not tunnel.get("remote_config"):
        raise CloudflareError("This tunnel is configured locally (config.yml) – change its routes there")
    return tunnel


def zone_for(snap: dict, hostname: str) -> dict:
    zones = sorted(snap.get("zones", []), key=lambda z: len(z["name"]), reverse=True)
    zone = next((z for z in zones if hostname == z["name"] or hostname.endswith("." + z["name"])), None)
    if zone is None:
        raise CloudflareError(f"{hostname} is not in a zone of this Cloudflare account")
    return zone


def current() -> dict:
    """Fresh data before every change, so changes are based on what is really at Cloudflare."""
    return refresh() or {}


def save_record(zone_id: str, record: dict, record_id: str = "", snap: dict | None = None) -> None:
    snap = snap or current()
    zone = _zone(snap, zone_id)
    name = record["name"]
    if not (name == zone["name"] or name.endswith("." + zone["name"])):
        raise CloudflareError(f"The name must end with {zone['name']}")
    body = {"type": record["type"], "name": name, "content": record["content"], "ttl": record.get("ttl") or 1}
    if record["type"] in ("A", "AAAA", "CNAME"):
        body["proxied"] = bool(record.get("proxied"))
    if record_id:
        api(f"/zones/{zone_id}/dns_records/{record_id}", token(), method="PUT", body=body)
    else:
        api(f"/zones/{zone_id}/dns_records", token(), method="POST", body=body)


def delete_record(zone_id: str, record_id: str, snap: dict | None = None) -> None:
    snap = snap or current()
    _zone(snap, zone_id)
    api(f"/zones/{zone_id}/dns_records/{record_id}", token(), method="DELETE")


def _tunnel_config(tunnel: dict) -> dict:
    path = f"/accounts/{tunnel['account_id']}/cfd_tunnel/{tunnel['id']}/configurations"
    return ((api(path, token()).get("result") or {}).get("config")) or {}


def _put_tunnel_config(tunnel: dict, config: dict) -> None:
    path = f"/accounts/{tunnel['account_id']}/cfd_tunnel/{tunnel['id']}/configurations"
    api(path, token(), method="PUT", body={"config": config})


def save_route(tunnel_id: str, hostname: str, service: str, create_dns: bool = True) -> None:
    """Add or change the route of a hostname (above the catch-all rule) and point DNS to the tunnel."""
    snap = current()
    tunnel = _tunnel(snap, tunnel_id)
    config = _tunnel_config(tunnel)
    ingress = [i for i in config.get("ingress") or [] if i.get("hostname") != hostname]
    rules = [i for i in ingress if i.get("hostname")]
    catch_all = [i for i in ingress if not i.get("hostname")] or [{"service": "http_status:404"}]
    config["ingress"] = rules + [{"hostname": hostname, "service": service}] + catch_all[-1:]
    _put_tunnel_config(tunnel, config)
    if create_dns:
        zone = zone_for(snap, hostname)
        target = f"{tunnel_id}{TUNNEL_SUFFIX}"
        existing = next((r for r in zone["records"] if r["name"] == hostname and r["type"] in ("A", "AAAA", "CNAME")),
                        None)
        if existing is None:
            save_record(zone["id"], {"type": "CNAME", "name": hostname, "content": target, "proxied": True}, "", snap)
        elif existing["type"] == "CNAME" and existing["content"] != target:
            save_record(zone["id"], {"type": "CNAME", "name": hostname, "content": target, "proxied": True},
                        existing["id"], snap)
        elif existing["type"] != "CNAME":
            raise CloudflareError(f"Route saved, but {hostname} has an {existing['type']} record – replace it with a "
                                  "CNAME to the tunnel yourself")


def delete_route(tunnel_id: str, hostname: str, delete_dns: bool = False) -> None:
    snap = current()
    tunnel = _tunnel(snap, tunnel_id)
    config = _tunnel_config(tunnel)
    config["ingress"] = [i for i in config.get("ingress") or [] if i.get("hostname") != hostname]
    _put_tunnel_config(tunnel, config)
    if delete_dns:
        zone = zone_for(snap, hostname)
        target = f"{tunnel_id}{TUNNEL_SUFFIX}"
        for r in zone["records"]:
            if r["name"] == hostname and r["type"] == "CNAME" and r["content"] == target:
                delete_record(zone["id"], r["id"], snap)
