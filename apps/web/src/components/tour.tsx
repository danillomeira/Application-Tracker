"use client";
/** Tour guiado por tela: destaca cada parte importante e explica o que fazer. Aparece na primeira visita. */
import { HelpCircle } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { Button, EASE } from "@/components/ui";
import { TOURS } from "@/lib/tours";

const VERSION = "v1";
const EVENT = "tracker:tour";

/** Tour só nas telas principais (/vagas, /candidaturas…); subpáginas como /vagas/123 não têm. */
function pageKey(pathname: string) {
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length > 1) return "";
  return parts[0] ?? "hoje";
}

function seen(page: string) {
  try {
    return localStorage.getItem(`tour:${page}:${VERSION}`) === "1";
  } catch {
    return true;
  }
}

function markSeen(page: string) {
  try {
    localStorage.setItem(`tour:${page}:${VERSION}`, "1");
  } catch {}
}

/** Botão "Como usar esta tela" (no cabeçalho). */
export function TourButton() {
  const page = pageKey(usePathname());
  if (!TOURS[page]) return null;
  return (
    <button
      data-tour="help"
      aria-label="Como usar esta tela"
      onClick={() => window.dispatchEvent(new CustomEvent(EVENT))}
      className="inline-flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      <HelpCircle size={17} />
      <span className="hidden sm:inline">Como usar esta tela</span>
    </button>
  );
}

type Rect = { top: number; left: number; width: number; height: number };

export function PageTour() {
  const pathname = usePathname();
  const page = pageKey(pathname);
  const steps = TOURS[page];
  const [i, setI] = useState<number | null>(null);
  const [rect, setRect] = useState<Rect | null>(null);

  const close = useCallback(() => {
    setI(null);
    markSeen(page);
  }, [page]);

  useEffect(() => {
    setI(null);
    if (!steps || seen(page)) return;
    // começa quando o primeiro item destacado já está na tela (listas carregam depois), ou após 6 s
    const target = steps.find((s) => s.target)?.target;
    const startedAt = Date.now();
    const t = setInterval(() => {
      if (!target || document.querySelector(`[data-tour="${target}"]`) || Date.now() - startedAt > 6000) {
        clearInterval(t);
        setI(0);
      }
    }, 300);
    return () => clearInterval(t);
  }, [page, steps]);

  useEffect(() => {
    const start = () => steps && setI(0);
    window.addEventListener(EVENT, start);
    return () => window.removeEventListener(EVENT, start);
  }, [steps]);

  const step = i != null && steps ? steps[i] : null;

  useLayoutEffect(() => {
    if (!step?.target) {
      setRect(null);
      return;
    }
    const el = document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`);
    if (!el) {
      setRect(null);
      return;
    }
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    const update = () => {
      const r = el.getBoundingClientRect();
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    };
    update();
    const t = setTimeout(update, 400); // depois do scroll suave
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      clearTimeout(t);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [step]);

  useEffect(() => {
    if (i == null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight" && steps && i < steps.length - 1) setI(i + 1);
      if (e.key === "ArrowLeft" && i > 0) setI(i - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [i, steps, close]);

  if (!steps) return null;
  const pad = 8;
  const vw = typeof window !== "undefined" ? window.innerWidth : 1200;
  const vh = typeof window !== "undefined" ? window.innerHeight : 800;
  const W = Math.min(360, vw - 24);
  let pos: { left: number; top: number } = { left: (vw - W) / 2, top: vh / 2 - 120 };
  if (rect) {
    const below = rect.top + rect.height + pad + 12;
    const fitsBelow = below + 220 < vh;
    const top = fitsBelow ? below : Math.max(12, rect.top - pad - 12 - 220);
    const left = Math.min(Math.max(12, rect.left + rect.width / 2 - W / 2), vw - W - 12);
    pos = { left, top };
  }

  return (
    <AnimatePresence>
      {step && i != null && (
        <motion.div key="tour" className="fixed inset-0 z-[60]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          {rect ? (
            <motion.div
              className="pointer-events-none fixed rounded-xl ring-2 ring-primary"
              style={{ boxShadow: "0 0 0 9999px rgb(2 6 23 / 0.55)" }}
              animate={{ top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }}
              transition={{ duration: 0.3, ease: EASE }}
            />
          ) : (
            <div className="fixed inset-0 bg-slate-950/55" />
          )}
          <div className="fixed inset-0" onClick={close} aria-hidden />
          <motion.div
            role="dialog"
            aria-label={step.title}
            className="fixed rounded-2xl border bg-card p-5 shadow-2xl"
            style={{ width: W }}
            initial={false}
            animate={{ ...pos, opacity: 1 }}
            transition={{ duration: 0.3, ease: EASE }}
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-primary">
              {i + 1} de {steps.length}
            </p>
            <h3 className="mt-1 font-semibold tracking-tight">{step.title}</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{step.body}</p>
            <div className="mt-4 flex items-center gap-2">
              <button onClick={close} className="text-xs font-medium text-muted-foreground hover:text-foreground">
                Pular tour
              </button>
              <div className="flex-1" />
              {i > 0 && (
                <Button size="sm" variant="ghost" onClick={() => setI(i - 1)}>
                  Voltar
                </Button>
              )}
              <Button size="sm" onClick={() => (i < steps.length - 1 ? setI(i + 1) : close())}>
                {i < steps.length - 1 ? "Próximo" : "Entendi"}
              </Button>
            </div>
            <div className="mt-3 flex justify-center gap-1">
              {steps.map((_, k) => (
                <span key={k} className={`h-1.5 rounded-full transition-all ${k === i ? "w-4 bg-primary" : "w-1.5 bg-muted"}`} />
              ))}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
