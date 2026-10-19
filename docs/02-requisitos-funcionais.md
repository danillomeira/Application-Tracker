# 02 · Requisitos funcionais

Formato: **ID**, descrição, **Prioridade** (M = obrigatório, S = importante, C = desejável), **Fase** do roadmap e **Aceite** (critérios verificáveis).

Prefixos: `PER` perfil · `CV` currículos · `VAG` vagas · `AVA` avaliação · `CAN` candidatura Easy Apply · `EXT` candidatura externa · `ACO` acompanhamento · `AGE` agenda · `ENT` entrevista · `OFE` oferta · `REL` relacionamento · `NOT` notificações · `DSH` dashboard · `ANA` aprendizado · `PLA` plataforma.

---

## PER · Perfil e onboarding

**RF-PER-01** Assistente de onboarding em etapas: importar, revisar perfil, preferências, banco de respostas, conexões. · M · F1
Aceite: dá para parar e retomar; cada etapa mostra progresso; ao final o sistema está apto a gerar coringas.

**RF-PER-02** Importar o PDF do perfil do LinkedIn ("Salvar como PDF") e CVs existentes (PDF/DOCX). A IA extrai os dados para o formato do currículo mestre. · M · F1
Aceite: experiências, formação, skills, idiomas e certificações extraídas para revisão; nada é salvo sem confirmação; campos de baixa confiança aparecem destacados.

**RF-PER-03** Importar repositórios públicos do GitHub (nome, descrição, linguagens, estrelas, README) como projetos candidatos do currículo mestre. · C · F7

**RF-PER-04** Currículo mestre estruturado (ver `11-curriculos.md`), com edição na interface e versionamento. · M · F1
Aceite: toda alteração gera nova versão; dá para comparar versões; os coringas indicam de qual versão do mestre derivam.

**RF-PER-05** Currículo mestre bilíngue (PT-BR e EN). A tradução é gerada por IA e revisada pelo usuário. · M · F1

**RF-PER-06** Banco de histórias **STAR** ligadas às experiências do mestre (situação, tarefa, ação, resultado, skills demonstradas). · S · F4
Aceite: cada história tem tags de competência (liderança, conflito, entrega, falha...) e é usada no dossiê e nas respostas abertas.

**RF-PER-07** Preferências de busca: cargos, senioridade, stacks, modelo de trabalho (remoto/híbrido/presencial), cidades aceitas, regime (CLT/PJ/ambos), salário mínimo por regime e moeda, setores preferidos e evitados, tamanho de empresa, idiomas, disponibilidade para viagem ou mudança. · M · F1

**RF-PER-08** Banco de respostas (ver `09-motor-candidatura.md` §4) com respostas canônicas, variações por idioma e regras por contexto (ex.: pretensão diferente para CLT e PJ). · M · F1

**RF-PER-09** Lista de bloqueio: empresas (incluindo a atual), domínios, recrutadoras e palavras-chave. · M · F2
Aceite: vaga que bate com a lista nunca entra na fila de candidatura e aparece como "bloqueada (motivo)".

**RF-PER-10** Cofre de documentos: diplomas, certificados, portfólio, carta de recomendação, documentos pedidos em processos. · C · F6

**RF-PER-11** Lista de referências profissionais (nome, relação, contato, consentimento, última vez usada). · C · F6

---

## CV · Currículos

**RF-CV-01** Templates de currículo em **LaTeX** (Jinja2 + pdflatex/tectonic). No mínimo: (a) **`classic`**, uma coluna, compatível com ATS, já implementado em `templates/resumes/classic/`; (b) variações do `classic` (ex.: uma página, sem projetos) para vagas que pedem CV curto. · M · F1
Aceite: o PDF gerado pelo template a partir do mestre fica visualmente equivalente ao PDF de referência.

