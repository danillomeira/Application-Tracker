"use client";

import { FileText } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Badge, Button, Card, CardTitle, EmptyState, Field, PageHeader, Select, Skeleton, Textarea } from "@/components/ui";
import { useGet, useSend, useTask } from "@/lib/hooks";
import { formatDateTime } from "@/lib/utils";

type Violation = { kind: string; text: string; suggestion?: string | null };
type Variant = {
  id: string;
  kind: string;
  slug: string;
  name: string;
  language: string;
  status: string;
  job_id: string | null;
  changes: string[];
  validation: { passed?: boolean; violations?: Violation[]; warnings?: Violation[] };
  content: {
    headline: string;
    summary: string;
    skill_rows: { category: string; items: string[] }[];
    experience: { experience_id: string; title: string; organization: string; period: string; bullets: string[] }[];
  };
  created_at: string;
};
type Render = { id: string; filename: string; page_count: number | null; rendered_at: string; ats_report: { ok?: boolean; checks?: { name: string; ok: boolean }[]; keyword_coverage?: number | null; missing_keywords?: string[] } };
type VariantDetail = Variant & { renders: Render[] };

export default function ResumesPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useGet<Variant[]>(["resumes"], "/api/v1/resumes/variants");
  const { data: profiles } = useGet<Record<string, { name: string; focus: string }>>(["resumes", "profiles"], "/api/v1/resumes/profiles");
  const [selected, setSelected] = useState<string | null>(null);
  const [profile, setProfile] = useState("data_engineer");
  const [lang, setLang] = useState("en");
  const refresh = () => qc.invalidateQueries({ queryKey: ["resumes"] });
  const baseline = useSend<{ profile: string; language: string }, Variant>("POST", "/api/v1/resumes/variants/baseline", { success: "Coringa criado a partir do mestre", invalidate: [["resumes"]] });
  const gen = useSend<{ profiles: string[]; languages: string[] }, { task_id: string }>("POST", "/api/v1/resumes/variants/wildcards/generate");
  const genTask = useTask(refresh);
  const wildcards = data?.filter((v) => v.kind === "wildcard") ?? [];
  const tailored = data?.filter((v) => v.kind === "tailored") ?? [];

  return (
    <div>
      <PageHeader icon={<FileText size={20} />} title="Currículos" description="Coringas por perfil e CVs específicos por vaga, sempre validados contra o mestre" />
      <Card className="mb-4 flex flex-wrap items-end gap-2">
        <Field label="Perfil">
          <Select value={profile} onChange={(e) => setProfile(e.target.value)}>
            {Object.entries(profiles ?? {}).map(([k, v]) => <option key={k} value={k}>{v.name}</option>)}
          </Select>
        </Field>
        <Field label="Idioma">
          <Select value={lang} onChange={(e) => setLang(e.target.value)}><option value="en">Inglês</option><option value="pt">Português</option></Select>
        </Field>
        <Button variant="outline" onClick={async () => setSelected((await baseline.mutateAsync({ profile, language: lang })).id)}>Criar direto do mestre (sem IA)</Button>
        <Button disabled={genTask.running} onClick={async () => genTask.start((await gen.mutateAsync({ profiles: [profile], languages: [lang] })).task_id)}>
          {genTask.running ? `Gerando… ${genTask.progress?.message ?? ""}` : "Gerar coringa com IA"}
        </Button>
      </Card>
      {isLoading ? (
        <Skeleton className="h-64" />
      ) : (
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="space-y-4">
            <VariantList title="Coringas" items={wildcards} selected={selected} onSelect={setSelected} />
            <VariantList title="Específicos por vaga" items={tailored} selected={selected} onSelect={setSelected} />
          </div>
          <div className="xl:col-span-2">{selected ? <VariantPanel id={selected} /> : <EmptyState title="Selecione um currículo" />}</div>
        </div>
      )}
    </div>
  );
}

