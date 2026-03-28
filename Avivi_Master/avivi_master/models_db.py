from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from avivi_master.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ClientRecord(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    hostname: Mapped[str] = mapped_column(String(512), default="")
    app_version: Mapped[str] = mapped_column(String(64), default="")
    fernet_key_b64: Mapped[str] = mapped_column(Text, default="")
    hmac_secret_b64: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    license_status: Mapped[str] = mapped_column(String(64), default="trial")
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hourly_rate_ils: Mapped[float | None] = mapped_column(Float, nullable=True)

    commands: Mapped[list["CommandQueueRow"]] = relationship(back_populates="client")
    missions: Mapped[list["MissionRow"]] = relationship(back_populates="client")


class MissionRow(Base):
    __tablename__ = "missions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(String(64), ForeignKey("clients.id"), index=True)
    mission_id: Mapped[str] = mapped_column(String(256), default="")
    version: Mapped[str] = mapped_column(String(64), default="")
    encrypted_blob: Mapped[bytes] = mapped_column(LargeBinary)
    signature_hex: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)

    client: Mapped["ClientRecord"] = relationship(back_populates="missions")


class AuditLogRow(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    actor: Mapped[str] = mapped_column(String(256), default="")
    action: Mapped[str] = mapped_column(String(256), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CommandQueueRow(Base):
    __tablename__ = "command_queue"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(String(64), ForeignKey("clients.id"), index=True)
    command_type: Mapped[str] = mapped_column(String(64), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    acked: Mapped[bool] = mapped_column(Boolean, default=False)

    client: Mapped["ClientRecord"] = relationship(back_populates="commands")


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(256), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ROIEventRow(Base):
    __tablename__ = "roi_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(128), default="")
    minutes_saved: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
