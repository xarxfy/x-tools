"""Build the standalone agent (a Python zipapp) from the installed sources."""

import io
import zipfile
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ("__init__.py", "agent.py", "collector.py", "dockerapi.py", "exchange.py", "httpjson.py", "masking.py", "proxmox.py")
MAIN = "from app.collector.agent import run\n\nrun()\n"


@lru_cache
def agent_bundle() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("__main__.py", MAIN)
        z.writestr("app/__init__.py", "")
        z.writestr("app/core/__init__.py", "")
        z.writestr("app/core/config.py", (HERE / "standalone_config.py").read_text())
        for name in MODULES:
            z.writestr(f"app/collector/{name}", (HERE / name).read_text())
    return buf.getvalue()
