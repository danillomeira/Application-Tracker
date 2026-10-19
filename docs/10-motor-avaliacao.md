# 10 · Motor de avaliação de vagas

Objetivo: gastar a cota de candidaturas e o tempo de preparação onde há mais chance **e** mais valor.

## 1. Pipeline
```
vaga normalizada
  → 1. filtros eliminatórios ──falhou──► status "blocked" (com motivos)
  → 2. features (determinísticas + extraídas por IA)
  → 3. nota de Chance (0–100)
  → 4. nota de Atratividade (0–100)
  → 5. quadrante + ação sugerida
  → 6. explicação (motivos + fontes)
```
Tudo grava em `job_score` com a versão dos pesos e do mestre. Recalcula quando qualquer um muda (RF-AVA-10).

## 2. Filtros eliminatórios
| Filtro | Regra |
|---|---|
| Bloqueio | empresa, domínio ou recrutador em `blocklist_entry`; inclui o empregador atual |
| Duplicada | já existe candidatura para a vaga canônica |
| Rejeição recente | rejeitado na mesma empresa há < `knockout.reapply_cooldown_days` (padrão 90) |
| Modelo de trabalho | fora de `preference.work_models` |
| Localidade | presencial/híbrido fora de `preference.locations` |
| Salário | máximo informado < mínimo do regime (só quando a vaga informa) |
| Requisito impeditivo | idioma não falado, cidadania/visto exigido, formação obrigatória ausente, senioridade ≥ 2 níveis acima |
| Golpe | pedido de pagamento, só contato por WhatsApp pessoal, empresa sem rastro, salário absurdo para o cargo |
| Palavras proibidas | `blocklist_entry.kind = keyword` no título |

## 3. Nota de Chance
`chance = 100 × Σ (peso_i × feature_i)`, com cada feature em [0, 1].

| Feature | Peso inicial | Cálculo |
|---|---|---|
| `fit_tecnico` | 0,30 | 0,7 × cobertura dos obrigatórios + 0,3 × cobertura dos desejáveis. Cobertura = requisito presente no mestre (por alias) ou similaridade ≥ 0,85 com uma skill do mestre |
| `senioridade` | 0,10 | 1 se o nível pedido = o seu; 0,6 se ±1 nível; 0,2 se ±2. Anos pedidos vs. anos calculados pela stack principal |
| `concorrencia` | 0,10 | f(candidatos / horas publicada). < 25 cand. → 1; 25–100 → 0,7; 100–200 → 0,4; > 200 → 0,15 |
| `frescor` | 0,10 | < 24 h → 1; 24–72 h → 0,8; 3–7 d → 0,55; 7–14 d → 0,35; 14–30 d → 0,15; > 30 d → 0,05 |
| `responsividade` | 0,15 | taxa de resposta estimada da empresa (§5) |
| `recrutador_ativo` | 0,05 | recrutador identificado (0,5) + selo de atividade recente (0,5) |
| `nao_fantasma` | 0,10 | 1 − penalidade: repost ≥ 2 (−0,3), aberta > 60 d (−0,3), descrição genérica (−0,2), layoff recente (−0,3); mínimo 0 |
| `conexoes` | 0,10 | indicação possível → 1; conexão de 1º grau no time → 0,7; de 2º grau → 0,4; nenhuma → 0 |

Feature sem dado → usa o valor neutro (0,5) e marca `missing: true` na explicação.

## 4. Nota de Atratividade
| Feature | Peso inicial | Fonte |
|---|---|---|
| `reputacao` | 0,25 | Notas públicas (Glassdoor/Indeed via pesquisa web) normalizadas: 3,0 → 0; 4,5 → 1. Tendência de 12 meses ±0,1 |
| `cultura` | 0,15 | Temas das avaliações classificados pela IA: positivos vs. alertas (burnout, liderança tóxica, horas extras) |
| `saude` | 0,15 | Headcount (crescimento +), funding recente (+), layoffs em 12 meses (−), notícias de crise (−) |
| `remuneracao` | 0,20 | Faixa (informada ou estimada) vs. pretensão no mesmo regime: ≥ 120% → 1; 100% → 0,7; 85% → 0,3; abaixo → 0 |
| `carreira` | 0,10 | Produto próprio (+) vs. body shop/alocação (−), stack moderna, plano de carreira citado |
| `condicoes` | 0,10 | Remoto (+), benefícios, flexibilidade |
| `alinhamento` | 0,05 | Setor em `sectors_preferred` (+) / `sectors_avoided` (−), feedback manual de vagas semelhantes |

Sem perfil de empresa ainda → neutro (0,5) + `missing`, e o perfil é enfileirado.

## 5. Responsividade (bayesiana)
Estimativa da taxa de resposta da empresa `r` (qualquer retorno humano em até 30 dias):

```
r = (respostas_proprias + α) / (candidaturas_proprias + α + β)
```
- **Prior** `Beta(α, β)` a partir da média do segmento (porte × setor × fonte) calculada no seu histórico; antes de existir histórico, usar `α = 2, β = 6` (≈ 25%).
- **Sinais públicos** (relatos de ghosting, tempo médio do processo) ajustam o prior: cada sinal forte equivale a ±2 observações.
- **Confiança** exibida: baixa (< 3 observações próprias), média (3–9), alta (≥ 10).

## 6. Quadrantes e ações
Limiares em `scoring_weights.thresholds` (padrão: chance 60, atratividade 60).

| Quadrante | Condição | Ação sugerida |
|---|---|---|
| `top` (prioridade máxima) | chance ≥ 60 e atratividade ≥ 60 | CV específico se a aderência ao coringa < limiar; mensagem ao recrutador; aplicar no mesmo dia; preparar o perfil da empresa |
| `bet` (aposta) | chance < 60 e atratividade ≥ 60 | CV específico + contato/indicação antes de aplicar; não usar o modo automático |
| `volume` | chance ≥ 60 e atratividade < 60 | Coringa; elegível ao modo automático |
| `discard` | ambos < 60 | Só se sobrar cota; padrão = não aplicar |

**Prioridade na fila** = `0,55 × chance + 0,45 × atratividade` + bônus de frescor (vagas < 24 h sobem) + bônus de watchlist.

## 7. Explicação
`chance_breakdown` e `attractiveness_breakdown` guardam por feature: `value`, `weight`, `contribution`, `evidence` (texto curto), `sources[]`, `missing`. O cartão da vaga mostra os 3 maiores positivos e os 2 maiores negativos. A tarefa `scoring.explain` só redige o texto; os números são do código.

## 8. Calibração (F7)
- Rótulo: `y = 1` se a candidatura chegou a `interviewing` ou além (alternativa configurável: qualquer resposta humana).
- Quando houver ≥ 100 candidaturas com desfecho (≥ 21 dias desde o envio), treinar uma **regressão logística** com as features de Chance (scikit-learn, regularização L2, validação cruzada de 5 folds).
- Converter os coeficientes em pesos normalizados; mostrar AUC, n e a comparação com os pesos atuais.
- **Nunca ativar sozinho:** o usuário aprova a nova versão. Manter um histórico para rollback.
- Atratividade: calibrada pelo feedback manual (`job_feedback`) e pelas vagas aprovadas vs. descartadas.

## 9. Testes
- Unitários para cada feature com casos de borda (sem dado, valores extremos).
- Teste de propriedade: notas sempre em [0, 100]; aumentar uma feature com peso positivo nunca diminui a nota.
- Snapshot tests de explicação para vagas de exemplo.
