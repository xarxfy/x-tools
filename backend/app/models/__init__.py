"""Data model.

IDs are short random hex strings (12 chars) so links stay stable and data from
the predecessor project (Server-Info) can be imported with its IDs intact.
"""

import secrets
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
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
    role: Mapped[str] = mapped_column(String(20), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    type: Mapped[str] = mapped_column(String(60), default="")
    notes: Mapped[str] = mapped_column(String(300), default="")
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
    key_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 of the agent key
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
