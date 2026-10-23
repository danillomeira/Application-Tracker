# 17 · Questões em aberto

> **Nota (F10, ADR-020):** o robô local (`tracker-agent`, Playwright) foi removido. Trechos que citam robô, agente local, Easy Apply automático ou kill switch são históricos. A candidatura é feita pelo usuário com o assistente do navegador ([09](09-motor-candidatura.md)); vagas do LinkedIn chegam por alertas no Gmail e pela importação na extensão.

Cada questão tem um **padrão assumido**: a IA que implementa pode seguir com ele se a questão ainda estiver aberta, avisando o usuário.

## Respondidas
| # | Questão | Resposta |
|---|---|---|
| Q-02 | Provedor de IA | Claude (Anthropic): API ou Claude Code local (ADR-017) |
| Q-03 | Formato dos currículos | LaTeX, estilo `classic` em `templates/resumes/classic/` (ADR-008) |
| Q-21 | Para quem é o app? | Qualquer candidato: nada pessoal no código; o currículo entra pelo onboarding (PDF do LinkedIn/CV) e os padrões (bloqueios, respostas) derivam dele |
| Q-22 | Sistemas suportados | Windows, macOS, Linux e WSL (worker em threads, comandos `tracker-init`/`tracker-dev` multiplataforma) |

Dados pessoais de quem usa (contas, histórico profissional, salários) **nunca** entram neste arquivo nem no código: ficam no banco ou em `data/` (fora do git).

## Abertas
| # | Questão | Padrão assumido |
|---|---|---|
| Q-06 | Nível de automação do Easy Apply: só revisão ou modo automático também? | Revisão; automático só na F7 e mediante ativação explícita |
| Q-07 | Onde roda: híbrido (VPS + agente local) ou 100% local no início? | 100% local na F0–F2; híbrido a partir da F3 (Gmail push e Telegram) |
| Q-08 | Vagas internacionais (EN, USD/EUR, fuso) ou só Brasil? | Ambas; PT e EN desde a F1 |
| Q-09 | Critérios pessoais: salário mínimo CLT/PJ, modelo de trabalho, setores preferidos/evitados | Preenchidos no onboarding (salário opcional); nenhum setor evitado por padrão |
| Q-16 | Coringas: os 4–5 propostos em `11-curriculos.md` §4 estão bons? | Começar com `data-engineer`, `ai-ml-engineer`, `software-engineer-backend` |
| Q-17 | Lista de empresas monitoradas e watchlist inicial | 100 empresas verificadas (opcional no fim do onboarding); o usuário adiciona outras |
| Q-18 | Empresas bloqueadas por padrão | O(s) empregador(es) atual(is) do currículo, derivados automaticamente; editável |
