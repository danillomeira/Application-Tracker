# 03 · Requisitos não funcionais

## Desempenho
- **RNF-01** Dashboard: telas principais carregam em < 1,5 s com 5.000 vagas e 1.000 candidaturas no banco.
- **RNF-02** Listas paginadas por cursor; nenhum endpoint retorna mais de 200 itens por página.
- **RNF-03** E-mail novo classificado e ligado à candidatura em até 15 min (meta: 2 min com push).
- **RNF-04** Geração de CV específico em < 90 s (IA + PDF + validação).
- **RNF-05** Dossiê de entrevista em < 10 min (tarefa assíncrona com progresso).
- **RNF-06** Kill switch interrompe o agente em ≤ 5 s.

## Confiabilidade
- **RNF-07** Toda tarefa assíncrona é idempotente (chave de idempotência por operação) e pode ser reexecutada com segurança.
- **RNF-08** Retentativa com backoff exponencial e jitter para APIs externas; após N falhas, a tarefa vai para uma fila de erro visível no dashboard.
- **RNF-09** O agente local persiste o estado de cada candidatura por etapa e retoma depois de uma queda sem duplicar envio.
- **RNF-10** Nenhuma candidatura é enviada duas vezes: verificação no banco + verificação na página ("Candidatura enviada") antes de enviar.
- **RNF-11** Ingestão do Gmail sem perda: guarda o último `historyId` processado; em caso de lacuna, faz ressincronização completa da janela.
- **RNF-12** Backup diário com teste de restauração mensal.

## Segurança (detalhes em `12-seguranca-privacidade.md`)
- **RNF-13** Tokens OAuth, cookies de sessão e chaves de API criptografados em repouso (AES-256-GCM via chave mestre em variável de ambiente).
- **RNF-14** Escopos OAuth mínimos; um escopo novo exige ADR.
- **RNF-15** Agente local sem portas de entrada: conexão de saída autenticada com a API (token de dispositivo, rotacionável).
- **RNF-16** Conteúdo vindo de e-mails, vagas e páginas é **dado não confiável**: entra nos prompts delimitado e nunca é tratado como instrução (defesa contra prompt injection).
- **RNF-17** HTML de vagas e e-mails sanitizado antes de renderizar no frontend.

## Custo
- **RNF-18** Orçamento mensal de IA configurável com alertas em 50%, 80% e 100%.
- **RNF-19** Cache de resultados de IA por hash de entrada (perfil de empresa: 30–60 dias; avaliação de vaga: até mudar o mestre ou os pesos).
- **RNF-20** Prompt caching nos prefixos estáveis (currículo mestre, instruções, banco de respostas).
- **RNF-21** Tarefas sem urgência (reavaliar vagas em massa, recalcular coringas, relatórios) via Message Batches API.
- **RNF-22** Infraestrutura hospedada barata: uma VPS pequena (2 vCPU, 4 GB) ou plano equivalente deve bastar.

## Usabilidade
- **RNF-23** Interface em pt-BR; conteúdo gerado em PT ou EN conforme a vaga.
- **RNF-24** Toda decisão automática mostra o porquê em até um clique.
- **RNF-25** Ações principais (aprovar, responder pendência) funcionam no celular.
- **RNF-26** Acessibilidade: navegação por teclado, contraste AA, rótulos em formulários.
- **RNF-27** Modo claro e escuro.

## Manutenibilidade
- **RNF-28** Seletores do LinkedIn e dos ATS isolados em arquivos de configuração versionados por site (`agent/sites/<site>/selectors.yaml`), sem seletor espalhado pelo código.
- **RNF-29** Prompts versionados em arquivos (`integrations/claude/prompts/<tarefa>/v<N>.md`), com a versão registrada em cada chamada.
- **RNF-30** Cobertura de testes ≥ 80% nos módulos de domínio (scoring, validador de fatos, máquina de estados, banco de respostas).
- **RNF-31** Toda integração externa atrás de uma interface com implementação fake para testes.

## Observabilidade
- **RNF-32** Logs estruturados em JSON com `request_id`, `task_id`, `application_id`.
- **RNF-33** Métricas: tarefas por estado, latência das integrações, custo de IA, erros do agente.
- **RNF-34** Erros do agente com screenshot, HTML e trace do Playwright anexados ao incidente.
- **RNF-35** Sentry (ou similar) opcional via variável de ambiente.

## Conformidade
- **RNF-36** Dados pessoais de terceiros (recrutadores, entrevistadores) restritos a dados profissionais públicos ou recebidos em comunicação direta; exclusão sob demanda.
- **RNF-37** Retenção configurável de e-mails brutos (padrão: guardar só metadados + trecho relevante; corpo completo por 90 dias).
