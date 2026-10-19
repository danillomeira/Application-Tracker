"use client";

import { KanbanSquare } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useState } from "react";
import { Avatar, Badge, Button, Chip, Field, Input, Modal, PageHeader, Select, Skeleton, Textarea } from "@/components/ui";
import { cn } from "@/lib/utils";
import { useGet, useSend } from "@/lib/hooks";
import { QUADRANT_LABEL, QUADRANT_TONE, STATUS_LABEL, STATUS_TONE } from "@/lib/labels";
import { relativeTime } from "@/lib/utils";

type App = {
  id: string;
  job_id: string;
  status: string;
  channel: string;
  job_title: string;
  company_name: string;
  quadrant: string | null;
  last_activity_at: string;
  next_action: string | null;
  submitted_at: string | null;
};

const COLUMNS: { key: string; title: string; statuses: string[]; drop: string; dot: string }[] = [
  { key: "fila", title: "Fila", statuses: ["discovered", "queued", "in_progress", "needs_input", "awaiting_review"], drop: "queued", dot: "bg-slate-400" },
  { key: "enviadas", title: "Candidatadas", statuses: ["submitted", "under_review"], drop: "under_review", dot: "bg-primary" },
  { key: "entrevista", title: "Entrevista", statuses: ["interviewing"], drop: "interviewing", dot: "bg-violet-500" },
  { key: "teste", title: "Teste técnico", statuses: ["assessment"], drop: "assessment", dot: "bg-warning" },
  { key: "oferta", title: "Oferta", statuses: ["offer", "accepted"], drop: "offer", dot: "bg-success" },
  { key: "encerradas", title: "Encerradas", statuses: ["rejected", "ghosted", "declined", "withdrawn"], drop: "rejected", dot: "bg-danger" },
];

export default function ApplicationsPage() {
  const [q, setQ] = useState("");
  const { data, isLoading } = useGet<App[]>(["applications", q], `/api/v1/applications${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  const move = useSend<{ id: string; status: string }>("PATCH", (v) => `/api/v1/applications/${v.id}`, {
    invalidate: [["applications"], ["dashboard"]],
  });
  const [dragging, setDragging] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [showFound, setShowFound] = useState(false);
  const found = (data ?? []).filter((a) => a.status === "discovered").length;
  return (
    <div>
      <PageHeader
        icon={<KanbanSquare size={20} />}
        title="Candidaturas"
        description="Arraste os cartões para mudar o status (transições inválidas são recusadas)"
        actions={
          <>
            <Input placeholder="Buscar" value={q} onChange={(e) => setQ(e.target.value)} className="w-48" />
            <ManualButton />
          </>
        }
      />
      {found > 0 && (
        <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground">
          <Chip active={showFound} count={found} onClick={() => setShowFound(!showFound)}>
            Mostrar vagas só encontradas
          </Chip>
          <span>Vagas que a busca encontrou mas você ainda não decidiu ficam em Vagas.</span>
        </div>
      )}
      {isLoading ? (
        <Skeleton className="h-96" />
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-4">
          {COLUMNS.map((col) => {
            const items = (data ?? []).filter((a) => col.statuses.includes(a.status) && (showFound || a.status !== "discovered"));
            return (
              <div
                key={col.key}
                className={cn(
                  "w-72 shrink-0 rounded-xl border border-transparent bg-muted/50 p-2 transition-colors",
                  over === col.key && dragging && "border-primary/50 bg-accent",
                )}
                onDragOver={(e) => {
                  e.preventDefault();
                  setOver(col.key);
                }}
                onDragLeave={() => setOver(null)}
                onDrop={() => {
                  if (dragging) move.mutate({ id: dragging, status: col.drop });
                  setDragging(null);
                  setOver(null);
                }}
              >
                <p className="mb-2 flex items-center gap-2 px-1.5 pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <span className={cn("h-2 w-2 rounded-full", col.dot)} />
                  {col.title}
                  <span className="ml-auto rounded-full bg-card px-1.5 tabular-nums">{items.length}</span>
                </p>
                <div className="min-h-16 space-y-2">
                  <AnimatePresence initial={false}>
                    {items.map((a) => (
                      <motion.div
                        key={a.id}
                        layout
                        layoutId={`app-${a.id}`}
                        initial={{ opacity: 0, scale: 0.96 }}
                        animate={{ opacity: dragging === a.id ? 0.5 : 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.96 }}
                        transition={{ type: "spring", stiffness: 420, damping: 34 }}
                      >
                        <Link
                          href={`/candidaturas/${a.id}`}
                          draggable
                          onDragStart={() => setDragging(a.id)}
                          onDragEnd={() => {
                            setDragging(null);
                            setOver(null);
                          }}
                          className="block cursor-grab rounded-lg border bg-card p-2.5 text-sm shadow-[var(--shadow-soft)] transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-[var(--shadow-lift)] active:cursor-grabbing"
                        >
                          <div className="flex items-start gap-2">
                            <Avatar name={a.company_name} className="h-7 w-7 rounded-lg text-[10px]" />
                            <div className="min-w-0">
                              <p className="line-clamp-2 font-medium leading-snug">{a.job_title}</p>
                              <p className="truncate text-xs text-muted-foreground">{a.company_name}</p>
                            </div>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-1">
                            <Badge tone={STATUS_TONE[a.status]}>{STATUS_LABEL[a.status]}</Badge>
                            {a.quadrant && <Badge tone={QUADRANT_TONE[a.quadrant]}>{QUADRANT_LABEL[a.quadrant]}</Badge>}
                          </div>
                          {a.next_action && <p className="mt-1.5 text-xs text-warning">→ {a.next_action}</p>}
                          <p className="mt-1 text-[11px] text-muted-foreground">{relativeTime(a.last_activity_at)}</p>
                        </Link>
                      </motion.div>
                    ))}
                  </AnimatePresence>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ManualButton() {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ company_name: "", title: "", url: "", channel: "external", description: "", notes: "" });
  const send = useSend("POST", "/api/v1/applications/manual", { success: "Candidatura registrada", invalidate: [["applications"]] });
  return (
    <>
      <Button onClick={() => setOpen(true)}>Registrar “enviei”</Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Registrar candidatura feita fora do sistema">
        <div className="space-y-3">
          <Field label="Empresa"><Input value={f.company_name} onChange={(e) => setF({ ...f, company_name: e.target.value })} /></Field>
          <Field label="Vaga"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label="URL"><Input value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} /></Field>
          <Field label="Canal">
            <Select value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>
              <option value="external">Site/ATS externo</option>
              <option value="easy_apply">Easy Apply (manual)</option>
              <option value="email">E-mail</option>
              <option value="referral">Indicação</option>
            </Select>
          </Field>
          <Field label="Descrição da vaga (opcional, melhora a avaliação)"><Textarea rows={4} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <Button
            disabled={!f.company_name || !f.title}
            onClick={async () => {
              await send.mutateAsync(f);
              setOpen(false);
            }}
          >
            Registrar
          </Button>
        </div>
      </Modal>
    </>
  );
}