**RF-CV-02** Currículos coringa: 3 a 6 perfis (ex.: Backend Python, Fullstack Next/Python, Dados/IA), cada um com foco, resumo, ordem e seleção de experiências e skills. Gerados por IA a partir do mestre e revisados. · M · F1
Aceite: cada coringa existe em PT e EN, tem PDF gerado e passa no validador de fatos e na checagem ATS.

**RF-CV-03** Escolha automática do CV por vaga: compara a vaga com cada coringa (similaridade semântica + cobertura de keywords obrigatórias). · M · F2
Aceite: guarda a nota de cada coringa e o motivo da escolha; usa o coringa se a nota ≥ `resume.match_threshold` (padrão 0,75); senão marca "CV específico recomendado".

**RF-CV-04** CV específico: gerado a partir do mestre para uma vaga, reordenando, reescrevendo bullets com as palavras da vaga e enfatizando experiências relevantes. · M · F1
Aceite: diff visível em relação ao coringa mais próximo; passa no validador de fatos; aprovação manual configurável (`resume.tailored_requires_approval`, padrão true).

**RF-CV-05** Validador determinístico de fatos: toda skill, empresa, cargo, data, formação e métrica do CV gerado precisa existir no mestre. · M · F1
Aceite: violação bloqueia o CV e mostra o trecho problemático; sinônimos são aceitos por um mapa de aliases ("Postgres" = "PostgreSQL").

**RF-CV-06** Checagem ATS: extrai o texto do PDF gerado (pypdf) e verifica se seções, datas, contato e keywords foram extraídos corretamente; mede a cobertura de keywords da vaga. · S · F1

**RF-CV-07** Carta de apresentação curta (≤ 150 palavras) por vaga, quando o formulário tiver campo para isso ou a vaga pedir. · S · F2

**RF-CV-08** Versionamento: todo PDF gerado tem hash SHA-256, data, versão do mestre e template. Candidaturas apontam para a versão exata. · M · F1

**RF-CV-09** Detecção do idioma da vaga para escolher o CV em PT ou EN. · M · F2

**RF-CV-10** Sugestão de novos coringas: se N vagas de alta prioridade num cluster semântico tiverem baixa aderência aos coringas existentes, sugere criar um novo. · C · F7

---

## VAG · Vagas

**RF-VAG-01** Buscas salvas com termos, filtros (localidade, remoto, senioridade, data de publicação, Easy Apply) e fontes, executadas com agenda própria (padrão: 2x por dia em horário comercial). · M · F2

**RF-VAG-02** Fonte LinkedIn via agente local (Playwright), com ritmo humano e limites (ver `07-integracoes.md`). · M · F5
Nota: até a F5, vagas do LinkedIn entram por URL colada (RF-VAG-05).

**RF-VAG-03** Fontes Greenhouse, Lever e Ashby via API pública dos job boards, para uma lista de empresas monitoradas. · M · F2

**RF-VAG-04** Fonte Gupy (vagas públicas da empresa) para empresas monitoradas. · S · F6

**RF-VAG-05** Importar vaga por URL ou por texto colado. A IA extrai os dados estruturados. · M · F2

**RF-VAG-06** Normalização: título, empresa, localidade, modelo de trabalho, regime, senioridade, faixa salarial, requisitos obrigatórios e desejáveis, benefícios, idioma, tipo de candidatura (Easy Apply / externa / e-mail), data de publicação, número de candidatos. · M · F2

**RF-VAG-07** Deduplicação entre fontes e reposts (empresa normalizada + título normalizado + similaridade de descrição ≥ 0,92). · M · F2
Aceite: mantém um registro canônico com todas as fontes; contabiliza reposts (sinal de vaga fantasma).

**RF-VAG-08** Snapshot imutável da descrição (texto + HTML sanitizado) no momento da coleta e no momento da candidatura. · M · F2
Por quê: vagas somem do ar e o dossiê de entrevista precisa da descrição original.

