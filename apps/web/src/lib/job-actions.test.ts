import { describe, expect, it } from "vitest";
import { activeCount, EMPTY, fromParams, toParams } from "@/app/(dashboard)/vagas/job-filters";
import { isApplied } from "./job-actions";

describe("isApplied", () => {
  it("só conta como candidatada depois do envio", () => {
    expect(isApplied("submitted")).toBe(true);
    expect(isApplied("interviewing")).toBe(true);
    expect(isApplied("in_progress")).toBe(false);
    expect(isApplied("needs_input")).toBe(false);
    expect(isApplied(null)).toBe(false);
  });
});

describe("filtros de vagas", () => {
  it("vários quadrantes vão para a API (não filtra só a primeira página)", () => {
    const qs = toParams({ ...EMPTY, quadrant: ["top", "bet"] }, true);
    expect(qs.getAll("quadrant")).toEqual(["top", "bet"]);
  });
  it("ida e volta pela URL preserva os filtros", () => {
    const f = { ...EMPTY, tech: ["Python", "Spark"], salary_min: 8000, q: "dados" };
    expect(fromParams(toParams(f))).toEqual(f);
  });
  it("a triagem não conta como filtro escondido", () => {
    expect(activeCount({ ...EMPTY, triage: "" })).toBe(0);
  });
});
