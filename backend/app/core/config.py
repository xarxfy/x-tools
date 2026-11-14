"""Configuration.

Everything that depends on the installation is configurable through environment
variables prefixed with ``XT_`` (or a ``.env`` file). Nothing in the code refers
to a specific host, domain, user or path.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VERSION = "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="XT_", env_file=".env", extra="ignore")

    # Where the database, the generated secret key and other state live.
    data_dir: Path = Path("/data")

    # Public address of the web UI (e.g. https://tools.example.com). Used for
    # links in notifications and to decide whether cookies are marked Secure.
    base_url: str = ""

    timezone: str = "UTC"

    # Directories that may contain docker compose projects. The collector only
    # reads compose files and Dockerfiles below these roots.
    # Comma-separated, e.g. XT_COMPOSE_ROOTS=/opt,/srv,/home
    compose_roots: str = "/opt,/srv,/home"

    # When the collector runs in a container, the host file system is mounted
    # here (read-only). Empty when running directly on the host.
    host_root: str = ""

    docker_socket: str = "/var/run/docker.sock"

    # Host on which the ports of services are checked (in a container usually
    # host.docker.internal, mapped to the Docker host via extra_hosts).
    check_host: str = "127.0.0.1"

    # Containers that cannot be stopped from the UI (so you cannot lock yourself out).
    # Comma-separated.
    protected_containers: str = "x-tools,x-tools-collector"

    # Optional fixed secret key (Fernet, url-safe base64). If empty, a key is
    # generated on first start and stored in data_dir/secret.key.
    secret_key: str = ""

    # Session lifetime in hours.
    session_hours: int = 24 * 14

    # Trust X-Forwarded-For / X-Forwarded-Proto from a reverse proxy in front of X-TOOLS.
    trust_proxy: bool = True

    # Interactive API documentation at /api/docs (for development; off by default).
    api_docs: bool = False

    # Directory with the built frontend (index.html + assets).
    frontend_dir: Path = Path(__file__).resolve().parents[3] / "frontend" / "dist"

    @field_validator("base_url")
    @classmethod
    def strip_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def compose_root_list(self) -> list[str]:
        return [v.strip().rstrip("/") for v in self.compose_roots.split(",") if v.strip()]

    @property
    def protected_list(self) -> list[str]:
        return [v.strip() for v in self.protected_containers.split(",") if v.strip()]

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'x-tools.db'}"

    @property
    def secure_cookies(self) -> bool:
        return self.base_url.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
