"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

export type TrackerEvent = { channel: string; type: string; data: Record<string, unknown> };

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";

type Listener = (e: TrackerEvent) => void;
const listeners = new Set<Listener>();
let socket: WebSocket | null = null;
let retry = 0;

function connect(setConnected: (v: boolean) => void) {
  if (socket && socket.readyState <= 1) return;
  socket = new WebSocket(WS_URL);
  socket.onopen = () => {
    retry = 0;
    setConnected(true);
  };
  socket.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data) as TrackerEvent;
      listeners.forEach((l) => l(event));
    } catch {}
  };
  socket.onclose = () => {
    setConnected(false);
    socket = null;
    retry = Math.min(retry + 1, 6);
    setTimeout(() => connect(setConnected), 500 * 2 ** retry);
  };
}

/** Conecta ao WebSocket do dashboard e invalida queries conforme os eventos. */
export function useLiveEvents(onEvent?: Listener) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const cb = useRef(onEvent);
  cb.current = onEvent;

  useEffect(() => {
    connect(setConnected);
    const l: Listener = (e) => {
      cb.current?.(e);
      if (e.type.startsWith("application")) qc.invalidateQueries({ queryKey: ["applications"] });
      if (e.type.startsWith("job")) qc.invalidateQueries({ queryKey: ["jobs"] });
      if (e.type.startsWith("pending_question")) qc.invalidateQueries({ queryKey: ["pending"] });
      if (e.type === "notification") qc.invalidateQueries({ queryKey: ["notifications"] });
      if (e.type.startsWith("agent")) qc.invalidateQueries({ queryKey: ["agent"] });
      if (e.type === "task.done" || e.type === "task.failed") qc.invalidateQueries();
    };
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, [qc]);

  return connected;
}
