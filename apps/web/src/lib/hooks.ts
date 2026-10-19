"use client";

import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ApiError, rawFetch } from "./api";
import { useLiveEvents } from "./ws";

/** GET simples (JSON) com cache do React Query. */
export function useGet<T>(key: QueryKey, path: string | null, opts?: { refetchInterval?: number }) {
  return useQuery<T>({
    queryKey: key,
    queryFn: async () => (await rawFetch(path as string)).json() as Promise<T>,
    enabled: !!path,
    refetchInterval: opts?.refetchInterval,
  });
}

type MutOpts = { success?: string; invalidate?: QueryKey[] };

/** POST/PUT/PATCH/DELETE com toast e invalidação. */
export function useSend<TBody = unknown, TOut = unknown>(method: string, path: string | ((v: TBody) => string), opts: MutOpts = {}) {
  const qc = useQueryClient();
  return useMutation<TOut, ApiError, TBody>({
    mutationFn: async (body: TBody) => {
      const url = typeof path === "function" ? path(body) : path;
      const res = await rawFetch(url, {
        method,
        headers: { "content-type": "application/json" },
        body: body === undefined || method === "GET" ? undefined : JSON.stringify(body),
      });
      const text = await res.text();
      return (text ? JSON.parse(text) : null) as TOut;
    },
    onSuccess: () => {
      if (opts.success) toast.success(opts.success);
      (opts.invalidate ?? []).forEach((k) => qc.invalidateQueries({ queryKey: k }));
    },
    onError: (e) => toast.error(e.message),
  });
}

/** Acompanha uma tarefa assíncrona (202 + task_id) até terminar. */
export function useTask(onDone?: (result: unknown) => void) {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ pct: number; message: string } | null>(null);
  const done = useRef(onDone);
  done.current = onDone;
  useLiveEvents((e) => {
    if (!taskId || e.data.task_id !== taskId) return;
    if (e.type === "task.progress") setProgress({ pct: Number(e.data.pct), message: String(e.data.message) });
    if (e.type === "task.done") {
      setProgress(null);
      setTaskId(null);
      toast.success("Concluído");
      done.current?.(e.data.result);
    }
    if (e.type === "task.failed") {
      setProgress(null);
      setTaskId(null);
      toast.error(`Falhou: ${String(e.data.error ?? "")}`.slice(0, 200));
    }
  });
  useEffect(() => {
    if (!taskId) return;
    const t = setInterval(async () => {
      try {
        const r = await (await rawFetch(`/api/v1/tasks/${taskId}`)).json();
        if (r.status === "done" || r.status === "failed") {
          setTaskId(null);
          setProgress(null);
          if (r.status === "done") done.current?.(r.result);
          else toast.error(`Falhou: ${r.error ?? ""}`.slice(0, 200));
        } else setProgress({ pct: r.progress, message: r.message ?? "" });
      } catch {}
    }, 4000);
    return () => clearInterval(t);
  }, [taskId]);
  return {
    start: (id: string) => {
      setTaskId(id);
      setProgress({ pct: 0, message: "na fila" });
    },
    running: !!taskId,
    progress,
  };
}
