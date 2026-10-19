from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tracker.core.db import Base, IdMixin, TimestampMixin, utcnow


class ScoringWeights(IdMixin, TimestampMixin, Base):
    __tablename__ = "scoring_weights"
    version: Mapped[int] = mapped_column(Integer, unique=True)
    chance_weights: Mapped[dict[str, Any]]
    attractiveness_weights: Mapped[dict[str, Any]]
    thresholds: Mapped[dict[str, Any]]
    source: Mapped[str] = mapped_column(Text, default="default")  # default|user|calibrated
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(default=dict)


class JobScore(IdMixin, TimestampMixin, Base):
    __tablename__ = "job_score"
    __table_args__ = (UniqueConstraint("job_id", "weights_version", "master_version"),)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job.id", ondelete="CASCADE"), index=True)
    weights_version: Mapped[int] = mapped_column(Integer)
    master_version: Mapped[int] = mapped_column(Integer)
    knockout: Mapped[dict[str, Any]] = mapped_column(default=dict)
    chance: Mapped[float] = mapped_column(Float, default=0.0)
    chance_breakdown: Mapped[dict[str, Any]] = mapped_column(default=dict)
    attractiveness: Mapped[float] = mapped_column(Float, default=0.0)
    attractiveness_breakdown: Mapped[dict[str, Any]] = mapped_column(default=dict)
    priority: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    quadrant: Mapped[str] = mapped_column(Text, index=True)  # top|bet|volume|discard|blocked
    suggested_action: Mapped[str] = mapped_column(Text, default="")
    best_variant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    variant_scores: Mapped[dict[str, Any]] = mapped_column(default=dict)
    explanation: Mapped[dict[str, Any]] = mapped_column(default=dict)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
