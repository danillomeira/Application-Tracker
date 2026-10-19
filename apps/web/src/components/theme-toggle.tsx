"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";
const ORDER: Theme[] = ["system", "light", "dark"];
const ICON = { system: Monitor, light: Sun, dark: Moon };
const LABEL = { system: "Tema do sistema", light: "Tema claro", dark: "Tema escuro" };

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.classList.toggle("light", theme === "light");
}

/** Alterna sistema → claro → escuro; lembra a escolha neste navegador. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");
  useEffect(() => {
    try {
      setTheme((localStorage.getItem("theme") as Theme) || "system");
    } catch {}
  }, []);
  const next = () => {
    const t = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
    setTheme(t);
    applyTheme(t);
    try {
      localStorage.setItem("theme", t);
    } catch {}
  };
  const Icon = ICON[theme];
  return (
    <button
      onClick={next}
      aria-label={`${LABEL[theme]} (clique para trocar)`}
      title={LABEL[theme]}
      className="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground transition-all hover:bg-muted hover:text-foreground active:scale-90"
    >
      <Icon size={16} />
    </button>
  );
}

/** Script inline no <head>: aplica o tema antes da pintura (sem "piscar"). */
export const THEME_SCRIPT = `try{var t=localStorage.getItem("theme");if(t==="dark")document.documentElement.classList.add("dark");if(t==="light")document.documentElement.classList.add("light")}catch(e){}`;
