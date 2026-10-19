from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tracker.core.db import Base, IdMixin, TimestampMixin, utcnow


class Application(IdMixin, TimestampMixin, Base):
    __tablename__ = "application"
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job.id"), unique=True)
    status: Mapped[str] = mapped_column(Text, default="discovered", index=True)
    channel: Mapped[str] = mapped_column(Text, default="easy_apply")
    mode: Mapped[str] = mapped_column(Text, default="review")  # review|auto|manual
    resume_render_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("resume_render.id"))
    resume_variant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("resume_variant.id"))
    cover_letter: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("job_snapshot.id"))
    priority_at_submit: Mapped[dict[str, Any] | None]
    queue_priority: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    next_action: Mapped[str | None] = mapped_column(Text)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(default=dict)


class ApplicationEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "application_event"
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    actor: Mapped[str] = mapped_column(Text, default="system")
    reason: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApplicationAnswer(IdMixin, TimestampMixin, Base):
    __tablename__ = "application_answer"
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    question_text: Mapped[str] = mapped_column(Text)
    field_kind: Mapped[str] = mapped_column(Text)
    options: Mapped[list[Any]] = mapped_column(default=list)
    answer: Mapped[dict[str, Any]]
    resolution: Mapped[str] = mapped_column(Text)  # profile|bank|rule|ai|user
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    answer_bank_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    locked: Mapped[bool] = mapped_column(Boolean, default=False)


class PendingQuestion(IdMixin, TimestampMixin, Base):
    __tablename__ = "pending_question"
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    question_text: Mapped[str] = mapped_column(Text)
    field_kind: Mapped[str] = mapped_column(Text)
    options: Mapped[list[Any]] = mapped_column(default=list)
    context: Mapped[dict[str, Any]] = mapped_column(default=dict)
    ai_suggestion: Mapped[dict[str, Any] | None]
    status: Mapped[str] = mapped_column(Text, default="open", index=True)
    answered_value: Mapped[dict[str, Any] | None]
    save_to_bank: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DailyQuota(IdMixin, TimestampMixin, Base):
    __tablename__ = "daily_quota"
    __table_args__ = (UniqueConstraint("day", "kind"),)
    day: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(Text)
    used: Mapped[int] = mapped_column(Integer, default=0)
    limit: Mapped[int] = mapped_column(Integer)
