"use client";

import { CompanyLogo } from "@/components/brand";
import Link from "next/link";
import { use } from "react";
import { Badge, Button, Card, CardTitle, PageHeader, ScoreBar, Skeleton } from "@/components/ui";
import { useGet, useSend, useTask } from "@/lib/hooks";
import { QUADRANT_LABEL, QUADRANT_TONE, STATUS_LABEL } from "@/lib/labels";
import { formatDateTime, money } from "@/lib/utils";

type Breakdown = Record<string, { value: number; weight: number; contribution: number; evidence: string; missing: boolean; sources: string[] }>;
type JobDetail = {
  id: string;
  title: string;
  company_id: string;
  company_name: string;
  location: string | null;
  work_model: string | null;
  regime: string | null;
  seniority: string | null;
  salary: { min?: number; max?: number; currency?: string; period?: string } | null;
  requirements: { must?: string[]; nice?: string[] };
  benefits: string[];
  description_text: string;
  apply_url: string | null;
  canonical_url: string | null;
  apply_kind: string;
  ats_kind: string | null;
  repost_count: number;
  status: string;
  application_id: string | null;
  application_status: string | null;
  sources: { source: string; url: string | null; seen_at: string }[];
  snapshots: { id: string; reason: string; captured_at: string }[];
  extra: { cover_letter?: { text: string }; hard_blockers?: string[]; scam_signals?: string[] };
  score: {
    chance: number;
    attractiveness: number;
    quadrant: string;
    suggested_action: string;
    chance_breakdown: Breakdown;
    attractiveness_breakdown: Breakdown;
    knockout: { passed: boolean; reasons: string[] };
    explanation: { missing_must?: string[]; responsiveness?: { rate: number; confidence: string } };
    variant_scores: Record<string, number | boolean | null>;
  } | null;
};

const FEATURE_LABEL: Record<string, string> = {
  fit_tecnico: "Aderência técnica", senioridade: "Senioridade", concorrencia: "Concorrência", frescor: "Frescor",
  responsividade: "Responsividade", recrutador_ativo: "Recrutador ativo", nao_fantasma: "Sinais de vaga fantasma", conexoes: "Conexões",
  reputacao: "Reputação", cultura: "Cultura", saude: "Saúde da empresa", remuneracao: "Remuneração", carreira: "Carreira",
  condicoes: "Condições", alinhamento: "Alinhamento",
};

