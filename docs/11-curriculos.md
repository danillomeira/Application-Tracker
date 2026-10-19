# 11 · Currículos

## 1. Conceitos
- **Currículo mestre:** tudo o que é verdade sobre o usuário. Fonte única. Versionado.
- **Coringa (`wildcard`):** recorte do mestre para um perfil de vaga recorrente. Reutilizado em muitas candidaturas.
- **Específico (`tailored`):** recorte do mestre para uma vaga, criado quando nenhum coringa atende bem.
- **Template:** o visual (LaTeX). Independente do conteúdo.
- **Render:** PDF gerado, imutável, com hash.

## 2. Currículo mestre
Origem: o **onboarding** (PDF do LinkedIn, CV em PDF/DOCX ou YAML) extrai o perfil com IA, a pessoa confere e confirma; vira `master_profile_version` e passa a ser editado pelo dashboard. Opcional: `data/master-profile.yaml` (fora do git) importado com `tracker-seed`.

Estrutura (resumo; o seed é a referência):
```yaml
contact: {full_name, email, phone, location, remote, linkedin, github, portfolio}
headlines: {<perfil>: "..."}
summary_facts: {years_experience_claim, key_achievements[], certifications_short}
skills: {<categoria>: [..]}
skill_aliases: {<skill>: [aliases]}
experience:
  - id, title, title_alternatives[], organization, location, start, end, type
    bullets_en[], bullets_pt[], skills[], extra_facts[], confirmar[]
projects: [{id, name, url, description_en, skills[]}]
education: [{degree, institution, start, end, status, show_by_default}]
certifications: [{name, issuer, year, show_by_default}]
languages: [{name, level}]
```
Regras:
- Bullets do mestre já são a melhor versão escrita pelo usuário. A IA reordena, seleciona e ajusta o vocabulário, mas não cria fatos.
- `**negrito**` em markdown nos bullets é convertido para `\textbf{}` no render (filtro `md_bold`).
- `title_alternatives` permite exibir outro título **só se** for um título que o usuário confirmou como legítimo para aquele cargo.
- Campos com `confirmar:` bloqueiam o uso do item em CVs gerados até a confirmação.
- Mesmo trabalho com troca de vínculo (ex.: consultor alocado no cliente → contratado direto pelo cliente) é **um bloco só**, com `employment_history` e `org_line_<idioma>` explicitando a efetivação; o render usa `org_line_<idioma>` no lugar de `organization` quando existir.

## 3. Template `classic`
Arquivos em `templates/resumes/classic/`:
- `classic.sty`: estilo (reproduz o PDF de referência: Computer Modern, nome centralizado em caixa alta, headline em negrito, seções em caixa alta com linha, tabela de skills de duas colunas, cargo/local e empresa/período alinhados, bullets compactos com destaques em negrito)
- `resume.tex.j2`: template Jinja2 com delimitadores seguros para LaTeX: `((* bloco *))`, `((( variável )))`, `((# comentário #))`

Exemplo de saída: qualquer render em Currículos (o `.tex` gerado pode ser baixado junto do PDF).

