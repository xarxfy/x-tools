"""Customer websites: deployed from a git repository by the optional deployer container."""

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.api.features import load as load_features
from app.collector import deploy_exchange as dx
from app.core.audit import audit
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import decrypt_json, encrypt_json
from app.models import Customer, Service, Site
from app.schemas import strip

router = APIRouter(prefix="/api/sites", tags=["sites"], dependencies=[Depends(current_user)])


class EnvVar(BaseModel):
    key: str = Field(max_length=64)
    value: str | None = Field(default=None, max_length=2000)  # None: keep the stored value

    @field_validator("key")
    @classmethod
    def check_key(cls, value: str) -> str:
        if not dx.ENV_KEY.match(value):
            raise ValueError("Variable names may contain letters, digits and _ and must not start with a digit")
        return value


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    customer_id: str | None = None
    repo_url: str = Field(max_length=300)
    branch: str = Field(default="main", max_length=100)
    compose_file: str = Field(default="", max_length=100)
    port: int | None = Field(default=None, ge=1, le=65535)
    token: str | None = Field(default=None, max_length=500)  # None: keep, "": remove
    env: list[EnvVar] = Field(default_factory=list, max_length=50)

    _strip = field_validator("name", "repo_url", "branch", "compose_file", mode="before")(strip)

    @field_validator("repo_url")
    @classmethod
    def check_url(cls, value: str) -> str:
        value = value.removesuffix("/")
        if not dx.REPO_URL.match(value) or ".." in value:
            raise ValueError("Use the https:// address of the repository without user name or password "
                             "(a token for private repositories is entered separately)")
        return value

    @field_validator("branch")
    @classmethod
    def check_branch(cls, value: str) -> str:
        if not dx.BRANCH.match(value) or ".." in value:
            raise ValueError("Invalid branch name")
        return value

    @field_validator("compose_file")
    @classmethod
    def check_compose(cls, value: str) -> str:
        if value and (not dx.COMPOSE_FILE.match(value) or ".." in value.split("/")):
            raise ValueError("Path of the compose file inside the repository, e.g. docker-compose.yml")
        return value


class SiteOut(BaseModel):
    id: str
    name: str
    slug: str
    customer_id: str | None
    service_id: str | None
    repo_url: str
    branch: str
    compose_file: str
    port: int | None
    has_token: bool
    env_keys: list[str]
    folder: str
    status: dict


class SiteList(BaseModel):
    deployer: bool
    sites: list[SiteOut]


def folder_of(slug: str) -> str:
    return get_settings().sites_dir.rstrip("/") + "/" + slug


def stored_env(site: Site) -> dict[str, str]:
    return decrypt_json(site.env) if site.env else {}


def stored_token(site: Site) -> str:
    return decrypt_json(site.token) if site.token else ""


def to_out(site: Site, with_log: bool = False) -> SiteOut:
    status = dx.status(site.id)
    if not with_log:
        status.pop("log", None)
    return SiteOut(id=site.id, name=site.name, slug=site.slug, customer_id=site.customer_id,
                   service_id=site.service_id, repo_url=site.repo_url, branch=site.branch,
                   compose_file=site.compose_file, port=site.port, has_token=bool(site.token),
                   env_keys=list(stored_env(site)), folder=folder_of(site.slug), status=status)


def get_site(db: Session, sid: str) -> Site:
    site = db.get(Site, sid)
    if site is None:
        raise HTTPException(404, "Website not found")
    return site


def need_customers() -> None:
    if not load_features().customers:
        raise HTTPException(404, "Customers are switched off")


