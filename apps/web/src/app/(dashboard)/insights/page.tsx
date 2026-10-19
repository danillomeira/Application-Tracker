"use client";

import { BarChart3 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, CardTitle, PageHeader, Select, Stat, Tabs, Textarea } from "@/components/ui";
import { useGet, useSend, useTask } from "@/lib/hooks";
import { formatDateTime } from "@/lib/utils";

type Funnel = { found: number; evaluated: number; submitted: number; responded: number; interviewing: number; assessment: number; offer: number; response_rate: number; interview_rate: number };
type Row = { key: string; sent: number; responses: number; positive: number; response_rate: number; positive_rate: number };
type Gap = { skill: string; jobs: number; share: number; trend: string };
type Goals = { applications: { done: number; target: number }; followups: { done: number; target: number }; alerts: string[] };
type Weekly = { headline?: string; highlights?: string[]; recommendations?: string[]; generated_at?: string };
type Study = { items: { skill: string; why: string; resources: string[]; effort_hours: number }[]; generated_at: string } | null;
type Linkedin = { suggestions: { section: string; current?: string | null; suggested: string; why: string }[]; generated_at: string } | null;
type Usage = { month_spend_usd: number; budget_usd: number; by_task: { task: string; calls: number; cost_usd: number }[] };

const pct = (v: number) => `${Math.round(v * 100)}%`;

export default function InsightsPage() {
  const [tab, setTab] = useState<"funil" | "aprendizado" | "perfil" | "custo">("funil");
  return (
    <div>
      <PageHeader icon={<BarChart3 size={20} />} title="Insights" description="O que está funcionando, o que falta e para onde ir" />
      <Tabs value={tab} onChange={setTab} items={[{ value: "funil", label: "Funil e desempenho" }, { value: "aprendizado", label: "Gaps e estudo" }, { value: "perfil", label: "Perfil do LinkedIn" }, { value: "custo", label: "Custo de IA" }]} />
      {tab === "funil" && <FunnelTab />}
      {tab === "aprendizado" && <LearnTab />}
      {tab === "perfil" && <LinkedinTab />}
      {tab === "custo" && <CostTab />}
    </div>
  );
}

