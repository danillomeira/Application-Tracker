from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tracker.core.db import Base, IdMixin, TimestampMixin, utcnow
from tracker.core.types import EMBEDDING_DIM, TextArray


class ResumeTemplate(IdMixin, TimestampMixin, Base):
    __tablename__ = "resume_template"
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    engine: Mapped[str] = mapped_column(Text, default="latex")
    path: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    supports_languages: Mapped[list[str]] = mapped_column(TextArray, default=lambda: ["en", "pt"])


class ResumeVariant(IdMixin, TimestampMixin, Base):
    __tablename__ = "resume_variant"
    kind: Mapped[str] = mapped_column(Text, index=True)  # wildcard | tailored
    slug: Mapped[str] = mapped_column(Text, index=True)
    name: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text, default="en")
    focus: Mapped[dict[str, Any]] = mapped_column(default=dict)
    content: Mapped[dict[str, Any]] = mapped_column(default=dict)
    changes: Mapped[list[Any]] = mapped_column(default=list)
    master_version: Mapped[int] = mapped_column(Integer)
    template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("resume_template.id"))
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("job.id", ondelete="SET NULL"), index=True)
    parent_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_variant.id", ondelete="SET NULL")
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    status: Mapped[str] = mapped_column(Text, default="draft")  # draft|approved|archived
    validation: Mapped[dict[str, Any]] = mapped_column(default=dict)


class ResumeRender(IdMixin, TimestampMixin, Base):
    __tablename__ = "resume_render"
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resume_variant.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(Text)
    tex_source_key: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text)
    rendered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ats_text: Mapped[str | None] = mapped_column(Text)
    ats_report: Mapped[dict[str, Any]] = mapped_column(default=dict)
    page_count: Mapped[int | None] = mapped_column(Integer)
