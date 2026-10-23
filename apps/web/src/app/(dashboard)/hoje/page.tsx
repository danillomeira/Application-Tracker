"use client";

import { CompanyLogo } from "@/components/brand";
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  Briefcase,
  CalendarClock,
  Check,
  CalendarDays,
  Inbox,
  Mail,
  Send,
  Sparkles,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { Badge, Card, CardTitle, EASE, EmptyState, ScoreRing, Skeleton, Stagger, StaggerItem } from "@/components/ui";
import { useGet } from "@/lib/hooks";
import { QUADRANT_LABEL, QUADRANT_TONE } from "@/lib/labels";
import { cn, formatDateTime } from "@/lib/utils";

type Today = {
  onboarding_needed: boolean;
  interviews: { event_id: string; application_id: string; company: string; job_title: string; starts_at: string; link: string | null; status: string }[];
  deadlines: { event_id: string; title: string; starts_at: string; application_id: string | null }[];
  pending: Record<string, number>;
  followups: { application_id: string; company: string; job_title: string; next_action: string | null; next_action_at: string | null }[];
  top_jobs: { job_id: string; title: string; company: string; quadrant: string; chance: number; attractiveness: number; action: string }[];
  stats: { applied_7d: number; responses_7d: number; new_jobs_7d: number };
  integration_errors: { name: string; error: string | null }[];
};

const PENDING: [string, string, string, React.ComponentType<{ size?: number }>][] = [
  ["resumes_to_approve", "CVs específicos para aprovar", "/curriculos", Sparkles],
  ["ambiguous_emails", "E-mails para associar", "/inbox", Mail],
  ["calendar_drafts", "Eventos para confirmar", "/agenda", CalendarDays],
  ["drafts", "Rascunhos de e-mail", "/inbox?tab=rascunhos", Inbox],
];

function Journey({ data }: { data: Today }) {
  const steps = [
    { icon: Briefcase, title: "Ver vagas", value: data.stats.new_jobs_7d, unit: "novas na semana", href: "/vagas", cta: "Ver vagas recomendadas" },
    { icon: Send, title: "Candidatar-se", value: data.stats.applied_7d, unit: "enviadas na semana", href: "/vagas", cta: "Escolher uma vaga" },
    { icon: Bell, title: "Acompanhar", value: data.stats.responses_7d, unit: "respostas na semana", href: "/candidaturas", cta: "Ver candidaturas" },
    { icon: CalendarClock, title: "Entrevistas", value: data.interviews.length, unit: "nos próximos 7 dias", href: "/entrevistas", cta: "Preparar entrevistas" },
  ];
  // o próximo passo sugerido: entrevista marcada > respostas chegando > candidatar > ver vagas
  const next = data.interviews.length ? 3 : data.stats.responses_7d ? 2 : data.stats.new_jobs_7d ? 1 : 0;
  return (
    <div data-tour="journey">
      <p className="mb-2 text-sm font-semibold">O caminho de uma candidatura</p>
      <Card className="relative overflow-hidden p-0">
        <div className="pointer-events-none absolute left-[12.5%] right-[12.5%] top-[42px] hidden h-0.5 bg-border md:block">
          <motion.div
            className="h-full bg-primary"
            initial={{ width: 0 }}
            animate={{ width: `${(next / (steps.length - 1)) * 100}%` }}
            transition={{ duration: 0.9, ease: EASE }}
          />
        </div>
        <div className="grid divide-y md:grid-cols-4 md:divide-y-0">
          {steps.map((st, idx) => {
            const isNext = idx === next;
            const done = idx < next;
            return (
              <Link
                key={st.title}
                href={st.href}
                className={cn(
                  "group relative flex flex-col items-center px-4 py-5 text-center transition-colors hover:bg-muted/50",
                  isNext && "bg-accent/50",
                )}
              >
                <span
                  className={cn(
                    "relative z-10 grid h-11 w-11 place-items-center rounded-full border-2 bg-card transition-transform group-hover:scale-105",
                    isNext ? "border-primary bg-primary text-primary-foreground shadow-md shadow-primary/30" : done ? "border-primary text-primary" : "text-muted-foreground",
                  )}
                >
                  <st.icon size={18} />
                </span>
                <p className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Passo {idx + 1}</p>
                <p className="font-semibold">{st.title}</p>
                <p className="mt-1">
                  <span className="text-2xl font-semibold tabular-nums">{st.value}</span>{" "}
                  <span className="text-xs text-muted-foreground">{st.unit}</span>
                </p>
                <span className={cn("mt-2 inline-flex items-center gap-1 text-xs font-medium", isNext ? "text-primary" : "text-muted-foreground group-hover:text-primary")}>
                  {st.cta} <ArrowRight size={12} className="transition-transform group-hover:translate-x-0.5" />
                </span>
                {isNext && <Badge tone="primary" className="absolute right-3 top-3">próximo passo</Badge>}
              </Link>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

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
      <Card className="relative overflow-hidden border-0 bg-gradient-to-br from-primary via-blue-500 to-sky-500 p-6 text-white shadow-lg shadow-primary/25 md:p-8">
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
            <Link href="/inbox">
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

      <Journey data={data} />

      <div data-tour="pending">
        <p className="mb-2 text-sm font-semibold">Pendências <span className="font-normal text-muted-foreground">· coisas que só você pode resolver</span></p>
        {PENDING.some(([k]) => (data.pending[k] ?? 0) > 0) ? (
          <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {PENDING.filter(([k]) => (data.pending[k] ?? 0) > 0).map(([k, label, href, Icon]) => (
              <StaggerItem key={k}>
                <Link href={href}>
                  <Card interactive className="flex items-center gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-warning/12 text-warning"><Icon size={18} /></div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{label}</p>
                      <p className="text-xs text-muted-foreground">clique para resolver</p>
                    </div>
                    <span className="grid h-8 min-w-8 place-items-center rounded-full bg-warning px-2 text-sm font-semibold text-white tabular-nums">{data.pending[k]}</span>
                  </Card>
                </Link>
              </StaggerItem>
            ))}
          </Stagger>
        ) : (
          <Card className="flex items-center gap-3 text-sm text-muted-foreground">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-success/12 text-success"><Check size={17} /></span>
            Tudo em dia: nenhuma pendência agora.
          </Card>
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
                    <CompanyLogo name={i.company} className="h-9 w-9" />
                    <div className="min-w-0 flex-1">
                      <Link href={`/candidaturas/${i.application_id}`} className="block truncate font-medium hover:text-primary">
                        {i.job_title}
                      </Link>
                      <p className="truncate text-xs text-muted-foreground">{i.company}</p>
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
                  <div className="flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors hover:bg-muted/50">
                    <CompanyLogo name={f.company} className="h-9 w-9" />
                    <div className="min-w-0">
                      <Link href={`/candidaturas/${f.application_id}`} className="block truncate font-medium hover:text-primary">
                        {f.job_title} · {f.company}
                      </Link>
                      <p className="truncate text-xs text-muted-foreground">{f.next_action}</p>
                    </div>
                  </div>
                </StaggerItem>
              ))}
            </Stagger>
          )}
        </Card>
      </div>

      <Card data-tour="top-jobs">
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
                    <CompanyLogo name={j.company} />
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
