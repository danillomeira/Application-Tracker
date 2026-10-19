"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  BriefcaseBusiness,
  Check,
  CircleDashed,
  FileUp,
  Link2,
  PartyPopper,
  Rocket,
  Sparkles,
  Target,
  Wallet,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { AiGuide, ExtensionGuide, GoogleGuide, LatexGuide, TagInput, TelegramGuide, Tip } from "@/components/setup-guides";
import { ThemeToggle } from "@/components/theme-toggle";
import { Badge, Button, Card, Chip, EASE, Field, Input, Select, Skeleton, Tabs } from "@/components/ui";
import { api, rawFetch } from "@/lib/api";
import { SENIORITY_LABEL, WORK_MODEL_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";

type Check_ = { ok: boolean; detail?: string; configured?: boolean; account?: string | null; redirect_uris?: string[]; optional?: boolean; backend?: string };
type Status = {
  completed: boolean;
  checks: { resume: Check_; preferences: Check_; ai: Check_; latex: Check_; google: Check_; telegram: Check_; extension: Check_ };
  companies: number;
  saved_searches: number;
};
type Master = {
  contact: { full_name: string; email: string; phone?: string | null; location?: string | null; linkedin?: string | null; github?: string | null };
  experience: { id: string; title: string; organization: string; start?: string | null; end?: string | null }[];
  skills: Record<string, string[]>;
  education: { degree: string; institution: string }[];
  languages: { name: string; level?: string | null }[];
  [k: string]: unknown;
};
type Prefs = {
  target_roles: string[];
  seniorities: string[];
  work_models: string[];
  locations: string[];
  regimes: string[];
  min_salary: Record<string, Record<string, number>>;
  salary_expectation: Record<string, Record<string, number>>;
  international: boolean;
  [k: string]: unknown;
};

const STEPS = [
  { key: "welcome", label: "Boas-vindas", icon: Sparkles },
  { key: "ai", label: "IA", icon: Bot },
  { key: "resume", label: "Currículo", icon: FileUp },
  { key: "prefs", label: "O que você busca", icon: Target },
  { key: "current", label: "Emprego atual", icon: Wallet },
  { key: "integrations", label: "Integrações", icon: Link2 },
  { key: "finish", label: "Pronto", icon: Rocket },
] as const;

const ROLE_SUGGESTIONS = [
  "Software Engineer",
  "Engenheiro de Software",
  "Backend",
  "Frontend",
  "Full Stack",
  "Data Engineer",
  "Engenheiro de Dados",
  "Data Scientist",
  "Machine Learning Engineer",
  "AI Engineer",
  "DevOps",
  "SRE",
  "Mobile",
  "QA",
  "Analytics Engineer",
];

export default function OnboardingPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [dir, setDir] = useState(1);
  const me = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const r = await api.GET("/api/v1/auth/me");
      if (!r.data) throw new Error("unauthenticated");
      return r.data;
    },
    retry: false,
  });
  const status = useQuery({
    queryKey: ["onboarding"],
    queryFn: async () => (await rawFetch("/api/v1/onboarding/status")).json() as Promise<Status>,
    enabled: me.isSuccess,
    refetchInterval: 8000,
  });
  useEffect(() => {
    if (me.isError) router.replace("/login");
  }, [me.isError, router]);

  const go = (n: number) => {
    setDir(n > step ? 1 : -1);
    setStep(Math.max(0, Math.min(STEPS.length - 1, n)));
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const refresh = () => qc.invalidateQueries({ queryKey: ["onboarding"] });
  const s = status.data;

  return (
    <div className="min-h-screen bg-[radial-gradient(1200px_600px_at_10%_-10%,color-mix(in_oklab,var(--primary)_14%,transparent),transparent),radial-gradient(900px_500px_at_110%_10%,color-mix(in_oklab,#8b5cf6_12%,transparent),transparent)]">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-4 py-5">
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-primary to-violet-500 text-white shadow-lg shadow-primary/30">
            <Sparkles size={17} />
          </div>
          <div className="leading-tight">
            <p className="font-semibold tracking-tight">Application Tracker</p>
            <p className="text-xs text-muted-foreground">configuração inicial</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {s?.completed && (
            <Button variant="ghost" size="sm" onClick={() => router.push("/hoje")}>
              Ir para o painel
            </Button>
          )}
          <ThemeToggle />
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 pb-16">
        <Stepper step={step} onGo={go} status={s} />
        <div className="relative mt-6">
          <AnimatePresence mode="wait" custom={dir}>
            <motion.div
              key={step}
              custom={dir}
              initial={{ opacity: 0, x: dir * 40 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: dir * -40 }}
              transition={{ duration: 0.3, ease: EASE }}
            >
              {!s ? (
                <Skeleton className="h-96" />
              ) : step === 0 ? (
                <Welcome onNext={() => go(1)} />
              ) : step === 1 ? (
                <StepCard title="Ligue a IA" ok={s.checks.ai.ok} detail={s.checks.ai.detail}>
                  <AiGuide onTested={refresh} />
                  <div className="mt-6 border-t pt-4">
                    <p className="mb-2 text-sm font-semibold">PDF dos currículos</p>
                    {s.checks.latex.ok ? <Badge tone="success">tectonic encontrado</Badge> : <LatexGuide />}
                  </div>
                </StepCard>
              ) : step === 2 ? (
                <ResumeStep hasResume={s.checks.resume.ok} onDone={() => { refresh(); go(3); }} />
              ) : step === 3 ? (
                <PrefsStep onDone={() => { refresh(); go(4); }} />
              ) : step === 4 ? (
                <CurrentJobStep onDone={() => go(5)} />
              ) : step === 5 ? (
                <IntegrationsStep s={s} />
              ) : (
                <FinishStep s={s} />
              )}
            </motion.div>
          </AnimatePresence>
        </div>
        {step > 0 && step < STEPS.length - 1 && (
          <div className="mt-6 flex items-center justify-between">
            <Button variant="ghost" onClick={() => go(step - 1)}>
              <ArrowLeft size={15} /> Voltar
            </Button>
            {[1, 4, 5].includes(step) && (
              <Button variant="outline" onClick={() => go(step + 1)}>
                {step === 1 ? "Continuar" : "Pular por agora"} <ArrowRight size={15} />
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Stepper({ step, onGo, status }: { step: number; onGo: (n: number) => void; status?: Status }) {
  const done = (key: string) =>
    ({
      ai: status?.checks.ai.ok,
      resume: status?.checks.resume.ok,
      prefs: status?.checks.preferences.ok,
    })[key];
  return (
    <div className="overflow-x-auto">
      <ol className="flex min-w-max items-center gap-1 rounded-2xl border bg-card/80 p-1.5 shadow-[var(--shadow-soft)] backdrop-blur">
        {STEPS.map((st, i) => {
          const active = i === step;
          const Icon = done(st.key) ? Check : st.icon;
          return (
            <li key={st.key}>
              <button
                onClick={() => onGo(i)}
                className={cn(
                  "relative flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition-colors",
                  active ? "text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {active && (
                  <motion.span
                    layoutId="onb-step"
                    className="absolute inset-0 rounded-xl bg-primary shadow-md shadow-primary/30"
                    transition={{ type: "spring", stiffness: 450, damping: 36 }}
                  />
                )}
                <Icon size={15} className={cn("relative", !active && done(st.key) && "text-success")} />
                <span className="relative hidden sm:inline">{st.label}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function StepCard({
  title,
  subtitle,
  ok,
  detail,
  children,
}: {
  title: string;
  subtitle?: string;
  ok?: boolean;
  detail?: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-6 md:p-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
        </div>
        {ok != null && (
          <Badge tone={ok ? "success" : "warning"} className="text-xs">
            {ok ? <Check size={12} /> : <CircleDashed size={12} />} {detail ?? (ok ? "pronto" : "pendente")}
          </Badge>
        )}
      </div>
      {children}
    </Card>
  );
}

function Welcome({ onNext }: { onNext: () => void }) {
  const items = [
    { icon: Bot, title: "Ligue a IA", text: "Com o seu Claude Code (assinatura) ou uma chave de API." },
    { icon: FileUp, title: "Envie seu currículo", text: "O PDF do LinkedIn ou o seu CV. A IA monta o currículo mestre." },
    { icon: Target, title: "Diga o que procura", text: "Cargos, modelo de trabalho, salário (opcional)." },
    { icon: Link2, title: "Conecte o resto", text: "Gmail, Agenda, Telegram e a extensão do navegador, quando quiser." },
  ];
  return (
    <div className="grid items-center gap-8 py-6 md:grid-cols-[1.1fr_1fr]">
      <div>
        <Badge tone="primary" className="mb-4">
          <Sparkles size={12} /> uns 10 minutos
        </Badge>
        <h1 className="text-3xl font-semibold leading-tight tracking-tight md:text-4xl">
          Sua busca de emprego,{" "}
          <span className="bg-gradient-to-r from-primary to-violet-500 bg-clip-text text-transparent">organizada e no automático</span>
        </h1>
        <p className="mt-4 text-muted-foreground">
          O app encontra vagas, dá nota de chance e atratividade, prepara o currículo certo para cada uma, ajuda a preencher candidaturas e acompanha
          as respostas no Gmail. Nada é enviado em seu nome sem você aprovar, e nada é inventado no seu currículo.
        </p>
        <Button size="lg" className="mt-6" onClick={onNext}>
          Começar <ArrowRight size={16} />
        </Button>
      </div>
      <div className="grid gap-3">
        {items.map((it, i) => (
          <motion.div
            key={it.title}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.08, duration: 0.4, ease: EASE }}
          >
            <Card interactive className="flex items-start gap-3">
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent text-primary">
                <it.icon size={17} />
              </div>
              <div>
                <p className="text-sm font-semibold">
                  {i + 1}. {it.title}
                </p>
                <p className="text-sm text-muted-foreground">{it.text}</p>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function ResumeStep({ hasResume, onDone }: { hasResume: boolean; onDone: () => void }) {
  const [phase, setPhase] = useState<"idle" | "uploading" | "extracting" | "review">("idle");
  const [importId, setImportId] = useState<string | null>(null);
  const [profile, setProfile] = useState<Master | null>(null);
  const [low, setLow] = useState<string[]>([]);
  const [drag, setDrag] = useState(false);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (phase !== "extracting" || !importId) return;
    const t = setInterval(async () => {
      try {
        const r = await (await rawFetch(`/api/v1/profile/import/${importId}`)).json();
        if (r.status === "extracted" && r.extracted) {
          setProfile(r.extracted.profile as Master);
          setLow(r.extracted.low_confidence ?? []);
          setPhase("review");
        } else if (r.status === "failed" || r.error) {
          toast.error(`Não consegui ler o arquivo: ${r.error ?? "erro"}`);
          setPhase("idle");
        }
      } catch {}
    }, 3000);
    return () => clearInterval(t);
  }, [phase, importId]);

  const upload = async (file: File) => {
    setPhase("uploading");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await (await rawFetch("/api/v1/profile/import", { method: "POST", body: fd })).json();
      setImportId(r.id);
      setPhase("extracting");
    } catch (e) {
      toast.error((e as Error).message);
      setPhase("idle");
    }
  };

  const confirm = async () => {
    if (!profile || !importId) return;
    setSaving(true);
    try {
      await rawFetch(`/api/v1/profile/import/${importId}/confirm`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ data: profile, change_note: "onboarding" }),
      });
      toast.success("Currículo mestre salvo");
      onDone();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const setContact = (k: keyof Master["contact"], v: string) => profile && setProfile({ ...profile, contact: { ...profile.contact, [k]: v } });

  return (
    <StepCard
      title="Seu currículo"
      subtitle="Ele vira o currículo mestre: a fonte de verdade para todos os CVs e respostas. Nada fora dele é usado."
      ok={hasResume}
      detail={hasResume ? "já cadastrado" : undefined}
    >
      {phase === "review" && profile ? (
        <div className="space-y-5">
          <Tip tone="info">Confira o principal. Detalhes (bullets, projetos, idiomas) dá para ajustar depois em Perfil.</Tip>
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Nome completo"><Input value={profile.contact.full_name ?? ""} onChange={(e) => setContact("full_name", e.target.value)} /></Field>
            <Field label="E-mail"><Input value={profile.contact.email ?? ""} onChange={(e) => setContact("email", e.target.value)} /></Field>
            <Field label="Telefone"><Input value={profile.contact.phone ?? ""} onChange={(e) => setContact("phone", e.target.value)} /></Field>
            <Field label="Cidade"><Input value={profile.contact.location ?? ""} onChange={(e) => setContact("location", e.target.value)} /></Field>
            <Field label="LinkedIn"><Input value={profile.contact.linkedin ?? ""} onChange={(e) => setContact("linkedin", e.target.value)} /></Field>
            <Field label="GitHub"><Input value={profile.contact.github ?? ""} onChange={(e) => setContact("github", e.target.value)} /></Field>
          </div>
          <div>
            <p className="mb-2 text-sm font-semibold">Experiências ({profile.experience.length})</p>
            <div className="divide-y rounded-xl border">
              {profile.experience.map((e) => (
                <div key={e.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{e.title}</p>
                    <p className="truncate text-xs text-muted-foreground">{e.organization}</p>
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {e.start ?? "?"} – {e.end ?? "atual"}
                  </span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-2 text-sm font-semibold">Competências</p>
            <div className="flex flex-wrap gap-1.5">
              {Object.values(profile.skills).flat().slice(0, 40).map((sk) => (
                <Badge key={sk}>{sk}</Badge>
              ))}
            </div>
          </div>
          {low.length > 0 && (
            <Tip>
              A IA ficou em dúvida em {low.length} campo(s) ({low.slice(0, 4).join(", ")}
              {low.length > 4 ? "…" : ""}). Vale revisar em Perfil depois.
            </Tip>
          )}
          <div className="flex flex-wrap gap-2">
            <Button onClick={confirm} disabled={saving}>
              {saving ? "Salvando…" : "Está certo, salvar"} <Check size={15} />
            </Button>
            <Button variant="ghost" onClick={() => setPhase("idle")}>
              Enviar outro arquivo
            </Button>
          </div>
        </div>
      ) : phase === "extracting" || phase === "uploading" ? (
        <div className="flex flex-col items-center py-12 text-center">
          <motion.div
            className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-primary to-violet-500 text-white shadow-lg shadow-primary/30"
            animate={{ scale: [1, 1.08, 1], rotate: [0, 6, -6, 0] }}
            transition={{ duration: 1.8, repeat: Infinity }}
          >
            <Sparkles size={24} />
          </motion.div>
          <p className="font-medium">{phase === "uploading" ? "Enviando…" : "Lendo o seu currículo com IA…"}</p>
          <p className="mt-1 text-sm text-muted-foreground">Leva de 30 s a 2 min. Pode deixar esta tela aberta.</p>
        </div>
      ) : (
        <div className="space-y-5">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              const f = e.dataTransfer.files[0];
              if (f) upload(f);
            }}
            onClick={() => fileRef.current?.click()}
            className={cn(
              "flex cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-all",
              drag ? "scale-[1.01] border-primary bg-accent" : "hover:border-primary/50 hover:bg-muted/40",
            )}
          >
            <div className="mb-3 grid h-12 w-12 place-items-center rounded-full bg-accent text-primary">
              <FileUp size={22} />
            </div>
            <p className="font-medium">Arraste o arquivo aqui ou clique para escolher</p>
            <p className="mt-1 text-sm text-muted-foreground">PDF ou DOCX (até 10 MB). Também aceita o YAML do currículo mestre.</p>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.yaml,.yml"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
            />
          </div>
          <div className="rounded-xl border bg-muted/30 p-4 text-sm">
            <p className="mb-1.5 font-semibold">Como baixar o PDF do seu LinkedIn</p>
            <ol className="list-decimal space-y-1 pl-5 text-muted-foreground">
              <li>Abra o seu perfil no LinkedIn (no computador).</li>
              <li>
                Clique em <b>Recursos</b> (ou <b>Mais</b>) logo abaixo do seu nome → <b>Salvar como PDF</b>.
              </li>
              <li>Envie esse PDF aqui. Se tiver um CV mais completo, envie o CV; dá para complementar depois.</li>
            </ol>
          </div>
          {hasResume && (
            <Button variant="outline" onClick={onDone}>
              Já tenho currículo salvo, continuar <ArrowRight size={15} />
            </Button>
          )}
        </div>
      )}
    </StepCard>
  );
}

function PrefsStep({ onDone }: { onDone: () => void }) {
  const prefs = useQuery({
    queryKey: ["prefs"],
    queryFn: async () => (await rawFetch("/api/v1/profile/preferences")).json() as Promise<Prefs>,
  });
  const master = useQuery({
    queryKey: ["master"],
    queryFn: async () => {
      try {
        return (await (await rawFetch("/api/v1/profile/master")).json()).data as Master;
      } catch {
        return null;
      }
    },
  });
  const [p, setP] = useState<Prefs | null>(null);
  const [salary, setSalary] = useState({ clt: "", pj: "" });
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (prefs.data && !p) {
      setP(prefs.data);
      setSalary({
        clt: String(prefs.data.salary_expectation?.CLT?.BRL ?? ""),
        pj: String(prefs.data.salary_expectation?.PJ?.BRL ?? ""),
      });
    }
  }, [prefs.data, p]);
  const suggestions = useMemo(() => {
    const titles = (master.data?.experience ?? []).map((e) => e.title);
    return [...new Set([...titles, ...ROLE_SUGGESTIONS])];
  }, [master.data]);
  if (!p) return <Skeleton className="h-96" />;
  const toggle = (k: "seniorities" | "work_models" | "regimes", v: string) =>
    setP({ ...p, [k]: p[k].includes(v) ? p[k].filter((x) => x !== v) : [...p[k], v] });
  const save = async () => {
    if (!p.target_roles.length) return toast.error("Adicione pelo menos um cargo");
    setSaving(true);
    const exp: Prefs["salary_expectation"] = {};
    if (Number(salary.clt)) exp.CLT = { BRL: Number(salary.clt) };
    if (Number(salary.pj)) exp.PJ = { BRL: Number(salary.pj) };
    try {
      await rawFetch("/api/v1/profile/preferences", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...p, salary_expectation: exp }),
      });
      toast.success("Preferências salvas");
      onDone();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <StepCard title="O que você procura" subtitle="Isso decide quais vagas entram (sem gastar IA) e como elas são avaliadas." ok={!!prefs.data?.target_roles.length}>
      <div className="space-y-6">
        <Field label="Cargos-alvo (Enter para adicionar)">
          <TagInput value={p.target_roles} onChange={(target_roles) => setP({ ...p, target_roles })} placeholder="Ex.: Data Engineer" suggestions={suggestions} />
        </Field>
        <div className="grid gap-6 md:grid-cols-2">
          <Field label="Senioridade">
            <div className="flex flex-wrap gap-1.5">
              {["junior", "mid", "senior", "staff", "lead"].map((v) => (
                <Chip key={v} active={p.seniorities.includes(v)} onClick={() => toggle("seniorities", v)}>
                  {SENIORITY_LABEL[v]}
                </Chip>
              ))}
            </div>
          </Field>
          <Field label="Modelo de trabalho">
            <div className="flex flex-wrap gap-1.5">
              {["remote", "hybrid", "onsite"].map((v) => (
                <Chip key={v} active={p.work_models.includes(v)} onClick={() => toggle("work_models", v)}>
                  {WORK_MODEL_LABEL[v]}
                </Chip>
              ))}
            </div>
          </Field>
          <Field label="Regime">
            <div className="flex flex-wrap gap-1.5">
              {["CLT", "PJ", "Cooperado", "Estágio"].map((v) => (
                <Chip key={v} active={p.regimes.includes(v)} onClick={() => toggle("regimes", v)}>
                  {v}
                </Chip>
              ))}
            </div>
          </Field>
          <Field label="Vagas internacionais">
            <div className="flex flex-wrap gap-1.5">
              <Chip active={p.international} onClick={() => setP({ ...p, international: true })}>Quero também (remoto global/LATAM)</Chip>
              <Chip active={!p.international} onClick={() => setP({ ...p, international: false })}>Só Brasil</Chip>
            </div>
          </Field>
        </div>
        <Field label="Cidades para híbrido/presencial (opcional)" hint="Vagas remotas entram independentemente da cidade.">
          <TagInput value={p.locations} onChange={(locations) => setP({ ...p, locations })} placeholder="Ex.: São Paulo, SP" />
        </Field>
        <div className="rounded-xl border p-4">
          <p className="text-sm font-semibold">Pretensão salarial (opcional)</p>
          <p className="mb-3 text-xs text-muted-foreground">
            Usada para avaliar as vagas e responder formulários. Pode deixar em branco; dá para mudar quando quiser em Perfil.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="CLT (R$/mês bruto)">
              <Input type="number" min={0} step={500} value={salary.clt} onChange={(e) => setSalary({ ...salary, clt: e.target.value })} placeholder="ex.: 9000" />
            </Field>
            <Field label="PJ (R$/mês)">
              <Input type="number" min={0} step={500} value={salary.pj} onChange={(e) => setSalary({ ...salary, pj: e.target.value })} placeholder="ex.: 14000" />
            </Field>
          </div>
        </div>
        <Button onClick={save} disabled={saving}>
          {saving ? "Salvando…" : "Salvar e continuar"} <ArrowRight size={15} />
        </Button>
      </div>
    </StepCard>
  );
}

function CurrentJobStep({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ company: "", regime: "CLT", monthly_gross: "", meal_monthly: "", plr_salaries: "" });
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    rawFetch("/api/v1/settings/current_compensation")
      .then((r) => r.json())
      .then((c) =>
        setF({
          company: c.company ?? "",
          regime: c.regime ?? "CLT",
          monthly_gross: c.monthly_gross ? String(c.monthly_gross) : "",
          meal_monthly: c.meal_monthly ? String(c.meal_monthly) : "",
          plr_salaries: c.plr_salaries ? String(c.plr_salaries) : "",
        }),
      )
      .catch(() => {});
  }, []);
  const save = async () => {
    setSaving(true);
    try {
      await rawFetch("/api/v1/settings/current_compensation", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          company: f.company || null,
          regime: f.regime,
          monthly_gross: Number(f.monthly_gross) || 0,
          meal_monthly: Number(f.meal_monthly) || 0,
          plr_salaries: Number(f.plr_salaries) || 0,
        }),
      });
      toast.success("Salvo");
      onDone();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <StepCard
      title="Emprego atual (opcional)"
      subtitle="Serve de base no comparador de ofertas (quanto cai na conta, PJ equivalente). Fica só no seu banco de dados."
    >
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Empresa"><Input value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} placeholder="Onde você trabalha hoje" /></Field>
        <Field label="Regime">
          <Select value={f.regime} onChange={(e) => setF({ ...f, regime: e.target.value })}>
            <option>CLT</option>
            <option>PJ</option>
          </Select>
        </Field>
        <Field label="Salário bruto por mês (R$)"><Input type="number" min={0} value={f.monthly_gross} onChange={(e) => setF({ ...f, monthly_gross: e.target.value })} /></Field>
        <Field label="Vale-refeição/alimentação por mês (R$)"><Input type="number" min={0} value={f.meal_monthly} onChange={(e) => setF({ ...f, meal_monthly: e.target.value })} /></Field>
        <Field label="PLR (nº de salários por ano)" hint="ex.: 1,5"><Input type="number" min={0} step={0.5} value={f.plr_salaries} onChange={(e) => setF({ ...f, plr_salaries: e.target.value })} /></Field>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">Plano de saúde, previdência e outros benefícios você completa depois em Ofertas.</p>
      <Button className="mt-5" onClick={save} disabled={saving}>
        {saving ? "Salvando…" : "Salvar e continuar"} <ArrowRight size={15} />
      </Button>
    </StepCard>
  );
}

function IntegrationsStep({ s }: { s: Status }) {
  const [tab, setTab] = useState<"google" | "telegram" | "extension">("google");
  const ok = { google: s.checks.google.ok, telegram: s.checks.telegram.ok, extension: s.checks.extension.ok };
  return (
    <StepCard title="Integrações (todas opcionais)" subtitle="Dá para fazer agora ou depois em Configurações → Integrações. Cada passo explica onde clicar.">
      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: "google", label: `${ok.google ? "✓ " : ""}Gmail e Agenda` },
          { value: "telegram", label: `${ok.telegram ? "✓ " : ""}Telegram` },
          { value: "extension", label: `${ok.extension ? "✓ " : ""}Extensão do navegador` },
        ]}
      />
      {tab === "google" && (
        <GoogleGuide redirectUris={s.checks.google.redirect_uris ?? []} configured={!!s.checks.google.configured} connected={s.checks.google.ok} />
      )}
      {tab === "telegram" && <TelegramGuide configured={!!s.checks.telegram.configured} linked={s.checks.telegram.ok} />}
      {tab === "extension" && <ExtensionGuide />}
    </StepCard>
  );
}

function FinishStep({ s }: { s: Status }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [opts, setOpts] = useState({ seed_companies: true, create_search: true, run_now: true });
  const [busy, setBusy] = useState(false);
  const ready = s.checks.resume.ok && s.checks.preferences.ok;
  const finish = async () => {
    setBusy(true);
    try {
      await rawFetch("/api/v1/onboarding/complete", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(opts),
      });
      await qc.invalidateQueries({ queryKey: ["onboarding"] });
      toast.success("Tudo pronto! A primeira busca de vagas já começou.");
      router.push(opts.run_now ? "/vagas" : "/hoje");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const rows: [string, Check_, boolean][] = [
    ["IA", s.checks.ai, true],
    ["Currículo mestre", s.checks.resume, true],
    ["Cargos-alvo", s.checks.preferences, true],
    ["PDF dos currículos (tectonic)", s.checks.latex, false],
    ["Gmail e Agenda", s.checks.google, false],
    ["Telegram", s.checks.telegram, false],
    ["Extensão do navegador", s.checks.extension, false],
  ];
  return (
    <StepCard title="Revisão final" subtitle="O essencial precisa estar verde; o resto você liga quando quiser.">
      <div className="divide-y rounded-xl border">
        {rows.map(([label, c, required]) => (
          <div key={label} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
            <span className="flex items-center gap-2">
              {c.ok ? <Check size={15} className="text-success" /> : <CircleDashed size={15} className={required ? "text-warning" : "text-muted-foreground"} />}
              {label}
              {!required && <span className="text-xs text-muted-foreground">(opcional)</span>}
            </span>
            <span className="truncate text-xs text-muted-foreground">{c.detail ?? (c.ok ? "ok" : "pendente")}</span>
          </div>
        ))}
      </div>
      <div className="mt-5 space-y-2 text-sm">
        {(
          [
            ["seed_companies", "Monitorar 100 empresas com site de vagas público (48 no Brasil, 52 fora)"],
            ["create_search", "Criar uma busca salva com os seus cargos-alvo (roda às 9h e 15h nos dias úteis)"],
            ["run_now", "Fazer a primeira busca agora"],
          ] as const
        ).map(([k, label]) => (
          <label key={k} className="flex cursor-pointer items-center gap-2">
            <input type="checkbox" checked={opts[k]} onChange={(e) => setOpts({ ...opts, [k]: e.target.checked })} className="accent-[var(--primary)]" />
            {label}
          </label>
        ))}
      </div>
      {!s.checks.ai.ok && <div className="mt-4"><Tip>Sem IA as vagas entram, mas sem leitura detalhada e notas completas.</Tip></div>}
      <Button size="lg" className="mt-6" disabled={!ready || busy} onClick={finish}>
        {busy ? "Preparando…" : "Concluir e ver as vagas"} <PartyPopper size={16} />
      </Button>
      {!ready && <p className="mt-2 text-xs text-warning">Falta o currículo e/ou os cargos-alvo.</p>}
      <p className="mt-6 flex items-center gap-1.5 text-xs text-muted-foreground">
        <BriefcaseBusiness size={13} /> Você pode voltar a esta tela em Configurações → Sistema.
      </p>
    </StepCard>
  );
}