function BreakdownTable({ data }: { data: Breakdown }) {
  return (
    <table className="w-full text-xs">
      <tbody>
        {Object.entries(data).map(([k, v]) => (
          <tr key={k} className="border-t align-top">
            <td className="w-36 py-1 font-medium">{FEATURE_LABEL[k] ?? k}</td>
            <td className="w-24 py-1"><ScoreBar label="" value={v.value * 100} /></td>
            <td className="py-1 pl-2 text-muted-foreground">
              {v.evidence} {v.missing && <Badge>sem dados</Badge>}
              {v.sources?.map((s) => <a key={s} href={s} target="_blank" rel="noreferrer" className="ml-1 text-primary underline">fonte</a>)}
            </td>
            <td className="w-12 py-1 text-right">{Math.round(v.weight * 100)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: job, refetch } = useGet<JobDetail>(["jobs", id], `/api/v1/jobs/${id}`);
  const tailorTask = useTask(() => refetch());
  const profileTask = useTask(() => refetch());
  const approve = useSend("POST", `/api/v1/jobs/${id}/approve`, { success: "Aprovada", invalidate: [["jobs"]] });
  const rescore = useSend("POST", `/api/v1/jobs/${id}/rescore`, { success: "Reavaliação agendada" });
  const tailor = useSend<{ job_id: string }, { task_id: string }>("POST", "/api/v1/resumes/variants/tailored");
  const letter = useSend<void, { task_id: string }>("POST", `/api/v1/resumes/cover-letter?job_id=${id}`);
  const profile = useSend<void, { task_id: string }>("POST", job ? `/api/v1/companies/${job.company_id}/refresh-profile` : "");
  if (!job) return <Skeleton className="h-96" />;
  const s = job.score;
  return (
    <div className="space-y-4">
      <PageHeader
        media={<CompanyLogo id={job.company_id} name={job.company_name} className="h-12 w-12" />}
        title={job.title}
        description={`${job.company_name} · ${job.location ?? "—"} · ${job.work_model ?? "modelo n/d"}${job.regime ? ` · ${job.regime}` : ""}`}
        actions={
          <>
            {job.application_id ? (
              <Link href={`/candidaturas/${job.application_id}`}><Button variant="outline">Candidatura: {STATUS_LABEL[job.application_status ?? ""]}</Button></Link>
            ) : null}
            <Button onClick={() => approve.mutate(undefined)} disabled={s?.quadrant === "blocked"}>Aprovar</Button>
            <Button variant="outline" disabled={tailorTask.running} onClick={async () => tailorTask.start((await tailor.mutateAsync({ job_id: id })).task_id)}>
              {tailorTask.running ? `CV: ${tailorTask.progress?.message}` : "Gerar CV específico"}
            </Button>
            <Button variant="outline" onClick={async () => tailorTask.start((await letter.mutateAsync()).task_id)}>Carta</Button>
            <Button variant="ghost" onClick={() => rescore.mutate(undefined)}>Reavaliar</Button>
          </>
        }
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {s && (
            <Card className="space-y-3">
              <div className="flex items-center gap-2">
                <Badge tone={QUADRANT_TONE[s.quadrant]}>{QUADRANT_LABEL[s.quadrant]}</Badge>
                <span className="text-sm">{s.suggested_action}</span>
              </div>
              {!s.knockout.passed && (
                <ul className="text-sm text-danger">{s.knockout.reasons.map((r) => <li key={r}>✕ {r}</li>)}</ul>
              )}
              <ScoreBar label="Chance" value={s.chance} />
              <BreakdownTable data={s.chance_breakdown} />
              <ScoreBar label="Atratividade" value={s.attractiveness} />
              <BreakdownTable data={s.attractiveness_breakdown} />
              {s.explanation.missing_must?.length ? (
                <p className="text-xs">Requisitos obrigatórios que você não tem: <b>{s.explanation.missing_must.join(", ")}</b></p>
              ) : null}
            </Card>
          )}
          <Card>
            <CardTitle>Descrição</CardTitle>
            <p className="whitespace-pre-wrap text-sm">{job.description_text}</p>
          </Card>
        </div>
        <div className="space-y-4">
          <Card className="space-y-2 text-sm">
            <CardTitle>Resumo</CardTitle>
            <p><b>Obrigatórios:</b> {job.requirements.must?.join(", ") || "—"}</p>
            <p><b>Desejáveis:</b> {job.requirements.nice?.join(", ") || "—"}</p>
            <p><b>Senioridade:</b> {job.seniority ?? "—"}</p>
            <p><b>Salário:</b> {job.salary?.max ? `${money(job.salary.min, job.salary.currency)} – ${money(job.salary.max, job.salary.currency)} / ${job.salary.period}` : "não informado"}</p>
            <p><b>Candidatura:</b> {job.apply_kind}{job.ats_kind ? ` (${job.ats_kind})` : ""}</p>
            {job.repost_count > 0 && <p className="text-warning">Repostada {job.repost_count}x</p>}
            {job.extra.scam_signals?.length ? <p className="text-danger">Sinais de golpe: {job.extra.scam_signals.join(", ")}</p> : null}
            {(job.apply_url || job.canonical_url) && (
              <a className="text-primary underline" href={job.apply_url ?? job.canonical_url ?? "#"} target="_blank" rel="noreferrer">Abrir vaga original</a>
            )}
          </Card>
          <Card className="space-y-2 text-sm">
            <CardTitle>Empresa</CardTitle>
            <p>{job.company_name}</p>
            {s?.explanation.responsiveness && (
              <p className="text-xs text-muted-foreground">
                Responde ~{Math.round(s.explanation.responsiveness.rate * 100)}% (confiança {s.explanation.responsiveness.confidence})
              </p>
            )}
            <Button size="sm" variant="outline" disabled={profileTask.running} onClick={async () => profileTask.start((await profile.mutateAsync()).task_id)}>
              {profileTask.running ? "Pesquisando…" : "Pesquisar reputação e cultura"}
            </Button>
          </Card>
          {job.extra.cover_letter && (
            <Card>
              <CardTitle>Carta de apresentação</CardTitle>
              <p className="whitespace-pre-wrap text-sm">{job.extra.cover_letter.text}</p>
            </Card>
          )}
          <Card className="text-xs">
            <CardTitle>Fontes e snapshots</CardTitle>
            {job.sources.map((src) => (
              <p key={src.source + src.seen_at}>{src.source} · {formatDateTime(src.seen_at)} {src.url && <a href={src.url} className="text-primary underline" target="_blank" rel="noreferrer">link</a>}</p>
            ))}
            {job.snapshots.map((sn) => <p key={sn.id}>snapshot {sn.reason} · {formatDateTime(sn.captured_at)}</p>)}
          </Card>
        </div>
      </div>
    </div>
  );
}
