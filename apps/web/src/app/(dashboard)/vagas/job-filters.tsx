"use client";

import { ChevronDown, Search, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { Chip, EASE, Input, Label } from "@/components/ui";
import { APPLY_KIND_LABEL, QUADRANT_LABEL, SENIORITY_LABEL, WORK_MODEL_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";

export type Facets = {
  total: number;
  techs: { value: string; count: number }[];
  companies: { id: string; name: string; count: number }[];
  work_model: { value: string; count: number }[];
  regime: { value: string; count: number }[];
  seniority: { value: string; count: number }[];
  apply_kind: { value: string; count: number }[];
  salary: { count: number; min: number | null; max: number | null };
};

export type Filters = {
  q: string;
  quadrant: string[];
  triage: string;
  sort: string;
  tech: string[];
  company: string[];
  work_model: string[];
  regime: string[];
  seniority: string[];
  apply_kind: string[];
  location: string;
  salary_min: number | null;
  with_salary: boolean;
  posted_within_days: number | null;
  min_chance: number | null;
  min_attractiveness: number | null;
  applied: "" | "true" | "false";
};

export const EMPTY: Filters = {
  q: "",
  quadrant: [],
  triage: "new",
  sort: "priority",
  tech: [],
  company: [],
  work_model: [],
  regime: [],
  seniority: [],
  apply_kind: [],
  location: "",
  salary_min: null,
  with_salary: false,
  posted_within_days: null,
  min_chance: null,
  min_attractiveness: null,
  applied: "",
};

const LISTS = ["quadrant", "tech", "company", "work_model", "regime", "seniority", "apply_kind"] as const;
const NUMS = ["salary_min", "posted_within_days", "min_chance", "min_attractiveness"] as const;

export function fromParams(sp: URLSearchParams): Filters {
  const f: Filters = { ...EMPTY };
  for (const k of LISTS) f[k] = sp.getAll(k);
  for (const k of NUMS) f[k] = sp.get(k) ? Number(sp.get(k)) : null;
  f.q = sp.get("q") ?? "";
  f.location = sp.get("location") ?? "";
  f.triage = sp.has("triage") ? (sp.get("triage") ?? "") : EMPTY.triage;
  f.sort = sp.get("sort") ?? EMPTY.sort;
  f.with_salary = sp.get("with_salary") === "true";
  f.applied = (sp.get("applied") as Filters["applied"]) ?? "";
  return f;
}

/** Filtros → query string (para a URL e para a API). A API aceita um quadrante; vários viram filtro local. */
export function toParams(f: Filters, forApi = false): URLSearchParams {
  const sp = new URLSearchParams();
  for (const k of LISTS) {
    if (forApi && k === "quadrant") continue;
    f[k].forEach((v) => sp.append(k, v));
  }
  for (const k of NUMS) if (f[k] != null) sp.set(k, String(f[k]));
  if (f.q) sp.set("q", f.q);
  if (f.location) sp.set("location", f.location);
  if (f.triage !== EMPTY.triage || forApi) sp.set("triage", f.triage);
  if (f.sort !== EMPTY.sort || forApi) sp.set("sort", f.sort);
  if (f.with_salary) sp.set("with_salary", "true");
  if (f.applied) sp.set("applied", f.applied);
  if (forApi && f.quadrant.length === 1) sp.set("quadrant", f.quadrant[0]);
  return sp;
}

export function activeCount(f: Filters) {
  return (
    LISTS.reduce((n, k) => n + f[k].length, 0) +
    NUMS.filter((k) => f[k] != null).length +
    (f.q ? 1 : 0) +
    (f.location ? 1 : 0) +
    (f.with_salary ? 1 : 0) +
    (f.applied ? 1 : 0) +
    (f.triage !== EMPTY.triage ? 1 : 0)
  );
}

function toggle(list: string[], v: string) {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

function Section({ title, children, defaultOpen = true, badge }: { title: string; children: React.ReactNode; defaultOpen?: boolean; badge?: number }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b py-3 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground"
        aria-expanded={open}
      >
        <span className="flex items-center gap-1.5">
          {title}
          {!!badge && <span className="rounded-full bg-primary px-1.5 text-[10px] text-primary-foreground">{badge}</span>}
        </span>
        <motion.span animate={{ rotate: open ? 0 : -90 }} transition={{ duration: 0.2 }}>
          <ChevronDown size={14} />
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: EASE }}
            className="overflow-hidden"
          >
            <div className="pt-2.5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ChipGroup({
  options,
  selected,
  onChange,
  labels,
}: {
  options: { value: string; count?: number }[];
  selected: string[];
  onChange: (v: string[]) => void;
  labels?: Record<string, string>;
}) {
  if (!options.length) return <p className="text-xs text-muted-foreground">Sem dados ainda.</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <Chip key={o.value} active={selected.includes(o.value)} count={o.count} onClick={() => onChange(toggle(selected, o.value))}>
          {labels?.[o.value] ?? o.value}
        </Chip>
      ))}
    </div>
  );
}

