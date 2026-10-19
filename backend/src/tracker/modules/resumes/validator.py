"""Validador determinístico de fatos (docs/11-curriculos.md §6, RF-CV-05).

Todo conteúdo gerado (CV, carta, respostas abertas) só pode usar fatos do mestre.
"""

from __future__ import annotations

import re

from tracker.modules.profile import facts
from tracker.modules.profile.schemas import MasterProfile
from tracker.modules.resumes.schemas import ResumeContent, ValidationReport, Violation
from tracker.modules.resumes.tech_terms import TECH_TERMS

# Palavras comuns em prosa que também são nomes de tecnologia: não detectar em texto livre.
AMBIGUOUS = {
    "r",
    "go",
    "rest",
    "ray",
    "elk",
    "lambda",
    "beam",
    "glue",
    "express",
    "spring",
    "rails",
    "apache",
    "s3",
    "spark",
}


def _strip_md(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).replace("--", "-")


def unknown_terms(text: str, master: MasterProfile, idx: dict[str, str] | None = None) -> list[str]:
    idx = idx if idx is not None else facts.skill_index(master)
    master_blob = facts.norm(master.model_dump_json())
    plain = " " + facts.norm(_strip_md(text)) + " "
    found: list[str] = []
    for term in TECH_TERMS:
        if term in AMBIGUOUS:
            continue
        t = facts.norm(term)
        if not t or not re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", plain):
            continue
        if t in idx or re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", master_blob):
            continue
        found.append(term)
    return found


def unknown_numbers(text: str, master_nums: set[str]) -> list[str]:
    return sorted(n for n in facts.numbers_in(_strip_md(text)) if n not in master_nums)


def check_text(text: str, master: MasterProfile, where: str) -> list[Violation]:
    out: list[Violation] = []
    nums = facts.master_numbers(master)
    for term in unknown_terms(text, master):
        out.append(
            Violation(
                kind="skill",
                text=f"{where}: '{term}' não está no currículo mestre",
                suggestion="remova ou adicione ao mestre se for verdade",
            )
        )
    for n in unknown_numbers(text, nums):
        out.append(
            Violation(
                kind="number",
                text=f"{where}: número '{n}' não aparece no mestre",
                suggestion="use apenas métricas do mestre",
            )
        )
    return out


def validate(content: ResumeContent, master: MasterProfile) -> ValidationReport:
    violations: list[Violation] = []
    warnings: list[Violation] = []
    idx = facts.skill_index(master)
    lang = content.language

    for row in content.skill_rows:
        for item in row.items:
            if facts.has_skill(master, item, idx) is None:
                violations.append(
                    Violation(kind="skill", text=f"skill '{item}' não está no mestre", suggestion="remova da tabela de skills")
                )

    for block in content.experience:
        exp = master.experience_by_id(block.experience_id)
        if exp is None:
            violations.append(Violation(kind="experience", text=f"experiência '{block.experience_id}' não existe"))
            continue
        if block.title not in [exp.title, *exp.title_alternatives]:
            violations.append(
                Violation(
                    kind="title",
                    text=f"cargo '{block.title}' não confirmado para {exp.id}",
                    suggestion=f"use '{exp.title}' ou um título alternativo confirmado",
                )
            )
        valid_orgs = {o for o in (exp.organization, exp.organization_short, exp.org_line_en, exp.org_line_pt) if o}
        if block.organization not in valid_orgs:
            violations.append(Violation(kind="organization", text=f"organização '{block.organization}' diferente do mestre"))
        expected = facts.format_period(exp.start, exp.end, lang)
        if block.period != expected:
            violations.append(Violation(kind="date", text=f"período '{block.period}' ≠ '{expected}'", suggestion=expected))
        for i, b in enumerate(block.bullets):
            violations.extend(check_text(b, master, f"{exp.id} bullet {i + 1}"))

    violations.extend(check_text(content.summary, master, "resumo"))
    violations.extend(check_text(content.headline, master, "headline"))

    master_degrees = {e.degree for e in master.education}
    for ed in content.education:
        if ed.degree not in master_degrees:
            violations.append(Violation(kind="education", text=f"formação '{ed.degree}' não está no mestre"))
    master_certs = {c.name for c in master.certifications}
    for c in content.certifications:
        if c.name not in master_certs:
            violations.append(Violation(kind="certification", text=f"certificação '{c.name}' não está no mestre"))

    project_ids = {p.id for p in master.projects}
    for p in content.projects:
        if p.project_id not in project_ids:
            violations.append(Violation(kind="project", text=f"projeto '{p.name}' não existe"))
        else:
            violations.extend(check_text(p.description, master, f"projeto {p.name}"))

    claimed = re.search(r"(\d+)\+?\s*(?:years|anos)", _strip_md(content.summary))
    if claimed:
        computed = facts.total_years(master)
        if int(claimed.group(1)) > computed:
            warnings.append(
                Violation(
                    kind="years",
                    text=f"resumo diz {claimed.group(0)}, datas somam {computed} anos",
                    suggestion="confira se a afirmação é defensável em entrevista",
                )
            )
    return ValidationReport(passed=not violations, violations=violations, warnings=warnings)


def validate_free_text(text: str, master: MasterProfile, where: str = "texto") -> ValidationReport:
    v = check_text(text, master, where)
    return ValidationReport(passed=not v, violations=v)
