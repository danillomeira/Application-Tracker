"use client";

import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  Bell,
  Briefcase,
  Calendar,
  FileText,
  Home,
  Inbox,
  KanbanSquare,
  Menu,
  Mic,
  Settings,
  Sparkles,
  UserRound,
  Users,
  Wallet,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, rawFetch } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useLiveEvents } from "@/lib/ws";
import { ThemeToggle } from "./theme-toggle";
import { PageTour, TourButton } from "./tour";
import { EASE } from "./ui";

const NAV_GROUPS = [
  {
    label: "Rotina",
    items: [
      { href: "/hoje", label: "Hoje", icon: Home },
      { href: "/vagas", label: "Vagas", icon: Briefcase },
      { href: "/candidaturas", label: "Candidaturas", icon: KanbanSquare },
      { href: "/inbox", label: "Inbox", icon: Inbox },
      { href: "/agenda", label: "Agenda", icon: Calendar },
      { href: "/entrevistas", label: "Entrevistas", icon: Mic },
    ],
  },
  {
    label: "Você",
    items: [
      { href: "/perfil", label: "Perfil", icon: UserRound },
      { href: "/curriculos", label: "Currículos", icon: FileText },
      { href: "/pessoas", label: "Pessoas", icon: Users },
      { href: "/ofertas", label: "Ofertas", icon: Wallet },
      { href: "/insights", label: "Insights", icon: BarChart3 },
    ],
  },
  { label: "Sistema", items: [{ href: "/config", label: "Configurações", icon: Settings }] },
];

function Brand() {
  return (
    <Link href="/hoje" className="flex items-center gap-2.5 px-2">
      <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-primary to-sky-500 text-white shadow-md shadow-primary/30">
        <Sparkles size={16} />
      </div>
      <div className="leading-tight">
        <p className="text-sm font-semibold tracking-tight">Application Tracker</p>
        <p className="text-[11px] text-muted-foreground">sua busca de emprego</p>
      </div>
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const connected = useLiveEvents();

  const me = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/auth/me");
      if (!res.data) throw new Error("unauthenticated");
      return res.data;
    },
    retry: false,
  });
  const onboarding = useQuery({
    queryKey: ["onboarding"],
    queryFn: async () => (await rawFetch("/api/v1/onboarding/status")).json() as Promise<{ completed: boolean }>,
    enabled: me.isSuccess,
    staleTime: 60_000,
  });
  const unread = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: async () => (await api.GET("/api/v1/notifications", { params: { query: { unread: true } } })).data ?? [],
    enabled: me.isSuccess,
  });

  useEffect(() => {
    if (me.isError) router.replace("/login");
  }, [me.isError, router]);
  useEffect(() => {
    if (onboarding.data && !onboarding.data.completed) router.replace("/onboarding");
  }, [onboarding.data, router]);
  useEffect(() => setOpen(false), [pathname]);
  const [desktop, setDesktop] = useState(true);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const on = () => setDesktop(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (onboarding.isError) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
        <p className="font-semibold">Não consegui falar com a API.</p>
        <p className="max-w-sm text-sm text-muted-foreground">Confira se ela está rodando (porta 8000) e tente de novo.</p>
        <button className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground" onClick={() => onboarding.refetch()}>
          Tentar de novo
        </button>
      </div>
    );
  }
  if (!me.isSuccess || !onboarding.data?.completed) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <motion.div
          className="h-9 w-9 rounded-xl bg-gradient-to-br from-primary to-sky-500"
          animate={{ rotate: [0, 90, 180, 270, 360], borderRadius: ["30%", "50%", "30%"] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>
    );
  }

  const count = unread.data?.length ?? 0;
  return (
    <div className="flex min-h-screen">
      <AnimatePresence>
        {open && (
          <motion.div
            className="fixed inset-0 z-30 bg-slate-950/40 backdrop-blur-sm md:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setOpen(false)}
          />
        )}
      </AnimatePresence>
      <aside
        inert={!open && !desktop}
        aria-hidden={!open && !desktop ? true : undefined}
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r bg-sidebar px-3 py-4 transition-transform duration-300 md:sticky md:top-0 md:h-screen md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="mb-6 flex items-center justify-between">
          <Brand />
          <button className="rounded-lg p-1 hover:bg-muted md:hidden" onClick={() => setOpen(false)} aria-label="Fechar menu">
            <X size={18} />
          </button>
        </div>
        <nav className="flex flex-1 flex-col gap-4 overflow-y-auto">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <p className="mb-1.5 px-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
                {group.label}
              </p>
              <div className="flex flex-col gap-0.5">
                {group.items.map(({ href, label, icon: Icon }) => {
                  const active = pathname.startsWith(href);
                  return (
                    <Link
                      key={href}
                      href={href}
                      className={cn(
                        "relative flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
                        active ? "font-medium text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      )}
                    >
                      {active && (
                        <motion.span
                          layoutId="nav-active"
                          className="absolute inset-0 rounded-lg bg-accent"
                          transition={{ type: "spring", stiffness: 500, damping: 40 }}
                        />
                      )}
                      <Icon size={17} className="relative" />
                      <span className="relative">{label}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
        <div className="mt-4 flex items-center justify-between rounded-xl border bg-card px-3 py-2">
          <div className="min-w-0">
            <p className="truncate text-xs font-medium">{me.data.email}</p>
            <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <span className={cn("h-1.5 w-1.5 rounded-full", connected ? "bg-success" : "bg-danger")} />
              {connected ? "tempo real ativo" : "reconectando…"}
            </p>
          </div>
          <ThemeToggle />
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col overflow-x-clip">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur-md md:px-6">
          <button className="rounded-lg p-1.5 hover:bg-muted md:hidden" onClick={() => setOpen(true)} aria-label="Abrir menu">
            <Menu size={18} />
          </button>
          <div className="flex-1" />
          <TourButton />
          <Link
            href="/config?tab=notificacoes"
            className="relative grid h-9 w-9 place-items-center rounded-lg transition-colors hover:bg-muted"
            aria-label={`Notificações${count ? ` (${count} não lidas)` : ""}`}
          >
            <Bell size={18} />
            <AnimatePresence>
              {count > 0 && (
                <motion.span
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  exit={{ scale: 0 }}
                  className="absolute right-1 top-1 grid min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] font-semibold text-white"
                >
                  {count}
                </motion.span>
              )}
            </AnimatePresence>
          </Link>
        </header>
        <main className="mx-auto w-full max-w-[1680px] flex-1 px-4 py-5 md:px-6 md:py-6">
          {/* Só animação de entrada. AnimatePresence com exit no App Router troca o conteúdo antes da saída
              terminar e a página nova fica presa invisível (opacity 0). */}
          <motion.div
            key={pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, ease: EASE }}
          >
            {children}
          </motion.div>
        </main>
        <PageTour />
      </div>
    </div>
  );
}
