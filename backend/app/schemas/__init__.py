"""Request/response models shared by the API routers."""

import re

from pydantic import BaseModel, Field, field_validator

DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*(:\d{1,5})?$")


def clean_domain(value: str) -> str:
    value = str(value).strip().lower().removeprefix("https://").removeprefix("http://").rstrip("/")
    if value and (len(value) > 253 or not DOMAIN_RE.match(value)):
        raise ValueError(f"invalid domain: {value}")
    return value


def strip(value):
    return value.strip() if isinstance(value, str) else value


class Port(BaseModel):
    port: int = Field(ge=1, le=65535)
    label: str = Field(default="", max_length=40)

    _strip = field_validator("label", mode="before")(strip)


HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.\-]{0,253})$|^\[?[0-9A-Fa-f:]+\]?$")


class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    host: str = Field(default="", max_length=255)
    domains: list[str] = Field(default_factory=list, max_length=10)
    ports: list[Port] = Field(default_factory=list, max_length=10)
    folder: str = Field(default="", max_length=200)
    type: str = Field(default="", max_length=60)
    notes: str = Field(default="", max_length=300)
    customer_id: str | None = None

    _strip = field_validator("name", "folder", "type", "notes", mode="before")(strip)

    @field_validator("domains")
    @classmethod
    def domains_valid(cls, values: list[str]) -> list[str]:
        out: list[str] = []
        for v in values:
            d = clean_domain(v)
            if d and d not in out:
                out.append(d)
        return out

    @field_validator("host", mode="before")
    @classmethod
    def host_valid(cls, value):
        value = str(value or "").strip().lower()
        if value and not HOST_RE.match(value):
            raise ValueError("host: an IP address or host name")
        return value.strip("[]")

    @field_validator("customer_id", mode="before")
    @classmethod
    def empty_none(cls, value):
        return value or None


class ServiceOut(BaseModel):
    id: str
    name: str
    host: str = ""
    domains: list[str]
    ports: list[Port]
    folder: str
    type: str
    notes: str
    customer_id: str | None
    customer_name: str | None = None
    credential_count: int = 0


class Credential(BaseModel):
    label: str = Field(default="", max_length=60)
    username: str = Field(default="", max_length=200)
    password: str = Field(default="", max_length=500)
    url: str = Field(default="", max_length=300)
    note: str = Field(default="", max_length=300)

    _strip = field_validator("label", "username", "url", "note", mode="before")(strip)


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    contact: str = Field(default="", max_length=80)
    email: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=40)
    owner: str = Field(default="", max_length=120)
    agreements: str = Field(default="", max_length=5000)
    notes: str = Field(default="", max_length=5000)
    service_ids: list[str] = Field(default_factory=list, max_length=100)

    _strip = field_validator("name", "contact", "email", "phone", "owner", "agreements", "notes", mode="before")(strip)


class CustomerOut(BaseModel):
    id: str
    name: str
    contact: str
    email: str
    phone: str
    owner: str
    agreements: str
    notes: str
    service_ids: list[str]
