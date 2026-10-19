from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, Integer, LargeBinary, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tracker.core.db import Base, IdMixin, TimestampMixin, utcnow
from tracker.core.types import TextArray


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_log"
    actor: Mapped[str] = mapped_column(Text)  # system | user | agent
    action: Mapped[str] = mapped_column(Text, index=True)
    entity_type: Mapped[str | None] = mapped_column(Text, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    before: Mapped[dict[str, Any] | None]
    after: Mapped[dict[str, Any] | None]
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Setting(IdMixin, TimestampMixin, Base):
    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(Text, unique=True)
    value: Mapped[dict[str, Any]]


class AiCall(IdMixin, TimestampMixin, Base):
    __tablename__ = "ai_call"
    task: Mapped[str] = mapped_column(Text, index=True)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    web_search_requests: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    stop_reason: Mapped[str | None] = mapped_column(Text)
    request_hash: Mapped[str | None] = mapped_column(Text, index=True)
    response: Mapped[dict[str, Any] | None]
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    batch_id: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class OAuthCredential(IdMixin, TimestampMixin, Base):
    __tablename__ = "oauth_credential"
    __table_args__ = (UniqueConstraint("provider", "account_email"),)
    provider: Mapped[str] = mapped_column(Text)
    account_email: Mapped[str] = mapped_column(Text)
    scopes: Mapped[list[str]] = mapped_column(TextArray, default=list)
    token_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="active")
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)


class BrowserSessionMeta(IdMixin, TimestampMixin, Base):
    __tablename__ = "browser_session_meta"
    site: Mapped[str] = mapped_column(Text, unique=True)
    last_login_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_safety_stop_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class IntegrationState(IdMixin, TimestampMixin, Base):
    """Saúde das integrações (RF-PLA-05) e cursores (ex.: historyId do Gmail)."""

    __tablename__ = "integration_state"
    name: Mapped[str] = mapped_column(Text, unique=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0)
    cursor: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Notification(IdMixin, TimestampMixin, Base):
    __tablename__ = "notification"
    channel: Mapped[str] = mapped_column(Text)  # telegram | web
    kind: Mapped[str] = mapped_column(Text, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    action_taken: Mapped[str | None] = mapped_column(Text)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)


class TaskRun(IdMixin, TimestampMixin, Base):
    """Rastreio de tarefas assíncronas exibidas no dashboard."""

    __tablename__ = "task_run"
    kind: Mapped[str] = mapped_column(Text, index=True)
    status: Mapped[str] = mapped_column(Text, default="pending")  # pending|running|done|failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None]
    error: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