function SearchableList<T extends { key: string; label: string; count: number }>({
  items,
  selected,
  onToggle,
  placeholder,
  initial = 14,
}: {
  items: T[];
  selected: string[];
  onToggle: (key: string) => void;
  placeholder: string;
  initial?: number;
}) {
  const [term, setTerm] = useState("");
  const [all, setAll] = useState(false);
  const t = term.trim().toLowerCase();
  const filtered = items.filter((i) => !t || i.label.toLowerCase().includes(t));
  const chosen = filtered.filter((i) => selected.includes(i.key));
  const rest = filtered.filter((i) => !selected.includes(i.key));
  const shown = [...chosen, ...(all || t ? rest : rest.slice(0, initial))];
  return (
    <div className="space-y-2">
      <div className="relative">
        <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input value={term} onChange={(e) => setTerm(e.target.value)} placeholder={placeholder} className="h-8 pl-7 text-xs" />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {shown.map((i) => (
          <Chip key={i.key} active={selected.includes(i.key)} count={i.count} onClick={() => onToggle(i.key)}>
            {i.label}
          </Chip>
        ))}
      </div>
      {!t && rest.length > initial && (
        <button type="button" onClick={() => setAll(!all)} className="text-xs font-medium text-primary hover:underline">
          {all ? "Mostrar menos" : `Mostrar todas (${items.length})`}
        </button>
      )}
    </div>
  );
}

function Range({
  label,
  value,
  onChange,
  min,
  max,
  step,
  format,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  min: number;
  max: number;
  step: number;
  format: (n: number) => string;
}) {
  const v = value ?? min;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <Label>{label}</Label>
        <span className={cn("font-semibold tabular-nums", value == null && "text-muted-foreground")}>
          {value == null ? "qualquer" : format(v)}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={v}
        onChange={(e) => {
          const n = Number(e.target.value);
          onChange(n <= min ? null : n);
        }}
        className="w-full accent-[var(--primary)]"
        aria-label={label}
      />
    </div>
  );
}

const brl = (n: number) => n.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const POSTED = [
  { value: 1, label: "24 h" },
  { value: 3, label: "3 dias" },
  { value: 7, label: "7 dias" },
  { value: 30, label: "30 dias" },
];

