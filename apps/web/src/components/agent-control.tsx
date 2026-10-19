"use client";

import { OctagonX, Play } from "lucide-react";
import Link from "next/link";
import { useGet, useSend } from "@/lib/hooks";
import { Button } from "./ui";

type AgentStatus = {
  blocked: string | null;
  in_window: boolean;
  quota: { used: number; limit: number };
  running: { id: string; kind: string }[];
  queue: unknown[];
};

/** Kill switch sempre visível no cabeçalho (RF-CAN-11). */
export function AgentControl() {
  const status = useGet<AgentStatus>(["agent", "status"], "/api/v1/agent-control/status", { refetchInterval: 15000 });
  const kill = useSend("POST", "/api/v1/agent-control/kill", { success: "Agente parado", invalidate: [["agent"]] });
  const resume = useSend("POST", "/api/v1/agent-control/resume", { success: "Agente liberado", invalidate: [["agent"]] });
  const s = status.data;
  if (!s) return null;
  const working = s.running.length > 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <Link href="/revisao" className="hidden text-muted-foreground sm:inline">
        Robô: {s.blocked ? <span className="text-danger">{s.blocked}</span> : working ? "trabalhando" : s.in_window ? "ocioso" : "fora da janela"}
        {" · "}
        {s.quota.used}/{s.quota.limit} hoje
      </Link>
      {s.blocked ? (
        <Button size="sm" variant="outline" onClick={() => resume.mutate(undefined)} title="Liberar o agente">
          <Play size={14} /> Liberar
        </Button>
      ) : (
        <Button size="sm" variant="danger" onClick={() => kill.mutate(undefined)} title="Parar o agente imediatamente">
          <OctagonX size={14} /> Parar
        </Button>
      )}
    </div>
  );
}
