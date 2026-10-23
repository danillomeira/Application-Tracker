# 16 · Riscos

> **Nota (F10, ADR-020):** o robô local (`tracker-agent`, Playwright) foi removido. Trechos que citam robô, agente local, Easy Apply automático ou kill switch são históricos. A candidatura é feita pelo usuário com o assistente do navegador ([09](09-motor-candidatura.md)); vagas do LinkedIn chegam por alertas no Gmail e pela importação na extensão.

| # | Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|---|
| R1 | Restrição ou banimento da conta do LinkedIn | Média | **Crítico** | Modo revisão padrão; limites baixos; ritmo humano; sessão real; parada em qualquer sinal com pausa de 72 h; aceite explícito; F1–F4 entregam valor sem automação |
| R2 | LinkedIn muda o layout e o robô quebra | Alta | Médio | Seletores isolados por papel/rótulo; fallback por IA em modo revisão; screenshots; dry run após mudanças; testes com fixtures |
| R3 | IA inventa ou distorce fatos no CV/respostas | Média | Alto | Validador determinístico; `used_facts`; perguntas sensíveis fora da IA; revisão de CV específico |
| R4 | E-mail mal classificado (perde convite) | Baixa | Alto | Pré-filtro amplo; limiar de confiança → pendência; resumo diário de "não classificados de ATS"; evals |
| R5 | Token do Google expira/desconecta | Média | Médio | App publicado (não "Testing"); saúde das integrações; alerta no Telegram; polling de fallback |
| R6 | Custo de IA acima do esperado | Média | Baixo | Orçamento com bloqueio; cache; batches; effort por tarefa; painel de custo |
| R7 | Prompt injection via e-mail ou vaga | Baixa | Médio | Conteúdo delimitado; enums; nenhuma ação crítica decidida só pela IA |
| R8 | Computador desligado → Easy Apply parado | Alta | Baixo | Esperado; fila persiste; resumo mostra o atraso |
| R9 | Candidatura duplicada ou enviada para a empresa errada | Baixa | Alto | Checagem no banco + na página; confirmação de empresa/cargo na tela de revisão; snapshot |
| R10 | Excesso de volume prejudica a imagem com recrutadores | Média | Médio | Prioridade por quadrante; cooldown por empresa; limite por empresa por mês (padrão 2 vagas) |
| R11 | Vazamento de dados pessoais | Baixa | Alto | `data/` fora do git; gitleaks; criptografia; storage privado |
| R12 | Desgaste do usuário (burnout de busca) | Média | Médio | Metas saudáveis; resumo em vez de alertas constantes; horas de silêncio |
| R13 | Afirmações do CV contestadas em entrevista (ex.: anos de experiência) | Média | Alto | Validador emite alerta de consistência; dossiê inclui "pontos a defender com evidência" |
