"use client";

import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

export type TrackerEvent = { channel: string; type: string; data: Record<string, unknown> };

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

type Listener = (e: TrackerEvent) => void;
const listeners = new Set<Listener>();
const statusSubs = new Set<(v: boolean) => void>(); // todos os componentes que mostram "conectado"
let socket: WebSocket | null = null;
let retry = 0;
let open = false;
let client: QueryClient | null = null;

const setOpen = (v: boolean) => {
  open = v;
  statusSubs.forEach((s) => s(v));
};

/** Invalidações globais: uma vez por evento, não uma por componente que escuta. */
function invalidate(e: TrackerEvent) {
  const qc = client;
  if (!qc) return;
  if (e.type.startsWith("application")) qc.invalidateQueries({ queryKey: ["applications"] });
  if (e.type.startsWith("job")) qc.invalidateQueries({ queryKey: ["jobs"] });
  if (e.type === "notification") qc.invalidateQueries({ queryKey: ["notifications"] });
  if (e.type === "task.done" || e.type === "task.failed") qc.invalidateQueries();
}

function connect() {
  if (socket && socket.readyState <= 1) return;
  socket = new WebSocket(WS_URL);
  socket.onopen = () => {
    retry = 0;
    setOpen(true);
  };
  socket.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data) as TrackerEvent;
      invalidate(event);
      listeners.forEach((l) => l(event));
    } catch {}
  };
  socket.onclose = () => {
    setOpen(false);
    socket = null;
    retry = Math.min(retry + 1, 6);
    setTimeout(connect, 500 * 2 ** retry);
  };
}

/** Conecta ao WebSocket do dashboard (uma conexão para o app todo) e repassa os eventos. */
export function useLiveEvents(onEvent?: Listener) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(open);
  const cb = useRef(onEvent);
  cb.current = onEvent;

  useEffect(() => {
    client = qc;
    connect();
    const l: Listener = (e) => cb.current?.(e);
    listeners.add(l);
    statusSubs.add(setConnected);
    setConnected(open);
    return () => {
      listeners.delete(l);
      statusSubs.delete(setConnected);
    };
  }, [qc]);

  return connected;
}
