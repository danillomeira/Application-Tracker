from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tracker.core.db import Base, IdMixin, TimestampMixin


class Offer(IdMixin, TimestampMixin, Base):
    __tablename__ = "offer"
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("application.id", ondelete="SET NULL"), index=True
    )
    company_name: Mapped[str] = mapped_column(Text)
    regime: Mapped[str] = mapped_column(Text)  # CLT | PJ
    base_salary: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(Text, default="BRL")
    period: Mapped[str] = mapped_column(Text, default="month")  # month | year
    bonus: Mapped[dict[str, Any]] = mapped_column(default=dict)
    benefits: Mapped[dict[str, Any]] = mapped_column(default=dict)
    equity: Mapped[dict[str, Any]] = mapped_column(default=dict)
    work_model: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    respond_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    annualized: Mapped[dict[str, Any]] = mapped_column(default=dict)
    negotiation: Mapped[dict[str, Any] | None]
    status: Mapped[str] = mapped_column(Text, default="received")
