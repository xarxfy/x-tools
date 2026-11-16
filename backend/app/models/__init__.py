"""Data model.

IDs are short random hex strings (12 chars) so links stay stable and data from
the predecessor project (Server-Info) can be imported with its IDs intact.
"""

import secrets
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def new_id() -> str:
    return secrets.token_hex(6)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(Base):
    """A role: a name and a set of permissions (core/permissions.py). viewer, operator and admin are built in."""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default=new_id)  # "admin" … or 12 hex chars
    name: Mapped[str] = mapped_column(String(40), unique=True)
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # v1 has a single admin; the role column makes more users/roles a UI-only change later.
    role: Mapped[str] = mapped_column(String(20), default="admin")  # id of a Role
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


class CustomerCategory(Base):
    """Priority class of customers (A-customer, B-customer, … – the names are free); `position` is the order."""

    __tablename__ = "customer_categories"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[str] = mapped_column(String(10), default="gray", server_default="gray")


class Tag(Base):
    """A tag of the central list (Administration → Order). Servers and customers carry tags by name."""

    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(30))
    color: Mapped[str] = mapped_column(String(10), default="gray", server_default="gray")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80))
    owner: Mapped[str] = mapped_column(String(120), default="")  # who registered the domain
    agreements: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("customer_categories.id", ondelete="SET NULL"), nullable=True)
    # Contract data (only shown to roles with customers.contracts)
    contract_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    notice_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # period of notice before the end
    support_hours: Mapped[str] = mapped_column(String(120), default="", server_default="")
    response_time: Mapped[str] = mapped_column(String(60), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    services: Mapped[list["Service"]] = relationship(back_populates="customer")
    contacts: Mapped[list["CustomerContact"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", order_by="CustomerContact.position")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    links: Mapped[list["CustomerLink"]] = relationship(
        cascade="all, delete-orphan", order_by="CustomerLink.position")
    tags: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")  # free tags (Hosting, Shop …)


class CustomerContact(Base):
    """A person at the customer (technical, billing, emergency …); `role` is free text."""

    __tablename__ = "customer_contacts"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(60), default="", server_default="")
    email: Mapped[str] = mapped_column(String(120), default="", server_default="")
    phone: Mapped[str] = mapped_column(String(40), default="", server_default="")
    position: Mapped[int] = mapped_column(Integer, default=0)

    customer: Mapped["Customer"] = relationship(back_populates="contacts")


class Ticket(Base):
    """A small ticket of a customer: something to do or to look into (status, priority, who, what it is about)."""

    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    number: Mapped[int] = mapped_column(Integer, unique=True)  # shown as #12, counted up for the whole installation
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(String(10), default="open", server_default="open")  # open|progress|waiting|done
    priority: Mapped[str] = mapped_column(String(10), default="normal", server_default="normal")  # low|normal|high|urgent
    due: Mapped[date | None] = mapped_column(Date, nullable=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id", ondelete="SET NULL"), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="tickets")
    assignee: Mapped["User | None"] = relationship()
    entries: Mapped[list["JournalEntry"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="JournalEntry.created_at")


class JournalEntry(Base):
    """The history of a customer: comments on tickets, status changes (kind "event") and free notes (no ticket)."""

    __tablename__ = "journal"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    ticket_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(10), default="note")  # note | event
    text: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    ticket: Mapped["Ticket | None"] = relationship(back_populates="entries")


class CustomerLink(Base):
    """A link of a customer (contract, documentation, password manager …). Only http(s) addresses."""

    __tablename__ = "customer_links"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(80))
    url: Mapped[str] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(Integer, default=0)



class Site(Base):
    """A customer website that X-TOOLS deploys from a git repository (by the optional deployer container)."""

    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(40), unique=True)  # folder and compose project name
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id", ondelete="SET NULL"), nullable=True)
    repo_url: Mapped[str] = mapped_column(String(300))
    branch: Mapped[str] = mapped_column(String(100), default="main")
    compose_file: Mapped[str] = mapped_column(String(100), default="")  # empty: detect, or static site
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)  # static sites: port on 127.0.0.1
    token: Mapped[str] = mapped_column(Text, default="")  # access token for private repos (encrypted)
    env: Mapped[str] = mapped_column(Text, default="")  # variables for the .env file (encrypted JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Heartbeat(Base):
    """A job (cron, backup …) that pings X-TOOLS when it has run; silence means a problem."""

    __tablename__ = "heartbeats"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80))
    token: Mapped[str] = mapped_column(String(48), unique=True)  # part of the secret ping address
    interval_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    grace_minutes: Mapped[int] = mapped_column(Integer, default=30)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    last_ping_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(String(10), default="")  # ok | fail | start
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    notes: Mapped[str] = mapped_column(Text, default="")
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


class NetworkEntry(Base):
    """An IP address entered by hand: a device without agent (router, NAS, printer, switch …)."""

    __tablename__ = "network_entries"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    ip: Mapped[str] = mapped_column(String(45))
    name: Mapped[str] = mapped_column(String(80))
    notes: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ServerGroup(Base):
    """A group of servers with a free name (Production, Customer A, Home network …); `position` is the order."""

    __tablename__ = "server_groups"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[str] = mapped_column(String(10), default="gray", server_default="gray")


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
    group_id: Mapped[str | None] = mapped_column(ForeignKey("server_groups.id", ondelete="SET NULL"), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")  # free tags of this server
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")  # free text: what is this server for …
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)


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
