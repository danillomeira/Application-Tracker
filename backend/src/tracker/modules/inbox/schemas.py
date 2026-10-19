"""Classificação de e-mails/mensagens (saída de `email.classify`) e DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Label = Literal[
    "confirmacao",
    "rejeicao",
    "convite_entrevista",
    "pedido_disponibilidade",
    "teste_tecnico",
    "oferta",
    "pedido_info",
    "recrutador_prospeccao",
    "notificacao_linkedin",
    "remarcacao",
    "cancelamento",
    "irrelevante",
]


class XDateTime(BaseModel):
    start: str = Field(description="ISO 8601 com fuso, ex.: 2026-10-21T14:00:00-03:00")
    end: str | None = None
    timezone_explicit: bool = Field(description="o e-mail informa o fuso explicitamente?")


class XPerson(BaseModel):
    name: str
    role: str | None = None
    email: str | None = None


class Extracted(BaseModel):
    datetimes: list[XDateTime] = Field(default_factory=list)
    meeting_link: str | None = None
    scheduling_link: str | None = Field(None, description="Calendly, Google Appointment, etc.")
    deadline: str | None = Field(None, description="prazo de teste técnico/resposta, ISO 8601")
    people: list[XPerson] = Field(default_factory=list)
    interview_kind: Literal["hr", "technical", "hiring_manager", "panel", "culture", "final"] | None = None
    duration_min: int | None = None
    company_name: str | None = None
    job_title: str | None = None
    offer_summary: str | None = None


class EmailClassification(BaseModel):
    label: Label
    confidence: float = Field(ge=0, le=1)
    application_match: str | None = Field(None, description="id da candidatura candidata que corresponde, se houver")
    summary: str = Field(description="1 frase em português")
    extracted: Extracted


class EmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    gmail_id: str
    thread_id: str | None
    from_addr: str
    from_name: str | None
    subject: str
    snippet: str
    received_at: datetime
    classification: str | None
    classification_confidence: float | None
    extracted: dict[str, Any]
    application_id: uuid.UUID | None
    link_status: str
    prefilter: str | None


class LinkIn(BaseModel):
    application_id: uuid.UUID


class ReclassifyIn(BaseModel):
    label: Label


class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    application_id: uuid.UUID | None
    to: str | None
    subject: str | None
    body: str
    gmail_draft_id: str | None
    status: str
    meta: dict[str, Any]
    created_at: datetime


class DraftUpdate(BaseModel):
    to: str | None = None
    subject: str | None = None
    body: str | None = None


class DraftText(BaseModel):
    subject: str
    body: str
