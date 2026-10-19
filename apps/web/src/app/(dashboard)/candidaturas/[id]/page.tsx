"use client";

import Link from "next/link";
import { use, useState } from "react";
import { Badge, Button, Card, CardTitle, Modal, PageHeader, Select, Skeleton, Textarea } from "@/components/ui";
import { useGet, useSend, useTask } from "@/lib/hooks";
import { EMAIL_LABEL, INTERVIEW_KIND, STATUS_LABEL, STATUS_TONE } from "@/lib/labels";
import { formatDateTime } from "@/lib/utils";

type Detail = {
  id: string;
  job_id: string;
  status: string;
  channel: string;
  mode: string;
  job_title: string;
  company_name: string;
  apply_kind: string | null;
  ats_kind: string | null;
  submitted_at: string | null;
  next_action: string | null;
  cover_letter: string | null;
  notes: string | null;
  resume_render_id: string | null;
  priority_at_submit: { chance: number; attractiveness: number; quadrant: string } | null;
  timeline: { id: string; kind: string; payload: Record<string, unknown>; actor: string; reason: string | null; occurred_at: string }[];
  answers: { id: string; question_text: string; answer: { value: unknown }; resolution: string; confidence: number }[];
  emails: { id: string; subject: string; from: string; received_at: string; classification: string | null; snippet: string }[];
  events_calendar: { id: string; kind: string; title: string; starts_at: string; status: string; link: string | null }[];
  interviews: { id: string; round: number; kind: string; starts_at: string | null }[];
  drafts: { id: string; kind: string; subject: string | null; status: string }[];
  pending_questions: { id: string; question: string; status: string }[];
  people: { id: string; name: string; role: string | null; relation: string }[];
};

type Package = {
  apply_url: string | null;
  resume: { filename: string; download: string } | null;
  cover_letter: string | null;
  answers: Record<string, unknown>;
  pending: string[];
  checklist: string[];
};

function describe(e: Detail["timeline"][number]) {
  const p = e.payload;
  switch (e.kind) {
    case "status_change":
      return `Status: ${STATUS_LABEL[String(p.from)] ?? "—"} → ${STATUS_LABEL[String(p.to)] ?? p.to}`;
    case "email_in":
      return `E-mail recebido (${EMAIL_LABEL[String(p.label)] ?? p.label}): ${p.summary ?? p.subject ?? ""}`;
    case "message_in":
      return `Mensagem no LinkedIn: ${p.summary ?? ""}`;
    case "agent_step":
      return `Robô: ${p.title} ${p.log ? `(${p.log})` : ""}`;
    case "note":
      return `Nota: ${p.text}`;
    case "email_draft":
      return `Rascunho criado (${p.kind})`;
    case "resume_selected":
      return "Currículo definido";
    case "question_answered":
      return `Pergunta respondida: ${p.question}`;
    case "skill_gap":
      return `Requisito que você não tem: ${(p.skills as string[]).join(", ")}`;
    default:
      return e.kind;
  }
}