**RF-VAG-09** Watchlist de empresas dos sonhos: alerta imediato quando abre vaga compatível. · S · F2

**RF-VAG-10** Detecção de vaga encerrada (ex.: "não aceita mais candidaturas") para tirar da fila. · S · F5

---

## AVA · Avaliação (ver `10-motor-avaliacao.md`)

**RF-AVA-01** Filtros eliminatórios configuráveis. · M · F2
**RF-AVA-02** Nota de **Chance** (0–100) com critérios ponderados e explicação. · M · F2
**RF-AVA-03** Nota de **Atratividade** (0–100) com critérios ponderados, explicação e fontes. · M · F2 (básica) / F4 (perfil de empresa completo)
**RF-AVA-04** Matriz de prioridade em 4 quadrantes, com ação sugerida por quadrante. · M · F2
**RF-AVA-05** Pesos editáveis na interface (sliders), com versão. · S · F2
**RF-AVA-06** Perfil de empresa com reputação, saúde e cultura, coletado por pesquisa web do Claude, com cache de 30 a 60 dias. · S · F4
**RF-AVA-07** Responsividade da empresa por suavização bayesiana com dados próprios e públicos, mostrando o grau de confiança. · S · F7
**RF-AVA-08** Calibração automática dos pesos (regressão logística) a partir de ~100 candidaturas com desfecho, com aprovação do usuário. · C · F7
**RF-AVA-09** Feedback manual ("boa vaga", "não quero", motivo) alimenta a calibração. · S · F2
**RF-AVA-10** Recalcular notas quando mudam o mestre, os pesos ou o perfil da empresa. · M · F2

---

## CAN · Candidatura Easy Apply (ver `09-motor-candidatura.md`)

**RF-CAN-01** Fila de candidatura ordenada por prioridade, respeitando a cota diária. · M · F5
**RF-CAN-02** Agente local com Playwright e perfil de navegador persistente com a sessão do usuário. · M · F5
**RF-CAN-03** Percorrer o modal etapa por etapa: detectar campos, preencher, anexar CV, avançar e revisar. · M · F5
**RF-CAN-04** Resolver cada pergunta na ordem: banco de respostas → regra determinística → IA com confiança → pendência para o usuário. · M · F5
**RF-CAN-05** Pergunta pendente pausa a candidatura sem perder o estado e notifica no Telegram com botões de resposta rápida, quando aplicável. · M · F5
**RF-CAN-06** A resposta do usuário vira entrada nova no banco de respostas (com opção "só desta vez"). · M · F5
**RF-CAN-07** Modo revisão: a candidatura para na tela final; o usuário aprova no dashboard (individual ou em lote) e o agente envia. · M · F5
**RF-CAN-08** Modo automático: envia sem revisão se a prioridade ≥ limiar, todas as respostas tiverem confiança ≥ limiar e a cota permitir. · S · F7
**RF-CAN-09** Limites: cota diária (padrão 20), janela de horário (padrão 09h–19h, dias úteis), intervalo aleatório entre ações e entre candidaturas, pausa longa a cada N candidaturas. · M · F5
**RF-CAN-10** Parada de segurança: captcha, verificação, aviso, logout ou erro inesperado → para tudo, salva screenshot e HTML, notifica. · M · F5
**RF-CAN-11** Kill switch no dashboard e no Telegram (`/stop`), que interrompe o agente em até 5 s. · M · F5
**RF-CAN-12** Modo simulação (dry run): faz tudo, menos clicar em enviar. · M · F5
**RF-CAN-13** Registro imutável: CV (versão + hash), todas as perguntas e respostas, screenshots de cada etapa, horário, descrição da vaga. · M · F5
**RF-CAN-14** Transmissão ao vivo do agente para o dashboard (etapa atual, screenshot, log). · S · F5
**RF-CAN-15** Fallback por IA para leitura de tela: se um seletor falhar, envia um snapshot da árvore de acessibilidade ao Claude para mapear os campos; em seguida exige revisão. · S · F5
**RF-CAN-16** Desistência: marcar candidatura como retirada, com motivo. · C · F6

