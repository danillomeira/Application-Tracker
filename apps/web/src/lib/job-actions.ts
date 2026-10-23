/** Regras e nomes das ações de vaga, iguais em todas as telas (cartão, gaveta, página da vaga, Hoje). */

/** Status em que você já enviou a candidatura (o resto ainda é "fila"). */
export const APPLIED_STATUSES = new Set([
  "submitted",
  "under_review",
  "interviewing",
  "assessment",
  "offer",
  "accepted",
  "rejected",
  "ghosted",
  "declined",
  "withdrawn",
]);

export const isApplied = (status: string | null | undefined): boolean => !!status && APPLIED_STATUSES.has(status);

export const ACTION_LABEL = {
  apply: "Candidatar no site",
  submitted: "Já me candidatei",
  skip: "Não tenho interesse",
  tailor: "Gerar currículo sob medida",
  cover: "Gerar carta",
  open: "Ver detalhes",
} as const;
