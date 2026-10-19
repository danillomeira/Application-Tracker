from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tracker.core.db import Base, IdMixin, TimestampMixin
from tracker.core.types import TextArray


class EmailMessage(IdMixin, TimestampMixin, Base):
    __tablename__ = "email_message"
    gmail_id: Mapped[str] = mapped_column(Text, unique=True)
    thread_id: Mapped[str | None] = mapped_column(Text, index=True)
    from_addr: Mapped[str] = mapped_column(Text)
    from_name: Mapped[str | None] = mapped_column(Text)
    to_addrs: Mapped[list[str]] = mapped_column(TextArray, default=list)
    subject: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    body_text: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    labels: Mapped[list[str]] = mapped_column(TextArray, default=list)
    classification: Mapped[str | None] = mapped_column(Text, index=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    extracted: Mapped[dict[str, Any]] = mapped_column(default=dict)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application.id", ondelete="SET NULL"), index=True
    )
    link_status: Mapped[str] = mapped_column(Text, default="none")  # auto|user|ambiguous|none
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prefilter: Mapped[str | None] = mapped_column(Text)  # motivo do pré-filtro


class LinkedinMessage(IdMixin, TimestampMixin, Base):
    __tablename__ = "linkedin_message"
    conversation_id: Mapped[str] = mapped_column(Text, index=True)
    message_id: Mapped[str] = mapped_column(Text, unique=True)
    from_name: Mapped[str] = mapped_column(Text)
    from_profile_url: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    classification: Mapped[str | None] = mapped_column(Text)
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    extracted: Mapped[dict[str, Any]] = mapped_column(default=dict)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application.id", ondelete="SET NULL")
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("person.id", ondelete="SET NULL"))
    link_status: Mapped[str] = mapped_column(Text, default="none")


class Draft(IdMixin, TimestampMixin, Base):
    __tablename__ = "draft"
    kind: Mapped[str] = mapped_column(Text)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    to: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    in_reply_to_email_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    gmail_draft_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="proposed")
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)
