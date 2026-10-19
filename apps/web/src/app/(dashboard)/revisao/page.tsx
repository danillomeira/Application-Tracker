"use client";

import { MessageSquareText } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Badge, Button, Card, CardTitle, EmptyState, Input, PageHeader, Select } from "@/components/ui";
import { useGet, useSend } from "@/lib/hooks";
import { QUADRANT_LABEL, QUADRANT_TONE } from "@/lib/labels";
import { formatDateTime, relativeTime } from "@/lib/utils";
import { useLiveEvents, type TrackerEvent } from "@/lib/ws";

type Review = { id: string; job_title: string; company_name: string; quadrant: string | null; next_action: string | null; last_activity_at: string };
type Pending = {
  id: string;
  application_id: string;
  question_text: string;
  field_kind: string;
  options: string[];
  ai_suggestion: { value?: string } | null;
  company_name: string;
  job_title: string;
  expires_at: string | null;
};
type AgentJob = { id: string; kind: string; status: string; error: string | null; application_id: string | null; artifacts: { key: string; name: string }[]; updated_at: string };
type AgentStatus = { blocked: string | null; in_window: boolean; running: AgentJob[]; queue: AgentJob[]; recent: AgentJob[]; safety_note: string | null; last_login_ok_at: string | null };

export default function ReviewPage() {
  return (
    <div className="space-y-6">
      <PageHeader icon={<MessageSquareText size={20} />} title="Revisão e pendências" description="Atalhos na fila: J/K navegar · A aprovar · D descartar" />
      <div className="grid gap-4 xl:grid-cols-2">
        <ReviewQueue />
        <PendingQuestions />
      </div>
      <AgentLive />
    </div>
  );
}

