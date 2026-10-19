"""Perfil de empresa (saída de `company.profile`) e DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceRef(BaseModel):
    url: str
    title: str | None = None
    date: str | None = None


class Claim(BaseModel):
    text: str
    source_urls: list[str] = Field(description="URLs que sustentam a afirmação (obrigatório)")


class Reputation(BaseModel):
    rating: float | None = Field(None, description="nota média 1-5 em sites de avaliação de empregadores")
    rating_source: str | None = None
    rating_trend_12m: float | None = Field(None, description="variação da nota em 12 meses")
    ceo_approval: float | None = Field(None, description="0-1")
    review_count: int | None = None


class CompanyProfileContent(BaseModel):
    summary: str
    history: list[Claim]
    mission: str | None = None
    values: list[Claim]
    products: list[str]
    business_model: str | None = None
    customers: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    reputation: Reputation
    culture_positive: list[str] = Field(default_factory=list)
    culture_alerts: list[str] = Field(default_factory=list, description="burnout, horas extras, liderança tóxica...")
    headcount_growth_12m: float | None = Field(None, description="ex.: 0.18 para +18%")
    recent_funding: bool | None = None
    layoffs_12m: bool | None = None
    crisis_news: bool | None = None
    is_product_company: bool | None = None
    is_body_shop: bool | None = None
    remote_friendly: bool | None = None
    ghosting_reports: int | None = Field(None, description="relatos públicos de candidatos sem retorno")
    avg_process_days: int | None = None
    sector: str | None = None
    size_range: str | None = None
    hq_location: str | None = None
    news: list[Claim] = Field(default_factory=list, description="notícias dos últimos 12 meses")
    sources: list[SourceRef]


class CompanyIn(BaseModel):
    name: str
    website: str | None = None
    linkedin_url: str | None = None
    ats_kind: Literal["greenhouse", "lever", "ashby", "gupy"] | None = None
    ats_board_token: str | None = None
    is_monitored: bool = False
    is_watchlisted: bool = False
    is_blocked: bool = False
    sector: str | None = None


class CompanyUpdate(BaseModel):
    website: str | None = None
    linkedin_url: str | None = None
    ats_kind: Literal["greenhouse", "lever", "ashby", "gupy"] | None = None
    ats_board_token: str | None = None
    is_monitored: bool | None = None
    is_watchlisted: bool | None = None
    is_blocked: bool | None = None
    sector: str | None = None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    domains: list[str]
    website: str | None
    linkedin_url: str | None
    sector: str | None
    size_range: str | None
    ats_kind: str | None
    ats_board_token: str | None
    is_monitored: bool
    is_watchlisted: bool
    is_blocked: bool
    last_polled_at: datetime | None


class CompanyDetail(CompanyOut):
    profile: dict[str, Any] | None = None
    profile_collected_at: datetime | None = None
    responsiveness: dict[str, Any] | None = None
    open_jobs: int = 0
    applications: int = 0
