"""Whether the ports of services answer – on the service's host or on the check host."""

import socket
from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings


def port_key(host: str, port: int) -> str:
    """Key used in the API and in issues: "8080" for the check host, "10.0.0.5:8080" for another host."""
    return f"{host}:{port}" if host else str(port)


def port_open(target: tuple[str, int]) -> bool:
    host, port = target
    try:
        with socket.create_connection((host or get_settings().check_host, port), timeout=1.5):
            return True
    except OSError:
        return False


def port_status(targets) -> dict[str, bool]:
    """targets: iterable of (host, port); host "" means XT_CHECK_HOST."""
    targets = sorted(set(targets))
    if not targets:
        return {}
    with ThreadPoolExecutor(max_workers=16) as pool:
        return {port_key(h, p): ok for (h, p), ok in zip(targets, pool.map(port_open, targets))}