---

## EXT · Candidatura externa

**RF-EXT-01** Classificar o tipo de candidatura (Easy Apply / ATS externo / e-mail) e o ATS de destino (Gupy, Workday, Greenhouse, Lever, Ashby, SmartRecruiters, Inhire, Solides, outro). · M · F2
**RF-EXT-02** Pacote de candidatura: CV escolhido, carta, respostas sugeridas para as perguntas comuns, link e checklist. · M · F6
**RF-EXT-03** Preenchimento assistido em ATS conhecidos (começando por Greenhouse, Lever e Gupy) no agente local, sempre em modo revisão. · S · F6
**RF-EXT-04** Botão "enviei" para registrar candidaturas feitas manualmente, com upload opcional do comprovante. · M · F2
**RF-EXT-05** Candidatura por e-mail: rascunho no Gmail com CV anexado. · C · F6

---

## NAV · Assistente no navegador (extensão)

Alternativa ao robô para candidaturas fora do Easy Apply: roda **na sessão normal do navegador do usuário**, sem automação de clique e sem envio.

**RF-NAV-01** Extensão Chrome/Edge (MV3) em `apps/extension`, autenticada por token próprio (`Authorization: Extension <token>`, só o SHA-256 fica salvo) gerado em Configurações. · M · F8
**RF-NAV-02** Painel lateral em páginas de vaga: cartão com Chance, Atratividade, reputação, responsividade da empresa (se costuma chamar para entrevista) e status da candidatura. Vaga conhecida não gasta IA; vaga nova é analisada só no clique (ou automaticamente em ATS conhecidos), com cache de 90 dias. · M · F8
**RF-NAV-03** Detecção dos campos do formulário (inputs, selects, radios, upload) e preenchimento pelo resolvedor determinístico: perfil → banco de respostas → regras → IA em lote (uma chamada por formulário). Anexa o CV escolhido. Perguntas sensíveis (salário, visto, dados pessoais protegidos) nunca vão para a IA e ficam para o usuário. · M · F8
**RF-NAV-04** Sugestão ao focar um campo não preenchido ("💡 … Usar / ✨ IA"); IA só quando o usuário pede. · S · F8
**RF-NAV-05** Aprendizado: respostas digitadas pelo usuário entram no banco de respostas. · S · F8
**RF-NAV-06** Detecção de envio (submit + página de sucesso, inclusive LinkedIn) e registro automático da candidatura (canal `assisted`) com as respostas usadas. Botão manual "Marquei como enviada". · M · F8
**RF-NAV-07** A extensão **nunca** envia formulários, nunca resolve captcha e respeita a lista de domínios ignorados. · M · F8

## FON · Fontes públicas de vagas

**RF-FON-01** Coleta por API pública de ATS: Greenhouse, Lever, Ashby, SmartRecruiters, Workable e Gupy (por subdomínio). · M · F8
**RF-FON-02** Seed de 100 empresas com job board público verificado (48 no Brasil, 52 fora), em `modules/jobs/seeds/companies.yaml`, gerado por `scripts/discover_boards.py`. · S · F8
**RF-FON-03** Sites de vagas agregados: Remotive, RemoteOK, Himalayas, Jobicy, Arbeitnow, We Work Remotely e Working Nomads, como fonte `boards` das buscas salvas. · S · F8
**RF-FON-04** Pré-filtro de relevância sem IA (cargos-alvo, palavras, senioridade) antes de ingerir boards grandes. · M · F8

## INB · Organização do Gmail

**RF-INB-01** Marcadores `Vagas/*` (Confirmação, Rejeição, Entrevista, Teste técnico, Oferta, Pedido de informação, Recrutador, LinkedIn) aplicados conforme a classificação. Exige o escopo `gmail.modify`, usado só para marcadores; desligável pela flag `gmail_labels`. · S · F8

