# 01 · Visão do produto

> **Nota (F10, ADR-020):** o robô local (`tracker-agent`, Playwright) foi removido. Trechos que citam robô, agente local, Easy Apply automático ou kill switch são históricos. A candidatura é feita pelo usuário com o assistente do navegador ([09](09-motor-candidatura.md)); vagas do LinkedIn chegam por alertas no Gmail e pela importação na extensão.

## 1. Problema

Procurar emprego bem feito toma um tempo enorme e é repetitivo:
- Achar vagas relevantes em várias fontes e descartar as ruins
- Adaptar o currículo para cada vaga
- Responder as mesmas perguntas em formulários diferentes (anos de experiência, pretensão, disponibilidade)
- Lembrar onde você se candidatou, com qual CV e o que respondeu
- Vigiar e-mail e LinkedIn para não perder um convite
- Combinar horários e montar a agenda
- Pesquisar empresa, vaga e valores antes de cada entrevista

Sem um sistema, você acaba aplicando em massa sem critério (baixa taxa de resposta) ou aplicando pouco (baixo volume). E perde oportunidades por falta de acompanhamento.

## 2. Solução

Um assistente pessoal que cobre o ciclo inteiro, **da vaga à oferta**. Ele automatiza o repetitivo, prioriza onde vale gastar esforço e deixa você decidir o que importa.

## 3. Usuário

Usuário único: o dono do sistema, um desenvolvedor procurando vagas de tecnologia no Brasil e possivelmente no exterior, com experiência em Next.js e Python. Não há multi-tenant nem cadastro público.

## 4. Objetivos

| # | Objetivo | Medida |
|---|---|---|
| O1 | Reduzir o tempo por candidatura | < 2 min de atenção humana por candidatura (meta: < 30 s no modo revisão com respostas conhecidas) |
| O2 | Aumentar a taxa de resposta | Taxa de resposta positiva maior que a sua média anterior, acompanhada por currículo e por quadrante de prioridade |
| O3 | Nunca perder um retorno | 100% dos e-mails de recrutamento classificados e ligados a uma candidatura em até 15 min |
| O4 | Chegar preparado | Dossiê pronto até 24 h antes de toda entrevista detectada |
| O5 | Visibilidade total | Funil, status e próximas ações em uma tela |

## 5. Não objetivos

- Ser um produto multiusuário ou SaaS
- Contornar proteções anti-bot de qualquer site
- Enviar e-mails ou mensagens automaticamente sem revisão
- Inventar ou "embelezar" experiência que o usuário não tem
- Substituir a preparação técnica (estudar algoritmos, system design). O sistema sugere o que estudar, mas não ensina

## 6. Escopo por área

| Área | No escopo |
|---|---|
| Perfil | Currículo mestre PT/EN, importação de PDF do LinkedIn e CVs, banco de histórias STAR, banco de respostas, preferências, lista de bloqueio, cofre de documentos |
| Currículos | Templates LaTeX (estilo `classic`), coringas por stack, CV específico sob demanda, carta de apresentação, checagem ATS, versionamento |
| Vagas | Buscas salvas, LinkedIn, Greenhouse, Lever, Ashby, Gupy, importação por URL ou texto, deduplicação, snapshot, watchlist de empresas dos sonhos |
| Avaliação | Filtros eliminatórios, nota de Chance, nota de Atratividade, prioridade, explicações, calibração com dados próprios |
| Candidatura | Easy Apply assistido e automático, pacote para candidaturas externas, fila de revisão, perguntas pendentes, limites e kill switch |
| Acompanhamento | Gmail, mensagens do LinkedIn, classificação, status automático, follow-ups, CRM de recrutadores |
| Agenda | Detecção de convite, sugestão de horários, rascunho de resposta, evento, bloco de estudo, prazos de testes técnicos |
| Entrevista | Dossiê, simulação, registro pós-entrevista, agradecimento |
| Oferta | Comparador CLT/PJ, referência salarial, roteiro de negociação, prazo de resposta |
| Aprendizado | Métricas, desempenho por CV, gaps de skills, plano de estudo, análise de rejeições, relatório semanal, otimização do perfil do LinkedIn |
| Plataforma | Dashboard web, notificações no Telegram, custo de IA, auditoria, backup, exportação |

## 7. Jornada completa

```
Onboarding ─ importa perfil e CVs → currículo mestre (PT/EN) → coringas → banco de respostas
           → preferências e filtros → lista de bloqueio → conecta Google, LinkedIn e Telegram
     │
Descoberta ─ buscas salvas (agendadas) → LinkedIn + Greenhouse/Lever/Ashby + Gupy + URL manual
           → normalização → deduplicação → snapshot → watchlist dispara alerta
     │
Avaliação ─ filtros eliminatórios → Chance + Atratividade → prioridade → ação sugerida
     │
Preparação ─ coringa ou CV específico → validador de fatos → checagem ATS → carta → recrutador
     │
Candidatura ─ Easy Apply: robô local etapa por etapa → pergunta nova → Telegram → banco de respostas
            ─ Externa: pacote pronto + preenchimento assistido → você confirma "enviei"
            ─ registro imutável do que foi enviado
     │
Acompanhamento ─ Gmail + LinkedIn → classificação → status → sem resposta? follow-up sugerido
     │
Agendamento ─ convite → horários livres → rascunho → confirmação → evento + bloco de estudo
     │
Entrevista ─ dossiê → simulação → entrevista → registro pós → rascunho de agradecimento
     │
Oferta ─ comparador CLT/PJ → referência salarial → negociação → decisão
     │
Aprendizado ─ desempenho por CV · gaps de skills · análise de rejeições · relatório semanal
```

## 8. Métricas de sucesso do produto

- Candidaturas por semana (total e por quadrante de prioridade)
- Taxa de resposta (qualquer retorno) e taxa de resposta positiva (entrevista ou teste)
- Conversão entrevista → próxima etapa → oferta
- Tempo médio até a primeira resposta, por empresa
- Tempo humano gasto por candidatura
- Taxa de perguntas resolvidas pelo banco de respostas sem intervenção
- Custo de IA por candidatura e por mês
- Incidentes no LinkedIn (captcha, avisos): meta zero
