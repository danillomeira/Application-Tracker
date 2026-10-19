from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tracker.core.db import Base, IdMixin, TimestampMixin, utcnow
from tracker.core.types import TextArray


class Company(IdMixin, TimestampMixin, Base):
    __tablename__ = "company"
    name: Mapped[str] = mapped_column(Text)
    normalized_name: Mapped[str] = mapped_column(Text, unique=True)
    domains: Mapped[list[str]] = mapped_column(TextArray, default=list)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    size_range: Mapped[str | None] = mapped_column(Text)
    sector: Mapped[str | None] = mapped_column(Text)
    hq_location: Mapped[str | None] = mapped_column(Text)
    ats_kind: Mapped[str | None] = mapped_column(Text)
    ats_board_token: Mapped[str | None] = mapped_column(Text)
    is_monitored: Mapped[bool] = mapped_column(Boolean, default=False)
    is_watchlisted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CompanyProfile(IdMixin, TimestampMixin, Base):
    __tablename__ = "company_profile"
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.id", ondelete="CASCADE"), index=True)
    content: Mapped[dict[str, Any]] = mapped_column(default=dict)
    sources: Mapped[list[Any]] = mapped_column(default=list)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    model: Mapped[str | None] = mapped_column(Text)


class CompanySignal(IdMixin, TimestampMixin, Base):
    __tablename__ = "company_signal"
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    value: Mapped[dict[str, Any]] = mapped_column(default=dict)
    source_url: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
