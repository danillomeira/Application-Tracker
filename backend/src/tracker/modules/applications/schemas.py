"""DTOs de candidaturas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    status: str
    channel: str
    mode: str
    resume_variant_id: uuid.UUID | None
    resume_render_id: uuid.UUID | None
    submitted_at: datetime | None
    queue_priority: float
    last_activity_at: datetime
    next_action: str | None
    next_action_at: datetime | None
    outcome_reason: str | None
    notes: str | None
    created_at: datetime
    job_title: str | None = None
    company_name: str | None = None
    company_id: uuid.UUID | None = None
    quadrant: str | None = None
    apply_kind: str | None = None
    ats_kind: str | None = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    payload: dict[str, Any]
    actor: str
    reason: str | None
    occurred_at: datetime


class AnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    step_index: int
    question_text: str
    field_kind: str
    options: list[Any]
    answer: dict[str, Any]
    resolution: str
    confidence: float


class ApplicationDetail(ApplicationOut):
    cover_letter: str | None
    evidence: dict[str, Any]
    priority_at_submit: dict[str, Any] | None
    applied_snapshot_id: uuid.UUID | None
    timeline: list[EventOut] = Field(default_factory=list)
    answers: list[AnswerOut] = Field(default_factory=list)
    emails: list[dict[str, Any]] = Field(default_factory=list)
    events_calendar: list[dict[str, Any]] = Field(default_factory=list)
    interviews: list[dict[str, Any]] = Field(default_factory=list)
    drafts: list[dict[str, Any]] = Field(default_factory=list)
    pending_questions: list[dict[str, Any]] = Field(default_factory=list)
    people: list[dict[str, Any]] = Field(default_factory=list)


class ApplicationPatch(BaseModel):
    status: str | None = None
    reason: str | None = None
    notes: str | None = None
    next_action: str | None = None
    next_action_at: datetime | None = None
    resume_variant_id: uuid.UUID | None = None


class NoteIn(BaseModel):
    text: str


class ManualApplicationIn(BaseModel):
    job_id: uuid.UUID | None = None
    url: str | None = None
    company_name: str | None = None
    title: str | None = None
    description: str | None = None
    submitted_at: datetime | None = None
    resume_variant_id: uuid.UUID | None = None
    channel: str = "external"
    notes: str | None = None