---

## ACO · Acompanhamento

**RF-ACO-01** Conexão Gmail via OAuth (escopos em `07-integracoes.md`). · M · F3
**RF-ACO-02** Ingestão incremental de e-mails (Gmail `history` + push via Pub/Sub; polling de 5 min como fallback). · M · F3
**RF-ACO-03** Pré-filtro barato (remetente de ATS conhecido, domínio de empresa com candidatura, palavras-chave) antes da IA. · M · F3
**RF-ACO-04** Classificação: `confirmacao`, `rejeicao`, `convite_entrevista`, `pedido_disponibilidade`, `teste_tecnico`, `oferta`, `pedido_info`, `recrutador_prospeccao`, `notificacao_linkedin`, `irrelevante`. Extrai também datas, links, pessoas e prazos. · M · F3
**RF-ACO-05** Associação e-mail → candidatura por domínio, nome da empresa, cargo, ATS e thread. Se ambígua, vira pendência para o usuário escolher. · M · F3
**RF-ACO-06** Atualização automática de status conforme a classificação, com registro de evento e motivo; o usuário pode desfazer. · M · F3
**RF-ACO-07** "Sem retorno" automático após `tracking.ghost_after_days` (padrão 21) sem resposta. · M · F3
**RF-ACO-08** Sugestão de follow-up após `tracking.followup_after_days` (padrão 7–10), com rascunho de e-mail ou mensagem. · S · F6
**RF-ACO-09** Mensagens do LinkedIn: a partir de notificações no Gmail, o agente local lê as conversas novas (somente leitura) e classifica como os e-mails. · S · F6
**RF-ACO-10** Prospecção ativa: recrutador que te procura sem candidatura vira oportunidade nova no kanban. · S · F3
**RF-ACO-11** Linha do tempo por candidatura com todos os eventos (coleta, nota, envio, e-mails, mensagens, entrevistas, notas pessoais). · M · F2

---

## AGE · Agenda

**RF-AGE-01** Conexão Google Calendar via OAuth. · M · F3
**RF-AGE-02** Convite com data definida → evento criado com título padrão, link da call, entrevistadores, link do dossiê e lembretes (1 dia e 1 hora antes). · M · F3
**RF-AGE-03** Pedido de disponibilidade → busca horários livres (freebusy) nas janelas preferidas e redige uma resposta com 3 opções, como **rascunho** no Gmail. · M · F3
**RF-AGE-04** Link de agendamento (Calendly, Google Appointment, etc.) → sugere horários e lembra de agendar; o evento é criado ao chegar a confirmação. · S · F3
**RF-AGE-05** Checagem de conflitos antes de sugerir ou criar um evento. · M · F3
**RF-AGE-06** Fuso horário: converter horários de vagas internacionais e mostrar os dois fusos. · M · F3
**RF-AGE-07** Bloco de estudo automático antes da entrevista (padrão 60 min, no dia anterior), com o dossiê. · S · F4
**RF-AGE-08** Prazo de teste técnico vira evento com lembretes (padrão 48 h e 24 h antes). · M · F3
**RF-AGE-09** Data ambígua ou baixa confiança → evento em rascunho para confirmação no dashboard. · M · F3
**RF-AGE-10** Remarcação e cancelamento detectados por e-mail atualizam ou removem o evento. · S · F3

---

## ENT · Entrevista