export default function ApplicationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: app } = useGet<Detail>(["applications", id], `/api/v1/applications/${id}`);
  const { data: statuses } = useGet<{ transitions: Record<string, string[]> }>(["statuses"], "/api/v1/applications/statuses");
  const inv = { invalidate: [["applications"]] };
  const patch = useSend<Record<string, unknown>>("PATCH", `/api/v1/applications/${id}`, { success: "Atualizado", ...inv });
  const submitted = useSend("POST", `/api/v1/applications/${id}/submitted`, { success: "Registrado como enviada", ...inv });
  const prepare = useSend("POST", `/api/v1/applications/${id}/prepare`, { success: "Preparação iniciada", ...inv });
  const note = useSend<{ text: string }>("POST", `/api/v1/applications/${id}/notes`, inv);
  const dossier = useSend<void, { task_id: string }>("POST", `/api/v1/interviews/applications/${id}/dossier`);
  const recruiterNote = useSend<{ application_id: string }, { task_id: string }>("POST", "/api/v1/drafts/recruiter-note");
  const task = useTask();
  const [noteText, setNoteText] = useState("");
  const [pkgOpen, setPkgOpen] = useState(false);
  const pkg = useGet<Package>(["package", id], pkgOpen ? `/api/v1/applications/${id}/package` : null);

  if (!app) return <Skeleton className="h-96" />;
  const allowed = statuses?.transitions[app.status] ?? [];
  return (
    <div className="space-y-4">
      <PageHeader
        title={`${app.job_title} · ${app.company_name}`}
        description={`Canal: ${app.channel} · modo ${app.mode}${app.submitted_at ? ` · enviada em ${formatDateTime(app.submitted_at)}` : ""}`}
        actions={
          <>
            <Badge tone={STATUS_TONE[app.status]}>{STATUS_LABEL[app.status]}</Badge>
            <Select
              value=""
              onChange={(e) => e.target.value && patch.mutate({ status: e.target.value })}
              className="w-48"
              aria-label="Mudar status"
            >
              <option value="">Mudar status…</option>
              {allowed.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
            </Select>
            <Link href={`/vagas/${app.job_id}`}><Button variant="outline">Vaga</Button></Link>
          </>
        }
      />
      {app.next_action && <Card className="border-warning text-sm">Próxima ação: <b>{app.next_action}</b></Card>}
      <div className="flex flex-wrap gap-2">
        {["discovered", "queued", "skipped"].includes(app.status) && <Button onClick={() => prepare.mutate(undefined)}>Preparar candidatura</Button>}
        {!app.submitted_at && <Button variant="outline" onClick={() => setPkgOpen(true)}>Pacote para candidatura externa</Button>}
        {!app.submitted_at && <Button variant="success" onClick={() => submitted.mutate(undefined)}>Enviei</Button>}
        <Button variant="outline" disabled={task.running} onClick={async () => task.start((await dossier.mutateAsync()).task_id)}>Gerar dossiê</Button>
        <Button variant="outline" disabled={task.running} onClick={async () => task.start((await recruiterNote.mutateAsync({ application_id: id })).task_id)}>Nota para recrutador</Button>
        {app.resume_render_id && (
          <a href={`/api/v1/resumes/renders/${app.resume_render_id}/pdf`} target="_blank" rel="noreferrer"><Button variant="ghost">CV enviado (PDF)</Button></a>
        )}
        {task.progress && <span className="self-center text-xs text-muted-foreground">{task.progress.message}</span>}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle>Linha do tempo</CardTitle>
          <ol className="space-y-2 text-sm">
            {app.timeline.map((e) => (
              <li key={e.id} className="border-l-2 pl-3">
                <p>{describe(e)}</p>
                <p className="text-xs text-muted-foreground">{formatDateTime(e.occurred_at)} · {e.actor}{e.reason ? ` · ${e.reason}` : ""}</p>
              </li>
            ))}
          </ol>
          <div className="mt-4 flex gap-2">
            <Textarea rows={2} placeholder="Adicionar nota" value={noteText} onChange={(e) => setNoteText(e.target.value)} />
            <Button disabled={!noteText} onClick={async () => { await note.mutateAsync({ text: noteText }); setNoteText(""); }}>Salvar</Button>
          </div>
        </Card>
        <div className="space-y-4">
          {app.pending_questions.some((p) => p.status === "open") && (
            <Card className="border-warning">
              <CardTitle>Perguntas pendentes</CardTitle>
              {app.pending_questions.filter((p) => p.status === "open").map((p) => <p key={p.id} className="text-sm">• {p.question}</p>)}
              <Link href="/revisao" className="text-xs text-primary underline">Responder</Link>
            </Card>
          )}
          {app.interviews.length > 0 && (
            <Card>
              <CardTitle>Entrevistas</CardTitle>
              {app.interviews.map((i) => (
                <Link key={i.id} href={`/entrevistas/${i.id}`} className="block text-sm hover:underline">
                  {i.round}ª · {INTERVIEW_KIND[i.kind] ?? i.kind} · {formatDateTime(i.starts_at)}
                </Link>
              ))}
            </Card>
          )}
          {app.events_calendar.length > 0 && (
            <Card>
              <CardTitle>Agenda</CardTitle>
              {app.events_calendar.map((e) => (
                <p key={e.id} className="text-sm">{formatDateTime(e.starts_at)} · {e.title} {e.status === "draft" && <Badge tone="warning">rascunho</Badge>}</p>
              ))}
            </Card>
          )}
          {app.emails.length > 0 && (
            <Card>
              <CardTitle>E-mails</CardTitle>
              {app.emails.map((e) => (
                <div key={e.id} className="mb-2 text-sm">
                  <p className="font-medium">{e.subject}</p>
                  <p className="text-xs text-muted-foreground">{e.from} · {formatDateTime(e.received_at)} · {EMAIL_LABEL[e.classification ?? ""] ?? "—"}</p>
                </div>
              ))}
            </Card>
          )}
          {app.people.length > 0 && (
            <Card>
              <CardTitle>Pessoas</CardTitle>
              {app.people.map((p) => <p key={p.id + p.relation} className="text-sm">{p.name} · {p.role ?? p.relation}</p>)}
            </Card>
          )}
          {app.answers.length > 0 && (
            <Card>
              <CardTitle>Respostas enviadas</CardTitle>
              <ul className="space-y-1 text-xs">
                {app.answers.map((a) => (
                  <li key={a.id}>
                    <span className="text-muted-foreground">{a.question_text}:</span> <b>{String(a.answer.value)}</b>{" "}
                    <Badge>{a.resolution}</Badge>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {app.cover_letter && (
            <Card>
              <CardTitle>Carta</CardTitle>
              <p className="whitespace-pre-wrap text-sm">{app.cover_letter}</p>
            </Card>
          )}
        </div>
      </div>

      <Modal open={pkgOpen} onClose={() => setPkgOpen(false)} title="Pacote para candidatura externa" wide>
        {!pkg.data ? (
          <Skeleton className="h-40" />
        ) : (
          <div className="space-y-3 text-sm">
            {pkg.data.apply_url && <a className="text-primary underline" href={pkg.data.apply_url} target="_blank" rel="noreferrer">Abrir página de candidatura</a>}
            {pkg.data.resume ? (
              <p>CV: <a className="text-primary underline" href={pkg.data.resume.download} target="_blank" rel="noreferrer">{pkg.data.resume.filename}</a></p>
            ) : (
              <p className="text-warning">Sem CV definido: clique em “Preparar candidatura”.</p>
            )}
            {pkg.data.cover_letter && <Textarea readOnly rows={5} value={pkg.data.cover_letter} />}
            <table className="w-full text-xs">
              <tbody>
                {Object.entries(pkg.data.answers).map(([q, a]) => (
                  <tr key={q} className="border-t"><td className="py-1 pr-2 text-muted-foreground">{q}</td><td className="py-1">{a == null ? <i>pendente</i> : String(a)}</td></tr>
                ))}
              </tbody>
            </table>
            <ul className="list-disc pl-5">{pkg.data.checklist.map((c) => <li key={c}>{c}</li>)}</ul>
          </div>
        )}
      </Modal>
    </div>
  );
}
