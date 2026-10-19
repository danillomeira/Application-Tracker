"""Schemas estritos para saídas de IA do perfil (sem campos livres)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class XContact(BaseModel):
    full_name: str
    email: str
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None


class XSkillGroup(BaseModel):
    category: str
    items: list[str]


class XExperience(BaseModel):
    id: str = Field(description="slug curto e único, ex.: 'acme-atual'")
    title: str
    organization: str
    location: str | None = None
    start: str | None = Field(None, description="YYYY-MM ou YYYY")
    end: str | None = Field(None, description="YYYY-MM, YYYY ou null se atual")
    bullets_en: list[str]
    skills: list[str]


class XProject(BaseModel):
    id: str
    name: str
    url: str | None = None
    description_en: str
    skills: list[str]


class XEducation(BaseModel):
    degree: str
    institution: str
    start: str | None = None
    end: str | None = None
    status: str | None = None


class XCertification(BaseModel):
    name: str
    issuer: str | None = None


class XLanguage(BaseModel):
    name: str
    level: str | None = None


class ExtractedProfile(BaseModel):
    contact: XContact
    headline: str | None = None
    skills: list[XSkillGroup]
    experience: list[XExperience]
    projects: list[XProject]
    education: list[XEducation]
    certifications: list[XCertification]
    languages: list[XLanguage]
    low_confidence: list[str] = Field(description="caminhos de campos com baixa confiança, ex.: 'experience[2].start'")


class TranslatedExperience(BaseModel):
    experience_id: str
    bullets: list[str]


class TranslatedProject(BaseModel):
    project_id: str
    description: str


class Translation(BaseModel):
    experiences: list[TranslatedExperience]
    projects: list[TranslatedProject]