**RF-ENT-01** Dossiê gerado automaticamente quando a entrevista é detectada (ou sob demanda). · M · F4
Conteúdo mínimo:
1. Resumo da vaga: responsabilidades, requisitos obrigatórios e desejáveis, o que o time provavelmente valoriza
2. Seu match: requisito → experiência e história STAR para citar; gaps e como abordá-los com honestidade
3. Empresa: história, produto, modelo de negócio, clientes, concorrentes, stack conhecida, notícias recentes (12 meses)
4. Missão e valores, cada um ligado a algo da sua trajetória
5. Entrevistadores (se informados): cargo e tempo de casa, só com dados públicos e profissionais
6. Perguntas prováveis técnicas e comportamentais, com esboço de resposta
7. Perguntas para fazer
8. Logística: horário (dois fusos), link, duração, formato, o que levar
9. Fontes com link e data
Aceite: toda afirmação factual sobre a empresa tem fonte; o dossiê aponta para o CV e as respostas enviados.

**RF-ENT-02** Página de cola de uma página (versão resumida do dossiê, imprimível). · S · F4
**RF-ENT-03** Simulação de entrevista no chat: o Claude faz o papel do entrevistador com base na vaga e na etapa (RH, técnica, gestor) e dá feedback por resposta (estrutura STAR, clareza, evidência, tempo). · S · F4
**RF-ENT-04** Registro pós-entrevista: perguntas feitas, como foi, nota pessoal, próximos passos, nomes. · M · F4
**RF-ENT-05** Rascunho de e-mail de agradecimento no Gmail, no mesmo dia. · S · F4
**RF-ENT-06** Perguntas registradas viram um banco de perguntas por empresa e por tipo de etapa, usado em dossiês futuros. · S · F4
**RF-ENT-07** Teste técnico: registro do enunciado, prazo, link do repositório entregue e status. · S · F4

---

## OFE · Oferta

**RF-OFE-01** Registro de proposta: regime, salário, bônus, PLR, benefícios (VR/VA, saúde, odonto, auxílios), equity, modelo de trabalho, data de início, prazo para resposta. · S · F7
**RF-OFE-02** Comparador CLT x PJ com o valor anual líquido equivalente (13º, férias + 1/3, FGTS, INSS, IRRF, benefícios; para PJ, imposto pelo regime escolhido, contador e ausência de benefícios). As premissas ficam editáveis e visíveis. · S · F7
**RF-OFE-03** Referência salarial por cargo, senioridade e local a partir de fontes públicas (pesquisa web), com fontes e datas. · C · F7
**RF-OFE-04** Roteiro de negociação baseado na proposta, nas alternativas e na referência. · C · F7
**RF-OFE-05** Comparação lado a lado de várias propostas. · C · F7

---

## REL · Relacionamento

**RF-REL-01** CRM leve de pessoas: recrutadores, gestores e conexões, com empresa, cargo, canal, histórico de interações e candidaturas ligadas. · S · F6
**RF-REL-02** Identificar o recrutador ou gestor da vaga (texto da vaga, "conheça o time" do LinkedIn) e sugerir um convite de conexão ou mensagem curta, em **rascunho** para o usuário enviar. · S · F6
**RF-REL-03** Indicações: registrar quem pode indicar e o status do pedido; vaga com indicação ganha bônus na nota de Chance. · S · F6

---

## NOT · Notificações

**RF-NOT-01** Bot do Telegram vinculado só ao chat do usuário (allowlist de `chat_id`). · M · F3
**RF-NOT-02** Eventos que geram alerta imediato: convite de entrevista, pedido de disponibilidade, teste técnico, oferta, pergunta pendente bloqueando a fila, parada de segurança do agente, falha de integração (token expirado). · M · F3
**RF-NOT-03** Ações direto no Telegram: responder pergunta pendente (botões/texto), aprovar candidatura, `/stop`, `/status`, `/hoje`. · S · F5
**RF-NOT-04** Resumo diário (padrão 08h) e relatório semanal (padrão segunda 08h). · S · F3
**RF-NOT-05** Silêncio configurável (ex.: 22h–07h), exceto para paradas de segurança. · S · F3

---

## DSH · Dashboard

