# 18 · Glossário

> **Nota (F10, ADR-020):** o robô local (`tracker-agent`, Playwright) foi removido. Trechos que citam robô, agente local, Easy Apply automático ou kill switch são históricos. A candidatura é feita pelo usuário com o assistente do navegador ([09](09-motor-candidatura.md)); vagas do LinkedIn chegam por alertas no Gmail e pela importação na extensão.

| Termo | Significado |
|---|---|
| **Agente local** | Processo `tracker-agent` na máquina do usuário que controla o navegador (Playwright) |
| **ATS** | Applicant Tracking System: Gupy, Greenhouse, Lever, Workday etc. |
| **Atratividade** | Nota 0–100 do quanto vale trabalhar na empresa/vaga |
| **Banco de respostas** | Respostas canônicas para perguntas de formulário, reutilizadas entre candidaturas |
| **Chance** | Nota 0–100 da probabilidade de resposta e avanço no processo |
| **Coringa** | Currículo derivado do mestre para um perfil de vaga recorrente (`wildcard`) |
| **CV específico** | Currículo gerado para uma vaga (`tailored`) |
| **Dossiê** | Material de preparação para uma entrevista |
| **Dry run** | Execução completa do robô sem clicar em enviar |
| **Easy Apply** | "Candidatura simplificada" do LinkedIn, feita dentro de um modal |
| **Effort** | Parâmetro da Claude API que controla a profundidade de raciocínio e o gasto de tokens |
| **Fantasma (vaga)** | Vaga publicada sem intenção real de contratação (repostada, antiga, genérica) |
| **Filtro eliminatório** | Regra que descarta a vaga antes da avaliação |
| **Ghosted / sem retorno** | Candidatura sem resposta após N dias |
| **Kill switch** | Comando que para o agente imediatamente |
| **Mestre** | Currículo mestre: fonte única de verdade sobre o usuário |
| **Pendência** | Algo que precisa de decisão humana (pergunta, aprovação, e-mail ambíguo, evento em rascunho) |
| **Política de automação** | Configuração do que pode rodar sozinho e do que exige revisão |
| **Quadrante** | `top`, `bet`, `volume`, `discard`: combinação de Chance e Atratividade |
| **Render** | PDF gerado de uma variante, imutável e com hash |
| **Snapshot** | Cópia imutável da vaga (ou do que foi enviado) em um momento |
| **STAR** | Situação, Tarefa, Ação, Resultado: formato de história para entrevistas comportamentais |
| **Validador de fatos** | Checagem determinística de que o conteúdo gerado só usa fatos do mestre |
| **Watchlist** | Empresas dos sonhos monitoradas com alerta imediato |
