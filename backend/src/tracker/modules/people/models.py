from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from tracker.core.db import Base, IdMixin, TimestampMixin


class Person(IdMixin, TimestampMixin, Base):
    __tablename__ = "person"
    full_name: Mapped[str] = mapped_column(Text)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.id", ondelete="SET NULL"), index=True
    )
    role: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text, index=True)
    kind: Mapped[str] = mapped_column(Text, default="recruiter")
    notes: Mapped[str | None] = mapped_column(Text)
    referral_status: Mapped[str | None] = mapped_column(Text)  # none|asked|accepted|declined
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PersonApplication(IdMixin, TimestampMixin, Base):
    __tablename__ = "person_application"
    __table_args__ = (UniqueConstraint("person_id", "application_id", "relation"),)
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("person.id", ondelete="CASCADE"))
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("application.id", ondelete="CASCADE"))
    relation: Mapped[str] = mapped_column(Text)
