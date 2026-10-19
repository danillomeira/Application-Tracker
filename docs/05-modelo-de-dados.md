# 05 · Modelo de dados

PostgreSQL 16 + pgvector. Convenções:
- PK `id UUID` (uuid7), `created_at`/`updated_at` `timestamptz` em todas as tabelas
- Enums como `text` + `CHECK` (mais fácil de migrar que enum nativo)
- Campos semiestruturados em `jsonb` validados por Pydantic na aplicação
- Embeddings: `vector(768)` (modelo em `08-ia-claude.md` §6)
- Soft delete só onde indicado (`archived_at`)

## 1. Perfil

### `master_profile_version`
| Campo | Tipo | Nota |
|---|---|---|
| version | int | sequencial, único |
| data | jsonb | documento completo do mestre (schema em `11-curriculos.md` §2) |
| source | text | `import_pdf`, `manual_edit`, `seed_yaml` |
| change_note | text | |
| is_current | bool | só uma `true` |

### `star_story`
`title`, `experience_id` (ref ao id dentro do mestre), `situation`, `task`, `action`, `result`, `competencies text[]`, `skills text[]`, `language`, `embedding vector`.

### `preference` (linha única)
`target_roles text[]`, `seniorities text[]`, `stacks text[]`, `work_models text[]`, `locations text[]`, `regimes text[]`, `min_salary jsonb` (`{"CLT": {"BRL": 12000}, "PJ": {"BRL": 16000}, "USD_annual": 60000}`), `sectors_preferred text[]`, `sectors_avoided text[]`, `company_sizes text[]`, `languages jsonb`, `relocation bool`, `travel bool`, `timezone text`.

### `answer_bank_entry`
| Campo | Tipo | Nota |
|---|---|---|
| canonical_question | text | forma normalizada |
| question_embedding | vector | busca semântica |
| field_kind | text | `text`, `number`, `select`, `radio`, `checkbox`, `textarea`, `date` |
| answer | jsonb | valor ou mapa de opções preferidas |
| conditions | jsonb | ex.: `{"regime": "PJ"}`, `{"language": "en"}` |
| language | text | `pt`, `en`, `any` |
| source | text | `user`, `user_once`, `derived_from_profile` |
| use_count / last_used_at | int / timestamptz | |
| aliases | text[] | variações já vistas da pergunta |

### `blocklist_entry`
`kind` (`company`, `domain`, `recruiter`, `keyword`), `value`, `reason`.

### `document`
Cofre: `kind`, `title`, `storage_key`, `mime`, `sha256`, `expires_at`.

## 2. Currículos

### `resume_template`
`slug` (`classic`), `name`, `engine` (`latex`), `path`, `version`, `supports_languages text[]`.

### `resume_variant`
| Campo | Tipo | Nota |
|---|---|---|
| kind | text | `wildcard` (coringa) ou `tailored` (específico) |
| slug | text | ex.: `data-engineer-en` |
| name | text | |
| language | text | `pt`/`en` |
| focus | jsonb | headline, stacks, ordem de seções, experiências e skills selecionadas |
| content | jsonb | conteúdo final renderizável |
| master_version | int | de qual mestre deriva |
| template_id | uuid | |
| job_id | uuid null | só para `tailored` |
| parent_variant_id | uuid null | coringa de origem |
| embedding | vector | |
| status | text | `draft`, `approved`, `archived` |
| validation | jsonb | resultado do validador de fatos e da checagem ATS |

### `resume_render`
PDF gerado (imutável): `variant_id`, `storage_key`, `sha256`, `tex_source_key`, `rendered_at`, `ats_text`, `page_count`.

## 3. Empresas e vagas

### `company`
`name`, `normalized_name` (único), `domains text[]`, `linkedin_url`, `website`, `size_range`, `sector`, `hq_location`, `ats_kind`, `ats_board_token`, `is_watchlisted`, `is_blocked`.

### `company_profile`
Perfil coletado (cache): `company_id`, `summary`, `history`, `mission`, `values jsonb`, `products jsonb`, `tech_stack text[]`, `reputation jsonb` (notas, tendências, temas), `health jsonb` (headcount, funding, layoffs), `news jsonb`, `sources jsonb` (url, título, data), `collected_at`, `expires_at`.

### `company_signal`
Evidência pontual com fonte: `company_id`, `kind` (`rating`, `layoff`, `funding`, `headcount`, `response_time`, `ghosting_report`...), `value jsonb`, `source_url`, `observed_at`.

### `saved_search`
`name`, `query`, `filters jsonb`, `sources text[]`, `schedule_cron`, `is_active`, `last_run_at`.

