"""The deployer: clones customer websites from git and starts them with docker compose.

Runs as its own container (compose profile "deploy") – the only part of X-TOOLS with network access *and* the
Docker socket. It takes jobs from <exchange>/deploy/jobs, validates every field again (the web process is not
trusted either) and works only below XT_SITES_DIR.
"""

import base64
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from app.collector.deploy_exchange import (
    ACTIONS, BRANCH, COMPOSE_FILE, ENV_KEY, REPO_URL, SLUG, deploy_dir,
)
from app.collector.exchange import write_json
from app.core.config import get_settings

COMPOSE_NAMES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
STATIC_DIRS = ("public", "dist", "build", "html", "_site")
STATIC_COMPOSE = ".x-tools-static.yml"
STATIC_NGINX = ".x-tools-nginx.conf"
JOB_TIMEOUT = 15 * 60
LOG_MAX = 120_000
POLL = 2


class JobError(Exception):
    pass


class Job:
    """Runs commands for one job and keeps the status file up to date."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.site_id = spec["site_id"]
        self.log = ""
        self.started = time.time()
        self.extra: dict = {}
        self.secrets = [v for v in [spec.get("token", "")] + list((spec.get("env") or {}).values()) if len(v) >= 6]
        self.lock = threading.Lock()

    def write(self, state: str) -> None:
        with self.lock:
            write_json(deploy_dir() / "status" / f"{self.site_id}.json",
                       {"state": state, "action": self.spec["action"], "started": self.started, "updated": time.time(),
                        "log": self.log[-LOG_MAX:], **self.extra})

    def say(self, text: str) -> None:
        for secret in self.secrets:
            text = text.replace(secret, "***")
        self.log += text if text.endswith("\n") else text + "\n"
        if time.time() - getattr(self, "_flushed", 0) > 1:
            self._flushed = time.time()
            self.write("running")

    def run(self, args: list[str], cwd: Path | None = None, env: dict | None = None, quiet: bool = False) -> str:
        if not quiet:
            self.say("$ " + " ".join(args))
        proc = subprocess.Popen(args, cwd=cwd, env={**base_env(), **(env or {})}, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace")
        killer = threading.Timer(JOB_TIMEOUT, proc.kill)
        killer.start()
        out = []
        try:
            for line in proc.stdout:
                out.append(line)
                if not quiet:
                    self.say(line)
            code = proc.wait()
        finally:
            killer.cancel()
        if code != 0:
            raise JobError(f"{args[0]} {args[1] if len(args) > 1 else ''} failed (exit code {code})")
        return "".join(out)


def base_env() -> dict:
    # Deliberately minimal: compose interpolates the process environment, build output may print it.
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/tmp", "LANG": "C.UTF-8",
            "GIT_TERMINAL_PROMPT": "0", **({"DOCKER_HOST": os.environ["DOCKER_HOST"]} if "DOCKER_HOST" in os.environ else {})}


def validate(spec: dict) -> Path:
    """Check a job; returns the site folder."""
    if spec.get("action") not in ACTIONS:
        raise JobError("Unknown action")
    if not SLUG.match(str(spec.get("slug", ""))):
        raise JobError("Invalid site name")
    if spec["action"] == "deploy":
        if not REPO_URL.match(str(spec.get("repo_url", ""))) or ".." in spec["repo_url"]:
            raise JobError("Invalid repository URL (only https:// or http://, without user name or password)")
        if not BRANCH.match(str(spec.get("branch", ""))) or ".." in spec["branch"]:
            raise JobError("Invalid branch")
        cf = spec.get("compose_file") or ""
        if cf and (not COMPOSE_FILE.match(cf) or ".." in cf.split("/")):
            raise JobError("Invalid compose file")
        for key in spec.get("env") or {}:
            if not ENV_KEY.match(key):
                raise JobError(f"Invalid variable name: {key}")
        port = spec.get("port")
        if port is not None and not (isinstance(port, int) and 1 <= port <= 65535):
            raise JobError("Invalid port")
    root = Path(get_settings().sites_dir).resolve()
    folder = (root / spec["slug"]).resolve()
    if folder.parent != root:
        raise JobError("Site folder outside of the sites folder")
    return folder


def git_env(token: str) -> dict:
    if not token:
        return {}
    auth = base64.b64encode(f"oauth2:{token}".encode()).decode()
    return {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {auth}"}


def find_compose(folder: Path, wanted: str) -> Path | None:
    if wanted:
        path = (folder / wanted).resolve()
        if folder not in path.parents or not path.is_file():
            raise JobError(f"Compose file '{wanted}' not found in the repository")
        return path
    for name in COMPOSE_NAMES:
        if (folder / name).is_file():
            return folder / name
    return None


def static_compose(folder: Path, port: int | None) -> Path:
    if not port:
        raise JobError("No compose file in the repository. For a static website enter a port.")
    root = next((d for d in STATIC_DIRS if (folder / d / "index.html").is_file()), "")
    if not root and not (folder / "index.html").is_file():
        raise JobError("No compose file and no index.html found – nothing to deploy")
    (folder / STATIC_NGINX).write_text(
        "server {\n  listen 80;\n  root /usr/share/nginx/html;\n  index index.html;\n"
        "  location ~ /\\. { return 404; }\n  location / { try_files $uri $uri/ =404; }\n}\n", encoding="utf-8")
    path = folder / STATIC_COMPOSE
    path.write_text(
        "services:\n  web:\n    image: nginx:alpine\n    restart: unless-stopped\n"
        f"    ports:\n      - \"127.0.0.1:{int(port)}:80\"\n"
        f"    volumes:\n      - ./{root or '.'}:/usr/share/nginx/html:ro\n"
        f"      - ./{STATIC_NGINX}:/etc/nginx/conf.d/default.conf:ro\n", encoding="utf-8")
    return path


def write_env(folder: Path, env: dict[str, str]) -> None:
    if not env:
        return
    lines = []
    for key, value in env.items():
        if "\n" in value or "\r" in value:
            raise JobError(f"Variable {key}: line breaks are not allowed")
        lines.append(f"{key}={value}" if value.replace("_", "").replace("-", "").replace(".", "").isalnum()
                     else f"{key}='{value}'" if "'" not in value else f'{key}="{value}"')
    path = folder / ".env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def do_deploy(job: Job, folder: Path) -> None:
    spec = job.spec
    genv = git_env(spec.get("token", ""))
    folder.parent.mkdir(parents=True, exist_ok=True)
    if (folder / ".git").is_dir():
        job.run(["git", "remote", "set-url", "origin", spec["repo_url"]], cwd=folder)
        job.run(["git", "fetch", "--depth", "1", "origin", spec["branch"]], cwd=folder, env=genv)
        job.run(["git", "reset", "--hard", "FETCH_HEAD"], cwd=folder)
    else:
        if folder.exists() and any(folder.iterdir()):
            raise JobError(f"{folder} exists and is not a git checkout – remove it or choose another name")
        job.run(["git", "clone", "--depth", "1", "--branch", spec["branch"], spec["repo_url"], str(folder)], env=genv)
    sha = job.run(["git", "log", "-1", "--format=%h%x1f%s"], cwd=folder, quiet=True).strip().split("\x1f")
    job.extra["commit"], job.extra["subject"] = sha[0], (sha[1] if len(sha) > 1 else "")
    write_env(folder, spec.get("env") or {})
    compose = find_compose(folder, spec.get("compose_file") or "") or static_compose(folder, spec.get("port"))
    job.extra["compose"] = compose.name
    job.run(["docker", "compose", "-p", compose_project(spec["slug"]), "--project-directory", str(folder),
             "-f", str(compose), "up", "-d", "--build", "--remove-orphans"], cwd=folder)


def compose_project(slug: str) -> str:
    return f"site-{slug}"


def do_stop(job: Job, folder: Path) -> None:
    if not folder.is_dir():
        raise JobError("The website has not been deployed yet")
    compose = find_compose(folder, "") or (folder / STATIC_COMPOSE)
    job.run(["docker", "compose", "-p", compose_project(job.spec["slug"]), "--project-directory", str(folder),
             "-f", str(compose), "stop"], cwd=folder)


def do_remove(job: Job, folder: Path) -> None:
    if folder.is_dir():
        compose = find_compose(folder, "") or (folder / STATIC_COMPOSE)
        if compose.is_file():
            job.run(["docker", "compose", "-p", compose_project(job.spec["slug"]), "--project-directory", str(folder),
                     "-f", str(compose), "down", "--remove-orphans"], cwd=folder)
        if job.spec.get("purge"):
            shutil.rmtree(folder)
            job.say(f"Removed {folder}")


def process(path: Path) -> None:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        return
    path.unlink(missing_ok=True)  # the job may contain a token: never leave it lying around
    if not isinstance(spec, dict) or not isinstance(spec.get("site_id"), str) or "/" in spec["site_id"]:
        return
    job = Job(spec)
    try:
        folder = validate(spec)
        job.write("running")
        {"deploy": do_deploy, "stop": do_stop, "remove": do_remove}[spec["action"]](job, folder)
        job.say("Done.")
        job.extra["finished"] = time.time()
        job.write("ok")
    except JobError as error:
        job.say(f"ERROR: {error}")
        job.extra["finished"] = time.time()
        job.write("failed")
    except Exception as error:  # noqa: BLE001 – report anything instead of dying
        job.say(f"ERROR: {type(error).__name__}: {error}")
        job.extra["finished"] = time.time()
        job.write("failed")


def heartbeat(path: Path) -> None:
    while True:
        path.touch()
        time.sleep(5)


def run() -> None:
    os.umask(0o022)  # checked-out files must be readable for the containers (nginx etc.)
    folder = deploy_dir()
    (folder / "jobs").mkdir(parents=True, exist_ok=True)
    (folder / "status").mkdir(parents=True, exist_ok=True)
    threading.Thread(target=heartbeat, args=(folder / "alive",), daemon=True).start()
    print("X-TOOLS deployer running; sites folder:", get_settings().sites_dir, flush=True)
    while True:
        for path in sorted((folder / "jobs").glob("*.json")):
            process(path)
        time.sleep(POLL)
