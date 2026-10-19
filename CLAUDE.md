# CLAUDE.md: instruções para a IA que implementa este projeto

Este arquivo é lido primeiro por qualquer agente de IA que trabalhe neste repositório. A especificação completa está em `docs/`. **Leia antes de codar:**

1. `docs/01-visao-produto.md`: o porquê
2. `docs/14-roadmap.md`: em que fase estamos e o que entra nela
3. Os documentos específicos do módulo que você vai mexer (veja o mapa abaixo)

## Mapa: módulo → documentos

| Vai mexer em | Leia |
|---|---|
| Qualquer coisa | `02-requisitos-funcionais.md` (seção do módulo), `03-requisitos-nao-funcionais.md`, `05-modelo-de-dados.md` |
| Currículos | `11-curriculos.md`, `08-ia-claude.md` |
| Vagas e avaliação | `10-motor-avaliacao.md`, `07-integracoes.md` |
| Robô de candidatura | `09-motor-candidatura.md`, `12-seguranca-privacidade.md` |
| Gmail / Calendar / Telegram | `07-integracoes.md`, `12-seguranca-privacidade.md` |
| Qualquer chamada ao Claude | `08-ia-claude.md` |
| Endpoints / frontend | `06-api.md`, `04-arquitetura.md` |

## Regras inegociáveis

1. **Nada sai em nome do usuário sem política.** Candidaturas, e-mails e mensagens só são enviados se `automation_policy` permitir. E-mails e mensagens no LinkedIn **nunca** são enviados automaticamente: só rascunhos.
2. **Sem alucinação de currículo.** Todo CV ou resposta gerado passa pelo validador determinístico de fatos (`11-curriculos.md` §6). Skill, empresa, cargo, data ou métrica fora do currículo mestre faz a geração falhar.
3. **Nunca contornar proteções.** Captcha, verificação, 2FA ou aviso de atividade incomum fazem o robô **parar**, salvar o estado e notificar. Nada de solvers de captcha, rotação de IP, fingerprint spoofing ou contas extras.
4. **Segredos fora do código.** Só via variáveis de ambiente. Tokens OAuth e cookies criptografados em repouso (`12-seguranca-privacidade.md`).
5. **Tudo explicável.** Notas, classificações e decisões automáticas guardam `reasons` e `sources`.
6. **Snapshot do que foi enviado.** Cada candidatura guarda a versão exata do CV (PDF + hash), as respostas e a descrição da vaga no momento do envio. Registros enviados são imutáveis.

## Convenções de código

### Backend (Python)
- Python 3.12, gerenciador `uv`, layout `backend/src/tracker/`
- FastAPI + SQLAlchemy 2 (async, estilo `Mapped[...]`) + Alembic + Pydantic v2
- Celery + Redis para tarefas assíncronas e agendadas
- Lint e format com `ruff`, tipos com `pyright` (modo strict nos módulos de domínio)
- Testes com `pytest` + `pytest-asyncio`. Banco real via testcontainers ou Postgres do compose; não use mock do ORM
- Organização por módulo de domínio (`modules/<nome>/{models,schemas,service,router,tasks}.py`). Integrações externas ficam em `integrations/`, atrás de uma interface, para poder usar fakes nos testes
- Toda chamada ao Claude passa por `integrations/claude/client.py` (wrapper único com log de custo, retry, fallback de refusal e cache). Nunca chame o SDK direto de um módulo
- Saídas de IA sempre estruturadas com Pydantic + `client.messages.parse()` (ver `08-ia-claude.md`)
- Datas em UTC no banco; fuso do usuário (`America/Sao_Paulo` por padrão) só na apresentação

### Frontend (TypeScript)
- Next.js App Router em `apps/web`, `pnpm`, TypeScript strict
- Tailwind + shadcn/ui, TanStack Query para dados do servidor
- Tipos da API gerados do OpenAPI do FastAPI (`openapi-typescript`). Não escreva tipos de API à mão
- Interface em **pt-BR**
- Componentes de servidor por padrão; cliente só quando precisa de interação

### Geral
- Commits no padrão Conventional Commits (`feat(resumes): ...`)
- Toda feature referencia os IDs de requisito (RF-xxx/RNF-xxx) no PR
- Migrações Alembic revisadas; nunca editar uma migração já aplicada

## Definição de pronto (vale para toda tarefa)

- [ ] Critérios de aceite do RF atendidos
- [ ] Testes unitários e de integração do caminho feliz e dos erros principais
- [ ] `ruff`, `pyright`, `pnpm lint` e `pnpm typecheck` limpos
- [ ] Migração criada, se mudou o schema
- [ ] Ações automáticas com log de auditoria
- [ ] Chamadas de IA com schema, validação e custo registrado
- [ ] Documentação em `docs/` atualizada se o comportamento mudou

## Como trabalhar

- Siga a ordem das fases do roadmap. Não implemente uma fase futura sem pedido explícito.
- Antes de uma tarefa grande, confira `docs/17-questoes-abertas.md`. Se uma questão bloquear o trabalho, use o padrão assumido que está lá e avise.
- Ao tomar uma decisão de arquitetura nova, registre um ADR em `docs/15-decisoes.md`.
- Para o robô do LinkedIn, desenvolva e teste contra **fixtures HTML locais** (`backend/tests/fixtures/linkedin/`), nunca contra o site real em testes automatizados.
