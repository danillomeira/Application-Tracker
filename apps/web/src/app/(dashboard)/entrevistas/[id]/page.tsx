"use client";

import { CompanyLogo } from "@/components/brand";
import { useQuery as useRQ, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { Badge, Button, Card, CardTitle, EmptyState, Field, Input, PageHeader, Select, Skeleton, Tabs, Textarea } from "@/components/ui";
import { rawFetch } from "@/lib/api";
import { useGet, useSend, useTask } from "@/lib/hooks";
import { INTERVIEW_KIND } from "@/lib/labels";
import { formatDateTime } from "@/lib/utils";

type Claim = { text: string; source_urls: string[] };
type Dossier = {
  job_summary: { responsibilities: string[]; must: string[]; nice: string[]; what_team_values: string[] };
  match: { requirement: string; experience_id: string; what_to_say: string; star_story_title?: string | null }[];
  gaps: { requirement: string; honest_approach: string }[];
  company: { overview: string; history: Claim[]; products: string[]; business_model?: string | null; competitors: string[]; tech_stack: string[]; news: Claim[] };
  mission?: string | null;
  values: { value: string; how_to_connect: string; source_urls: string[] }[];
  interviewers: { name: string; role?: string | null; notes?: string | null }[];
  likely_questions: { question: string; type: string; answer_outline: string }[];
  questions_to_ask: string[];
  logistics: { when?: string | null; link?: string | null; duration?: string | null; format?: string | null; what_to_bring: string[] };
  points_to_defend: string[];
  sources: { url: string; title?: string | null }[];
};
type InterviewDetail = {
  id: string;
  application_id: string;
  round: number;
  kind: string;
  starts_at: string | null;
  company_name: string;
  job_title: string;
  link: string | null;
  post_notes: { questions?: string[]; feeling?: string; highlights?: string; next_steps?: string } | null;
  self_rating: number | null;
  dossier: { status: string; content: Dossier; generated_at: string } | null;
  mock_sessions: { id: string; status: string; kind: string }[];
};
type Turn = { feedback: { overall: number; star_structure: number; clarity: number; evidence: number; strengths: string[]; improvements: string[]; better_answer_outline: string } | null; next_question: string | null; done: boolean; final_summary: string | null };

const Src = ({ urls }: { urls: string[] }) => (
  <>{urls.map((u, i) => <a key={u} href={u} target="_blank" rel="noreferrer" className="ml-1 text-xs text-primary underline">[{i + 1}]</a>)}</>
);

export default function InterviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const qc = useQueryClient();
  const { data } = useGet<InterviewDetail>(["interviews", id], `/api/v1/interviews/${id}`);
  const [tab, setTab] = useState<"dossie" | "cola" | "simulacao" | "pos">("dossie");
  const regen = useSend<void, { task_id: string }>("POST", `/api/v1/interviews/${id}/dossier`);
  const task = useTask(() => qc.invalidateQueries({ queryKey: ["interviews", id] }));
  if (!data) return <Skeleton className="h-96" />;
  const d = data.dossier?.content;
  return (
    <div className="space-y-4">
      <PageHeader
        media={<CompanyLogo name={data.company_name} className="h-12 w-12" />}
        title={`${data.company_name} · ${data.job_title}`}
        description={`${data.round}ª etapa · ${INTERVIEW_KIND[data.kind] ?? data.kind} · ${formatDateTime(data.starts_at)}`}
        actions={
          <>
            {data.link && <a href={data.link} target="_blank" rel="noreferrer"><Button>Entrar na chamada</Button></a>}
            <Link href={`/candidaturas/${data.application_id}`}><Button variant="outline">Candidatura</Button></Link>
            <Button variant="outline" disabled={task.running} onClick={async () => task.start((await regen.mutateAsync()).task_id)}>
              {task.running ? task.progress?.message ?? "Gerando…" : "Regenerar dossiê"}
            </Button>
          </>
        }
      />
      <Tabs value={tab} onChange={setTab} items={[{ value: "dossie", label: "Dossiê" }, { value: "cola", label: "Página de cola" }, { value: "simulacao", label: "Simulação" }, { value: "pos", label: "Pós-entrevista" }]} />
      {tab === "dossie" && (!d ? <EmptyState title={data.dossier?.status === "running" ? "Dossiê em preparação…" : "Dossiê ainda não gerado"} /> : <DossierView d={d} />)}
      {tab === "cola" && <Cheatsheet id={id} />}
      {tab === "simulacao" && <Mock applicationId={data.application_id} kind={data.kind} />}
      {tab === "pos" && <PostNotes id={id} data={data} />}
    </div>
  );
}