def make_slug(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30].strip("-") or "site"
    if len(base) < 3:
        base = f"site-{base}"
    slug, n = base, 2
    while db.scalar(select(Site).where(Site.slug == slug)) or (Path(get_settings().sites_dir) / slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def apply(site: Site, body: SiteIn, db: Session) -> None:
    if body.customer_id and db.get(Customer, body.customer_id) is None:
        raise HTTPException(422, "Unknown customer")
    old_env = stored_env(site)
    keys = [v.key for v in body.env]
    if len(set(keys)) != len(keys):
        raise HTTPException(422, "A variable is listed twice")
    env = {}
    for var in body.env:
        value = var.value if var.value is not None else old_env.get(var.key)
        if value is None:
            raise HTTPException(422, f"Variable {var.key} needs a value")
        env[var.key] = value
    site.name, site.customer_id, site.repo_url, site.branch = body.name, body.customer_id, body.repo_url, body.branch
    site.compose_file, site.port = body.compose_file, body.port
    site.env = encrypt_json(env) if env else ""
    if body.token is not None:
        site.token = encrypt_json(body.token) if body.token else ""


def sync_service(site: Site, db: Session) -> None:
    """Every website is also a service (ports, domains, credentials, monitoring) of its customer."""
    service = db.get(Service, site.service_id) if site.service_id else None
    if service is None:
        service = Service(name=site.name, type="Website", folder=folder_of(site.slug))
        db.add(service)
        db.flush()
        site.service_id = service.id
    service.customer_id = site.customer_id
    if site.port and not any(p.get("port") == site.port for p in service.ports or []):
        service.ports = [*(service.ports or []), {"port": site.port, "label": "Web"}]


def queue(action: str, site: Site, purge: bool = False) -> None:
    if not dx.alive():
        raise HTTPException(503, "The deployer is not running. Start it with COMPOSE_PROFILES=deploy "
                                 "(see Installation → Deploying customer websites).")
    send_token = action == "deploy"
    try:
        dx.submit(action, site, stored_token(site) if send_token else "", stored_env(site) if send_token else {}, purge)
    except RuntimeError as error:
        raise HTTPException(409, str(error)) from None


@router.get("", response_model=SiteList)
def list_sites(customer_id: str | None = Query(default=None), db: Session = Depends(get_db)):
    query = select(Site).order_by(Site.name)
    if customer_id:
        query = query.where(Site.customer_id == customer_id)
    return SiteList(deployer=dx.alive(), sites=[to_out(s) for s in db.scalars(query)])


@router.post("", response_model=SiteOut, status_code=201, dependencies=[Depends(require("sites.deploy"))])
def create_site(body: SiteIn, db: Session = Depends(get_db)):
    need_customers()
    site = Site(slug=make_slug(db, body.name))
    apply(site, body, db)
    db.add(site)
    sync_service(site, db)
    db.commit()
    audit("site.created", site.name, site.repo_url)
    return to_out(site)


@router.put("/{sid}", response_model=SiteOut, dependencies=[Depends(require("sites.deploy"))])
def update_site(sid: str, body: SiteIn, db: Session = Depends(get_db)):
    site = get_site(db, sid)
    apply(site, body, db)
    sync_service(site, db)
    db.commit()
    audit("site.updated", site.name)
    return to_out(site)


@router.get("/{sid}", response_model=SiteOut, dependencies=[Depends(require("sites.deploy"))])
def read_site(sid: str, db: Session = Depends(get_db)):
    """With the log of the last job (operators only: logs can contain build output)."""
    site = get_site(db, sid)
    return to_out(site, with_log=True)


@router.post("/{sid}/deploy", response_model=SiteOut, dependencies=[Depends(require("sites.deploy"))])
def deploy(sid: str, db: Session = Depends(get_db)):
    site = get_site(db, sid)
    queue("deploy", site)
    audit("site.deploy", site.name)
    return to_out(site)


@router.post("/{sid}/stop", response_model=SiteOut, dependencies=[Depends(require("sites.deploy"))])
def stop(sid: str, db: Session = Depends(get_db)):
    site = get_site(db, sid)
    queue("stop", site)
    audit("site.stop", site.name)
    return to_out(site)


@router.delete("/{sid}", status_code=204, dependencies=[Depends(require("sites.deploy"))])
def delete_site(sid: str, purge: bool = False, db: Session = Depends(get_db)):
    """Forget the website. With purge=true the containers are removed and the folder is deleted as well."""
    site = get_site(db, sid)
    if purge:
        queue("remove", site, purge=True)
    name = site.name
    db.delete(site)  # the service (with credentials and domains) stays
    db.commit()
    audit("site.deleted", name, "containers and files removed" if purge else "")
    return Response(status_code=204)