export function FilterPanel({ f, set, facets }: { f: Filters; set: (p: Partial<Filters>) => void; facets?: Facets }) {
  const salaryMax = Math.max(30000, Math.ceil((facets?.salary.max ?? 30000) / 5000) * 5000);
  return (
    <div className="text-sm">
      <Section title="Prioridade" badge={f.quadrant.length}>
        <ChipGroup
          options={["top", "bet", "volume", "discard", "blocked"].map((v) => ({ value: v }))}
          selected={f.quadrant}
          onChange={(quadrant) => set({ quadrant })}
          labels={QUADRANT_LABEL}
        />
      </Section>
      <Section title="Tecnologias" badge={f.tech.length}>
        <SearchableList
          items={(facets?.techs ?? []).map((t) => ({ key: t.value, label: t.value, count: t.count }))}
          selected={f.tech}
          onToggle={(k) => set({ tech: toggle(f.tech, k) })}
          placeholder="Python, React, AWS…"
        />
        <p className="mt-2 text-[11px] text-muted-foreground">Vaga precisa citar todas as selecionadas.</p>
      </Section>
      <Section title="Empresas" badge={f.company.length}>
        <SearchableList
          items={(facets?.companies ?? []).map((c) => ({ key: c.id, label: c.name, count: c.count }))}
          selected={f.company}
          onToggle={(k) => set({ company: toggle(f.company, k) })}
          placeholder="Buscar empresa"
          initial={10}
        />
      </Section>
      <Section title="Salário" badge={(f.salary_min != null ? 1 : 0) + (f.with_salary ? 1 : 0)}>
        <div className="space-y-3">
          <Range label="Mínimo por mês" value={f.salary_min} onChange={(salary_min) => set({ salary_min })} min={0} max={salaryMax} step={500} format={brl} />
          <label className="flex cursor-pointer items-center gap-2 text-xs">
            <input type="checkbox" checked={f.with_salary} onChange={(e) => set({ with_salary: e.target.checked })} className="accent-[var(--primary)]" />
            Só vagas que informam salário
            <span className="text-muted-foreground">({facets?.salary.count ?? 0})</span>
          </label>
          <p className="text-[11px] text-muted-foreground">Anual é convertido para mensal (÷ 12). Poucas vagas informam salário.</p>
        </div>
      </Section>
      <Section title="Modelo de trabalho" badge={f.work_model.length}>
        <ChipGroup options={facets?.work_model ?? []} selected={f.work_model} onChange={(work_model) => set({ work_model })} labels={WORK_MODEL_LABEL} />
      </Section>
      <Section title="Senioridade" badge={f.seniority.length}>
        <ChipGroup options={facets?.seniority ?? []} selected={f.seniority} onChange={(seniority) => set({ seniority })} labels={SENIORITY_LABEL} />
      </Section>
      <Section title="Regime" badge={f.regime.length} defaultOpen={false}>
        <ChipGroup options={facets?.regime ?? []} selected={f.regime} onChange={(regime) => set({ regime })} />
      </Section>
      <Section title="Local" badge={f.location ? 1 : 0} defaultOpen={false}>
        <Input value={f.location} onChange={(e) => set({ location: e.target.value })} placeholder="São Paulo, Brasil, Remote…" className="h-8 text-xs" />
      </Section>
      <Section title="Publicada há" badge={f.posted_within_days != null ? 1 : 0} defaultOpen={false}>
        <div className="flex flex-wrap gap-1.5">
          {POSTED.map((p) => (
            <Chip
              key={p.value}
              active={f.posted_within_days === p.value}
              onClick={() => set({ posted_within_days: f.posted_within_days === p.value ? null : p.value })}
            >
              até {p.label}
            </Chip>
          ))}
        </div>
      </Section>
      <Section title="Notas mínimas" badge={(f.min_chance != null ? 1 : 0) + (f.min_attractiveness != null ? 1 : 0)} defaultOpen={false}>
        <div className="space-y-3">
          <Range label="Chance" value={f.min_chance} onChange={(min_chance) => set({ min_chance })} min={0} max={95} step={5} format={(n) => `≥ ${n}`} />
          <Range
            label="Atratividade"
            value={f.min_attractiveness}
            onChange={(min_attractiveness) => set({ min_attractiveness })}
            min={0}
            max={95}
            step={5}
            format={(n) => `≥ ${n}`}
          />
        </div>
      </Section>
      <Section title="Candidatura" badge={f.apply_kind.length + (f.applied ? 1 : 0)} defaultOpen={false}>
        <div className="space-y-2.5">
          <ChipGroup options={facets?.apply_kind ?? []} selected={f.apply_kind} onChange={(apply_kind) => set({ apply_kind })} labels={APPLY_KIND_LABEL} />
          <div className="flex flex-wrap gap-1.5">
            <Chip active={f.applied === "false"} onClick={() => set({ applied: f.applied === "false" ? "" : "false" })}>
              Ainda não me candidatei
            </Chip>
            <Chip active={f.applied === "true"} onClick={() => set({ applied: f.applied === "true" ? "" : "true" })}>
              Já me candidatei
            </Chip>
          </div>
        </div>
      </Section>
    </div>
  );
}

