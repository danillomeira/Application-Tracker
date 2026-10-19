"use client";

import {
  AlertTriangle,
  ArrowRight,
  Bell,
  Briefcase,
  CalendarClock,
  CalendarDays,
  FileCheck2,
  Inbox,
  Mail,
  MessageCircleQuestion,
  Send,
  Sparkles,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { Badge, Card, CardTitle, EmptyState, ScoreRing, Skeleton, Stagger, StaggerItem, Stat } from "@/components/ui";
import { useGet } from "@/lib/hooks";
import { QUADRANT_LABEL, QUADRANT_TONE } from "@/lib/labels";
import { formatDateTime } from "@/lib/utils";

type Today = {
  onboarding_needed: boolean;
  interviews: { event_id: string; application_id: string; company: string; job_title: string; starts_at: string; link: string | null; status: string }[];
  deadlines: { event_id: string; title: string; starts_at: string; application_id: string | null }[];
  pending: Record<string, number>;
  followups: { application_id: string; company: string; job_title: string; next_action: string | null; next_action_at: string | null }[];
  top_jobs: { job_id: string; title: string; company: string; quadrant: string; chance: number; attractiveness: number; action: string }[];
  quota: { used: number; limit: number };
  agent: { running: boolean; queued: number; paused_until: string | null; last_safety_stop_at: string | null };
  stats: { applied_7d: number; responses_7d: number; new_jobs_7d: number };
  integration_errors: { name: string; error: string | null }[];
};

const PENDING: [string, string, string, React.ComponentType<{ size?: number }>][] = [
  ["questions", "Perguntas pendentes", "/revisao", MessageCircleQuestion],
  ["reviews", "Candidaturas para revisar", "/revisao", FileCheck2],
  ["resumes_to_approve", "CVs específicos para aprovar", "/curriculos", Sparkles],
  ["ambiguous_emails", "E-mails para associar", "/inbox", Mail],
  ["calendar_drafts", "Eventos para confirmar", "/agenda", CalendarDays],
  ["drafts", "Rascunhos de e-mail", "/inbox?tab=rascunhos", Inbox],
];

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}

