"""Conteúdo renderizável de currículo e schemas de IA (docs/11)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SkillRow(BaseModel):
    category: str
    items: list[str]


class ExpBlock(BaseModel):
    experience_id: str
    title: str
    organization: str
    location: str | None = None
    period: str
    bullets: list[str]


class ProjBlock(BaseModel):
    project_id: str
    name: str
    url: str | None = None
    description: str


class EduBlock(BaseModel):
    degree: str
    period: str
    institution: str


class CertBlock(BaseModel):
    name: str
    issuer: str | None = None


class LangBlock(BaseModel):
    name: str
    level: str | None = None


class ResumeContent(BaseModel):
    language: str = "en"
    headline: str
    summary: str
    skill_rows: list[SkillRow]
    experience: list[ExpBlock]
    projects: list[ProjBlock] = Field(default_factory=list)
    education: list[EduBlock] = Field(default_factory=list)
    certifications: list[CertBlock] = Field(default_factory=list)
    languages: list[LangBlock] = Field(default_factory=list)


# ---------- Saída de IA (estrita) ----------
class DraftExperience(BaseModel):
    experience_id: str
    title: str = Field(description="cargo exatamente como no mestre ou em title_alternatives")
    bullets: list[str]


class ResumeDraft(BaseModel):
    headline: str
    summary: str
    skill_rows: list[SkillRow]
    experiences: list[DraftExperience] = Field(description="na ordem de exibição")
    project_ids: list[str]
    used_facts: list[str] = Field(description="ids de experiências/projetos e métricas usados")
    changes: list[str] = Field(description="o que foi adaptado e por quê, em português")


class CoverLetter(BaseModel):
    text: str = Field(description="no máximo 150 palavras")
    used_facts: list[str]


# ---------- API ----------
class Violation(BaseModel):
    kind: str
    text: str
    suggestion: str | None = None


class ValidationReport(BaseModel):
    passed: bool
    violations: list[Violation] = Field(default_factory=list)
    warnings: list[Violation] = Field(default_factory=list)


class AtsCheck(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class AtsReport(BaseModel):
    ok: bool
    checks: list[AtsCheck]
    keyword_coverage: float | None = None
    missing_keywords: list[str] = Field(default_factory=list)


class RenderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    filename: str
    sha256: str
    page_count: int | None
    rendered_at: datetime
    ats_report: dict[str, Any]


class VariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    slug: str
    name: str
    language: str
    focus: dict[str, Any]
    content: dict[str, Any]
    changes: list[Any]
    master_version: int
    job_id: uuid.UUID | None
    parent_variant_id: uuid.UUID | None
    status: str
    validation: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class VariantDetail(VariantOut):
    renders: list[RenderOut] = Field(default_factory=list)


class VariantUpdate(BaseModel):
    name: str | None = None
    content: ResumeContent | None = None
    status: str | None = Field(default=None, pattern="^(draft|approved|archived)$")


class BaselineIn(BaseModel):
    profile: str = "data_engineer"
    language: str = Field(default="en", pattern="^(en|pt)$")
    name: str | None = None


class TailorIn(BaseModel):
    job_id: uuid.UUID
    base_variant_id: uuid.UUID | None = None


class WildcardsIn(BaseModel):
    profiles: list[str] | None = None
    languages: list[str] = Field(default_factory=lambda: ["en", "pt"])


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slug: str
    name: str
    engine: str
    version: int
    supports_languages: list[str]