function DossierView({ d }: { d: Dossier }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardTitle>A vaga</CardTitle>
        <p className="text-sm"><b>Responsabilidades:</b> {d.job_summary.responsibilities.join("; ")}</p>
        <p className="text-sm"><b>Obrigatórios:</b> {d.job_summary.must.join(", ")}</p>
        <p className="text-sm"><b>O time valoriza:</b> {d.job_summary.what_team_values.join(", ")}</p>
      </Card>
      <Card>
        <CardTitle>Logística</CardTitle>
        <p className="text-sm">{d.logistics.when} · {d.logistics.duration} · {d.logistics.format}</p>
        {d.logistics.what_to_bring.length > 0 && <ul className="list-disc pl-5 text-sm">{d.logistics.what_to_bring.map((x) => <li key={x}>{x}</li>)}</ul>}
      </Card>
      <Card className="lg:col-span-2">
        <CardTitle>Seus pontos de match</CardTitle>
        <ul className="space-y-2 text-sm">
          {d.match.map((m) => (
            <li key={m.requirement}><b>{m.requirement}</b> <Badge>{m.experience_id}</Badge>{m.star_story_title && <Badge tone="primary">STAR: {m.star_story_title}</Badge>}<br />{m.what_to_say}</li>
          ))}
        </ul>
        {d.gaps.length > 0 && (
          <>
            <CardTitle className="mt-4">Gaps (com honestidade)</CardTitle>
            <ul className="space-y-1 text-sm">{d.gaps.map((g) => <li key={g.requirement}><b>{g.requirement}:</b> {g.honest_approach}</li>)}</ul>
          </>
        )}
        {d.points_to_defend.length > 0 && (
          <>
            <CardTitle className="mt-4">Esteja pronto para defender</CardTitle>
            <ul className="list-disc pl-5 text-sm">{d.points_to_defend.map((p) => <li key={p}>{p}</li>)}</ul>
          </>
        )}
      </Card>
      <Card>
        <CardTitle>A empresa</CardTitle>
        <p className="text-sm">{d.company.overview}</p>
        {d.mission && <p className="mt-2 text-sm"><b>Missão:</b> {d.mission}</p>}
        <ul className="mt-2 space-y-1 text-sm">{d.company.history.map((h) => <li key={h.text}>• {h.text}<Src urls={h.source_urls} /></li>)}</ul>
        {d.company.products.length > 0 && <p className="mt-2 text-sm"><b>Produtos:</b> {d.company.products.join(", ")}</p>}
        {d.company.tech_stack.length > 0 && <p className="text-sm"><b>Stack:</b> {d.company.tech_stack.join(", ")}</p>}
        {d.company.competitors.length > 0 && <p className="text-sm"><b>Concorrentes:</b> {d.company.competitors.join(", ")}</p>}
        {d.company.news.length > 0 && (
          <>
            <CardTitle className="mt-3">Notícias recentes</CardTitle>
            <ul className="space-y-1 text-sm">{d.company.news.map((n) => <li key={n.text}>• {n.text}<Src urls={n.source_urls} /></li>)}</ul>
          </>
        )}
      </Card>
      <Card>
        <CardTitle>Valores → sua história</CardTitle>
        <ul className="space-y-2 text-sm">{d.values.map((v) => <li key={v.value}><b>{v.value}</b><Src urls={v.source_urls} /><br />{v.how_to_connect}</li>)}</ul>
        {d.interviewers.length > 0 && (
          <>
            <CardTitle className="mt-4">Entrevistadores</CardTitle>
            <ul className="text-sm">{d.interviewers.map((i) => <li key={i.name}>{i.name}{i.role ? ` · ${i.role}` : ""}{i.notes ? ` — ${i.notes}` : ""}</li>)}</ul>
          </>
        )}
      </Card>
      <Card className="lg:col-span-2">
        <CardTitle>Perguntas prováveis</CardTitle>
        <ul className="space-y-2 text-sm">
          {d.likely_questions.map((q) => (
            <li key={q.question}><details><summary className="cursor-pointer"><Badge>{q.type}</Badge> {q.question}</summary><p className="mt-1 whitespace-pre-wrap pl-4 text-muted-foreground">{q.answer_outline}</p></details></li>
          ))}
        </ul>
        <CardTitle className="mt-4">Perguntas para você fazer</CardTitle>
        <ul className="list-disc pl-5 text-sm">{d.questions_to_ask.map((q) => <li key={q}>{q}</li>)}</ul>
      </Card>
      <Card className="text-xs lg:col-span-2">
        <CardTitle>Fontes</CardTitle>
        <ol className="list-decimal pl-5">{d.sources.map((s) => <li key={s.url}><a href={s.url} className="text-primary underline" target="_blank" rel="noreferrer">{s.title ?? s.url}</a></li>)}</ol>
      </Card>
    </div>
  );
}

function Cheatsheet({ id }: { id: string }) {
  const { data, isError } = useRQ({
    queryKey: ["cheatsheet", id],
    queryFn: async () => (await rawFetch(`/api/v1/interviews/${id}/cheatsheet`)).text(),
    retry: false,
  });
  if (isError) return <EmptyState title="O dossiê ainda não está pronto" />;
  return (
    <Card>
      <div className="mb-2 flex justify-end"><Button size="sm" variant="outline" onClick={() => window.print()}>Imprimir</Button></div>
      <pre className="whitespace-pre-wrap font-sans text-sm">{data ?? "Carregando…"}</pre>
    </Card>
  );
}

