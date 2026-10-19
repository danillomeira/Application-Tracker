"""tracker-agent: robô local (docs/09). Uso:

tracker-agent login        # abre o navegador para você entrar no LinkedIn (uma vez)
tracker-agent run          # processa a fila (Ctrl+C ou kill switch para parar)
tracker-agent run --once   # processa uma tarefa e sai
tracker-agent check        # testa a conexão com a API
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import random
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, async_playwright

from tracker.agent.api import AgentApi, HttpAgentApi
from tracker.agent.human import Pace
from tracker.agent.sites.ats import assisted
from tracker.agent.sites.linkedin import easy_apply, messages, search
from tracker.agent.sites.linkedin.easy_apply import SELECTORS, StopJob

VERSION = "0.1.0"
log = logging.getLogger("tracker.agent")


class Killed(Exception):
    pass


@contextlib.asynccontextmanager
async def browser(profile_dir: str, headless: bool) -> AsyncIterator[BrowserContext]:
    """Contexto persistente com a sessão real do usuário. Sem spoofing de UA/fingerprint."""
    path = Path(os.path.expanduser(profile_dir))  # noqa: ASYNC240 (uma vez, na inicialização)
    path.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
    os.chmod(path, 0o700)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(path), headless=headless, viewport=None, locale="pt-BR", timezone_id="America/Sao_Paulo"
        )
        try:
            yield ctx
        finally:
            await ctx.close()


async def _heartbeat(api: AgentApi, job_id: str, task: asyncio.Task[Any], interval: float = 2.0) -> None:
    """Kill switch em ≤ 5 s (RF-CAN-11): o heartbeat cancela a tarefa ao receber `kill`."""
    while not task.done():
        await asyncio.sleep(interval)
        try:
            if (await api.heartbeat(job_id)).get("kill"):
                task.cancel("kill switch")
                return
        except Exception as exc:
            log.warning("heartbeat falhou: %s", exc)


async def handle(ctx: BrowserContext, job: dict[str, Any], api: AgentApi, pace: Pace, cfg: dict[str, Any]) -> Any:
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    kind = job["kind"]
    if kind == "apply":
        return await easy_apply.run(page, job, api, pace, cfg.get("follow_company", False))
    if kind == "search":
        return await search.run(page, job, api, pace)
    if kind == "read_messages":
        return await messages.run(page, job, api, pace)
    if kind == "fill_external":
        tab = await ctx.new_page()  # aba fica aberta para o usuário revisar e enviar
        return await assisted.run(tab, job, api, pace)
    await api.fail(job["id"], f"tipo desconhecido: {kind}")
    return None


async def run_once(ctx: BrowserContext, api: AgentApi, pace: Pace, cfg: dict[str, Any]) -> dict[str, Any] | None:
    r = await api.next_job()
    if "job" not in r:
        return r
    job = r["job"]
    log.info("tarefa %s (%s)", job["id"], job["kind"])
    task = asyncio.create_task(handle(ctx, job, api, pace, cfg))
    hb = asyncio.create_task(_heartbeat(api, job["id"], task))
    try:
        result = await task
        return {"job": job, "result": result}
    except asyncio.CancelledError:
        log.warning("tarefa interrompida pelo kill switch")
        return {"job": job, "killed": True}
    except StopJob as exc:
        return {"job": job, "stopped": str(exc)}
    except Exception as exc:
        log.exception("erro na tarefa")
        with contextlib.suppress(Exception):
            await api.fail(job["id"], f"{type(exc).__name__}: {exc}"[:900])
        return {"job": job, "error": str(exc)}
    finally:
        hb.cancel()


async def loop(api: AgentApi, profile_dir: str, headless: bool, once: bool) -> None:
    hello = await api.hello(VERSION, ["linkedin", "greenhouse", "lever", "gupy"])
    limits = hello["limits"]
    pace = Pace(tuple(limits["action_delay_s"]))  # type: ignore[arg-type]
    cfg = {"follow_company": False}
    applied_since_pause = 0
    async with browser(profile_dir, headless) as ctx:
        while True:
            out = await run_once(ctx, api, pace, cfg)
            if once:
                return
            if out and "wait" in out:
                log.info("aguardando: %s", out["wait"])
                await asyncio.sleep(float(out.get("retry_in", 60)))
                continue
            if out and out.get("stopped") in ("captcha", "checkpoint", "login", "warning"):
                log.error("parada de segurança (%s). Resolva manualmente e libere pelo dashboard.", out["stopped"])
                await asyncio.sleep(300)
                continue
            if out and out.get("job", {}).get("kind") == "apply":
                applied_since_pause += 1
                if applied_since_pause >= int(limits["long_pause_every"]):
                    applied_since_pause = 0
                    lo, hi = limits["long_pause_min"]
                    await asyncio.sleep(random.uniform(lo, hi) * 60)  # noqa: S311
                else:
                    lo, hi = limits["between_applications_s"]
                    await pace.pause(lo, hi)


async def login(api: AgentApi, profile_dir: str) -> None:
    async with browser(profile_dir, headless=False) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(SELECTORS["login_url"])
        print("Entre no LinkedIn na janela aberta (inclusive 2FA). Aguardando o feed carregar...")
        await page.wait_for_url("**/feed/**", timeout=600_000)
        await api.login_ok()
        print("Sessão salva no perfil do navegador. Pode fechar.")


def main(argv: list[str] | None = None) -> None:
    from tracker.core.config import get_settings

    parser = argparse.ArgumentParser(prog="tracker-agent")
    parser.add_argument("command", choices=["login", "run", "check"])
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--headless", action="store_true", help="não recomendado para o LinkedIn")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = get_settings()
    api = HttpAgentApi(s.agent_api_url, s.agent_device_token)
    if args.command == "check":
        r = asyncio.run(api.hello(VERSION, ["linkedin"]))
        print("API OK. Bloqueio:", r.get("blocked") or "nenhum", "| dry run:", r.get("dry_run"))
        return
    if args.command == "login":
        asyncio.run(login(api, s.agent_profile_dir))
        return
    try:
        asyncio.run(loop(api, s.agent_profile_dir, args.headless, args.once))
    except KeyboardInterrupt:
        print("\nAgente encerrado.")
        sys.exit(0)


if __name__ == "__main__":
    main()
