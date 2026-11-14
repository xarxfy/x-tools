"""FastAPI application: JSON API under /api, the React app for everything else."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import agents, auth, customers, docker, monitor, services
from app.core.config import VERSION, get_settings
from app.core.db import run_migrations, session_scope
from app.core.security import secret_key
from app.monitor.alerts import start_background


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations()
    secret_key()  # make sure the key exists (and is generated on first start)
    with session_scope() as db:
        auth.announce_setup_code(db)
    start_background()
    yield


def create_app() -> FastAPI:
    docs = get_settings().api_docs
    app = FastAPI(title="X-TOOLS", version=VERSION, lifespan=lifespan, redoc_url=None,
                  docs_url="/api/docs" if docs else None, openapi_url="/api/openapi.json" if docs else None)
    app.include_router(auth.router)
    app.include_router(services.router)
    app.include_router(customers.router)
    app.include_router(docker.router)
    app.include_router(agents.router)
    app.include_router(agents.report_router)
    app.include_router(monitor.router)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Content-Security-Policy",
                                    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(404)
    async def not_found(request: Request, _exc):
        # Unknown API paths stay 404; everything else is a route of the React app.
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        root = get_settings().frontend_dir.resolve()
        # Top-level files of the build (favicon.svg, robots.txt …) – never outside the build folder.
        candidate = (root / request.url.path.lstrip("/")).resolve()
        if candidate.is_file() and candidate.parent == root:
            return FileResponse(candidate)
        index = root / "index.html"
        if index.exists():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse({"detail": "Frontend not built"}, status_code=404)

    frontend = get_settings().frontend_dir
    assets = Path(frontend) / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/", include_in_schema=False)
    async def index():
        index_file = Path(frontend) / "index.html"
        if index_file.exists():
            return FileResponse(index_file, headers={"Cache-Control": "no-cache"})
        return JSONResponse({"name": "X-TOOLS", "version": VERSION, "detail": "Frontend not built"})

    return app


app = create_app()