function VariantList({ title, items, selected, onSelect }: { title: string; items: Variant[]; selected: string | null; onSelect: (id: string) => void }) {
  return (
    <Card>
      <CardTitle>{title} ({items.length})</CardTitle>
      {items.length === 0 && <p className="text-xs text-muted-foreground">Nenhum ainda.</p>}
      <ul className="space-y-1">
        {items.map((v) => (
          <li key={v.id}>
            <button onClick={() => onSelect(v.id)} className={`w-full rounded-md p-2 text-left text-sm hover:bg-muted ${selected === v.id ? "bg-accent" : ""}`}>
              <span className="font-medium">{v.name}</span> <span className="text-xs uppercase text-muted-foreground">{v.language}</span>
              <div className="mt-1 flex gap-1">
                <Badge tone={v.status === "approved" ? "success" : v.status === "draft" ? "warning" : "neutral"}>{v.status}</Badge>
                <Badge tone={v.validation.passed ? "success" : "danger"}>{v.validation.passed ? "validado" : "violações"}</Badge>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function VariantPanel({ id }: { id: string }) {
  const qc = useQueryClient();
  const { data: v } = useGet<VariantDetail>(["resumes", id], `/api/v1/resumes/variants/${id}`);
  const [json, setJson] = useState("");
  useEffect(() => { if (v) setJson(JSON.stringify(v.content, null, 2)); }, [v]);
  const inv = { invalidate: [["resumes"], ["dashboard"]] };
  const approve = useSend("POST", `/api/v1/resumes/variants/${id}/approve`, { success: "Aprovado", ...inv });
  const update = useSend<Record<string, unknown>>("PUT", `/api/v1/resumes/variants/${id}`, { success: "Salvo e revalidado", ...inv });
  const render = useSend<void, { task_id: string }>("POST", `/api/v1/resumes/variants/${id}/render`);
  const renderTask = useTask(() => qc.invalidateQueries({ queryKey: ["resumes", id] }));
  if (!v) return <Skeleton className="h-96" />;
  const last = v.renders[0];
  return (
    <div className="space-y-4">
      <Card className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="font-semibold">{v.name} <span className="text-xs uppercase text-muted-foreground">{v.language} · {v.kind}</span></p>
            {v.job_id && <Link href={`/vagas/${v.job_id}`} className="text-xs text-primary underline">vaga de origem</Link>}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={renderTask.running} onClick={async () => renderTask.start((await render.mutateAsync()).task_id)}>{renderTask.running ? "Compilando…" : "Gerar PDF"}</Button>
            {v.status !== "approved" && <Button size="sm" variant="success" onClick={() => approve.mutate(undefined)}>Aprovar</Button>}
            {v.status !== "archived" && <Button size="sm" variant="ghost" onClick={() => update.mutate({ status: "archived" })}>Arquivar</Button>}
          </div>
        </div>
        {(v.validation.violations?.length ?? 0) > 0 && (
          <div className="rounded-md bg-danger/10 p-2 text-sm text-danger">
            <p className="font-medium">O validador encontrou fatos fora do mestre (o PDF fica bloqueado):</p>
            <ul className="list-disc pl-5">{v.validation.violations!.map((x, i) => <li key={i}>{x.text}{x.suggestion ? ` — ${x.suggestion}` : ""}</li>)}</ul>
          </div>
        )}
        {(v.validation.warnings?.length ?? 0) > 0 && (
          <ul className="text-xs text-warning">{v.validation.warnings!.map((x, i) => <li key={i}>⚠ {x.text}</li>)}</ul>
        )}
        {v.changes.length > 0 && (
          <details className="text-xs"><summary className="cursor-pointer">O que a IA adaptou</summary><ul className="list-disc pl-5">{v.changes.map((c, i) => <li key={i}>{c}</li>)}</ul></details>
        )}
      </Card>
      {last && (
        <Card className="space-y-2 text-sm">
          <CardTitle>Último PDF</CardTitle>
          <div className="flex flex-wrap items-center gap-3">
            <a className="text-primary underline" href={`/api/v1/resumes/renders/${last.id}/pdf`} target="_blank" rel="noreferrer">{last.filename}</a>
            <span className="text-xs text-muted-foreground">{last.page_count} página(s) · {formatDateTime(last.rendered_at)}</span>
            <a className="text-xs underline" href={`/api/v1/resumes/renders/${last.id}/tex`} target="_blank" rel="noreferrer">fonte .tex</a>
            <Badge tone={last.ats_report.ok ? "success" : "warning"}>ATS {last.ats_report.ok ? "ok" : "atenção"}</Badge>
            {last.ats_report.keyword_coverage != null && <Badge>palavras-chave {Math.round(last.ats_report.keyword_coverage * 100)}%</Badge>}
          </div>
          <ul className="grid grid-cols-2 gap-x-4 text-xs">{last.ats_report.checks?.map((c) => <li key={c.name}>{c.ok ? "✓" : "✕"} {c.name}</li>)}</ul>
          <iframe title="pré-visualização" src={`/api/v1/resumes/renders/${last.id}/pdf`} className="h-[600px] w-full rounded border" />
        </Card>
      )}
      <Card className="space-y-2">
        <CardTitle>Conteúdo (editável)</CardTitle>
        <Textarea rows={20} className="font-mono text-xs" value={json} onChange={(e) => setJson(e.target.value)} spellCheck={false} />
        <Button size="sm" onClick={() => { try { update.mutate({ content: JSON.parse(json) }); } catch { toast.error("JSON inválido"); } }}>Salvar e revalidar</Button>
      </Card>
    </div>
  );
}
