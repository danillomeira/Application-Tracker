"use client";

import { Check, ExternalLink, MapPin, ThumbsDown, ThumbsUp, X } from "lucide-react";
import Link from "next/link";
import { Avatar, Badge, Button, Card, ScoreRing } from "@/components/ui";
import { useSend } from "@/lib/hooks";
import { QUADRANT_LABEL, QUADRANT_TONE, SENIORITY_LABEL, STATUS_LABEL, WORK_MODEL_LABEL } from "@/lib/labels";
import { cn, relativeTime } from "@/lib/utils";

export type Score = {
  chance: number;
  attractiveness: number;
  priority: number;
  quadrant: string;
  suggested_action: string;
  explanation: {
    chance?: { positives: string[]; negatives: string[] };
    attractiveness?: { positives: string[]; negatives: string[] };
    knockout?: string[];
    missing_must?: string[];
  };
};

export type JobRow = {
  id: string;
  company_id?: string;
  company_name: string | null;
  title: string;
  location: string | null;
  work_model: string | null;
  regime: string | null;
  seniority?: string | null;
  salary?: { min?: number | null; max?: number | null; currency?: string | null; period?: string | null } | null;
  requirements?: { must?: string[]; nice?: string[] } | null;
  apply_kind: string;
  apply_url?: string | null;
  canonical_url?: string | null;
  posted_at: string | null;
  first_seen_at: string;
  applicants_count: number | null;
  status: string;
  triage: string;
  score: Score | null;
  application_id: string | null;
  application_status: string | null;
};

const PERIOD: Record<string, string> = { month: "/mês", year: "/ano", hour: "/h" };

export function formatSalary(s: JobRow["salary"]): string | null {
  if (!s || (s.min == null && s.max == null)) return null;
  const cur = s.currency || "BRL";
  const fmt = (n: number) =>
    n.toLocaleString("pt-BR", { style: "currency", currency: cur, maximumFractionDigits: 0, notation: n >= 100000 ? "compact" : "standard" });
  const range = s.min != null && s.max != null && s.min !== s.max ? `${fmt(s.min)} – ${fmt(s.max)}` : fmt((s.max ?? s.min) as number);
  return `${range}${PERIOD[s.period ?? "month"] ?? ""}`;
}

/** Cartão de avaliação da vaga (docs/10 §7). */
export function JobCard({ job, onTech }: { job: JobRow; onTech?: (tech: string) => void }) {
  const inv = { invalidate: [["jobs"], ["dashboard"], ["facets"]] };
  const approve = useSend("POST", `/api/v1/jobs/${job.id}/approve`, { success: "Aprovada: preparando candidatura", ...inv });
  const skip = useSend("POST", `/api/v1/jobs/${job.id}/skip`, { success: "Descartada", ...inv });
  const fb = useSend<{ verdict: string }>("POST", `/api/v1/jobs/${job.id}/feedback`, { success: "Obrigado: isso ajusta as notas" });
  const s = job.score;
  const reasons = [...(s?.explanation.chance?.positives ?? []), ...(s?.explanation.attractiveness?.positives ?? [])].slice(0, 2);
  const negatives = [
    ...(s?.explanation.knockout ?? []),
    ...(s?.explanation.chance?.negatives ?? []),
    ...(s?.explanation.attractiveness?.negatives ?? []),
  ].slice(0, 2);
  const salary = formatSalary(job.salary);
  const techs = (job.requirements?.must ?? []).filter((t) => t.length <= 24).slice(0, 5);
  const link = job.apply_url || job.canonical_url;
  return (
    <Card interactive className="group flex h-full flex-col gap-3">
      <div className="flex items-start gap-3">
        <Avatar name={job.company_name} />
        <div className="min-w-0 flex-1">
          <Link href={`/vagas/${job.id}`} className="line-clamp-2 font-semibold leading-snug tracking-tight hover:text-primary">
            {job.title}
          </Link>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
            <span className="font-medium text-foreground/80">{job.company_name}</span>
            {job.location && (
              <span className="inline-flex items-center gap-0.5">
                · <MapPin size={11} /> {job.location}
              </span>
            )}
            <span>· {relativeTime(job.posted_at ?? job.first_seen_at)}</span>
          </p>
        </div>
        {s && (
          <div className="flex shrink-0 gap-2">
            <ScoreRing value={s.chance} label="Chance" size={42} />
            <ScoreRing value={s.attractiveness} label="Atrat." size={42} />
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {s && <Badge tone={QUADRANT_TONE[s.quadrant]}>{QUADRANT_LABEL[s.quadrant]}</Badge>}
        {job.work_model && <Badge>{WORK_MODEL_LABEL[job.work_model] ?? job.work_model}</Badge>}
        {job.regime && <Badge>{job.regime}</Badge>}
        {job.seniority && <Badge>{SENIORITY_LABEL[job.seniority] ?? job.seniority}</Badge>}
        {job.apply_kind === "easy_apply" && <Badge tone="primary">Easy Apply</Badge>}
        {salary && <Badge tone="success">{salary}</Badge>}
        {job.application_status && job.application_status !== "discovered" && <Badge tone="primary">{STATUS_LABEL[job.application_status]}</Badge>}
      </div>

      {techs.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {techs.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => onTech?.(t)}
              title={onTech ? `Filtrar por ${t}` : t}
              className={cn(
                "rounded-md border border-dashed px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors",
                onTech && "hover:border-primary hover:text-primary",
              )}
            >
              {t}
            </button>
          ))}
        </div>
      )}

      {s ? (
        <ul className="space-y-0.5 text-xs">
          {reasons.map((r) => (
            <li key={r} className="flex gap-1.5 text-success">
              <Check size={13} className="mt-0.5 shrink-0" /> <span className="line-clamp-1">{r}</span>
            </li>
          ))}
          {negatives.map((r) => (
            <li key={r} className="flex gap-1.5 text-danger">
              <X size={13} className="mt-0.5 shrink-0" /> <span className="line-clamp-1">{r}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">Avaliando…</p>
      )}

      <div className="mt-auto flex items-center gap-1.5 border-t pt-3">
        <Button size="sm" onClick={() => approve.mutate(undefined)} disabled={approve.isPending || s?.quadrant === "blocked"}>
          <Check size={14} /> Aprovar
        </Button>
        <Button size="sm" variant="outline" onClick={() => skip.mutate(undefined)}>
          Descartar
        </Button>
        <div className="flex-1" />
        <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => fb.mutate({ verdict: "good" })} aria-label="Gostei desta vaga">
          <ThumbsUp size={14} />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8"
          onClick={() => fb.mutate({ verdict: "not_interested" })}
          aria-label="Não me interessa"
        >
          <ThumbsDown size={14} />
        </Button>
        {link && (
          <a
            href={link}
            target="_blank"
            rel="noreferrer"
            className="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Abrir anúncio original"
          >
            <ExternalLink size={14} />
          </a>
        )}
      </div>
    </Card>
  );
}