/** Chips dos filtros ativos, removíveis um a um. */
export function ActiveFilters({ f, set, facets, onClear }: { f: Filters; set: (p: Partial<Filters>) => void; facets?: Facets; onClear: () => void }) {
  const company = (id: string) => facets?.companies.find((c) => c.id === id)?.name ?? "empresa";
  const items: { key: string; label: string; remove: () => void }[] = [
    ...f.quadrant.map((v) => ({ key: `q-${v}`, label: QUADRANT_LABEL[v] ?? v, remove: () => set({ quadrant: f.quadrant.filter((x) => x !== v) }) })),
    ...f.tech.map((v) => ({ key: `t-${v}`, label: v, remove: () => set({ tech: f.tech.filter((x) => x !== v) }) })),
    ...f.company.map((v) => ({ key: `c-${v}`, label: company(v), remove: () => set({ company: f.company.filter((x) => x !== v) }) })),
    ...f.work_model.map((v) => ({ key: `w-${v}`, label: WORK_MODEL_LABEL[v] ?? v, remove: () => set({ work_model: f.work_model.filter((x) => x !== v) }) })),
    ...f.seniority.map((v) => ({ key: `s-${v}`, label: SENIORITY_LABEL[v] ?? v, remove: () => set({ seniority: f.seniority.filter((x) => x !== v) }) })),
    ...f.regime.map((v) => ({ key: `r-${v}`, label: v, remove: () => set({ regime: f.regime.filter((x) => x !== v) }) })),
    ...f.apply_kind.map((v) => ({ key: `a-${v}`, label: APPLY_KIND_LABEL[v] ?? v, remove: () => set({ apply_kind: f.apply_kind.filter((x) => x !== v) }) })),
    ...(f.salary_min != null ? [{ key: "sal", label: `≥ ${brl(f.salary_min)}/mês`, remove: () => set({ salary_min: null }) }] : []),
    ...(f.with_salary ? [{ key: "ws", label: "com salário", remove: () => set({ with_salary: false }) }] : []),
    ...(f.location ? [{ key: "loc", label: `local: ${f.location}`, remove: () => set({ location: "" }) }] : []),
    ...(f.posted_within_days != null ? [{ key: "pd", label: `até ${f.posted_within_days} dia(s)`, remove: () => set({ posted_within_days: null }) }] : []),
    ...(f.min_chance != null ? [{ key: "mc", label: `chance ≥ ${f.min_chance}`, remove: () => set({ min_chance: null }) }] : []),
    ...(f.min_attractiveness != null ? [{ key: "ma", label: `atratividade ≥ ${f.min_attractiveness}`, remove: () => set({ min_attractiveness: null }) }] : []),
    ...(f.applied ? [{ key: "ap", label: f.applied === "true" ? "já me candidatei" : "ainda não me candidatei", remove: () => set({ applied: "" }) }] : []),
  ];
  if (!items.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <AnimatePresence initial={false}>
        {items.map((i) => (
          <motion.button
            key={i.key}
            layout
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ duration: 0.15 }}
            onClick={i.remove}
            className="inline-flex items-center gap-1 rounded-full bg-accent px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/15"
            aria-label={`Remover filtro ${i.label}`}
          >
            {i.label} <X size={12} />
          </motion.button>
        ))}
      </AnimatePresence>
      <button onClick={onClear} className="ml-1 text-xs font-medium text-muted-foreground hover:text-danger">
        Limpar tudo
      </button>
    </div>
  );
}
