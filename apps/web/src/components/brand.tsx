"use client";
/** Logo da empresa, ícones de tecnologia e dica (tooltip) usada para explicar botões. */
import { useState } from "react";
import { Avatar } from "@/components/ui";
import { techIcon } from "@/lib/tech-icons";
import { cn } from "@/lib/utils";

/** Logo do site da empresa (cache no backend), pelo id ou só pelo nome; sem logo, as iniciais coloridas. */
export function CompanyLogo({ id, name, className }: { id?: string | null; name: string | null | undefined; className?: string }) {
  const [failed, setFailed] = useState(false);
  const src = id ? `/api/v1/companies/${id}/logo` : name ? `/api/v1/companies/logo?name=${encodeURIComponent(name)}` : null;
  if (!src || failed) return <Avatar name={name} className={className} />;
  return (
    <div className={cn("grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-xl border bg-white p-1.5 shadow-sm", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={`Logo ${name ?? ""}`}
        loading="lazy"
        className="h-full w-full object-contain"
        onError={() => setFailed(true)}
      />
    </div>
  );
}

/** Dica ao passar o mouse ou focar (acessível por teclado). */
export function Tooltip({ label, children, side = "top" }: { label: string; children: React.ReactNode; side?: "top" | "bottom" }) {
  return (
    <span className="group/tt relative inline-flex">
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none invisible absolute left-1/2 z-50 w-max max-w-56 -translate-x-1/2 rounded-md bg-slate-900 px-2 py-1 text-center text-[11px] leading-snug text-white opacity-0 shadow-lg transition-opacity duration-150 group-focus-within/tt:visible group-focus-within/tt:opacity-100 group-hover/tt:visible group-hover/tt:opacity-100 dark:bg-slate-700",
          side === "top" ? "bottom-full mb-1.5" : "top-full mt-1.5",
        )}
      >
        {label}
      </span>
    </span>
  );
}

function TechBadge({ name, size, onPick }: { name: string; size: number; onPick?: (tech: string) => void }) {
  const [failed, setFailed] = useState(false);
  const src = techIcon(name);
  // com onPick vira botão (filtra por essa tecnologia); sem, é só um rótulo com foco para o tooltip
  const Tag = onPick ? "button" : "span";
  const props = {
    title: onPick ? `Filtrar por ${name}` : name,
    "aria-label": onPick ? `Filtrar por ${name}` : name,
    tabIndex: 0,
    ...(onPick
      ? {
          type: "button" as const,
          onClick: (e: React.MouseEvent) => {
            e.stopPropagation();
            onPick(name);
          },
          onKeyDown: (e: React.KeyboardEvent) => e.stopPropagation(),
        }
      : {}),
  };
  if (!src || failed) {
    return (
      <Tag {...props} className="inline-flex h-7 items-center rounded-lg border bg-card px-2 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary">
        {name}
      </Tag>
    );
  }
  return (
    <Tooltip label={name}>
      <Tag {...props} className="grid place-items-center rounded-lg border bg-card p-1 shadow-sm transition-colors hover:border-primary/40" style={{ width: size + 10, height: size + 10 }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt="" width={size} height={size} loading="lazy" onError={() => setFailed(true)} />
      </Tag>
    </Tooltip>
  );
}

/** Tecnologias como ícones (nome no tooltip). Com ícone primeiro; o resto vira "+N". */
export function TechIcons({ techs, max = 6, size = 18, onPick }: { techs: string[]; max?: number; size?: number; onPick?: (tech: string) => void }) {
  const uniq = [...new Set(techs.map((t) => t.trim()).filter((t) => t && t.length <= 30))];
  const withIcon = uniq.filter((t) => techIcon(t));
  const ordered = [...withIcon, ...uniq.filter((t) => !techIcon(t))];
  const shown = ordered.slice(0, max);
  const rest = ordered.length - shown.length;
  if (!shown.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {shown.map((t) => (
        <TechBadge key={t} name={t} size={size} onPick={onPick} />
      ))}
      {rest > 0 && (
        <Tooltip label={ordered.slice(max).join(", ")}>
          <span className="inline-flex h-7 items-center rounded-lg bg-muted px-2 text-[11px] font-medium text-muted-foreground">+{rest}</span>
        </Tooltip>
      )}
    </div>
  );
}

/** Ícone pequeno da tecnologia (para chips de filtro). */
export function TechDot({ name }: { name: string }) {
  const src = techIcon(name);
  // eslint-disable-next-line @next/next/no-img-element
  return src ? <img src={src} alt="" width={14} height={14} loading="lazy" className="shrink-0" /> : null;
}