### `job`
| Campo | Tipo | Nota |
|---|---|---|
| company_id | uuid | |
| title / normalized_title | text | |
| location, work_model, regime, seniority | text | |
| salary | jsonb | `{min, max, currency, period, regime, estimated: bool}` |
| requirements | jsonb | `{must: [...], nice: [...]}` |
| benefits | text[] | |
| language | text | |
| apply_kind | text | `easy_apply`, `external`, `email` |
| ats_kind | text | |
| posted_at | timestamptz | |
| applicants_count | int | |
| status | text | `open`, `closed`, `unknown` |
| canonical_url | text | |
| description_text | text | |
| embedding | vector | |
| repost_count | int | |
| first_seen_at / last_seen_at | timestamptz | |

### `job_source`
Uma linha por fonte onde a vaga apareceu: `job_id`, `source` (`linkedin`, `greenhouse`, `lever`, `ashby`, `gupy`, `manual`), `external_id`, `url`, `saved_search_id`, `seen_at`, `raw jsonb`.

### `job_snapshot`
Imutável: `job_id`, `reason` (`collected`, `applied`), `description_text`, `description_html_sanitized`, `captured_at`, `sha256`.

## 4. Avaliação

### `scoring_weights`
`version`, `chance_weights jsonb`, `attractiveness_weights jsonb`, `thresholds jsonb`, `source` (`default`, `user`, `calibrated`), `is_current`, `metrics jsonb` (para pesos calibrados: AUC, n).

### `job_score`
`job_id`, `weights_version`, `master_version`, `knockout jsonb` (`{passed, reasons[]}`), `chance`, `chance_breakdown jsonb`, `attractiveness`, `attractiveness_breakdown jsonb`, `quadrant` (`top`, `bet`, `volume`, `discard`), `suggested_action`, `best_variant_id`, `variant_scores jsonb`, `computed_at`. Única por (`job_id`, `weights_version`, `master_version`).

### `job_feedback`
`job_id`, `verdict` (`good`, `not_interested`), `reason`.

## 5. Candidaturas

### `application`
| Campo | Tipo | Nota |
|---|---|---|
| job_id | uuid | único (uma candidatura por vaga) |
| status | text | ver máquina de estados |
| channel | text | `easy_apply`, `external`, `email`, `referral`, `inbound` (recrutador procurou) |
| mode | text | `review`, `auto`, `manual` |
| resume_render_id | uuid | PDF exato enviado |
| cover_letter | text | |
| submitted_at | timestamptz | |
| applied_snapshot_id | uuid | `job_snapshot` no envio |
| priority_at_submit | jsonb | notas no momento |
| last_activity_at | timestamptz | |
| next_action / next_action_at | text / timestamptz | |
| outcome_reason | text | motivo de rejeição/desistência |
| notes | text | |

#### Máquina de estados
```
discovered ─► queued ─► in_progress ─► awaiting_review ─► submitted
     │           │            │                 │              │
     └► skipped  └► blocked   └► needs_input ◄──┘              ▼
                                  (pergunta)             under_review
                                                              │
         ┌────────────────┬────────────────┬─────────────────┤
         ▼                ▼                ▼                 ▼
    interviewing ─► assessment ─► offer ─► accepted     rejected
         │                                  └► declined
         └────────────────────────────────────────────► ghosted (sem retorno)
Qualquer estado ativo ─► withdrawn
```
- Transições válidas definidas em código (`applications/state_machine.py`) e testadas
- Toda transição gera um `application_event`
- `ghosted` volta para `under_review`/`interviewing` se chegar resposta

### `application_event`
Linha do tempo: `application_id`, `kind` (`status_change`, `email_in`, `email_draft`, `message_in`, `interview_scheduled`, `note`, `agent_step`, `followup_suggested`...), `payload jsonb`, `actor` (`system`, `user`, `agent`), `reason`, `occurred_at`.

### `application_answer`
Imutável depois do envio: `application_id`, `step_index`, `question_text`, `field_kind`, `options jsonb`, `answer jsonb`, `resolution` (`bank`, `rule`, `ai`, `user`), `confidence`, `answer_bank_entry_id`.

### `pending_question`
`application_id`, `question_text`, `field_kind`, `options jsonb`, `context jsonb`, `ai_suggestion jsonb`, `status` (`open`, `answered`, `expired`), `answered_value`, `save_to_bank bool`.

### `agent_job`
Tarefas de navegador: `kind` (`search`, `apply`, `read_messages`, `fill_external`), `payload jsonb`, `status` (`pending`, `leased`, `running`, `paused`, `done`, `failed`, `cancelled`), `lease_until`, `attempts`, `state jsonb` (checkpoint por etapa), `artifacts jsonb` (screenshots, html, trace), `error`.

