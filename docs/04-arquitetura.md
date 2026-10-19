# 04 · Arquitetura

## 1. Visão de componentes

```
                         ┌──────────────────────────────────┐
                         │  Next.js (apps/web)              │
                         │  Dashboard · PWA                 │
                         └───────────────┬──────────────────┘
                                         │ REST + WebSocket (cookie de sessão)
┌────────────────────────────────────────▼──────────────────────────────────────┐
│ HOSPEDADO (VPS / Railway / Fly)                                               │
│                                                                               │
│  ┌─────────────────────┐   ┌───────────────────────┐   ┌───────────────────┐  │
│  │ tracker-api         │   │ tracker-worker        │   │ tracker-beat      │  │
│  │ FastAPI             │◄─►│ Celery workers        │◄──│ Celery Beat       │  │
│  │ REST, WS, webhooks  │   │ filas: default, ai,   │   │ agendamentos      │  │
│  │ gateway do agente   │   │ ingest, docs, batch   │   │                   │  │
│  └──────────┬──────────┘   └──────────┬────────────┘   └───────────────────┘  │
│             │                         │                                       │
│      ┌──────▼─────────────────────────▼──────┐   ┌─────────────────────────┐  │
│      │ PostgreSQL 16 + pgvector              │   │ Redis (broker, cache,   │  │
│      │                                       │   │ pub/sub para WS)        │  │
│      └───────────────────────────────────────┘   └─────────────────────────┘  │
│      ┌───────────────────────────────────────┐                                │
│      │ Object storage (S3/R2/MinIO) PDFs,    │                                │
│      │ snapshots, screenshots                │                                │
│      └───────────────────────────────────────┘                                │
└──────────────────────────────▲────────────────────────────────────────────────┘
                               │ WebSocket de saída, autenticado (token de dispositivo)
┌──────────────────────────────┴───────────────────┐
│ LOCAL (máquina do usuário)                       │
│  tracker-agent                                   │
│  Playwright + perfil persistente do Chromium     │
│  LinkedIn (busca, Easy Apply, mensagens)         │
│  ATS externos (preenchimento assistido)          │
└──────────────────────────────────────────────────┘

Externos: Claude API · Gmail API · Google Calendar API · Google Pub/Sub ·
          Telegram Bot API · Greenhouse/Lever/Ashby/Gupy (APIs públicas)
```

### Por que híbrido
- **Hospedado:** precisa estar no ar 24 h (Gmail push, agendamentos, Telegram, dashboard no celular).
- **Local:** o LinkedIn precisa da sessão real do usuário, do IP residencial e de um navegador comum. Rodar isso na nuvem aumenta muito o risco de bloqueio.
- **Modo 100% local** também é suportado: tudo no `docker compose` e Gmail por polling em vez de push.

## 2. Responsabilidades

| Componente | Responsabilidade |
|---|---|
| `tracker-api` | Autenticação, CRUD, regras de domínio síncronas, WebSocket para o dashboard, gateway do agente, webhooks (Pub/Sub do Gmail, Telegram) |
| `tracker-worker` | Ingestão de vagas, avaliação, geração de CV/PDF, classificação de e-mail, dossiês, calendário, notificações, batches |
| `tracker-beat` | Buscas salvas, polling do Gmail, renovação do `watch` do Gmail (a cada 6 dias), "sem retorno", follow-ups, resumo diário, relatório semanal, backups |
| `tracker-agent` | Executa *jobs de navegador* recebidos da API: buscar vagas, candidatar, ler mensagens, preencher ATS. Não decide nada de negócio sozinho; pergunta à API |
| `apps/web` | Interface; nenhuma regra de negócio |

### Filas do Celery
- `default`: tarefas rápidas
- `ai`: chamadas ao Claude (concorrência limitada para respeitar rate limits)
- `ingest`: Gmail e fontes de vagas
- `docs`: geração de PDF (LaTeX via tectonic, isolado em container)
- `batch`: envio e coleta de Message Batches

## 3. Estrutura do repositório

