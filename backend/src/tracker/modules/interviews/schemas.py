"""Dossiê (RF-ENT-01), simulação (RF-ENT-03) e DTOs de entrevistas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from tracker.modules.companies.schemas import Claim, SourceRef


class JobSummary(BaseModel):
    responsibilities: list[str]
    must: list[str]
    nice: list[str]
    what_team_values: list[str] = Field(description="o que o time provavelmente valoriza, inferido do anúncio")


class MatchPoint(BaseModel):
    requirement: str
    experience_id: str = Field(description="id da experiência/projeto do perfil que prova o requisito")
    what_to_say: str = Field(description="como citar, em 1-2 frases, só com fatos do perfil")
    star_story_title: str | None = None


class Gap(BaseModel):
    requirement: str
    honest_approach: str


class CompanyBrief(BaseModel):
    overview: str
    history: list[Claim]
    products: list[str]
    business_model: str | None = None
    customers: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    news: list[Claim] = Field(default_factory=list)


class ValueLink(BaseModel):
    value: str
    how_to_connect: str = Field(description="ligação com algo concreto da trajetória do candidato")
    source_urls: list[str]


class InterviewerBrief(BaseModel):
    name: str
    role: str | None = None
    notes: str | None = Field(None, description="só informação profissional pública")


class LikelyQuestion(BaseModel):
    question: str
    type: Literal["technical", "behavioral", "company", "role"]
    answer_outline: str


class Logistics(BaseModel):
    when: str | None = None
    link: str | None = None
    duration: str | None = None
    format: str | None = None
    what_to_bring: list[str] = Field(default_factory=list)


class DossierContent(BaseModel):
    job_summary: JobSummary
    match: list[MatchPoint]
    gaps: list[Gap]
    company: CompanyBrief
    mission: str | None = None
    values: list[ValueLink]
    interviewers: list[InterviewerBrief] = Field(default_factory=list)
    likely_questions: list[LikelyQuestion]
    questions_to_ask: list[str]
    logistics: Logistics
    points_to_defend: list[str] = Field(default_factory=list, description="afirmações do CV que podem ser questionadas")
    sources: list[SourceRef]


class AnswerFeedback(BaseModel):
    star_structure: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    evidence: int = Field(ge=1, le=5)
    overall: int = Field(ge=1, le=5)
    strengths: list[str]
    improvements: list[str]
    better_answer_outline: str


class MockTurn(BaseModel):
    feedback: AnswerFeedback | None = Field(None, description="avaliação da última resposta (null no primeiro turno)")
    next_question: str | None = None
    done: bool = False
    final_summary: str | None = None


class InterviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    application_id: uuid.UUID
    round: int
    kind: str
    starts_at: datetime | None
    interviewers: list[Any]
    post_notes: dict[str, Any] | None
    self_rating: int | None
    scheduled_event_id: uuid.UUID | None
    company_name: str | None = None
    job_title: str | None = None
    dossier_status: str | None = None
    link: str | None = None


class InterviewIn(BaseModel):
    application_id: uuid.UUID
    kind: Literal["hr", "technical", "hiring_manager", "panel", "culture", "final"] = "hr"
    starts_at: datetime
    duration_min: int = 60
    link: str | None = None
    interviewers: list[dict[str, Any]] = Field(default_factory=list)


class PostNotesIn(BaseModel):
    questions: list[str] = Field(default_factory=list)
    feeling: str | None = None
    highlights: str | None = None
    next_steps: str | None = None
    self_rating: int | None = Field(default=None, ge=1, le=5)
    generate_thank_you: bool = True


class MockStartIn(BaseModel):
    application_id: uuid.UUID
    interview_kind: Literal["hr", "technical", "hiring_manager", "panel", "culture", "final"] = "technical"


class MockAnswerIn(BaseModel):
    answer: str


class AssessmentIn(BaseModel):
    application_id: uuid.UUID
    kind: Literal["take_home", "live_coding", "online_test"] = "take_home"
    instructions: str | None = None
    deadline_at: datetime | None = None
    repo_url: str | None = None
    status: Literal["pending", "in_progress", "submitted"] = "pending"


class AssessmentOut(AssessmentIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
