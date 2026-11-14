"""Collector and Docker API against a fake Docker daemon on a Unix socket."""

import json
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler

import pytest

from conftest import csrf_headers

CONTAINERS = [
    {"Names": ["/web"], "Image": "nginx", "State": "running", "Status": "Up 2 hours (healthy)", "Created": 1,
     "Ports": [{"PublicPort": 8080, "PrivatePort": 80, "Type": "tcp", "IP": "127.0.0.1"}],
     "Labels": {"com.docker.compose.project": "site", "com.docker.compose.service": "web",
                "com.docker.compose.project.working_dir": "{root}/site",
                "com.docker.compose.project.config_files": "{root}/site/compose.yml"}},
    {"Names": ["/x-tools"], "Image": "x-tools", "State": "running", "Status": "Up", "Labels": {}},
    {"Names": ["/old"], "Image": "busybox", "State": "exited", "Status": "Exited (0)", "Labels": {}},
]


class FakeDocker(BaseHTTPRequestHandler):
    calls: list = []

    def log_message(self, *args):
        pass

    def address_string(self):
        return "unix"

    def reply(self, status, body=b""):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        root = self.server.root
        if self.path == "/version":
            return self.reply(200, b'{"Version": "27.0"}')
        if self.path.startswith("/containers/json"):
            return self.reply(200, json.dumps(CONTAINERS).replace("{root}", root).encode())
        if self.path == "/containers/web/json":
            return self.reply(200, b'{"Config": {"Tty": false}}')
        if self.path.startswith("/containers/web/logs"):
            line = b"2026-11-14T10:00:00.123Z started DB_PASSWORD=hunter2 ok\n"
            return self.reply(200, b"\x01\x00\x00\x00" + len(line).to_bytes(4, "big") + line)
        self.reply(404)

    def do_POST(self):
        FakeDocker.calls.append(self.path)
        self.reply(204)


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


@pytest.fixture()
def docker_env(admin, tmp_path, monkeypatch):
    sock = tmp_path / "docker.sock"
    root = tmp_path / "srv"
    (root / "site" / "app").mkdir(parents=True)
    (root / "site" / "compose.yml").write_text("services:\n  web:\n    environment:\n      DB_PASSWORD: hunter2\n"
                                               "      DB_HOST: db\n")
    (root / "site" / "app" / "Dockerfile").write_text("FROM nginx\nENV API_TOKEN=abc123\n")
    (root / "site" / ".env").write_text("SECRET=nope\n")
    server = UnixServer(str(sock), FakeDocker)
    server.root = str(root)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("XT_DOCKER_SOCKET", str(sock))
    monkeypatch.setenv("XT_COMPOSE_ROOTS", str(root))
    from app.core import config
    config.get_settings.cache_clear()
    FakeDocker.calls = []
    yield admin
    server.shutdown()
    server.server_close()


def collect_once():
    from app.collector.collector import collect_snapshot
    from app.collector.exchange import exchange_dir, write_json
    snap = collect_snapshot()
    write_json(exchange_dir() / "snapshot.json", snap)
    return snap


def test_snapshot(docker_env):
    snap = collect_once()
    assert snap["error"] is None and snap["docker"] == "27.0"
    project = snap["projects"][0]
    assert project["name"] == "site" and project["containers"][0]["health"] == "healthy"
    compose = project["compose"][0]["content"]
    assert "hunter2" not in compose and "DB_HOST: db" in compose
    assert [d["path"].rsplit("/", 2)[-2:] for d in project["dockerfiles"]] == [["app", "Dockerfile"]]
    assert "abc123" not in project["dockerfiles"][0]["content"]
    assert "nope" not in json.dumps(snap)  # .env is never read
    assert {c["name"] for c in snap["containers"]} == {"x-tools", "old"}
    assert "mem_total" in snap["system"]

    r = docker_env.get("/api/docker").json()
    assert r["stale"] is False and "x-tools" in r["protected"]
    assert r["snapshot"]["projects"][0]["service"] is None


def test_files_outside_roots_not_read(docker_env, monkeypatch, tmp_path):
    monkeypatch.setenv("XT_COMPOSE_ROOTS", str(tmp_path / "elsewhere"))
    from app.core import config
    config.get_settings.cache_clear()
    snap = collect_once()
    assert snap["projects"][0]["compose"][0]["content"] is None
    assert snap["projects"][0]["dockerfiles"] == []


def run_collector_in_background(stop):
    from app.collector.collector import take_commands
    from app.collector.exchange import commands_dir, write_json

    def loop():
        while not stop.is_set():
            for cid, result, _ in take_commands():
                write_json(commands_dir() / f"{cid}.result.json", result)
            time.sleep(0.1)
    threading.Thread(target=loop, daemon=True).start()


def test_actions_and_logs(docker_env):
    collect_once()
    h = csrf_headers(docker_env)
    stop = threading.Event()
    run_collector_in_background(stop)
    try:
        r = docker_env.post("/api/docker/action", json={"action": "stop", "container": "web"}, headers=h)
        assert r.status_code == 200, r.text
        assert FakeDocker.calls == ["/containers/web/stop?t=20"]
        # protected, unknown and invalid containers are refused before anything reaches the collector
        assert docker_env.post("/api/docker/action", json={"action": "stop", "container": "x-tools"},
                               headers=h).status_code == 422
        assert docker_env.post("/api/docker/action", json={"action": "start", "container": "ghost"},
                               headers=h).status_code == 422
        assert docker_env.post("/api/docker/action", json={"action": "kill", "container": "web"},
                               headers=h).status_code == 422
        assert docker_env.post("/api/docker/action", json={"action": "stop", "container": "web"}).status_code == 403
        assert len(FakeDocker.calls) == 1

        logs = docker_env.post("/api/docker/logs", json={"container": "web", "lines": 50}, headers=h).json()["logs"]
        assert "started" in logs and "hunter2" not in logs and logs.startswith("2026-11-14 10:00:00")
    finally:
        stop.set()


def test_masking():
    from app.collector.masking import mask_inline, mask_secrets
    text = mask_secrets("PASSWORD: s3cret\nPASSWORD_FILE: /run/secrets/pw\nKEY: ${KEY}\nmonkey: banana\n"
                        "url: postgres://user:pw123@db/x")
    assert "s3cret" not in text and "/run/secrets/pw" in text and "${KEY}" in text and "banana" in text
    assert "pw123" not in text
    assert "tok" not in mask_inline('{"accessToken": "tok"}')
