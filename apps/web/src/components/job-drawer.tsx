"use client";
/**
 * Painel da vaga: tudo o que é preciso para decidir e agir, com UM próximo passo claro.
 * Fluxo: abrir no site → candidatar-se lá (a extensão ajuda) → "Já me candidatei" → acompanhar em Candidaturas.
 */
import {
  ArrowRight,
  BarChart3,
  Check,
  ChevronDown,
  ExternalLink,
  FileText,
  Laptop,
  MapPin,
  ThumbsDown,
  ThumbsUp,
  Wallet,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CompanyLogo, TechIcons } from "@/components/brand";
import { formatSalary, type JobRow } from "@/components/job-card";
import { Badge, Button, ScoreRing } from "@/components/ui";
import { useGet, useSend } from "@/lib/hooks";
import { QUADRANT_LABEL, QUADRANT_TONE, SENIORITY_LABEL, STATUS_LABEL, WORK_MODEL_LABEL } from "@/lib/labels";
import { cn, formatDate, relativeTime } from "@/lib/utils";

type Detail = JobRow & { description_text: string; benefits: string[] };

const APPLIED = new Set(["submitted", "under_review", "interviewing", "assessment", "offer", "accepted", "rejected", "ghosted", "declined", "withdrawn"]);

function Section({ title, children, defaultOpen = true }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t pt-4">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between text-left text-sm font-semibold" aria-expanded={open}>
        {title}
        <ChevronDown size={15} className={cn("text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="mt-3">{children}</div>}
    </div>
  );
}

export function JobDrawer({ job, onClose }: { job: JobRow | null; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (job) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [job, onClose]);
  return (
    <AnimatePresence>
      {job && (
        <>
          <motion.div
            className="fixed inset-0 z-40 bg-slate-950/40 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            role="dialog"
            aria-label={`Vaga ${job.title}`}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l bg-card shadow-2xl"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 40 }}
          >
            <DrawerBody key={job.id} job={job} onClose={onClose} />
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function DrawerBody({ job, onClose }: { job: JobRow; onClose: () => void }) {
  const { data: detail } = useGet<Detail>(["job", job.id], `/api/v1/jobs/${job.id}`);
  const j = { ...job, ...(detail ?? {}) } as Detail;
  const inv = { invalidate: [["jobs"], ["dashboard"], ["facets"], ["applications"], ["job", job.id]] };
  const applied = useSend<{ job_id: string; channel: string }>("POST", "/api/v1/applications/manual", {
    success: "Candidatura registrada: acompanhe em Candidaturas",
    ...inv,
  });
  const skip = useSend("POST", `/api/v1/jobs/${job.id}/skip`, { success: "Vaga descartada", ...inv });
  const tailor = useSend("POST", `/api/v1/jobs/${job.id}/approve`, { success: "Preparando currículo sob medida: aparece em Currículos", ...inv });
  const fb = useSend<{ verdict: string }>("POST", `/api/v1/jobs/${job.id}/feedback`, { success: "Obrigado: isso ajusta as próximas notas" });
  const [opened, setOpened] = useState(false);
  const link = j.apply_url || j.canonical_url;
  const s = j.score;
  const status = j.application_status;
  const isApplied = !!status && APPLIED.has(status);
  const salary = formatSalary(j.salary);
  const pos = [...(s?.explanation.chance?.positives ?? []), ...(s?.explanation.attractiveness?.positives ?? [])];
  const neg = [...(s?.explanation.knockout ?? []), ...(s?.explanation.chance?.negatives ?? []), ...(s?.explanation.attractiveness?.negatives ?? [])];
  const techs = [...(j.requirements?.must ?? []), ...(j.requirements?.nice ?? [])];

  return (
    <>
      <div className="flex items-start gap-3 border-b p-5">
        <CompanyLogo id={j.company_id} name={j.company_name} className="h-12 w-12" />
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold leading-snug tracking-tight">{j.title}</h2>
          <p className="text-sm text-muted-foreground">{j.company_name}</p>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {j.location && <span className="inline-flex items-center gap-1"><MapPin size={13} /> {j.location}</span>}
            {j.work_model && <span className="inline-flex items-center gap-1"><Laptop size={13} /> {WORK_MODEL_LABEL[j.work_model] ?? j.work_model}</span>}
            {j.seniority && <span className="inline-flex items-center gap-1"><BarChart3 size={13} /> {SENIORITY_LABEL[j.seniority] ?? j.seniority}</span>}
            {salary && <span className="inline-flex items-center gap-1 font-medium text-success"><Wallet size={13} /> {salary}</span>}
          </div>
        </div>
        <button onClick={onClose} aria-label="Fechar" className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground">
          <X size={17} />
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-5">
        {/* Próximo passo: o bloco mais importante da tela */}
        <div className={cn("rounded-2xl border p-4", isApplied ? "border-success/30 bg-success/5" : "border-primary/25 bg-accent/60")}>
          {isApplied ? (
            <>
              <p className="flex items-center gap-2 font-semibold text-success"><Check size={17} /> Você já se candidatou</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Status: <b>{STATUS_LABEL[status!]}</b>. As respostas da empresa no Gmail atualizam o status sozinhas.
              </p>
              <Link href="/candidaturas" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
                Acompanhar em Candidaturas <ArrowRight size={14} />
              </Link>
            </>
          ) : j.triage === "skipped" ? (
            <>
              <p className="font-semibold">Você marcou esta vaga como sem interesse</p>
              <p className="mt-1 text-sm text-muted-foreground">Ela não aparece mais na lista de novas. Mudou de ideia? Abra o site e candidate-se normalmente.</p>
            </>
          ) : (
            <>
              <p className="text-sm font-semibold">Como se candidatar</p>
              <ol className="mt-3 space-y-3">
                <li className="flex gap-3">
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">1</span>
                  <div className="flex-1">
                    <p className="text-sm">Abra a vaga no site da empresa e candidate-se por lá.</p>
                    {link ? (
                      <a href={link} target="_blank" rel="noreferrer" onClick={() => setOpened(true)}>
                        <Button size="lg" className="mt-2 w-full">
                          <ExternalLink size={16} /> Abrir a vaga no site
                        </Button>
                      </a>
                    ) : (
                      <p className="mt-1 text-xs text-warning">Esta vaga não tem link. Procure pelo título no site da empresa.</p>
                    )}
                    <p className="mt-1.5 text-xs text-muted-foreground">Com a extensão instalada, ela preenche o formulário para você. Quem clica em enviar é você.</p>
                  </div>
                </li>
                <li className="flex gap-3">
                  <span className={cn("grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-semibold", opened ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>2</span>
                  <div className="flex-1">
                    <p className="text-sm">Enviou? Registre aqui para acompanhar as respostas.</p>
                    <Button
                      variant={opened ? "default" : "outline"}
                      className="mt-2 w-full"
                      disabled={applied.isPending}
                      onClick={async () => {
                        await applied.mutateAsync({ job_id: job.id, channel: "external" });
                        onClose();
                      }}
                    >
                      <Check size={16} /> Já me candidatei
                    </Button>
                    <p className="mt-1.5 text-xs text-muted-foreground">Se usou a extensão, isso acontece sozinho ao enviar.</p>
                  </div>
                </li>
              </ol>
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-3">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={async () => {
                    await skip.mutateAsync(undefined);
                    onClose();
                  }}
                >
                  <X size={14} /> Não tenho interesse
                </Button>
                <Button variant="ghost" size="sm" disabled={tailor.isPending} onClick={() => tailor.mutate(undefined)} title="A IA monta um currículo ajustado para esta vaga">
                  <FileText size={14} /> Gerar currículo sob medida
                </Button>
              </div>
            </>
          )}
        </div>

        {s && (
          <Section title="Combina com você?">
            <div className="flex items-center gap-5">
              <ScoreRing value={s.chance} label="Chance" size={54} />
              <ScoreRing value={s.attractiveness} label="Atratividade" size={54} />
              <div className="text-xs text-muted-foreground">
                <p><b className="text-foreground">Chance</b>: quão provável é você ser chamado (requisitos, senioridade, concorrência).</p>
                <p className="mt-1"><b className="text-foreground">Atratividade</b>: quanto a vaga vale a pena (empresa, salário, modelo de trabalho).</p>
              </div>
            </div>
            <div className="mt-3 flex items-center gap-2">
              <Badge tone={QUADRANT_TONE[s.quadrant]}>{QUADRANT_LABEL[s.quadrant]}</Badge>
              <span className="text-xs text-muted-foreground">{s.suggested_action}</span>
            </div>
            {(pos.length > 0 || neg.length > 0) && (
              <ul className="mt-3 space-y-1 text-sm">
                {pos.map((r) => <li key={r} className="flex gap-2 text-success"><Check size={15} className="mt-0.5 shrink-0" />{r}</li>)}
                {neg.map((r) => <li key={r} className="flex gap-2 text-danger"><X size={15} className="mt-0.5 shrink-0" />{r}</li>)}
              </ul>
            )}
            <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
              As notas fazem sentido?
              <Button size="sm" variant="ghost" className="h-7" onClick={() => fb.mutate({ verdict: "good" })}><ThumbsUp size={13} /> Sim</Button>
              <Button size="sm" variant="ghost" className="h-7" onClick={() => fb.mutate({ verdict: "not_interested" })}><ThumbsDown size={13} /> Não me interessa</Button>
            </div>
          </Section>
        )}

        {techs.length > 0 && (
          <Section title="Tecnologias pedidas">
            <TechIcons techs={j.requirements?.must ?? []} max={20} size={22} />
            {(j.requirements?.nice ?? []).length > 0 && (
              <>
                <p className="mb-1.5 mt-3 text-xs font-medium text-muted-foreground">Desejáveis</p>
                <TechIcons techs={j.requirements?.nice ?? []} max={20} size={18} />
              </>
            )}
          </Section>
        )}

        {detail?.benefits && detail.benefits.length > 0 && (
          <Section title="Benefícios" defaultOpen={false}>
            <div className="flex flex-wrap gap-1.5">{detail.benefits.map((b) => <Badge key={b}>{b}</Badge>)}</div>
          </Section>
        )}

        <Section title="Descrição da vaga" defaultOpen={false}>
          {detail ? (
            <p className="max-h-96 overflow-y-auto whitespace-pre-line text-sm leading-relaxed text-muted-foreground">{detail.description_text || "Sem descrição."}</p>
          ) : (
            <p className="text-sm text-muted-foreground">Carregando…</p>
          )}
        </Section>

        <p className="pt-2 text-xs text-muted-foreground">
          Encontrada {relativeTime(j.first_seen_at)}
          {j.posted_at ? ` · publicada em ${formatDate(j.posted_at)}` : ""} ·{" "}
          <Link href={`/vagas/${j.id}`} className="text-primary hover:underline">página completa da vaga</Link>
        </p>
      </div>
    </>
  );
}
