"""Filtro de relevância SEM IA, aplicado antes de gravar vagas de fontes amplas.

Empresas grandes têm milhares de vagas (ex.: Bosch). Só entram as que batem com seus cargos-alvo,
buscas salvas ou stacks; o resto nem chega ao banco (e não gasta IA).
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.modules.jobs.models import SavedSearch
from tracker.modules.jobs.normalize import RawJob, normalize_title
from tracker.modules.profile import service as profile_service

DEFAULT_TERMS = [
    "data engineer",
    "engenheiro de dados",
    "engenheira de dados",
    "analytics engineer",
    "software engineer",
    "engenheiro de software",
    "backend",
    "back-end",
    "full stack",
    "fullstack",
    "machine learning",
    "ml engineer",
    "ai engineer",
    "python developer",
    "desenvolvedor python",
    "data platform",
    "mlops",
]


def split_terms(query: str) -> list[str]:
    return [normalize_title(t) for t in re.split(r"\||\bOR\b|,", query) if t.strip()]


async def terms(session: AsyncSession) -> list[str]:
    prefs = await profile_service.get_preferences(session)
    out: list[str] = [normalize_title(r) for r in prefs.target_roles]
    for ss in (await session.scalars(select(SavedSearch).where(SavedSearch.is_active.is_(True)))).all():
        out += split_terms(ss.query)
    return [t for t in dict.fromkeys(out or [normalize_title(t) for t in DEFAULT_TERMS]) if t]


def matches(title: str, terms_: list[str]) -> bool:
    t = f" {normalize_title(title)} "
    return any(all(f" {w} " in t or w in t for w in term.split()) for term in terms_)


# Senioridade/função que nunca interessam (estágio, gestão): cortadas antes de gastar IA.
EXCLUDED_TITLE = re.compile(
    r"\b(estagio|estagiari[oa]|intern|internship|trainee|aprendiz|gerente|manager|director|diretor[a]?|"
    r"head of|vp|vice president|coordenador[a]?)\b"
)
BR_LOCATION = re.compile(
    r"\b(brazil|brasil|sao paulo|brasilia|rio de janeiro|belo horizonte|curitiba|florianopolis|porto alegre|recife|"
    r"campinas|fortaleza|salvador|goiania|remoto|hibrido|presencial|teletrabalho)\b|,\s*(sp|mg|df|rj|pr|sc|rs|pe|go|ba|ce)\b|\bbr\b"
)
OPEN_TO_BRAZIL = re.compile(r"\b(worldwide|anywhere|global|latam|latin america|south america|americas)\b")
AMBIGUOUS_LOCATION = {"", "n/a", "remote", "hybrid", "in-office", "on-site", "onsite", "multiple locations", "remote-friendly"}


def _fold(text: str | None) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower().strip()


def location_ok(location: str | None, brazilian_company: bool, international: bool = True) -> bool:
    """A vaga pode ser feita do Brasil? Brasil/LATAM/mundo entram; "Remote - USA", Bengaluru, Londres... não.

    Local vazio ou genérico ("Remote", "Hybrid") só entra se a empresa for brasileira.
    """
    loc = _fold(location)
    if BR_LOCATION.search(loc):
        return True
    if international and OPEN_TO_BRAZIL.search(loc):
        return True
    return loc in AMBIGUOUS_LOCATION and brazilian_company


def filter_relevant(
    raws: list[RawJob], terms_: list[str], brazilian_company: bool | None = None, international: bool = True
) -> list[RawJob]:
    """Título bate com os termos, sem estágio/gestão e (se `brazilian_company` for informado) com local acessível do Brasil."""
    out: list[RawJob] = []
    for r in raws:
        if not matches(r.title, terms_) or EXCLUDED_TITLE.search(_fold(r.title)):
            continue
        if brazilian_company is not None and not location_ok(r.location, brazilian_company, international):
            continue
        out.append(r)
    return out