function Mock({ applicationId, kind }: { applicationId: string; kind: string }) {
  const [session, setSession] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<{ role: string; text: string }[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [answer, setAnswer] = useState("");
  const [mkind, setMkind] = useState(kind);
  const [done, setDone] = useState(false);
  const start = useSend<{ application_id: string; interview_kind: string }, { id: string; turn: Turn; transcript: { role: string; text: string }[] }>("POST", "/api/v1/mock-sessions");
  const reply = useSend<{ answer: string }, { turn: Turn; transcript: { role: string; text: string }[]; status: string }>("POST", `/api/v1/mock-sessions/${session}/turn`);
  return (
    <Card className="space-y-3">
      {!session ? (
        <div className="flex items-end gap-2">
          <Field label="Etapa simulada">
            <Select value={mkind} onChange={(e) => setMkind(e.target.value)}>{Object.entries(INTERVIEW_KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
          </Field>
          <Button disabled={start.isPending} onClick={async () => {
            const r = await start.mutateAsync({ application_id: applicationId, interview_kind: mkind });
            setSession(r.id); setTranscript(r.transcript); setTurns([r.turn]);
          }}>{start.isPending ? "Preparando…" : "Começar simulação"}</Button>
        </div>
      ) : (
        <>
          <div className="max-h-[500px] space-y-3 overflow-auto">
            {transcript.map((t, i) => (
              <div key={i} className={`rounded-md p-2 text-sm ${t.role === "interviewer" ? "bg-muted" : "bg-accent ml-8"}`}>
                <p className="text-xs font-semibold">{t.role === "interviewer" ? "Entrevistador" : "Você"}</p>
                <p className="whitespace-pre-wrap">{t.text}</p>
              </div>
            ))}
          </div>
          {turns.filter((t) => t.feedback).slice(-1).map((t, i) => (
            <div key={i} className="rounded-md border p-2 text-sm">
              <p className="font-medium">Feedback da última resposta: {t.feedback!.overall}/5 (STAR {t.feedback!.star_structure} · clareza {t.feedback!.clarity} · evidência {t.feedback!.evidence})</p>
              <p className="text-success">+ {t.feedback!.strengths.join("; ")}</p>
              <p className="text-warning">→ {t.feedback!.improvements.join("; ")}</p>
              <details><summary className="cursor-pointer text-xs">Resposta melhor</summary><p className="whitespace-pre-wrap text-xs">{t.feedback!.better_answer_outline}</p></details>
            </div>
          ))}
          {done ? (
            <p className="text-sm font-medium">Fim da simulação. {turns.at(-1)?.final_summary}</p>
          ) : (
            <div className="flex gap-2">
              <Textarea rows={4} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Sua resposta (use STAR: situação, tarefa, ação, resultado)" />
              <Button disabled={!answer || reply.isPending} onClick={async () => {
                const r = await reply.mutateAsync({ answer });
                setTranscript(r.transcript); setTurns((x) => [...x, r.turn]); setAnswer(""); setDone(r.status === "finished");
              }}>{reply.isPending ? "…" : "Responder"}</Button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function PostNotes({ id, data }: { id: string; data: InterviewDetail }) {
  const [f, setF] = useState({
    questions: (data.post_notes?.questions ?? []).join("\n"),
    feeling: data.post_notes?.feeling ?? "",
    highlights: data.post_notes?.highlights ?? "",
    next_steps: data.post_notes?.next_steps ?? "",
    self_rating: data.self_rating ?? 3,
    generate_thank_you: true,
  });
  const save = useSend("POST", `/api/v1/interviews/${id}/post-notes`, { success: "Registrado. Rascunho de agradecimento em preparação.", invalidate: [["interviews"]] });
  return (
    <Card className="space-y-3">
      <Field label="Perguntas que fizeram (uma por linha)"><Textarea rows={5} value={f.questions} onChange={(e) => setF({ ...f, questions: e.target.value })} /></Field>
      <Field label="Pontos marcantes da conversa (vão para o e-mail de agradecimento)"><Textarea rows={3} value={f.highlights} onChange={(e) => setF({ ...f, highlights: e.target.value })} /></Field>
      <Field label="Como foi"><Textarea rows={2} value={f.feeling} onChange={(e) => setF({ ...f, feeling: e.target.value })} /></Field>
      <Field label="Próximos passos"><Input value={f.next_steps} onChange={(e) => setF({ ...f, next_steps: e.target.value })} /></Field>
      <Field label="Sua nota (1–5)"><Input type="number" min={1} max={5} value={f.self_rating} onChange={(e) => setF({ ...f, self_rating: Number(e.target.value) })} /></Field>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={f.generate_thank_you} onChange={(e) => setF({ ...f, generate_thank_you: e.target.checked })} /> Gerar rascunho de agradecimento</label>
      <Button onClick={() => save.mutate({ ...f, questions: f.questions.split("\n").map((q) => q.trim()).filter(Boolean) })}>Salvar</Button>
    </Card>
  );
}