**RF-DSH-01** Tela inicial "Hoje": próximas entrevistas, pendências (perguntas, aprovações, e-mails ambíguos, eventos em rascunho), follow-ups do dia, cota usada, estado do agente. · M · F2
**RF-DSH-02** Kanban de candidaturas por status, com filtros e arrastar para mudar o status. · M · F2
**RF-DSH-03** Lista de vagas ordenada por prioridade, com o cartão de avaliação (notas, motivos, ação sugerida) e ações: aprovar, descartar, CV específico, ver detalhes. · M · F2
**RF-DSH-04** Fila de revisão com atalhos de teclado (A aprovar, D descartar, E editar, J/K navegar) e aprovação em lote. · M · F5
**RF-DSH-05** Detalhe da candidatura: linha do tempo, CV enviado, respostas, e-mails, eventos, dossiê, notas. · M · F2
**RF-DSH-06** Biblioteca de currículos: mestre, coringas, específicos, diffs, PDFs, checagem ATS. · M · F1
**RF-DSH-07** Editor do banco de respostas, com busca e estatística de uso. · M · F5
**RF-DSH-08** Agenda integrada (semana) com eventos do processo seletivo. · S · F3
**RF-DSH-09** Execução ao vivo do agente (WebSocket). · S · F5
**RF-DSH-10** Configurações: preferências, filtros, pesos, limites, políticas de automação, integrações, notificações. · M · F2
**RF-DSH-11** Responsivo para celular, para aprovar e responder fora do computador; PWA instalável. · S · F3
**RF-DSH-12** Busca global (vagas, empresas, pessoas, candidaturas). · C · F6

---

## ANA · Aprendizado

**RF-ANA-01** Funil: encontradas → avaliadas → candidatadas → resposta → entrevista → teste → oferta, por período. · M · F3
**RF-ANA-02** Taxa de resposta por currículo, por quadrante, por fonte, por stack e por dia da semana ou hora de envio. · S · F7
**RF-ANA-03** Mapa de gaps de skills: requisitos frequentes nas vagas de alta prioridade que não estão no mestre, com frequência e tendência. · S · F7
**RF-ANA-04** Plano de estudo sugerido a partir dos gaps (o quê, por quê, recursos, estimativa de esforço). · C · F7
**RF-ANA-05** Análise de rejeições: padrões (etapa, tipo de vaga, senioridade, motivos citados). · C · F7
**RF-ANA-06** Otimização do perfil do LinkedIn: compara o perfil com o mestre e as vagas-alvo e sugere título, sobre, skills e destaques. · C · F7
**RF-ANA-07** Relatório semanal com métricas, destaques e três recomendações acionáveis. · S · F3
**RF-ANA-08** Metas semanais (candidaturas, follow-ups, estudo) com acompanhamento e alerta de ritmo excessivo, para evitar desgaste. · C · F7

---

## PLA · Plataforma

**RF-PLA-01** Autenticação de usuário único com login Google restrito ao e-mail em `AUTH_ALLOWED_EMAIL`. · M · F0
**RF-PLA-02** Políticas de automação centralizadas (`automation_policy`): o que roda sozinho, o que exige revisão e o que nunca é automático. · M · F2
**RF-PLA-03** Log de auditoria de toda ação automática e de toda chamada externa que muda estado (quem, o quê, quando, entrada, saída, motivo). · M · F0
**RF-PLA-04** Painel de custo de IA: por tarefa, por dia e por mês, com orçamento mensal (`AI_MONTHLY_BUDGET_USD`) que, ao estourar, bloqueia tarefas não essenciais e alerta. · M · F1
**RF-PLA-05** Painel de saúde das integrações (último sucesso, erros, token expirando). · M · F3
**RF-PLA-06** Backup automático diário do banco e dos arquivos, com retenção de 30 dias e teste de restauração documentado. · M · F0
**RF-PLA-07** Exportação completa (JSON + CSV + PDFs) e exclusão completa dos dados. · S · F6
**RF-PLA-08** Feature flags por módulo para ligar e desligar integrações e automações. · S · F0
