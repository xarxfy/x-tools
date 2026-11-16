"""Configuration.

Everything that depends on the installation is configurable through environment
variables prefixed with ``XT_`` (or a ``.env`` file). Nothing in the code refers
to a specific host, domain, user or path.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VERSION = "1.0.0-beta.2"


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

    # Folder shared between the web process and the collector (snapshot,
    # command files). Empty: <data_dir>/exchange. In the container setup it is a
    # separate volume, so the collector never sees the database or secret key.
    exchange_dir: str = ""

    # Where deployed customer websites live (git checkouts, one folder per site). It is mounted into the
    # deployer container under the same path, so relative bind mounts in compose files resolve on the host.
    sites_dir: str = "/srv/x-tools-sites"

    # Ask GitHub once in a while whether a newer X-TOOLS version exists (shown in Settings → About).
    update_check: bool = True
    update_repo: str = "xarxfy/x-tools"
    github_api: str = "https://api.github.com"

    # Seconds between two Docker snapshots.
    collect_interval: int = 60

    # Background monitoring (port/site checks, notifications). Off in tests.
    monitor: bool = True

    # Seconds between two monitoring runs / two rounds of website checks.
    alert_interval: int = 60
    site_interval: int = 300

    # Cloudflare API base URL (only changed for tests).
    cloudflare_api: str = "https://api.cloudflare.com/client/v4"

    # Telegram Bot API base URL (only changed for tests or a local bot API server).
    telegram_api: str = "https://api.telegram.org"

    # Home folder shown as "~" in paths (optional, e.g. /home/alice).
    home_dir: str = ""

    # When the collector runs in a container, the host file system is mounted
    # here (read-only). Empty when running directly on the host.
    host_root: str = ""

    docker_socket: str = "/var/run/docker.sock"

    # Host on which the ports of services are checked (in a container usually
    # host.docker.internal, mapped to the Docker host via extra_hosts).
    check_host: str = "127.0.0.1"

    # Containers that cannot be stopped from the UI (so you cannot lock yourself out).
    # Comma-separated.
    protected_containers: str = "x-tools,x-tools-collector,x-tools-deployer"

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
    def exchange_path(self) -> Path:
        return Path(self.exchange_dir) if self.exchange_dir else self.data_dir / "exchange"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'x-tools.db'}"

    @property
    def secure_cookies(self) -> bool:
        return self.base_url.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