### `daily_quota`
`date`, `kind` (`easy_apply`, `linkedin_search`, `linkedin_page_views`), `used`, `limit`.

## 6. Comunicação

### `email_message`
`gmail_id` (único), `thread_id`, `from_addr`, `from_name`, `to_addrs`, `subject`, `snippet`, `body_text` (retenção limitada), `received_at`, `labels text[]`, `classification`, `classification_confidence`, `extracted jsonb` (datas, links, pessoas, prazos), `application_id null`, `link_status` (`auto`, `user`, `ambiguous`, `none`), `processed_at`.

### `linkedin_message`
`conversation_id`, `message_id`, `from_name`, `from_profile_url`, `text`, `received_at`, `classification`, `extracted jsonb`, `application_id null`, `person_id null`.

### `draft`
Rascunhos gerados: `kind` (`email_reply`, `followup`, `thank_you`, `linkedin_note`, `linkedin_message`, `availability`), `application_id`, `to`, `subject`, `body`, `gmail_draft_id null`, `status` (`proposed`, `created_in_gmail`, `sent_by_user`, `discarded`).

## 7. Agenda e entrevistas

### `calendar_event`
`application_id`, `kind` (`interview`, `assessment_deadline`, `study_block`, `followup`), `google_event_id`, `title`, `starts_at`, `ends_at`, `timezone`, `location_or_link`, `attendees jsonb`, `status` (`draft`, `confirmed`, `cancelled`), `source_email_id`.

### `interview`
`application_id`, `round` (int), `kind` (`hr`, `technical`, `hiring_manager`, `panel`, `culture`, `final`), `scheduled_event_id`, `interviewers jsonb`, `dossier_id`, `post_notes jsonb` (perguntas, sensação, próximos passos), `self_rating`, `thank_you_draft_id`.

### `interview_dossier`
`application_id`, `interview_id null`, `content jsonb` (seções de RF-ENT-01), `cheatsheet_md`, `sources jsonb`, `model`, `prompt_version`, `generated_at`, `status`.

### `interview_question_log`
`company_id`, `interview_kind`, `question`, `my_answer_notes`, `asked_at`.

### `assessment`
`application_id`, `kind` (`take_home`, `live_coding`, `online_test`), `instructions`, `deadline_at`, `repo_url`, `status`.

### `mock_session`
`application_id`, `interview_kind`, `transcript jsonb`, `feedback jsonb`.

## 8. Oferta e pessoas

### `offer`
`application_id`, `regime`, `base_salary`, `currency`, `period`, `bonus jsonb`, `benefits jsonb`, `equity jsonb`, `work_model`, `start_date`, `respond_by`, `annualized jsonb` (resultado do comparador com premissas), `status`.

### `person`
`full_name`, `company_id`, `role`, `linkedin_url`, `email`, `kind` (`recruiter`, `hiring_manager`, `interviewer`, `connection`, `referrer`), `notes`, `last_contact_at`.

### `person_application` (N:N)
`person_id`, `application_id`, `relation` (`recruiter`, `interviewer`, `referrer`).

## 9. Plataforma

### `oauth_credential`
`provider` (`google`), `account_email`, `scopes text[]`, `token_encrypted bytea`, `refresh_encrypted bytea`, `expires_at`, `status`.

### `browser_session_meta`
Metadados apenas (o perfil fica na máquina local): `site`, `last_login_ok_at`, `last_safety_stop_at`, `notes`.

### `setting`
`key` (único), `value jsonb`. Ex.: `automation_policy`, `limits`, `resume.match_threshold`, `tracking.ghost_after_days`, `notifications.quiet_hours`.

### `ai_call`
Custo e rastreabilidade: `task`, `model`, `prompt_version`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `cost_usd`, `latency_ms`, `stop_reason`, `request_hash`, `entity_type`, `entity_id`, `batch_id null`, `error`.

### `audit_log`
`actor`, `action`, `entity_type`, `entity_id`, `before jsonb`, `after jsonb`, `reason`, `occurred_at`. Apenas inserção.

### `notification`
`channel` (`telegram`, `web`), `kind`, `payload jsonb`, `sent_at`, `action_taken`.

## 10. Índices essenciais
- `job(company_id, normalized_title)`, `job USING hnsw (embedding vector_cosine_ops)`
- `job_source(source, external_id)` único
- `application(status, last_activity_at)`
- `email_message(gmail_id)` único, `email_message(application_id)`
- `answer_bank_entry USING hnsw (question_embedding vector_cosine_ops)`
- `ai_call(created_at)`, `ai_call(task, created_at)`
- `agent_job(status, created_at)`
