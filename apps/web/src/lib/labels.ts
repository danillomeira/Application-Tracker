export const STATUS_LABEL: Record<string, string> = {
  discovered: "Encontrada",
  queued: "Na fila",
  in_progress: "Em andamento",
  needs_input: "Pergunta pendente",
  awaiting_review: "Aguardando revisão",
  submitted: "Candidatada",
  under_review: "Em análise",
  interviewing: "Entrevista",
  assessment: "Teste técnico",
  offer: "Oferta",
  accepted: "Aceita",
  declined: "Recusada por mim",
  rejected: "Rejeitada",
  ghosted: "Sem retorno",
  skipped: "Descartada",
  blocked: "Bloqueada",
  withdrawn: "Retirada",
};

export const STATUS_TONE: Record<string, "neutral" | "primary" | "success" | "warning" | "danger"> = {
  discovered: "neutral",
  queued: "primary",
  in_progress: "primary",
  needs_input: "warning",
  awaiting_review: "warning",
  submitted: "primary",
  under_review: "primary",
  interviewing: "success",
  assessment: "success",
  offer: "success",
  accepted: "success",
  declined: "neutral",
  rejected: "danger",
  ghosted: "neutral",
  skipped: "neutral",
  blocked: "danger",
  withdrawn: "neutral",
};

export const QUADRANT_LABEL: Record<string, string> = {
  top: "Prioridade máxima",
  bet: "Aposta",
  volume: "Volume",
  discard: "Descartar",
  blocked: "Bloqueada",
};

export const QUADRANT_TONE: Record<string, "neutral" | "primary" | "success" | "warning" | "danger"> = {
  top: "success",
  bet: "primary",
  volume: "warning",
  discard: "neutral",
  blocked: "danger",
};

export const EMAIL_LABEL: Record<string, string> = {
  confirmacao: "Confirmação",
  rejeicao: "Rejeição",
  convite_entrevista: "Convite de entrevista",
  pedido_disponibilidade: "Pedido de disponibilidade",
  teste_tecnico: "Teste técnico",
  oferta: "Oferta",
  pedido_info: "Pedido de informação",
  recrutador_prospeccao: "Recrutador (prospecção)",
  notificacao_linkedin: "Notificação do LinkedIn",
  remarcacao: "Remarcação",
  cancelamento: "Cancelamento",
  irrelevante: "Irrelevante",
};

export const INTERVIEW_KIND: Record<string, string> = {
  hr: "RH",
  technical: "Técnica",
  hiring_manager: "Gestor",
  panel: "Painel",
  culture: "Cultura",
  final: "Final",
};

export const WORK_MODEL_LABEL: Record<string, string> = { remote: "Remoto", hybrid: "Híbrido", onsite: "Presencial" };

export const SENIORITY_LABEL: Record<string, string> = {
  intern: "Estágio",
  junior: "Júnior",
  mid: "Pleno",
  senior: "Sênior",
  staff: "Staff",
  principal: "Principal",
  lead: "Liderança",
  manager: "Gestão",
};

export const APPLY_KIND_LABEL: Record<string, string> = {
  easy_apply: "Easy Apply",
  external: "Site da empresa",
  email: "Por e-mail",
  unknown: "Não identificado",
};