function ReviewQueue() {
  const { data } = useGet<Review[]>(["applications", "review"], "/api/v1/review-queue");
  const approve = useSend<{ ids: string[] }>("POST", "/api/v1/review-queue/approve", {
    success: "Aprovado: o robô vai enviar na próxima passada",
    invalidate: [["applications"], ["dashboard"]],
  });
  const skip = useSend<{ id: string; status: string }>("PATCH", (v) => `/api/v1/applications/${v.id}`, {
    success: "Descartada",
    invalidate: [["applications"]],
  });
  const [idx, setIdx] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const items = useMemo(() => data ?? [], [data]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName.match(/INPUT|TEXTAREA|SELECT/)) return;
      const cur = items[idx];
      if (e.key === "j") setIdx((i) => Math.min(i + 1, items.length - 1));
      if (e.key === "k") setIdx((i) => Math.max(i - 1, 0));
      if (e.key === "a" && cur) approve.mutate({ ids: [cur.id] });
      if (e.key === "d" && cur) skip.mutate({ id: cur.id, status: "skipped" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, idx, approve, skip]);
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <CardTitle className="mb-0">Fila de revisão ({items.length})</CardTitle>
        {selected.size > 0 && <Button size="sm" onClick={() => { approve.mutate({ ids: [...selected] }); setSelected(new Set()); }}>Aprovar {selected.size} selecionadas</Button>}
      </div>
      {items.length === 0 ? (
        <EmptyState title="Nada para revisar" />
      ) : (
        <ul className="space-y-2">
          {items.map((a, i) => (
            <li key={a.id} className={`flex items-center gap-2 rounded-md border p-2 text-sm ${i === idx ? "border-primary" : ""}`}>
              <input
                type="checkbox"
                aria-label="selecionar"
                checked={selected.has(a.id)}
                onChange={(e) => { const s = new Set(selected); if (e.target.checked) s.add(a.id); else s.delete(a.id); setSelected(s); }}
              />
              <div className="flex-1">
                <Link href={`/candidaturas/${a.id}`} className="font-medium hover:underline">{a.job_title} · {a.company_name}</Link>
                <p className="text-xs text-muted-foreground">{a.next_action ?? "aguardando sua aprovação"} · {relativeTime(a.last_activity_at)}</p>
              </div>
              {a.quadrant && <Badge tone={QUADRANT_TONE[a.quadrant]}>{QUADRANT_LABEL[a.quadrant]}</Badge>}
              <Button size="sm" onClick={() => approve.mutate({ ids: [a.id] })}>Aprovar</Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function PendingQuestions() {
  const { data } = useGet<Pending[]>(["pending"], "/api/v1/pending-questions");
  return (
    <Card>
      <CardTitle>Perguntas pendentes ({data?.length ?? 0})</CardTitle>
      {!data?.length ? (
        <EmptyState title="Nenhuma pergunta pendente" />
      ) : (
        <div className="space-y-3">{data.map((p) => <PendingItem key={p.id} p={p} />)}</div>
      )}
    </Card>
  );
}

function PendingItem({ p }: { p: Pending }) {
  const [value, setValue] = useState(p.ai_suggestion?.value ?? "");
  const [save, setSave] = useState(true);
  const answer = useSend<{ value: string; save_to_bank: boolean }>("POST", `/api/v1/pending-questions/${p.id}/answer`, {
    success: "Respondida: a candidatura volta para a fila",
    invalidate: [["pending"], ["applications"], ["dashboard"]],
  });
  return (
    <div className="rounded-md border p-3 text-sm">
      <p className="text-xs text-muted-foreground">{p.company_name} · {p.job_title}{p.expires_at ? ` · expira ${formatDateTime(p.expires_at)}` : ""}</p>
      <p className="font-medium">{p.question_text}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {p.options.length > 0 ? (
          <Select value={value} onChange={(e) => setValue(e.target.value)} className="max-w-xs">
            <option value="">Escolha…</option>
            {p.options.map((o) => <option key={o}>{o}</option>)}
          </Select>
        ) : (
          <Input value={value} onChange={(e) => setValue(e.target.value)} className="max-w-md" placeholder={p.field_kind === "number" ? "número" : "resposta"} />
        )}
        <label className="flex items-center gap-1 text-xs">
          <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} /> salvar no banco de respostas
        </label>
        <Button size="sm" disabled={!value} onClick={() => answer.mutate({ value, save_to_bank: save })}>Responder</Button>
      </div>
      {p.ai_suggestion?.value && <p className="mt-1 text-xs text-muted-foreground">Sugestão da IA (baixa confiança): {p.ai_suggestion.value}</p>}
    </div>
  );
}

function AgentLive() {
  const { data, refetch } = useGet<AgentStatus>(["agent", "status"], "/api/v1/agent-control/status", { refetchInterval: 10000 });
  const [steps, setSteps] = useState<TrackerEvent[]>([]);
  useLiveEvents((e) => {
    if (e.channel !== "agent") return;
    if (e.type === "agent.step") setSteps((s) => [e, ...s].slice(0, 30));
    refetch();
  });
  const cancel = useSend<string>("POST", (id) => `/api/v1/agent-control/jobs/${id}/cancel`, { invalidate: [["agent"]] });
  if (!data) return null;
  const shot = (key?: string) => (key ? `/api/v1/agent-control/artifacts?key=${encodeURIComponent(key)}` : null);
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardTitle>Robô ao vivo</CardTitle>
        <p className="text-sm">
          Estado: {data.blocked ? <span className="text-danger">{data.blocked}</span> : data.running.length ? "trabalhando" : data.in_window ? "ocioso" : "fora da janela de horário"}
        </p>
        {data.safety_note && <p className="text-xs text-danger">Última parada de segurança: {data.safety_note}</p>}
        <p className="text-xs text-muted-foreground">Login no LinkedIn confirmado: {formatDateTime(data.last_login_ok_at)} · rode <code>tracker-agent login</code> se expirar</p>
        <ul className="mt-3 max-h-80 space-y-2 overflow-auto text-sm">
          {steps.map((s, i) => (
            <li key={i} className="border-l-2 pl-2">
              <p>{String(s.data.title)} <span className="text-xs text-muted-foreground">{String(s.data.log ?? "")}</span></p>
              {typeof s.data.screenshot_key === "string" && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={shot(s.data.screenshot_key) ?? ""} alt="screenshot da etapa" className="mt-1 max-h-48 rounded border" />
              )}
            </li>
          ))}
          {steps.length === 0 && <li className="text-xs text-muted-foreground">As etapas aparecem aqui em tempo real.</li>}
        </ul>
      </Card>
      <Card>
        <CardTitle>Fila do robô ({data.queue.length})</CardTitle>
        <ul className="space-y-1 text-sm">
          {[...data.running, ...data.queue].map((j) => (
            <li key={j.id} className="flex items-center justify-between gap-2">
              <span>
                <Badge tone={j.status === "running" || j.status === "leased" ? "success" : j.status === "paused" ? "warning" : "neutral"}>{j.status}</Badge>{" "}
                {j.kind} {j.application_id && <Link className="text-primary underline" href={`/candidaturas/${j.application_id}`}>candidatura</Link>}
                {j.error && <span className="text-xs text-danger"> · {j.error}</span>}
              </span>
              <Button size="sm" variant="ghost" onClick={() => cancel.mutate(j.id)}>Cancelar</Button>
            </li>
          ))}
        </ul>
        <CardTitle className="mt-4">Recentes</CardTitle>
        <ul className="space-y-1 text-xs">
          {data.recent.map((j) => (
            <li key={j.id}>
              {j.kind} · {j.status} · {relativeTime(j.updated_at)}{j.error ? ` · ${j.error}` : ""}
              {j.artifacts.at(-1) && (
                <a className="ml-1 text-primary underline" href={shot(j.artifacts.at(-1)?.key) ?? "#"} target="_blank" rel="noreferrer">última tela</a>
              )}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
