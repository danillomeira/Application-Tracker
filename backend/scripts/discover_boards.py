"""Descobre e VERIFICA os job boards públicos das empresas que mais contratam em tecnologia.

Para cada empresa, testa slugs candidatos nos endpoints públicos (Greenhouse, Lever, Ashby,
SmartRecruiters, Workable, Gupy) e grava só os que respondem com vagas. Saída:
src/tracker/modules/jobs/seeds/companies.yaml

Uso: uv run python scripts/discover_boards.py
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import httpx
import yaml

OUT = Path(__file__).resolve().parents[1] / "src" / "tracker" / "modules" / "jobs" / "seeds" / "companies.yaml"
UA = {"User-Agent": "ApplicationTracker/0.1 (uso pessoal)"}

# (nome, região, slugs candidatos). Lista curada de grandes contratantes de tecnologia; editável.
BRAZIL = [
    ("Nubank", ["nubank"]),
    ("iFood", ["ifood", "ifoodcarreiras"]),
    ("Mercado Livre", ["mercadolivre", "mercadolibre"]),
    ("Itaú Unibanco", ["itau", "itauunibanco"]),
    ("XP Inc.", ["xpinc", "xp"]),
    ("BTG Pactual", ["btgpactual", "btg"]),
    ("Stone", ["stone", "stoneco"]),
    ("PagBank", ["pagbank", "pagseguro"]),
    ("PicPay", ["picpay"]),
    ("Banco Inter", ["inter", "bancointer"]),
    ("C6 Bank", ["c6bank"]),
    ("Neon", ["neon"]),
    ("Creditas", ["creditas"]),
    ("QuintoAndar", ["quintoandar"]),
    ("Loft", ["loft"]),
    ("Hotmart", ["hotmart"]),
    ("RD Station", ["rdstation", "resultadosdigitais"]),
    ("TOTVS", ["totvs"]),
    ("Localiza&Co", ["localiza"]),
    ("Ambev", ["ambev"]),
    ("Natura &Co", ["natura", "naturaco"]),
    ("Grupo Boticário", ["grupoboticario", "boticario"]),
    ("Magalu", ["magalu", "luizalabs"]),
    ("Grupo Casas Bahia", ["casasbahia", "via"]),
    ("Raízen", ["raizen"]),
    ("Vale", ["vale"]),
    ("Embraer", ["embraer"]),
    ("CI&T", ["ciandt", "cit"]),
    ("Stefanini", ["stefanini"]),
    ("Thoughtworks", ["thoughtworks"]),
    ("Zup Innovation", ["zup", "zupinnovation"]),
    ("Globo", ["globo"]),
    ("EBANX", ["ebanx"]),
    ("Cielo", ["cielo"]),
    ("Sicredi", ["sicredi"]),
    ("Unico", ["unico", "unicoidtech"]),
    ("Olist", ["olist"]),
    ("Wildlife Studios", ["wildlifestudios", "wildlife"]),
    ("VTEX", ["vtex"]),
    ("Contabilizei", ["contabilizei"]),
    ("Wellhub", ["gympass", "wellhub"]),
    ("Dock", ["dock", "dock.tech"]),
    ("Pismo", ["pismo"]),
    ("Cora", ["cora"]),
    ("Asaas", ["asaas"]),
    ("Vivo", ["vivo", "telefonica"]),
    ("Serasa Experian", ["serasaexperian", "serasa"]),
    ("Dasa", ["dasa"]),
    ("Afya", ["afya"]),
    ("Sympla", ["sympla"]),
    ("Conta Azul", ["contaazul"]),
    ("Méliuz", ["meliuz"]),
    ("Blip", ["blip", "take"]),
    ("Movile", ["movile"]),
    ("Arco Educação", ["arco", "arcoeducacao"]),
    ("CloudWalk", ["cloudwalk"]),
    ("Jusbrasil", ["jusbrasil"]),
    ("Gupy", ["gupy"]),
    ("Trybe", ["trybe", "betrybe"]),
    ("Alura", ["alura"]),
    ("Santander Brasil", ["santander", "santanderbrasil"]),
    ("Bradesco", ["bradesco", "vagasbradesco"]),
    ("Porto", ["porto", "portoseguro"]),
    ("SulAmérica", ["sulamerica"]),
    ("Gerdau", ["gerdau"]),
    ("WEG", ["weg"]),
    ("Suzano", ["suzano"]),
    ("Votorantim", ["votorantim"]),
    ("Lojas Renner", ["renner", "lojasrenner"]),
    ("Azzas 2154", ["arezzo", "azzas2154"]),
    ("Carrefour Brasil", ["carrefour", "grupocarrefourbrasil"]),
    ("Assaí", ["assai"]),
    ("GPA", ["gpa"]),
    ("Unilever Brasil", ["unilever"]),
    ("Nestlé Brasil", ["nestle"]),
    ("Rede D'Or", ["rededor"]),
    ("Hapvida NotreDame", ["hapvida"]),
    ("Einstein", ["einstein"]),
    ("CPFL", ["cpfl"]),
    ("Energisa", ["energisa"]),
    ("Neoenergia", ["neoenergia"]),
    ("Claro", ["claro"]),
    ("TIM Brasil", ["tim", "timbrasil"]),
    ("Compass UOL", ["compassuol", "compass"]),
    ("Softplan", ["softplan"]),
    ("Sankhya", ["sankhya"]),
    ("Senior Sistemas", ["senior", "seniorsistemas"]),
    ("Locaweb", ["locaweb"]),
    ("Zé Delivery", ["zedelivery", "ze"]),
    ("Quero Educação", ["queroeducacao"]),
    ("Tembici", ["tembici"]),
    ("Kovi", ["kovi"]),
    ("Capgemini Brasil", ["capgemini"]),
    ("NTT DATA Brasil", ["nttdata"]),
    ("Avanade", ["avanade"]),
    ("Accenture Brasil", ["accenture"]),
    ("Banco Pan", ["bancopan", "pan"]),
    ("Neoway", ["neoway"]),
    ("Ifood Benefícios", ["ifoodbeneficios"]),
    ("Bemobi", ["bemobi"]),
]
INTERNATIONAL = [
    ("Stripe", ["stripe"]),
    ("Airbnb", ["airbnb"]),
    ("Databricks", ["databricks"]),
    ("Snowflake", ["snowflake", "snowflakecomputing"]),
    ("Datadog", ["datadog"]),
    ("Cloudflare", ["cloudflare"]),
    ("GitLab", ["gitlab"]),
    ("Coinbase", ["coinbase"]),
    ("Robinhood", ["robinhood"]),
    ("Spotify", ["spotify"]),
    ("Palantir", ["palantir"]),
    ("Plaid", ["plaid"]),
    ("Figma", ["figma"]),
    ("Notion", ["notion"]),
    ("OpenAI", ["openai"]),
    ("Anthropic", ["anthropic"]),
    ("Ramp", ["ramp"]),
    ("Deel", ["deel"]),
    ("Remote", ["remote", "remotecom"]),
    ("Canonical", ["canonical"]),
    ("Elastic", ["elastic"]),
    ("MongoDB", ["mongodb"]),
    ("Confluent", ["confluent"]),
    ("dbt Labs", ["dbtlabsinc", "dbtlabs"]),
    ("Grafana Labs", ["grafanalabs"]),
    ("HashiCorp", ["hashicorp"]),
    ("Twilio", ["twilio"]),
    ("Okta", ["okta"]),
    ("Zapier", ["zapier"]),
    ("DoorDash", ["doordash", "doordashusa"]),
    ("Instacart", ["instacart"]),
    ("Lyft", ["lyft"]),
    ("Pinterest", ["pinterest"]),
    ("Reddit", ["reddit"]),
    ("Discord", ["discord"]),
    ("Duolingo", ["duolingo"]),
    ("Asana", ["asana"]),
    ("Dropbox", ["dropbox"]),
    ("Airtable", ["airtable"]),
    ("Brex", ["brex"]),
    ("Gusto", ["gusto"]),
    ("Rippling", ["rippling"]),
    ("Vercel", ["vercel"]),
    ("Supabase", ["supabase"]),
    ("Hugging Face", ["huggingface"]),
    ("Bosch", ["BoschGroup"]),
    ("Toptal", ["toptal"]),
    ("Automattic", ["automattic"]),
    ("Wikimedia", ["wikimedia"]),
    ("Sentry", ["sentry"]),
    ("PostHog", ["posthog"]),
    ("Linear", ["linear"]),
    ("Retool", ["retool"]),
    ("Scale AI", ["scaleai"]),
    ("Samsara", ["samsara"]),
    ("Affirm", ["affirm"]),
    ("Chime", ["chime"]),
    ("SoFi", ["sofi"]),
    ("Nuro", ["nuro"]),
]


async def check(client: httpx.AsyncClient, ats: str, slug: str) -> int:
    try:
        if ats == "greenhouse":
            r = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
            return len(r.json().get("jobs", [])) if r.status_code == 200 else 0
        if ats == "lever":
            r = await client.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
            return len(r.json()) if r.status_code == 200 and isinstance(r.json(), list) else 0
        if ats == "ashby":
            r = await client.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
            return len(r.json().get("jobs", [])) if r.status_code == 200 else 0
        if ats == "smartrecruiters":
            r = await client.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 1})
            return int(r.json().get("totalFound", 0)) if r.status_code == 200 else 0
        if ats == "workable":
            r = await client.get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
            return len(r.json().get("jobs", [])) if r.status_code == 200 else 0
        if ats == "gupy":
            r = await client.get(f"https://{slug}.gupy.io/")
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S) if r.status_code == 200 else None
            if not m:
                return 0
            return len(json.loads(m.group(1)).get("props", {}).get("pageProps", {}).get("jobs") or [])
    except Exception:
        return 0
    return 0


ATS_ORDER = ["greenhouse", "lever", "ashby", "workable", "smartrecruiters", "gupy"]


async def discover(name: str, slugs: list[str], region: str, client: httpx.AsyncClient, sem: asyncio.Semaphore) -> dict | None:
    order = ["gupy", *[a for a in ATS_ORDER if a != "gupy"]] if region == "BR" else ATS_ORDER
    async with sem:
        for ats in order:
            for slug in slugs:
                n = await check(client, ats, slug)
                if n > 0:
                    return {"name": name, "region": region, "ats_kind": ats, "ats_board_token": slug, "open_jobs_at_discovery": n}
    return {"name": name, "region": region, "ats_kind": None, "ats_board_token": None, "open_jobs_at_discovery": 0}


async def main() -> None:
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=20, headers=UA, follow_redirects=True) as client:
        tasks = [discover(n, s, "BR", client, sem) for n, s in BRAZIL] + [
            discover(n, s, "INTL", client, sem) for n, s in INTERNATIONAL
        ]
        results = [r for r in await asyncio.gather(*tasks) if r]
    found = [r for r in results if r["ats_kind"]]
    missing = [r["name"] for r in results if not r["ats_kind"]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "# Gerado por scripts/discover_boards.py: boards públicos VERIFICADOS (responderam com vagas).\n"
        "# Empresas sem board público detectado ficam em `no_public_board` (use a extensão ao navegar no site delas).\n"
        + yaml.safe_dump({"companies": found, "no_public_board": missing}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    br = sum(1 for r in found if r["region"] == "BR")
    print(f"verificadas: {len(found)} (BR {br}, fora {len(found) - br}); sem board público: {len(missing)}")
    print("sem board:", ", ".join(missing))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
