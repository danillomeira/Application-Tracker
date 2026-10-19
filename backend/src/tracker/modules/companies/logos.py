"""Logo das empresas: domínio (curado no seed, salvo na empresa ou um palpite estrito) → ícone do site, em cache.

Um logo errado é pior que nenhum: o palpite só aceita o nome inteiro da empresa e descarta redirecionamentos
para outra marca (ex.: "Blip" → disney.com). Sem logo, o dashboard mostra as iniciais.
"""

from __future__ import annotations

import functools
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core.storage import get_storage
from tracker.modules.companies.models import Company
from tracker.modules.companies.service import normalize_company

STOP = {
    "inc",
    "sa",
    "ltda",
    "group",
    "grupo",
    "co",
    "the",
    "corp",
    "corporation",
    "company",
    "technologies",
    "tecnologia",
    "labs",
}
UA = {"User-Agent": "Mozilla/5.0 (compatible; ApplicationTracker/1.0)"}
_transport: httpx.AsyncBaseTransport | None = None


def set_transport(t: httpx.AsyncBaseTransport | None) -> None:
    global _transport
    _transport = t


@functools.cache
def seed_domains() -> dict[str, str]:
    path = Path(__file__).resolve().parents[1] / "jobs" / "seeds" / "companies.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {normalize_company(c["name"]): c["domain"] for c in data.get("companies", []) if c.get("domain")}


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def name_tokens(name: str) -> list[str]:
    words = [w for w in re.split(r"[^a-z0-9]+", _ascii(name).replace("&", "")) if w]
    return [w for w in words if w not in STOP] or words


def plausible(final_url: str, name: str) -> bool:
    """O site final ainda é da empresa? (algum pedaço do nome aparece no domínio)"""
    host = urlparse(final_url).netloc.lower().removeprefix("www.")
    root = host.split(".")[0]
    tokens = [t for t in name_tokens(name) if len(t) >= 3]
    return any(t in root or root in t for t in tokens) or "".join(name_tokens(name)) in host


async def guess_domain(client: httpx.AsyncClient, name: str, brazilian: bool) -> str | None:
    slug = "".join(name_tokens(name))
    if len(slug) < 3:
        return None
    for tld in [".com.br", ".com"] if brazilian else [".com", ".io", ".ai", ".com.br"]:
        try:
            r = await client.get(f"https://{slug}{tld}", timeout=5)
        except httpx.HTTPError:
            continue
        if r.status_code < 400 and plausible(str(r.url), name):
            return urlparse(str(r.url)).netloc.lower().removeprefix("www.")
    return None


async def fetch_icon(client: httpx.AsyncClient, domain: str) -> bytes | None:
    for url in (f"https://www.google.com/s2/favicons?domain={domain}&sz=128", f"https://icons.duckduckgo.com/ip3/{domain}.ico"):
        try:
            r = await client.get(url, timeout=6)
        except httpx.HTTPError:
            continue
        if r.status_code == 200 and len(r.content) > 200:
            return r.content
    return None


async def company_logo(session: AsyncSession, company: Company) -> bytes | None:
    """PNG/ICO do logo ou None. Resultado (inclusive "não achei") fica em cache no storage."""
    storage = get_storage()
    key, miss = f"logos/{company.id}.img", f"logos/{company.id}.none"
    if storage.exists(key):
        return storage.get(key)
    if storage.exists(miss):
        return None
    domain = (company.domains or [None])[0] or (urlparse(company.website).netloc if company.website else None)
    domain = domain or seed_domains().get(company.normalized_name)
    async with httpx.AsyncClient(follow_redirects=True, headers=UA, transport=_transport) as client:
        if not domain:
            hq = (company.hq_location or "").lower()
            domain = await guess_domain(client, company.name, brazilian=not hq or "brasil" in hq)
        icon = await fetch_icon(client, domain) if domain else None
    if domain and not company.domains:
        company.domains = [domain]
        await session.commit()
    if icon is None:
        storage.put(miss, b"", "text/plain")
        return None
    storage.put(key, icon, "image/png")
    return icon


async def logo_by_name(session: AsyncSession, name: str) -> bytes | None:
    """Logo a partir só do nome (telas que não têm o id): empresa cadastrada → logo dela; senão domínio
    curado ou palpite estrito, em cache por nome. Não cria empresa."""
    from sqlalchemy import select

    norm = normalize_company(name)
    if not norm:
        return None
    company = await session.scalar(select(Company).where(Company.normalized_name == norm))
    if company is not None:
        return await company_logo(session, company)
    storage = get_storage()
    slug = re.sub(r"[^a-z0-9]+", "-", _ascii(norm)).strip("-")[:80] or "x"
    key, miss = f"logos/name-{slug}.img", f"logos/name-{slug}.none"
    if storage.exists(key):
        return storage.get(key)
    if storage.exists(miss):
        return None
    async with httpx.AsyncClient(follow_redirects=True, headers=UA, transport=_transport) as client:
        domain = seed_domains().get(norm) or await guess_domain(client, name, brazilian=True)
        icon = await fetch_icon(client, domain) if domain else None
    if icon is None:
        storage.put(miss, b"", "text/plain")
        return None
    storage.put(key, icon, "image/png")
    return icon
