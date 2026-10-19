"""Logos de empresas: domínio curado, palpite estrito (sem marca errada) e cache."""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

from tracker.modules.companies import logos
from tracker.modules.companies.service import get_or_create

PNG = b"\x89PNG" + b"0" * 400


@pytest.fixture
def web():
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        calls.append(url)
        if "s2/favicons" in url:
            return httpx.Response(200 if "nubank.com.br" in url or "globex.com" in url else 404, content=PNG)
        if req.url.host == "blip.com.br":  # o site redireciona para outra marca
            return httpx.Response(302, headers={"location": "https://www.disney.com/"})
        if req.url.host == "www.disney.com":
            return httpx.Response(200, text="disney")
        if req.url.host == "globex.com":
            return httpx.Response(200, text="globex")
        return httpx.Response(404)

    logos.set_transport(httpx.MockTransport(handler))
    yield calls
    logos.set_transport(None)


def test_plausible_rejects_other_brands() -> None:
    assert logos.plausible("https://www.btgpactual.com/", "BTG Pactual")
    assert logos.plausible("https://inter.co/", "Banco Inter")
    assert not logos.plausible("https://www.disney.com/", "Blip")
    assert not logos.plausible("https://www.facebook.com/", "DoorDash")


async def test_logo_from_seed_domain_cached(client: AsyncClient, session, web) -> None:
    c = await get_or_create(session, "Nubank")
    await session.commit()
    r = await client.get(f"/api/v1/companies/{c.id}/logo")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    await session.refresh(c)
    assert c.domains == ["nubank.com.br"]  # curado no seed
    n = len(web)
    assert (await client.get(f"/api/v1/companies/{c.id}/logo")).status_code == 200
    assert len(web) == n  # segunda vez vem do cache, sem rede


async def test_guess_is_strict_and_misses_are_cached(client: AsyncClient, session, web) -> None:
    blip = await get_or_create(session, "Blipzz")
    globex = await get_or_create(session, "Globex")
    blip.hq_location, globex.hq_location = "Internacional", "Internacional"
    await session.commit()
    assert (await client.get(f"/api/v1/companies/{globex.id}/logo")).status_code == 200
    assert (await client.get(f"/api/v1/companies/{blip.id}/logo")).status_code == 404
    n = len(web)
    assert (await client.get(f"/api/v1/companies/{blip.id}/logo")).status_code == 404
    assert len(web) == n  # "não achei" também fica em cache


async def test_logo_by_name_without_company_record(client: AsyncClient, session, web) -> None:
    r = await client.get("/api/v1/companies/logo", params={"name": "Nubank"})  # curado no seed, sem cadastro
    assert r.status_code == 200
    assert (await client.get("/api/v1/companies/logo", params={"name": "Empresa Inexistente XYZ"})).status_code == 404
    c = await get_or_create(session, "Globex")
    c.hq_location = "Internacional"
    await session.commit()
    assert (await client.get("/api/v1/companies/logo", params={"name": "Globex"})).status_code == 200  # usa a empresa
