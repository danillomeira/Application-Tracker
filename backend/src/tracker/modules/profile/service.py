"""Serviço do perfil: mestre versionado, preferências, banco de respostas, bloqueios."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core import audit
from tracker.integrations.embeddings import embed_one, normalize_text
from tracker.modules.profile.models import (
    AnswerBankEntry,
    BlocklistEntry,
    MasterProfileVersion,
    Preference,
)
from tracker.modules.profile.schemas import DiffEntry, MasterProfile, PreferenceData


async def current_version(session: AsyncSession) -> MasterProfileVersion | None:
    return await session.scalar(select(MasterProfileVersion).where(MasterProfileVersion.is_current.is_(True)))


async def current_master(session: AsyncSession) -> tuple[int, MasterProfile]:
    row = await current_version(session)
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "currículo mestre ainda não cadastrado (faça o onboarding)")
    return row.version, MasterProfile.model_validate(row.data)


async def save_master(
    session: AsyncSession,
    data: MasterProfile | dict[str, Any],
    source: str,
    note: str | None = None,
) -> MasterProfileVersion:
    profile = data if isinstance(data, MasterProfile) else MasterProfile.model_validate(data)
    last = await current_version(session)
    next_version = (last.version + 1) if last else 1
    await session.execute(update(MasterProfileVersion).where(MasterProfileVersion.is_current.is_(True)).values(is_current=False))
    row = MasterProfileVersion(
        version=next_version,
        data=profile.model_dump(mode="json", exclude_none=False),
        source=source,
        change_note=note,
        is_current=True,
    )
    session.add(row)
    await session.flush()
    await audit.record(
        session,
        actor="user" if source == "manual_edit" else "system",
        action="profile.master.save",
        entity_type="master_profile",
        entity_id=row.id,
        after={"version": next_version},
        reason=note,
    )
    return row


def load_yaml(path: Path) -> MasterProfile:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return MasterProfile.model_validate(raw)


def diff(a: Any, b: Any, path: str = "") -> list[DiffEntry]:
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[DiffEntry] = []
        for k in sorted(set(a) | set(b), key=str):
            out.extend(diff(a.get(k), b.get(k), f"{path}.{k}" if path else str(k)))
        return out
    if isinstance(a, list) and isinstance(b, list):
        out = []
        for i in range(max(len(a), len(b))):
            out.extend(diff(a[i] if i < len(a) else None, b[i] if i < len(b) else None, f"{path}[{i}]"))
        return out
    return [] if a == b else [DiffEntry(path=path, before=a, after=b)]


async def get_preferences(session: AsyncSession) -> PreferenceData:
    row = await session.scalar(select(Preference))
    return PreferenceData.model_validate(row.data if row else {})


async def put_preferences(session: AsyncSession, data: PreferenceData) -> PreferenceData:
    row = await session.scalar(select(Preference))
    if row is None:
        row = Preference(data={})
        session.add(row)
    row.data = data.model_dump(mode="json")
    await session.flush()
    return data


def normalize_question(q: str) -> str:
    q = normalize_text(q)
    q = re.sub(r"[?*:]+", " ", q)
    return re.sub(r"\s+", " ", q).strip()


async def upsert_answer(session: AsyncSession, entry: AnswerBankEntry) -> AnswerBankEntry:
    entry.canonical_question = entry.canonical_question.strip()
    entry.question_embedding = embed_one(entry.canonical_question)
    session.add(entry)
    await session.flush()
    return entry


SENSITIVE_PATTERNS = [
    r"salar",
    r"pretens",
    r"remunera",
    r"compensation",
    r"expected pay",
    r"ctc",
    r"visa",
    r"visto",
    r"sponsor",
    r"patroc",
    r"authori[sz]",
    r"autoriza",
    r"disabilit",
    r"defici",
    r"\brace\b",
    r"\braca\b",
    r"ethnic",
    r"etnia",
    r"gender",
    r"genero",
    r"sexual",
    r"orienta",
    r"veteran",
    r"criminal",
    r"antecedent",
    r"\bcpf\b",
    r"\brg\b",
    r"passport",
    r"passaporte",
    r"birth",
    r"nasciment",
    r"religi",
    # dados que só você tem (nunca pela IA): matrícula, códigos e documentos
    r"matricula",
    r"employee (id|number)",
    r"numero de (funcionario|colaborador|registro)",
    r"registro funcional",
    r"codigo de (indicacao|referencia|funcionario|colaborador)",
    r"referral code",
    r"\bcnh\b",
    r"\bpis\b",
    r"titulo de eleitor",
    r"conta bancaria",
]


def is_sensitive(question: str) -> bool:
    q = normalize_text(question)
    return any(re.search(p, q) for p in SENSITIVE_PATTERNS)


def default_blocklist(master: MasterProfile) -> list[tuple[str, str, str]]:
    """Empregador(es) atual(is) do currículo: não faz sentido receber vagas de onde você já trabalha (Q-18)."""
    out: list[tuple[str, str, str]] = []
    for e in master.experience:
        org = (e.organization_short or e.organization or "").strip()
        if e.end is None and e.type == "employment" and org and org.lower() not in {v.lower() for _, v, _ in out}:
            out.append(("company", org, "empregador atual"))
    return out


DEGREE_ORDER = [
    (r"doutorado|ph\.?d|doctor", "Doctorate", ["Doctorate", "PhD", "Doutorado"]),
    (r"mestrado|master|msc|m\.sc", "Master's Degree", ["Master", "Mestrado"]),
    (r"mba|p[oó]s|especializa|lato sensu|postgraduate", "Postgraduate",
     ["Postgraduate", "Pós-graduação", "Especialização", "MBA"]),
    (r"bacharel|bachelor|gradua|licenciatura|engenharia|b\.?sc|superior", "Bachelor's Degree",
     ["Bachelor", "Bacharelado", "Graduação", "Superior completo"]),
    (r"tecn[oó]logo|associate|t[eé]cnico", "Associate Degree", ["Associate", "Tecnólogo", "Técnico"]),
]  # fmt: skip


def highest_education(master: MasterProfile) -> tuple[str, list[str]] | None:
    """Maior formação concluída do currículo (curso em andamento não conta)."""
    done = [e for e in master.education if (e.status or "").lower() not in {"in progress", "em andamento", "cursando"}]
    for pattern, value, prefer in DEGREE_ORDER:
        if any(re.search(pattern, e.degree, re.I) for e in done):
            return value, prefer
    return None


async def seed_defaults(session: AsyncSession, master: MasterProfile) -> dict[str, int]:
    """Bloqueios padrão e respostas derivadas do perfil (Q-18)."""
    created = {"blocklist": 0, "answers": 0}
    if not await session.scalar(select(BlocklistEntry.id).limit(1)):
        for kind, value, reason in default_blocklist(master):
            session.add(BlocklistEntry(kind=kind, value=value, reason=reason))
            created["blocklist"] += 1
    if not await session.scalar(select(AnswerBankEntry.id).limit(1)):
        langs = {lang.name.lower(): lang.level for lang in master.languages}
        defaults: list[tuple[str, str, dict[str, Any], list[str]]] = []
        if langs.get("english"):
            defaults.append(
                (
                    "What is your level of English?",
                    "select",
                    {"value": langs["english"], "prefer": ["Advanced", "Fluent", "Avançado"]},
                    ["english proficiency", "nivel de ingles", "qual seu nivel de ingles"],
                )
            )
        if langs.get("portuguese"):
            defaults.append(
                (
                    "What is your level of Portuguese?",
                    "select",
                    {"value": langs["portuguese"], "prefer": ["Native", "Nativo", "Fluent"]},
                    ["nivel de portugues"],
                )
            )
        if edu := highest_education(master):
            defaults.append(
                (
                    "What is your highest level of education?",
                    "select",
                    {"value": edu[0], "prefer": edu[1]},
                    ["nivel de escolaridade", "grau de instrucao", "highest degree"],
                )
            )
        defaults += [
            (
                "Are you comfortable working remotely?",
                "radio",
                {"value": "Yes", "prefer": ["Yes", "Sim"]},
                ["voce tem disponibilidade para trabalho remoto"],
            ),
            (
                "Are you willing to work in a hybrid model?",
                "radio",
                {"value": "Yes", "prefer": ["Yes", "Sim"]},
                ["aceita trabalho hibrido"],
            ),
        ]
        for q, kind, ans, aliases in defaults:
            await upsert_answer(
                session,
                AnswerBankEntry(
                    canonical_question=q,
                    field_kind=kind,
                    answer=ans,
                    aliases=aliases,
                    source="derived_from_profile",
                    language="any",
                ),
            )
            created["answers"] += 1
    await session.flush()
    return created
