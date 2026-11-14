"""External checks of customer websites: DNS, HTTPS answer, certificate – as visitors see them."""

import http.client
import ipaddress
import re
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.core.db import session_scope
from app.models import Service
from app.monitor import state

KEY = "sitechecks"
CLOUDFLARE_NETS = [ipaddress.ip_network(n) for n in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
    "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
    "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32",
    "2a06:98c0::/29", "2c0f:f248::/32")]
HTTP_ERRORS = {
    502: "Bad Gateway – the service behind the proxy does not answer",
    503: "Service unavailable",
    504: "Gateway timeout",
    520: "Unknown error from the origin",
    521: "Origin refuses the connection",
    522: "Connection to the origin timed out",
    523: "Origin unreachable",
    524: "Origin answers too slowly",
    525: "SSL handshake with the origin failed",
    526: "Invalid certificate at the origin",
    530: "Cloudflare Tunnel not reachable",
}
CERT_WARN_DAYS = 14


def is_cloudflare(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in CLOUDFLARE_NETS if net.version == addr.version)


def check_site(domain: str) -> dict:
    """Check one domain from outside (does not follow redirects)."""
    host, _, port_s = domain.partition(":")
    port = int(port_s) if port_s.isdigit() else 443
    result: dict = {"checked_at": time.time(), "ips": [], "cloudflare": False}
    try:
        ips = sorted({ai[4][0] for ai in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)})
        result["ips"] = ips[:6]
        result["cloudflare"] = any(is_cloudflare(ip) for ip in ips)
    except (socket.gaierror, UnicodeError):
        result.update(level="down", label="DNS: domain not found")
        return result
    conn = http.client.HTTPSConnection(host, port, timeout=10, context=ssl.create_default_context())
    start = time.monotonic()
    try:
        conn.request("GET", "/", headers={"User-Agent": "x-tools-check/1.0", "Accept": "text/html"})
        res = conn.getresponse()
        result["ms"] = round((time.monotonic() - start) * 1000)
        cert = conn.sock.getpeercert() if conn.sock else None
        if cert and cert.get("notAfter"):
            result["cert_expires"] = ssl.cert_time_to_seconds(cert["notAfter"])
        status = result["status"] = res.status
        location = res.getheader("Location", "") or ""
    except ssl.SSLCertVerificationError as error:
        result.update(level="down", label=f"Invalid certificate: {error.verify_message}")
        return result
    except (OSError, http.client.HTTPException) as error:
        reason = "timeout" if isinstance(error, TimeoutError) else (str(error) or type(error).__name__)
        result.update(level="down", label=f"not reachable ({reason[:120]})")
        return result
    finally:
        conn.close()

    if status in HTTP_ERRORS:
        result.update(level="down", label=f"HTTP {status} – {HTTP_ERRORS[status]}")
    elif status >= 500:
        result.update(level="down", label=f"HTTP {status} – server error")
    elif 300 <= status < 400:
        if "cloudflareaccess.com" in location:
            result.update(level="up", label="reachable · protected by Cloudflare Access")
        else:
            target = re.sub(r"^https?://", "", location)[:60]
            result.update(level="up", label=f"redirects → {target}" if target else f"redirect ({status})")
    elif status in (401, 403):
        result.update(level="warn", label=f"HTTP {status} – access denied")
    elif status >= 400:
        result.update(level="warn", label=f"HTTP {status}")
    else:
        result.update(level="up", label="reachable")
    days = (result.get("cert_expires", 0) - time.time()) / 86400
    if result.get("cert_expires") and days < CERT_WARN_DAYS and result["level"] == "up":
        result.update(level="warn", label=result["label"] + f" · certificate expires in {max(0, int(days))} days")
    return result


def customer_domains() -> list[str]:
    """Domains of all services that belong to a customer."""
    with session_scope() as db:
        services = db.scalars(select(Service).where(Service.customer_id.is_not(None)))
        return sorted({d for s in services for d in (s.domains or [])})


def load_results() -> dict:
    return state.load(KEY, {}) or {}


def run_checks(domains: list[str] | None = None) -> dict:
    """Check the given domains (default: all customer domains) and store the results."""
    domains = sorted(set(customer_domains() if domains is None else domains))
    if not domains:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(domains))) as pool:
        results = dict(zip(domains, pool.map(check_site, domains)))
    keep = set(customer_domains())

    def merge(data):
        data.update(results)
        return {d: v for d, v in data.items() if d in keep}  # forget domains that are no longer used
    state.update(KEY, merge)
    return results
