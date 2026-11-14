"""Minimal Docker Engine API client over the Unix socket (standard library only)."""

import http.client
import json
import socket

from app.core.config import get_settings


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float = 10):
        super().__init__("localhost", timeout=timeout)
        self.unix_path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.unix_path)
        self.sock = sock


def _request(method: str, path: str, timeout: float) -> tuple[int, bytes]:
    conn = UnixHTTPConnection(get_settings().docker_socket, timeout=timeout)
    try:
        conn.request(method, path)
        res = conn.getresponse()
        return res.status, res.read()
    finally:
        conn.close()


def get_raw(path: str, timeout: float = 10) -> bytes:
    status, body = _request("GET", path, timeout)
    if status != 200:
        raise OSError(f"Docker API {path.split('?')[0]}: HTTP {status}")
    return body


def get(path: str):
    return json.loads(get_raw(path))


def post(path: str, timeout: float) -> tuple[int, bytes]:
    return _request("POST", path, timeout)
