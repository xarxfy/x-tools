"""Whether the ports of services answer on the check host."""

import socket
from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings


def port_open(port: int) -> bool:
    try:
        with socket.create_connection((get_settings().check_host, port), timeout=1):
            return True
    except OSError:
        return False


def port_status(ports) -> dict[int, bool]:
    ports = sorted(set(ports))
    if not ports:
        return {}
    with ThreadPoolExecutor(max_workers=16) as pool:
        return dict(zip(ports, pool.map(port_open, ports)))
