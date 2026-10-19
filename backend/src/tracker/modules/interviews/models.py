from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tracker.core.db import Base, IdMixin, TimestampMixin, utcnow


class Interview(IdMixin, TimestampMixin, Base):
    __tablename__ = "interview"
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    round: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(Text, default="hr")
    scheduled_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calendar_event.id", ondelete="SET NULL")
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interviewers: Mapped[list[Any]] = mapped_column(default=list)
    post_notes: Mapped[dict[str, Any] | None]
    self_rating: Mapped[int | None] = mapped_column(Integer)
    thank_you_draft_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class InterviewDossier(IdMixin, TimestampMixin, Base):
    __tablename__ = "interview_dossier"
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    interview_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("interview.id", ondelete="SET NULL"))
    content: Mapped[dict[str, Any]] = mapped_column(default=dict)
    cheatsheet_md: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list[Any]] = mapped_column(default=list)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(Text, default="pending")


class InterviewQuestionLog(IdMixin, TimestampMixin, Base):
    __tablename__ = "interview_question_log"
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.id", ondelete="CASCADE"), index=True)
    interview_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    interview_kind: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    my_answer_notes: Mapped[str | None] = mapped_column(Text)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Assessment(IdMixin, TimestampMixin, Base):
    __tablename__ = "assessment"
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(Text, default="take_home")
    instructions: Mapped[str | None] = mapped_column(Text)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    repo_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending")  # pending|in_progress|submitted


class MockSession(IdMixin, TimestampMixin, Base):
    __tablename__ = "mock_session"
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    interview_kind: Mapped[str] = mapped_column(Text, default="technical")
    transcript: Mapped[list[Any]] = mapped_column(default=list)
    feedback: Mapped[list[Any]] = mapped_column(default=list)
    status: Mapped[str] = mapped_column(Text, default="active")
