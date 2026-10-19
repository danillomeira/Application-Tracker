from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tracker.core.db import Base, IdMixin, TimestampMixin


class CalendarEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "calendar_event"
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(Text)  # interview|assessment_deadline|study_block|followup
    google_event_id: Mapped[str | None] = mapped_column(Text, index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(Text, default="America/Sao_Paulo")
    location_or_link: Mapped[str | None] = mapped_column(Text)
    attendees: Mapped[list[Any]] = mapped_column(default=list)
    status: Mapped[str] = mapped_column(Text, default="draft")  # draft|confirmed|cancelled
    source_email_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)
