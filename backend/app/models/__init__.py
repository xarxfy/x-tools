"""Data model.

IDs are short random hex strings (12 chars) so links stay stable and data from
the predecessor project (Server-Info) can be imported with its IDs intact.
"""

import secrets
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def new_id() -> str:
    return secrets.token_hex(6)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # v1 has a single admin; the role column makes more users/roles a UI-only change later.
    role: Mapped[str] = mapped_column(String(20), default="admin")  # admin | operator | viewer
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Two-factor login (TOTP). The secret is encrypted with the instance key; recovery codes are hashed.
    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    totp_last_step: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    recovery_codes: Mapped[list] = mapped_column(JSON, default=list)


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Only a hash of the session token is stored; the token itself lives in the cookie.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")

    user: Mapped[User] = relationship()


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80))
    contact: Mapped[str] = mapped_column(String(80), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    owner: Mapped[str] = mapped_column(String(120), default="")  # who registered the domain
    agreements: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    services: Mapped[list["Service"]] = relationship(back_populates="customer")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80))
    # [{"port": 8080, "label": "Web"}]
    ports: Mapped[list] = mapped_column(JSON, default=list)
    # ["app.example.com"]
    domains: Mapped[list] = mapped_column(JSON, default=list)
    folder: Mapped[str] = mapped_column(String(200), default="")
    # Where the ports are checked; empty = XT_CHECK_HOST (the X-TOOLS host).
    host: Mapped[str] = mapped_column(String(255), default="", server_default="")
    type: Mapped[str] = mapped_column(String(60), default="")
    notes: Mapped[str] = mapped_column(String(300), default="")
    # Setup checklist from the assistant: [{"text": "...", "done": false}]
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    # A service belongs to at most one customer.
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped[Customer | None] = relationship(back_populates="services")
    credentials: Mapped["CredentialSet | None"] = relationship(back_populates="service", cascade="all, delete-orphan")


class CredentialSet(Base):
    """All logins of one service, stored encrypted as a single blob."""

    __tablename__ = "credentials"

    service_id: Mapped[str] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[str] = mapped_column(Text)  # Fernet token of a JSON list

    service: Mapped[Service] = relationship(back_populates="credentials")


class Setting(Base):
    """Key/value settings (e.g. notifications). Secrets inside are encrypted."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    # "proxmox": Proxmox host (API: nodes, storage, guests) · "docker": machine with Docker containers
    kind: Mapped[str] = mapped_column(String(20), default="docker", server_default="docker")
    key_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 of the agent key
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Options of the last install command (Proxmox/Cloudflare tokens …), encrypted – prefills the next one.
    install_options: Mapped[str | None] = mapped_column(Text, nullable=True)


class Event(Base):
    """History: one row per problem, from when it appeared until it was solved."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(300), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    level: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(String(500))
    link: Mapped[str] = mapped_column(String(200), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Metric(Base):
    """History: host metrics every few minutes (percentages)."""

    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), index=True)  # "local" or an agent id
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    load: Mapped[float | None] = mapped_column(Float, nullable=True)
    mem: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk: Mapped[float | None] = mapped_column(Float, nullable=True)


class AuditLog(Base):
    """Who did what and when (logins, changes, container actions, viewed credentials …)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(60), index=True)
    target: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[str] = mapped_column(String(500), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