### Render
1. Montar o contexto a partir da variante (`content` jsonb).
2. Escapar **todo** texto com o filtro `tex` (`& % $ # _ { } ~ ^ \` → sequências LaTeX).
3. Renderizar o Jinja → `.tex`.
4. Compilar com **tectonic** (ou `pdflatex` em container TeX Live) em diretório temporário, **sem shell-escape**, com timeout de 60 s.
5. Salvar PDF + `.tex` no storage, calcular SHA-256, extrair o texto (pypdf) para a checagem ATS.
6. Nome do arquivo: `<Nome>_<Sobrenome>_<Perfil>_<IDIOMA>.pdf` a partir do contato do mestre (ex.: `Ana_Silva_Data_Engineer_EN.pdf`). Nunca `final_v3`.

### Rótulos por idioma
| Chave | EN | PT |
|---|---|---|
| summary | Summary | Resumo |
| skills | Technical Skills | Competências Técnicas |
| experience | Professional Experience | Experiência Profissional |
| projects | Featured Projects | Projetos em Destaque |
| education | Education | Formação |
| certifications | Certifications | Certificações |

## 4. Perfis de coringa
Definidos em `modules/resumes/content.py` (`WILDCARD_PROFILES`), genéricos para qualquer candidato. Cada um tem um foco (usado pela IA) e uma ordem de ênfase das categorias de skill; categorias do currículo que não estiverem na lista entram no fim, então nenhuma competência some.

| Slug | Foco |
|---|---|
| `data_engineer` | pipelines ETL/ELT, batch e streaming, modelagem, qualidade de dados, cloud |
| `ai_ml_engineer` | modelos e LLMs em produção, RAG, agentes, MLOps |
| `data_scientist` | análise, estatística, modelagem preditiva, experimentação |
| `software_engineer_backend` | APIs, sistemas distribuídos, integrações, confiabilidade |
| `frontend` | interfaces web, acessibilidade, desempenho, design systems |
| `fullstack` | produto ponta a ponta |
| `mobile` | apps Android/iOS nativos ou multiplataforma |
| `devops_sre` | IaC, CI/CD, Kubernetes, observabilidade |

As categorias extraídas do CV são normalizadas para chaves canônicas (`category_key`: "Data Engineering" → `data_engineering`).

Cada coringa em EN e PT. O limite de páginas é 2 (padrão do `classic`); variação de 1 página para vagas que pedem.

## 5. Escolha do CV por vaga
```
nota(coringa) = 0,6 × cos(embedding_vaga, embedding_coringa)
              + 0,4 × cobertura_dos_obrigatórios_no_coringa
```
- Maior nota ≥ `resume.match_threshold` (0,75) → usa o coringa.
- Senão → "CV específico recomendado". Em `top`/`bet` gera automaticamente; em `volume` usa o melhor coringa.
- Idioma = idioma da vaga (`job.language`); vaga em PT para empresa estrangeira → PT, salvo regra do usuário.

## 6. Validador de fatos (determinístico)
Executado em todo conteúdo gerado (`resume.*`, carta, respostas abertas):
1. **Skills:** cada skill citada no texto ou na tabela precisa existir em `skills` do mestre (via `skill_aliases`, normalização de caixa e pontuação).
2. **Organizações, cargos e datas:** precisam bater com uma experiência do mestre (ou `title_alternatives` confirmados).
3. **Números:** toda métrica numérica (140, 30 minutos, 5x, 60%+, 8–12, 20+, 30+...) precisa aparecer nos fatos da experiência citada.
4. **Formação e certificações:** só as do mestre.
5. **Anos de experiência:** consistentes com o cálculo a partir das datas. Uma afirmação que exceda o cálculo gera um **alerta** (não bloqueio) para o usuário revisar (ver questão em aberto Q-11).

Saída: `{passed, violations: [{kind, text, suggestion}], warnings: [...]}`. Violação bloqueia o render.

## 7. Checagem ATS
- Texto extraído contém: nome, e-mail, telefone, títulos de seção, datas no formato `Mon YYYY`.
- Ordem de leitura correta (cabeçalho → resumo → skills → experiência).
- Sem caracteres quebrados (ligaduras: `glyphtounicode` ativo no `classic.sty`).
- Cobertura de keywords da vaga: % de obrigatórios presentes no texto do PDF.
- Resultado mostrado na biblioteca de currículos e no cartão da vaga.

## 8. Carta de apresentação
Template `cover_letter.tex.j2` no mesmo estilo (cabeçalho igual, corpo ≤ 150 palavras): por que a empresa, 2 provas concretas do mestre ligadas aos requisitos, fechamento. Também gerada em texto puro para campos de formulário.
