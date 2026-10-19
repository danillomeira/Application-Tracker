from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from tracker.core.db import Base, IdMixin, TimestampMixin
from tracker.core.types import EMBEDDING_DIM, TextArray


class MasterProfileVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "master_profile_version"
    version: Mapped[int] = mapped_column(Integer, unique=True)
    data: Mapped[dict[str, Any]]
    source: Mapped[str] = mapped_column(Text)  # import_pdf | manual_edit | seed_yaml
    change_note: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class ProfileImport(IdMixin, TimestampMixin, Base):
    __tablename__ = "profile_import"
    filename: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending")  # pending|extracted|applied|failed
    extracted: Mapped[dict[str, Any] | None]
    error: Mapped[str | None] = mapped_column(Text)


class StarStory(IdMixin, TimestampMixin, Base):
    __tablename__ = "star_story"
    title: Mapped[str] = mapped_column(Text)
    experience_id: Mapped[str | None] = mapped_column(Text)
    situation: Mapped[str] = mapped_column(Text)
    task: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(Text)
    competencies: Mapped[list[str]] = mapped_column(TextArray, default=list)
    skills: Mapped[list[str]] = mapped_column(TextArray, default=list)
    language: Mapped[str] = mapped_column(Text, default="en")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))


class Preference(IdMixin, TimestampMixin, Base):
    __tablename__ = "preference"
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)


class AnswerBankEntry(IdMixin, TimestampMixin, Base):
    __tablename__ = "answer_bank_entry"
    canonical_question: Mapped[str] = mapped_column(Text, index=True)
    question_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    field_kind: Mapped[str] = mapped_column(Text, default="text")
    answer: Mapped[dict[str, Any]]
    conditions: Mapped[dict[str, Any]] = mapped_column(default=dict)
    language: Mapped[str] = mapped_column(Text, default="any")
    source: Mapped[str] = mapped_column(Text, default="user")
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aliases: Mapped[list[str]] = mapped_column(TextArray, default=list)


class BlocklistEntry(IdMixin, TimestampMixin, Base):
    __tablename__ = "blocklist_entry"
    kind: Mapped[str] = mapped_column(Text)  # company | domain | recruiter | keyword
    value: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)


class Document(IdMixin, TimestampMixin, Base):
    __tablename__ = "document"
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Reference(IdMixin, TimestampMixin, Base):
    __tablename__ = "professional_reference"
    name: Mapped[str] = mapped_column(Text)
    relation: Mapped[str] = mapped_column(Text)
    contact: Mapped[str] = mapped_column(Text)
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
