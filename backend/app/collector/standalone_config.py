"""Settings for the standalone agent bundle (agent.pyz).

When the server builds the agent bundle for the install script, this file is
packed as ``app/core/config.py`` instead of the real one, so the agent runs
with the Python standard library only (no pip, no virtualenv on the target).
It reads the same ``XT_*`` variables as the real settings.
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

VERSION = "standalone"


def _list(value: str) -> list[str]:
    return [v.strip().rstrip("/") for v in value.split(",") if v.strip()]


@dataclass
class Settings:
    timezone: str = field(default_factory=lambda: os.environ.get("XT_TIMEZONE", "UTC"))
    compose_roots: str = field(default_factory=lambda: os.environ.get("XT_COMPOSE_ROOTS", "/opt,/srv,/home,/root"))
    host_root: str = field(default_factory=lambda: os.environ.get("XT_HOST_ROOT", ""))
    docker_socket: str = field(default_factory=lambda: os.environ.get("XT_DOCKER_SOCKET", "/var/run/docker.sock"))
    home_dir: str = field(default_factory=lambda: os.environ.get("XT_HOME_DIR", ""))
    protected_containers: str = ""
    collect_interval: int = 60

    @property
    def compose_root_list(self) -> list[str]:
        return _list(self.compose_roots)

    @property
    def protected_list(self) -> list[str]:
        return _list(self.protected_containers)

    @property
    def exchange_path(self) -> Path:
        return Path("/nonexistent")


@lru_cache
def get_settings() -> Settings:
    return Settings()