function FunnelTab() {
  const [days, setDays] = useState(30);
  const { data: f } = useGet<Funnel>(["insights", "funnel", days], `/api/v1/insights/funnel?days=${days}`);
  const { data: perf } = useGet<Record<string, Row[]>>(["insights", "perf"], "/api/v1/insights/performance");
  const { data: goals } = useGet<Goals>(["insights", "goals"], "/api/v1/insights/goals");
  const { data: weekly } = useGet<Weekly>(["insights", "weekly"], "/api/v1/insights/weekly-report");
  const { data: rej } = useGet<{ total: number; by_stage: Record<string, number>; reasons: string[] }>(["insights", "rej"], "/api/v1/insights/rejections");
  const regen = useSend("POST", "/api/v1/insights/weekly-report", { success: "Relatório sendo gerado" });
  const [dim, setDim] = useState("by_resume");
  const stages: [keyof Funnel, string][] = [["found", "Vagas encontradas"], ["evaluated", "Avaliadas"], ["submitted", "Candidaturas"], ["responded", "Respostas"], ["interviewing", "Entrevistas"], ["assessment", "Testes"], ["offer", "Ofertas"]];
  const max = Math.max(1, ...(f ? stages.map(([k]) => Number(f[k])) : [1]));
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-4">
        <Stat label="Taxa de resposta" value={f ? pct(f.response_rate) : "—"} />
        <Stat label="Taxa de entrevista" value={f ? pct(f.interview_rate) : "—"} />
        <Stat label="Meta semanal" value={goals ? `${goals.applications.done}/${goals.applications.target}` : "—"} hint="candidaturas" />
        <Stat label="Follow-ups na semana" value={goals ? `${goals.followups.done}/${goals.followups.target}` : "—"} />
      </div>
      {goals?.alerts.map((a) => <Card key={a} className="border-warning text-sm">{a}</Card>)}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <CardTitle className="mb-0">Funil</CardTitle>
            <Select value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-32"><option value={7}>7 dias</option><option value={30}>30 dias</option><option value={90}>90 dias</option></Select>
          </div>
          <ul className="space-y-2" aria-label="funil">
            {f && stages.map(([k, label]) => (
              <li key={k} className="text-sm">
                <div className="flex justify-between"><span>{label}</span><span className="font-medium">{f[k]}</span></div>
                <div className="h-2 rounded bg-muted"><div className="h-2 rounded bg-primary" style={{ width: `${(Number(f[k]) / max) * 100}%` }} /></div>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <CardTitle className="mb-0">Relatório semanal</CardTitle>
            <Button size="sm" variant="outline" onClick={() => regen.mutate(undefined)}>Gerar agora</Button>
          </div>
          {weekly?.headline ? (
            <>
              <p className="font-medium">{weekly.headline}</p>
              <ul className="mt-2 list-disc pl-5 text-sm">{weekly.highlights?.map((h) => <li key={h}>{h}</li>)}</ul>
              <p className="mt-2 text-sm font-medium">Recomendações</p>
              <ol className="list-decimal pl-5 text-sm">{weekly.recommendations?.map((r) => <li key={r}>{r}</li>)}</ol>
              <p className="mt-2 text-xs text-muted-foreground">{formatDateTime(weekly.generated_at)}</p>
            </>
          ) : <p className="text-sm text-muted-foreground">Gerado toda segunda às 8h.</p>}
        </Card>
      </div>
      <Card>
        <div className="mb-2 flex items-center justify-between">
          <CardTitle className="mb-0">Desempenho</CardTitle>
          <Select value={dim} onChange={(e) => setDim(e.target.value)} className="w-56">
            <option value="by_resume">por currículo</option><option value="by_quadrant">por quadrante</option><option value="by_source">por fonte</option>
            <option value="by_channel">por canal</option><option value="by_weekday">por dia da semana</option><option value="by_hour">por hora de envio</option>
          </Select>
        </div>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground"><tr><th className="p-1">Grupo</th><th>Enviadas</th><th>Respostas</th><th>Positivas</th><th>Taxa de resposta</th></tr></thead>
          <tbody>{perf?.[dim]?.map((r) => <tr key={r.key} className="border-t"><td className="p-1">{r.key}</td><td>{r.sent}</td><td>{r.responses}</td><td>{r.positive}</td><td>{pct(r.response_rate)}</td></tr>)}</tbody>
        </table>
      </Card>
      {rej && rej.total > 0 && (
        <Card className="text-sm">
          <CardTitle>Rejeições ({rej.total})</CardTitle>
          <p>{Object.entries(rej.by_stage).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>
          <ul className="mt-2 list-disc pl-5 text-xs">{rej.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </Card>
      )}
    </div>
  );
}

function LearnTab() {
  const qc = useQueryClient();
  const { data: gaps } = useGet<Gap[]>(["insights", "gaps"], "/api/v1/insights/skill-gaps");
  const { data: plan } = useGet<Study>(["insights", "study"], "/api/v1/insights/study-plan");
  const { data: wild } = useGet<{ cluster: string; jobs: number; suggestion: string }[]>(["insights", "wild"], "/api/v1/insights/wildcard-suggestions");
  const make = useSend<void, { task_id: string }>("POST", "/api/v1/insights/study-plan");
  const task = useTask(() => qc.invalidateQueries({ queryKey: ["insights", "study"] }));
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardTitle>Requisitos que mais faltam nas vagas que você mira</CardTitle>
        <table className="w-full text-sm">
          <tbody>{gaps?.map((g) => <tr key={g.skill} className="border-t"><td className="py-1">{g.skill}</td><td>{g.jobs} vagas</td><td>{pct(g.share)}</td><td><Badge tone={g.trend === "subindo" ? "warning" : "neutral"}>{g.trend}</Badge></td></tr>)}</tbody>
        </table>
        {!gaps?.length && <p className="text-sm text-muted-foreground">Sem dados ainda.</p>}
        {wild && wild.length > 0 && (
          <>
            <CardTitle className="mt-4">Sugestões de novos coringas</CardTitle>
            <ul className="list-disc pl-5 text-sm">{wild.map((w) => <li key={w.cluster}>{w.suggestion}</li>)}</ul>
          </>
        )}
      </Card>
      <Card>
        <div className="mb-2 flex items-center justify-between">
          <CardTitle className="mb-0">Plano de estudo</CardTitle>
          <Button size="sm" disabled={task.running} onClick={async () => task.start((await make.mutateAsync()).task_id)}>{task.running ? "Gerando…" : "Gerar plano"}</Button>
        </div>
        {plan?.items?.map((i) => (
          <div key={i.skill} className="mb-3 text-sm">
            <p className="font-medium">{i.skill} <Badge>{i.effort_hours} h</Badge></p>
            <p className="text-muted-foreground">{i.why}</p>
            <ul className="list-disc pl-5 text-xs">{i.resources.map((r) => <li key={r}>{r}</li>)}</ul>
          </div>
        ))}
      </Card>
    </div>
  );
}

function LinkedinTab() {
  const qc = useQueryClient();
  const { data } = useGet<Linkedin>(["insights", "linkedin"], "/api/v1/insights/linkedin-profile");
  const [current, setCurrent] = useState("");
  const make = useSend<{ current_profile: string }, { task_id: string }>("POST", "/api/v1/insights/linkedin-profile");
  const task = useTask(() => qc.invalidateQueries({ queryKey: ["insights", "linkedin"] }));
  return (
    <div className="space-y-4">
      <Card className="space-y-2">
        <CardTitle>Otimizar o perfil do LinkedIn</CardTitle>
        <Textarea rows={6} placeholder="Cole aqui o texto atual do seu perfil (título, sobre, experiências) — opcional" value={current} onChange={(e) => setCurrent(e.target.value)} />
        <Button disabled={task.running} onClick={async () => task.start((await make.mutateAsync({ current_profile: current })).task_id)}>{task.running ? "Analisando…" : "Gerar sugestões"}</Button>
      </Card>
      {data?.suggestions?.map((s, i) => (
        <Card key={i} className="space-y-1 text-sm">
          <Badge>{s.section}</Badge>
          {s.current && <p className="text-muted-foreground line-through">{s.current}</p>}
          <p className="whitespace-pre-wrap">{s.suggested}</p>
          <p className="text-xs text-muted-foreground">{s.why}</p>
          <Button size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(s.suggested)}>Copiar</Button>
        </Card>
      ))}
    </div>
  );
}

function CostTab() {
  const { data } = useGet<Usage>(["ai", "usage"], "/api/v1/ai/usage");
  if (!data) return null;
  const share = data.budget_usd ? data.month_spend_usd / data.budget_usd : 0;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        <Stat label="Gasto no mês" value={`US$ ${data.month_spend_usd.toFixed(2)}`} hint={`orçamento US$ ${data.budget_usd}`} />
        <Stat label="Uso do orçamento" value={pct(share)} />
        <Stat label="Chamadas (30 dias)" value={data.by_task.reduce((a, t) => a + t.calls, 0)} />
      </div>
      <Card>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground"><tr><th className="p-1">Tarefa</th><th>Chamadas</th><th>Custo (US$)</th></tr></thead>
          <tbody>{data.by_task.map((t) => <tr key={t.task} className="border-t"><td className="p-1">{t.task}</td><td>{t.calls}</td><td>{t.cost_usd.toFixed(4)}</td></tr>)}</tbody>
        </table>
      </Card>
    </div>
  );
}
