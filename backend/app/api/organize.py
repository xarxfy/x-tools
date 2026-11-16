"""The central list of tags (Administration → Order). Categories and server groups have their own routes
(api/customers.py, api/agents.py) but are changed with the same permission, admin.organize."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, require
from app.core.audit import audit
from app.core.db import get_db
from app.core.palette import COLOR_PATTERN, DEFAULT
from app.models import Agent, Customer, Tag
from app.schemas import strip

router = APIRouter(prefix="/api/tags", tags=["organize"], dependencies=[Depends(current_user)])


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    color: str = Field(default=DEFAULT, pattern=COLOR_PATTERN)

    _strip = field_validator("name", mode="before")(strip)

    @field_validator("name")
    @classmethod
    def printable(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v or not v.isprintable():
            raise ValueError("Name is missing")
        return v


class MergeIn(BaseModel):
    into: str = Field(max_length=12)


def usage(db: Session) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for kind, model in (("servers", Agent), ("customers", Customer)):
        for row in db.scalars(select(model)):
            for tag in row.tags or []:
                counts.setdefault(tag.lower(), {"servers": 0, "customers": 0})[kind] += 1
    return counts


def tag_out(t: Tag, counts: dict[str, dict[str, int]]) -> dict:
    used = counts.get(t.name.lower(), {})
    return {"id": t.id, "name": t.name, "color": t.color, "servers": used.get("servers", 0), "customers": used.get("customers", 0)}


def check_tags(db: Session, tags: list[str]) -> list[str]:
    """Tags can only be picked from the central list: returns them in the spelling of the list, no duplicates."""
    known = {t.name.lower(): t.name for t in db.scalars(select(Tag))}
    out: list[str] = []
    for tag in tags:
        key = " ".join(str(tag).split()).lower()
        if not key:
            continue
        if key not in known:
            raise HTTPException(422, f"Unknown tag: {tag}. Tags are managed in Administration → Order.")
        if known[key] not in out:
            out.append(known[key])
    return out


def unique(db: Session, name: str, own: str = "") -> None:
    if any(t.id != own and t.name.lower() == name.lower() for t in db.scalars(select(Tag))):
        raise HTTPException(409, "A tag with this name already exists")


def get_tag(db: Session, tid: str) -> Tag:
    tag = db.get(Tag, tid)
    if tag is None:
        raise HTTPException(404, "Tag not found")
    return tag


def replace_everywhere(db: Session, old: str, new: str | None) -> None:
    """Rename a tag on all servers and customers, or remove it (new=None); no duplicates afterwards."""
    for model in (Agent, Customer):
        for row in db.scalars(select(model)):
            tags = row.tags or []
            if not any(t.lower() == old.lower() for t in tags):
                continue
            out: list[str] = []
            for t in tags:
                t = new if t.lower() == old.lower() else t
                if t and t not in out:
                    out.append(t)
            row.tags = out


@router.get("")
def list_tags(db: Session = Depends(get_db)):
    counts = usage(db)
    return [tag_out(t, counts) for t in sorted(db.scalars(select(Tag)), key=lambda t: t.name.lower())]


@router.post("", status_code=201, dependencies=[Depends(require("admin.organize"))])
def create_tag(body: TagIn, db: Session = Depends(get_db)):
    unique(db, body.name)
    tag = Tag(name=body.name, color=body.color)
    db.add(tag)
    db.commit()
    audit("tag.created", tag.name)
    return tag_out(tag, usage(db))


@router.put("/{tid}", dependencies=[Depends(require("admin.organize"))])
def update_tag(tid: str, body: TagIn, db: Session = Depends(get_db)):
    tag = get_tag(db, tid)
    unique(db, body.name, tid)
    old = tag.name
    if body.name != old:
        replace_everywhere(db, old, body.name)
        tag.name = body.name
    tag.color = body.color
    db.commit()
    if body.name != old:  # (the audit log writes in its own session: only after the commit)
        audit("tag.renamed", f"{old} → {body.name}")
    return tag_out(tag, usage(db))


@router.post("/{tid}/merge", dependencies=[Depends(require("admin.organize"))])
def merge_tag(tid: str, body: MergeIn, db: Session = Depends(get_db)):
    """Everything that carries this tag gets the other one; this tag is removed."""
    tag, target = get_tag(db, tid), get_tag(db, body.into)
    if tag.id == target.id:
        raise HTTPException(422, "Choose another tag")
    replace_everywhere(db, tag.name, target.name)
    db.delete(tag)
    db.commit()
    audit("tag.merged", f"{tag.name} → {target.name}")
    return tag_out(target, usage(db))


@router.delete("/{tid}", status_code=204, dependencies=[Depends(require("admin.organize"))])
def delete_tag(tid: str, db: Session = Depends(get_db)):
    tag = get_tag(db, tid)
    replace_everywhere(db, tag.name, None)
    db.delete(tag)
    db.commit()
    audit("tag.deleted", tag.name)
    return Response(status_code=204)
