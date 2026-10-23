# 09 · Motor de candidatura (Easy Apply)

## 1. Visão geral

```
API (decide)                                   Agente local (executa)
────────────                                   ──────────────────────
fila priorizada + cota + janela ── job.assign ──► abre a vaga
                                                  já candidatado? → aborta
                                                  abre o modal Easy Apply
                                ◄─ fields.resolve ─ extrai campos da etapa
resolve: banco → regra → IA → pendente
                                ── fields.resolved ► preenche, anexa CV, avança
   (pendente) → Telegram/dashboard ── job.resume ──► continua do checkpoint
                                ◄── review.ready ── tela "Revisar candidatura"
modo revisão: espera aprovação
modo auto: checa política
                                ─ review.approved ► clica "Enviar"
                                ◄─ job.submitted ── confirma sucesso + evidência
grava snapshot imutável
```

## 2. Agente local

### Navegador
- Playwright (Python) com **contexto persistente** do Chromium em `AGENT_PROFILE_DIR`. O login é feito pelo usuário uma vez (`tracker-agent login linkedin`).
- **Janela visível** (headed) por padrão. No WSL2, usar WSLg; testar na F0. Alternativa: rodar o agente no Windows nativo (Python + Playwright para Windows).
- Um único navegador, uma única aba de trabalho, sem paralelismo.
- User agent, viewport e fuso **reais** da máquina. Nada de spoofing.

### Ritmo humano (`agent/browser.py`)
- Intervalos log-normais entre ações (2–7 s) e entre candidaturas (45–180 s)
- Digitação com atraso por caractere (40–120 ms) em campos de texto
- Rolagem até o elemento antes de clicar
- Pausa longa a cada N candidaturas
- Limites diários em `daily_quota`, verificados antes de cada ação

### Segurança (`agent/safety.py`)
Antes e depois de cada ação, verificar:
| Sinal | Ação |
|---|---|
| Captcha / "verificação de segurança" / checkpoint | `safety.stop`, notificação imediata |
| Página de login (sessão expirou) | `safety.stop`, pedir login manual |
| Aviso de uso incomum / restrição | `safety.stop` + **pausar o módulo por 72 h** + alerta |
| Layout desconhecido (seletor crítico ausente) | tentar o fallback por IA (§6) em modo revisão; se falhar, `safety.stop` |
| Erro HTTP 429 / página de erro | parar, aplicar backoff de horas |
| Kill switch | parar em ≤ 5 s, salvar checkpoint |

Em todo `safety.stop`: screenshot, HTML, trace do Playwright, URL → `agent_job.artifacts`.

## 3. Percorrendo o modal

1. Abrir a URL da vaga. Se aparecer "Candidatura enviada" / "Applied", marcar `submitted` (reconciliação) e encerrar.
2. Clicar em "Candidatura simplificada" / "Easy Apply".
3. Para cada etapa:
   - **Extrair campos** pela árvore de acessibilidade: rótulo, tipo (text, number, select, radio, checkbox, textarea, file, date, typeahead), opções, obrigatório, valor atual, mensagem de erro.
   - Enviar `fields.resolve`. Receber valores ou `pause`.
   - Preencher. Campos que o LinkedIn já preencheu com dados do perfil (e-mail, telefone): manter se baterem com o mestre; senão, corrigir.
   - **Currículo:** selecionar o PDF existente ou fazer upload do `resume_render` escolhido. Conferir que o nome do arquivo anexado bate.
   - Clicar "Avançar"/"Next"/"Revisar". Se aparecer um erro de validação, reenviar só os campos com erro para a resolução (máx. 2 tentativas) e depois pausar.
   - Salvar o checkpoint (`agent_job.state`) e um screenshot da etapa.
4. Na tela de revisão: desmarcar "Seguir empresa" (configurável), `review.ready`.
5. Após a aprovação: "Enviar candidatura". Esperar a confirmação, capturar evidência e fechar o diálogo.

## 4. Resolução de perguntas

Ordem (a primeira que resolver com confiança suficiente vence):