export default function TodayPage() {
  const { data, isLoading } = useGet<Today>(["dashboard", "today"], "/api/v1/dashboard/today", { refetchInterval: 60000 });
  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-28" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
        <Skeleton className="h-64" />
      </div>
    );
  }
  const totalPending = Object.values(data.pending).reduce((a, b) => a + (b || 0), 0);
  const raw = new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
  const today = raw.charAt(0).toUpperCase() + raw.slice(1);

  return (
    <div className="space-y-6">
      <Card className="relative overflow-hidden border-0 bg-gradient-to-br from-primary via-indigo-500 to-violet-500 p-6 text-white shadow-lg shadow-primary/25 md:p-8">
        <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-white/10 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-20 right-24 h-40 w-40 rounded-full bg-white/10 blur-2xl" />
        <p className="text-sm text-white/80">{today}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight md:text-3xl">{greeting()}!</h1>
        <p className="mt-2 max-w-xl text-sm text-white/85">
          {totalPending
            ? `Você tem ${totalPending} pendência(s) e ${data.interviews.length} entrevista(s) nos próximos dias.`
            : data.interviews.length
              ? `Nenhuma pendência. ${data.interviews.length} entrevista(s) chegando: bora se preparar.`
              : "Tudo em dia. Que tal revisar as melhores vagas novas?"}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link href="/vagas?quadrant=top">
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-primary shadow-sm transition-transform hover:-translate-y-0.5">
              <Briefcase size={15} /> Ver melhores vagas
            </span>
          </Link>
          {totalPending > 0 && (
            <Link href="/revisao">
              <span className="inline-flex items-center gap-1.5 rounded-lg bg-white/15 px-3 py-1.5 text-sm font-medium text-white backdrop-blur transition-colors hover:bg-white/25">
                Resolver pendências <ArrowRight size={14} />
              </span>
            </Link>
          )}
        </div>
      </Card>

      {data.onboarding_needed && (
        <Card className="flex items-center justify-between gap-3 border-warning/40 bg-warning/5">
          <div>
            <p className="font-medium">Comece pelo seu currículo</p>
            <p className="text-sm text-muted-foreground">Envie o PDF do LinkedIn ou o seu CV para montar o currículo mestre.</p>
          </div>
          <Link href="/onboarding" className="text-sm font-medium text-primary hover:underline">Abrir onboarding</Link>
        </Card>
      )}
      {data.integration_errors.length > 0 && (
        <Card className="flex gap-3 border-danger/40 bg-danger/5">
          <AlertTriangle size={18} className="mt-0.5 shrink-0 text-danger" />
          <div>
            <p className="font-medium text-danger">Integrações com erro</p>
            {data.integration_errors.map((i) => (
              <p key={i.name} className="text-sm text-muted-foreground">
                {i.name}: {i.error}
              </p>
            ))}
            <Link href="/config" className="text-xs font-medium text-primary hover:underline">Ver em Configurações</Link>
          </div>
        </Card>
      )}

      <Stagger className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StaggerItem><Stat label="Candidaturas (7 dias)" value={data.stats.applied_7d} icon={<Send size={17} />} /></StaggerItem>
        <StaggerItem><Stat label="Respostas (7 dias)" value={data.stats.responses_7d} icon={<Bell size={17} />} tone="success" /></StaggerItem>
        <StaggerItem><Stat label="Vagas novas (7 dias)" value={data.stats.new_jobs_7d} icon={<Briefcase size={17} />} tone="warning" /></StaggerItem>
        <StaggerItem>
          <Stat
            label="Easy Apply hoje"
            value={`${data.quota.used}/${data.quota.limit}`}
            hint={data.agent.running ? "robô trabalhando" : `${data.agent.queued} na fila`}
            icon={<Zap size={17} />}
          />
        </StaggerItem>
      </Stagger>

      <div>
        <p className="mb-2 text-sm font-semibold">Pendências</p>
        <Stagger className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {PENDING.map(([k, label, href, Icon]) => {
            const n = data.pending[k] ?? 0;
            return (
              <StaggerItem key={k}>
                <Link href={href}>
                  <Card interactive className={n ? "border-warning/40" : "opacity-70"}>
                    <div className="flex items-center justify-between">
                      <span className={n ? "text-warning" : "text-muted-foreground"}><Icon size={17} /></span>
                      <span className="text-xl font-semibold tabular-nums">{n}</span>
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">{label}</p>
                  </Card>
                </Link>
              </StaggerItem>
            );
          })}
        </Stagger>
        {data.agent.paused_until && (
          <p className="mt-2 text-xs text-danger">Robô pausado por segurança até {formatDateTime(data.agent.paused_until)}</p>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle className="flex items-center gap-2"><CalendarClock size={16} className="text-primary" /> Próximas entrevistas</CardTitle>
          {data.interviews.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Nenhuma nos próximos 7 dias.</p>
          ) : (
            <Stagger className="space-y-2">
              {data.interviews.map((i) => (
                <StaggerItem key={i.event_id}>
                  <div className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2.5 text-sm transition-colors hover:bg-muted/50">
                    <div className="min-w-0">
                      <Link href={`/candidaturas/${i.application_id}`} className="block truncate font-medium hover:text-primary">
                        {i.company} · {i.job_title}
                      </Link>
                      <p className="text-xs text-muted-foreground">{formatDateTime(i.starts_at)}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {i.status === "draft" && <Badge tone="warning">confirmar</Badge>}
                      {i.link && (
                        <a href={i.link} target="_blank" rel="noreferrer" className="text-xs font-medium text-primary hover:underline">
                          entrar
                        </a>
                      )}
                    </div>
                  </div>
                </StaggerItem>
              ))}
            </Stagger>
          )}
          {data.deadlines.length > 0 && (
            <>
              <CardTitle className="mt-5">Prazos de testes técnicos</CardTitle>
              <ul className="space-y-1 text-sm">
                {data.deadlines.map((d) => (
                  <li key={d.event_id} className="flex justify-between gap-2">
                    <span className="truncate">{d.title}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">{formatDateTime(d.starts_at)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>

        <Card>
          <CardTitle>Follow-ups e próximas ações</CardTitle>
          {data.followups.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Nada para hoje.</p>
          ) : (
            <Stagger className="space-y-2 text-sm">
              {data.followups.map((f) => (
                <StaggerItem key={f.application_id}>
                  <div className="rounded-lg border px-3 py-2.5 transition-colors hover:bg-muted/50">
                    <Link href={`/candidaturas/${f.application_id}`} className="font-medium hover:text-primary">
                      {f.company} · {f.job_title}
                    </Link>
                    <p className="text-xs text-muted-foreground">{f.next_action}</p>
                  </div>
                </StaggerItem>
              ))}
            </Stagger>
          )}
        </Card>
      </div>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <CardTitle className="mb-0">Melhores vagas novas</CardTitle>
          <Link href="/vagas" className="flex items-center gap-1 text-xs font-medium text-primary hover:underline">
            ver todas <ArrowRight size={13} />
          </Link>
        </div>
        {data.top_jobs.length === 0 ? (
          <EmptyState icon={<Briefcase size={22} />} title="Sem vagas novas de alta prioridade">
            Adicione empresas monitoradas ou importe vagas em <Link href="/vagas" className="text-primary underline">Vagas</Link>.
          </EmptyState>
        ) : (
          <Stagger className="grid gap-2 md:grid-cols-2">
            {data.top_jobs.map((j) => (
              <StaggerItem key={j.job_id}>
                <Link href={`/vagas/${j.job_id}`}>
                  <div className="flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-[var(--shadow-soft)]">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{j.title}</p>
                      <p className="truncate text-xs text-muted-foreground">{j.company}</p>
                      <Badge tone={QUADRANT_TONE[j.quadrant]} className="mt-1">{QUADRANT_LABEL[j.quadrant]}</Badge>
                    </div>
                    <ScoreRing value={j.chance} label="Chance" size={40} />
                    <ScoreRing value={j.attractiveness} label="Atrat." size={40} />
                  </div>
                </Link>
              </StaggerItem>
            ))}
          </Stagger>
        )}
      </Card>
    </div>
  );
}