```
Application-Tracker/
├── README.md
├── CLAUDE.md
├── docs/
├── apps/
│   └── web/                         # Next.js
│       ├── app/
│       │   ├── (dashboard)/hoje/
│       │   ├── (dashboard)/vagas/
│       │   ├── (dashboard)/candidaturas/
│       │   ├── (dashboard)/curriculos/
│       │   ├── (dashboard)/entrevistas/
│       │   ├── (dashboard)/agenda/
│       │   ├── (dashboard)/pessoas/
│       │   ├── (dashboard)/insights/
│       │   └── (dashboard)/config/
│       ├── components/
│       ├── lib/api/                 # cliente gerado do OpenAPI
│       └── package.json
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   ├── src/tracker/
│   │   ├── main.py                  # app FastAPI
│   │   ├── core/                    # config, db, security, crypto, logging, audit, flags
│   │   ├── modules/
│   │   │   ├── profile/             # mestre, STAR, preferências, banco de respostas, bloqueios
│   │   │   ├── resumes/             # coringas, específicos, render, validador, ATS
│   │   │   ├── jobs/                # vagas, buscas, dedup, snapshots
│   │   │   ├── companies/           # perfis, sinais, watchlist
│   │   │   ├── scoring/             # filtros, notas, pesos, calibração
│   │   │   ├── applications/        # candidaturas, estados, eventos, fila, cota
│   │   │   ├── inbox/               # e-mails, mensagens, classificação, associação
│   │   │   ├── calendar/            # eventos, disponibilidade
│   │   │   ├── interviews/          # dossiês, simulação, pós-entrevista
│   │   │   ├── offers/              # propostas, CLT x PJ
│   │   │   ├── people/              # CRM
│   │   │   ├── notifications/       # Telegram, resumo diário
│   │   │   ├── analytics/           # funil, gaps, relatórios
│   │   │   └── agent_gateway/       # protocolo com o agente local
│   │   ├── integrations/
│   │   │   ├── claude/              # client.py, prompts/, schemas/, cost.py
│   │   │   ├── embeddings/
│   │   │   ├── google/              # oauth, gmail, calendar, pubsub
│   │   │   ├── telegram/
│   │   │   └── job_sources/         # greenhouse, lever, ashby, gupy
│   │   ├── workers/                 # celery_app.py, beat_schedule.py
│   │   └── agent/                   # tracker-agent (roda local)
│   │       ├── runner.py
│   │       ├── browser.py           # contexto persistente, ritmo humano
│   │       ├── safety.py            # detecção de captcha/aviso, kill switch
│   │       └── sites/
│   │           ├── linkedin/        # selectors.yaml, search.py, easy_apply.py, messages.py
│   │           ├── greenhouse/
│   │           ├── lever/
│   │           └── gupy/
│   └── tests/
│       ├── fixtures/                # HTML de páginas, e-mails de exemplo, vagas
│       ├── unit/
│       ├── integration/
│       └── evals/                   # avaliações dos prompts
├── templates/
│   └── resumes/
│       └── classic/                 # classic.sty + resume.tex.j2 (+ cover_letter.tex.j2)
├── data/                            # FORA DO GIT: master-profile.yaml (seed), cvs/, exports
├── infra/
│   ├── docker-compose.yml           # postgres, redis, minio, api, worker, beat
│   ├── docker-compose.prod.yml
│   └── Dockerfile.backend
├── .env.example
└── .github/workflows/ci.yml
```

## 4. Fluxos principais

### 4.1 Da vaga à fila
```
Beat → task run_saved_search
  → fonte API (Greenhouse/Lever/Ashby) roda no worker
  → fonte LinkedIn vira job "search" para o agente local
  → upsert_job (normaliza, dedup, snapshot)
  → evaluate_job (filtros → Chance → Atratividade → prioridade)
      → precisa de perfil de empresa? enqueue company_profile (cache)
  → select_resume (coringa ou "específico recomendado")
  → status "na_fila" ou "aguardando_aprovacao", conforme a policy
  → WS: dashboard atualizado; quadrante máximo → Telegram
```

### 4.2 Candidatura Easy Apply
```
Agente conecta → pede próximo job (respeitando cota e janela)
  → abre a vaga → confere "já candidatado?" → abre o modal
  → para cada etapa: extrai campos → POST /agent/resolve-fields
        API: banco de respostas → regras → Claude → pendente?
  → pendente: pausa, salva o estado, Telegram; aguarda resposta
  → tela final: modo revisão → aguarda aprovação | automático → envia
  → confirma o sucesso na página → POST /agent/applications/{id}/submitted (snapshot)
```

### 4.3 E-mail → status → agenda
```
Gmail push (Pub/Sub) → /webhooks/gmail → task sync_gmail(historyId)
  → pré-filtro → classify_email (Claude) → associar à candidatura
  → atualizar status + evento na linha do tempo
  → convite_entrevista com data → criar evento + dossiê + bloco de estudo
  → pedido_disponibilidade → freebusy → rascunho de resposta → Telegram
  → baixa confiança → pendência no dashboard
```

### 4.4 Dossiê
```
interview criada → task build_dossier
  → company_profile (cache ou pesquisa web)
  → snapshot da vaga + CV enviado + respostas + STAR
  → Claude (pesquisa web + síntese estruturada) → validar fontes → salvar
  → Telegram: "dossiê pronto"
```

## 5. Comunicação em tempo real
- O dashboard abre `WS /ws` e assina canais (`agent`, `applications`, `notifications`).
- Workers publicam no Redis pub/sub; a API repassa para o WS.
- O agente usa `WS /agent/ws` (canal separado, token de dispositivo).

## 6. Configuração

Variáveis principais (`.env.example`):

```
APP_ENV=dev
APP_BASE_URL=http://localhost:3000
API_BASE_URL=http://localhost:8000
SECRET_KEY=...
ENCRYPTION_KEY=...                  # 32 bytes base64, para tokens e cookies
AUTH_ALLOWED_EMAIL=...
USER_TIMEZONE=America/Sao_Paulo

DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
S3_ENDPOINT=... S3_BUCKET=... S3_ACCESS_KEY=... S3_SECRET_KEY=...

ANTHROPIC_API_KEY=...
AI_MONTHLY_BUDGET_USD=30
AI_MODEL_DEFAULT=claude-opus-5-5

GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=...
GOOGLE_PUBSUB_TOPIC=projects/<proj>/topics/gmail-tracker
GMAIL_ACCOUNT=...                   # conta que recebe os e-mails das candidaturas

TELEGRAM_BOT_TOKEN=... TELEGRAM_ALLOWED_CHAT_ID=...

AGENT_DEVICE_TOKEN=...
AGENT_PROFILE_DIR=~/.tracker-agent/chromium
SENTRY_DSN=
```

Configurações de negócio (limites, pesos, limiares, políticas) ficam no banco (`settings`), editáveis no dashboard, com padrões em código.