1. **Campos de perfil**: nome, e-mail, telefone, cidade, LinkedIn, GitHub, portfólio → direto do mestre.
2. **Banco de respostas, correspondência exata**: pergunta normalizada (minúsculas, sem acentos e pontuação) igual a `canonical_question` ou a um alias, respeitando `conditions` (idioma da vaga, regime).
3. **Banco de respostas, semântica**: similaridade de embedding ≥ 0,90 com o mesmo `field_kind`. Opções de select/radio mapeadas por similaridade de texto; se mais de uma opção puder corresponder, deixar pendente para revisão.
4. **Regras determinísticas** (`apply/rules.py`):
   - "Quantos anos de experiência com X?" → soma dos períodos das experiências que usam a skill X (pelo mestre), arredondada para baixo. Se X não estiver no mestre → **0** (nunca inventar), e a vaga recebe flag de gap
   - "Você fala inglês/espanhol?" → `languages` do mestre
   - "Pretensão salarial" → `preference.min_salary` + regra de margem por regime/moeda (**nunca IA**)
   - "Disponível para começar?" → banco de respostas
   - "Concorda com..." (termos, políticas de privacidade) → padrão configurável, inicialmente pendente na primeira vez
5. **IA** (`apply.answer`) para perguntas abertas e de múltipla escolha não cobertas. Resultado com `confidence`.
6. **Pendente**: confiança abaixo do limiar, pergunta sensível ou campo desconhecido.

Perguntas **sensíveis** (sempre banco ou pendência, nunca IA): salário, autorização de trabalho/visto, patrocínio, deficiência, raça, gênero, orientação, antecedentes, dados de documentos.

### Pergunta pendente
- A candidatura vai para `needs_input`, o agente salva o checkpoint e **passa para a próxima vaga da fila** (não fica parado).
- Notificação no Telegram: empresa, cargo, pergunta, opções (botões quando houver ≤ 6), sugestão da IA.
- Ao responder: escolher "salvar no banco" (padrão) ou "só desta vez". A candidatura volta para a fila com prioridade.
- Pendências expiram em 72 h (configurável) → candidatura vai para `skipped` com motivo.

## 5. Políticas (`automation_policy`)
```yaml
easy_apply:
  mode: review                # review | auto
  auto:
    min_quadrant: top         # top | top_or_volume
    min_chance: 70
    min_answer_confidence: 0.9
    allow_tailored_resume: false   # CV específico sempre exige revisão
    max_per_day: 10           # dentro da cota geral
  follow_company: false
  dry_run: false
external_apply:
  mode: assisted              # sempre revisão
email:
  send: never                 # só rascunhos, imutável
linkedin_messages:
  send: never                 # só rascunhos, imutável
```
`email.send` e `linkedin_messages.send` não podem ser alterados para outro valor (validação no backend).

## 6. Fallback por IA para layout desconhecido
Quando um seletor crítico falha:
1. Capturar a árvore de acessibilidade (`page.accessibility.snapshot()`) da área do modal.
2. `apply.map_fields` devolve o mapeamento campo → localizador (role + nome).
3. Executar com os localizadores retornados, em **modo revisão obrigatório** para aquela candidatura.
4. Registrar o mapeamento como sugestão de atualização do `selectors.yaml` (para revisão humana no repositório).

## 7. Candidaturas externas (F6)
- `apply_kind = external`: o sistema monta o pacote (CV, carta, respostas para as perguntas conhecidas do ATS, checklist).
- Para Greenhouse e Lever: o detalhe da vaga via API pública traz as perguntas do formulário, o que permite preparar todas as respostas antes.
- Preenchimento assistido no agente (mesmo motor de resolução, adaptadores por site em `agent/sites/<ats>/`), **sempre em revisão**, com o usuário clicando em enviar.
- Contas em ATS (Gupy, Workday) são do usuário; o agente não cria contas.

## 8. Testes do motor
- **Fixtures HTML** de cada tipo de etapa do Easy Apply (`tests/fixtures/linkedin/easy_apply/*.html`) servidas localmente; o Playwright roda contra elas no CI.
- Casos: etapa de contato, upload de CV, perguntas com select/radio/texto/número, typeahead de cidade, erro de validação, tela de revisão, sucesso, captcha, logout, layout alterado.
- Testes de resolução de perguntas com o banco de respostas e a IA fake.
- `dry_run` obrigatório nas primeiras 10 candidaturas reais após qualquer mudança de seletor.
