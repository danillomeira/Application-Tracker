"""Pontos de entrada: tracker-api, tracker-worker, tracker-beat."""

from __future__ import annotations

import os
import sys


def run_api() -> None:
    import uvicorn

    uvicorn.run(
        "tracker.main:app",
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8000")),
        reload="--reload" in sys.argv,
    )


def run_worker() -> None:
    from tracker.workers.celery_app import celery_app

    queues = os.environ.get("WORKER_QUEUES", "default,ai,ingest,docs,batch")
    # Threads, não prefork: o modelo de embeddings (~2 GB) é carregado UMA vez por processo. Com prefork cada filho
    # carregava o seu e 4 filhos estouravam a memória do WSL. As tarefas são quase só I/O (HTTP, banco, `claude -p`)
    # e cada uma abre o próprio engine (NullPool), então threads são seguras.
    from tracker.core.config import get_settings

    concurrency = get_settings().worker_concurrency
    celery_app.worker_main(["worker", "--loglevel=INFO", f"--queues={queues}", f"--concurrency={concurrency}", "--pool=threads"])


def run_beat() -> None:
    from tracker.workers.celery_app import celery_app

    celery_app.start(["beat", "--loglevel=INFO"])


def run_seed() -> None:
    """tracker-seed [caminho.yaml]: dados base (template de CV, pesos de avaliação).

    Com um YAML de currículo mestre (opcional, para quem prefere arquivo), também importa o mestre e cria os
    padrões derivados dele. Sem YAML, o currículo entra pelo onboarding do dashboard.
    """
    import asyncio
    from pathlib import Path

    from tracker.core.config import REPO_ROOT
    from tracker.core.db import dispose_engine, get_sessionmaker
    from tracker.modules.profile import service
    from tracker.modules.resumes.service import ensure_template
    from tracker.modules.scoring.service import current_weights

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "data" / "master-profile.yaml"

    async def main() -> None:
        async with get_sessionmaker()() as s:
            await ensure_template(s)
            await current_weights(s)
            if path.exists():
                master = service.load_yaml(path)
                current = await service.current_version(s)
                if current is not None and current.data == master.model_dump(mode="json"):
                    print(f"Mestre já está atualizado (versão {current.version}).")
                else:
                    row = await service.save_master(s, master, "seed_yaml", f"importado de {path.name}")
                    print(f"Currículo mestre importado: versão {row.version}.")
                print(f"Padrões: {await service.seed_defaults(s, master)}")
            else:
                print("Dados base criados. Abra o dashboard: o onboarding pede o seu currículo (PDF do LinkedIn ou CV).")
            await s.commit()
        await dispose_engine()

    asyncio.run(main())


def run_init() -> None:
    """tracker-init: cria o .env a partir do .env.example com segredos aleatórios (Linux, macOS e Windows)."""
    import base64
    import secrets

    from tracker.core.config import REPO_ROOT

    env, example = REPO_ROOT / ".env", REPO_ROOT / ".env.example"
    if env.exists() and "--force" not in sys.argv:
        print(f"{env} já existe (use --force para recriar). Nada foi alterado.")
        return
    generated = {
        "SECRET_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
        "AGENT_DEVICE_TOKEN": secrets.token_urlsafe(32),
        "GMAIL_PUSH_SECRET": secrets.token_urlsafe(24),
        "TELEGRAM_WEBHOOK_SECRET": secrets.token_urlsafe(24),
    }
    email = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--email=")), "")
    lines = []
    for line in example.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0].strip()
        if key in generated and not line.lstrip().startswith("#"):
            line = f"{key}={generated[key]}"
        elif key == "AUTH_ALLOWED_EMAIL" and email:
            line = f"AUTH_ALLOWED_EMAIL={email}"
        lines.append(line)
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Criado {env} com segredos aleatórios. Próximo passo: preencha AUTH_ALLOWED_EMAIL (seu e-mail) se ainda não fez.")


def run_dev() -> None:
    """tracker-dev: sobe API, worker e agendador juntos (Ctrl+C encerra os três). Funciona em Linux, macOS e Windows."""
    import signal
    import subprocess
    import time

    procs = {
        name: subprocess.Popen([sys.executable, "-c", f"from tracker.cli import {fn}; {fn}()"])  # noqa: S603
        for name, fn in (("api", "run_api"), ("worker", "run_worker"), ("beat", "run_beat"))
    }
    print("API em http://localhost:8000 · worker · agendador. Ctrl+C para parar.")
    try:
        while all(p.poll() is None for p in procs.values()):
            time.sleep(1)
        dead = [n for n, p in procs.items() if p.poll() is not None]
        print(f"Processo encerrado: {', '.join(dead)}. Parando os demais.")
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs.values():
            if p.poll() is None:
                if os.name == "nt":
                    p.terminate()  # Windows: sem SIGINT entre processos
                else:
                    p.send_signal(signal.SIGINT)
        for p in procs.values():
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()
