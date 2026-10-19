import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { QUADRANT_LABEL, STATUS_LABEL, STATUS_TONE } from "./labels";
import { cn, formatDate, formatDateTime, money } from "./utils";

describe("formatação", () => {
  it("usa o fuso de São Paulo", () => {
    expect(formatDateTime("2026-10-18T02:30:00Z")).toBe("17/10/2026, 23:30");
    expect(formatDate("2026-10-18T02:30:00Z")).toBe("17/10/2026");
  });
  it("trata vazios", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(money(undefined)).toBe("—");
  });
  it("formata reais sem centavos", () => {
    expect(money(11173.53).replace(/\s/g, " ")).toBe("R$ 11.174");
  });
  it("mescla classes do Tailwind", () => {
    expect(cn("p-2", false && "x", "p-4")).toBe("p-4");
  });
});

describe("rótulos acompanham o backend", () => {
  const src = readFileSync(new URL("../../../../backend/src/tracker/modules/applications/state_machine.py", import.meta.url), "utf8");
  const statuses = [...src.slice(src.indexOf("STATUSES = ["), src.indexOf("]", src.indexOf("STATUSES = ["))).matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);

  it("todo status da máquina de estados tem rótulo e cor", () => {
    expect(statuses.length).toBeGreaterThan(10);
    for (const s of statuses) {
      expect(STATUS_LABEL[s], s).toBeTruthy();
      expect(STATUS_TONE[s], s).toBeTruthy();
    }
  });
  it("quadrantes do motor de avaliação", () => {
    for (const q of ["top", "bet", "volume", "discard"]) expect(QUADRANT_LABEL[q]).toBeTruthy();
  });
});
