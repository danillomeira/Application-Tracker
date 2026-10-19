"""Comparador CLT x PJ (RF-OFE-02). Premissas sempre visíveis e editáveis.

ATENÇÃO: tabelas de INSS/IRRF mudam todo ano. Os valores padrão abaixo são uma aproximação
(INSS 2025; IRRF com a isenção até R$ 5.000 vigente a partir de 2026) e devem ser conferidos.
"""

from __future__ import annotations

from typing import Any

DEFAULT_PREMISES: dict[str, Any] = {
    "inss_brackets": [[1518.00, 0.075], [2793.88, 0.09], [4190.83, 0.12], [8157.41, 0.14]],
    "irrf_brackets": [
        [2428.80, 0.0, 0.0],
        [2826.65, 0.075, 182.16],
        [3751.05, 0.15, 394.16],
        [4664.68, 0.225, 675.49],
        [None, 0.275, 908.73],
    ],
    "irrf_exempt_up_to": 5000.00,
    "irrf_reduction_until": 7350.00,
    "irrf_reduction_a": 978.62,
    "irrf_reduction_b": 0.133145,
    "fgts_rate": 0.08,
    "count_fgts_as_income": True,
    "pj_tax_rate": 0.11,  # Simples (fator R) + INSS do pró-labore, aproximado
    "pj_accountant_monthly": 300.00,
    "pj_paid_months": 12,
    "pj_private_health_monthly": 0.0,
    # Tabela exclusiva da PLR (anual, tributação na fonte separada do salário). Conferir a cada ano.
    "plr_brackets": [
        [7640.80, 0.0, 0.0],
        [11354.62, 0.075, 573.06],
        [15055.00, 0.15, 1424.65],
        [18723.24, 0.225, 2553.78],
        [None, 0.275, 3489.94],
    ],
}


def inss(gross: float, brackets: list[list[float]]) -> float:
    total, prev = 0.0, 0.0
    for limit, rate in brackets:
        if gross <= prev:
            break
        total += (min(gross, limit) - prev) * rate
        prev = limit
    return round(total, 2)


def irrf(taxable: float, p: dict[str, Any]) -> float:
    tax = 0.0
    for limit, rate, ded in p["irrf_brackets"]:
        if limit is None or taxable <= limit:
            tax = max(0.0, taxable * rate - ded)
            break
    if taxable <= p["irrf_exempt_up_to"]:
        return 0.0
    if taxable <= p["irrf_reduction_until"]:
        tax = max(0.0, tax - max(0.0, p["irrf_reduction_a"] - p["irrf_reduction_b"] * taxable))
    return round(tax, 2)


def plr_tax(plr: float, p: dict[str, Any]) -> float:
    for limit, rate, ded in p["plr_brackets"]:
        if limit is None or plr <= limit:
            return round(max(0.0, plr * rate - ded), 2)
    return 0.0


def clt_annual(
    monthly_gross: float,
    benefits_monthly: float = 0.0,
    bonus_annual: float = 0.0,
    premises: dict[str, Any] | None = None,
    plr_annual: float = 0.0,
    pension_employee_rate: float = 0.0,
    pension_match_rate: float = 0.0,
    pension_match_cap: float = 0.0,
    employee_costs_monthly: float = 0.0,
) -> dict[str, Any]:
    """CLT anual líquido. Previdência: sua contribuição é poupança sua (e reduz a base do IR);
    a contrapartida da empresa (até o teto) entra como ganho."""
    p = {**DEFAULT_PREMISES, **(premises or {})}
    i = inss(monthly_gross, p["inss_brackets"])
    pension_employee = monthly_gross * pension_employee_rate
    match_rate = min(pension_employee_rate, pension_match_rate, pension_match_cap or pension_match_rate)
    pension_employer = monthly_gross * match_rate
    ir = irrf(monthly_gross - i - pension_employee, p)
    net_month = monthly_gross - i - ir
    thirteenth = net_month  # aproximação: 13º com os mesmos descontos
    vac_bonus_gross = monthly_gross / 3
    vac_net = vac_bonus_gross - inss(monthly_gross + vac_bonus_gross, p["inss_brackets"]) + i  # desconto marginal
    fgts = p["fgts_rate"] * (13 * monthly_gross + vac_bonus_gross) if p["count_fgts_as_income"] else 0.0
    bonus_net = bonus_annual * (1 - 0.275) if bonus_annual else 0.0
    plr_net = plr_annual - plr_tax(plr_annual, p) if plr_annual else 0.0
    pension_annual = 12 * (pension_employee + pension_employer)
    annual = (
        12 * net_month
        + thirteenth
        + vac_net
        + fgts
        + 12 * benefits_monthly
        + bonus_net
        + plr_net
        + 12 * pension_employer
        - 12 * employee_costs_monthly
    )
    return {
        "regime": "CLT",
        "monthly_gross": monthly_gross,
        "inss": i,
        "irrf": ir,
        "net_monthly": round(net_month, 2),
        "take_home_monthly": round(net_month - pension_employee - employee_costs_monthly, 2),
        "employee_costs_monthly": round(employee_costs_monthly, 2),
        "thirteenth_net": round(thirteenth, 2),
        "vacation_third_net": round(vac_net, 2),
        "fgts": round(fgts, 2),
        "benefits_annual": round(12 * benefits_monthly, 2),
        "bonus_net": round(bonus_net, 2),
        "plr_gross": round(plr_annual, 2),
        "plr_net": round(plr_net, 2),
        "pension_employee_monthly": round(pension_employee, 2),
        "pension_employer_monthly": round(pension_employer, 2),
        "pension_annual_total": round(pension_annual, 2),
        "annual_net": round(annual, 2),
        "monthly_equivalent": round(annual / 12, 2),
    }


def pj_annual(
    monthly_invoice: float,
    benefits_monthly: float = 0.0,
    bonus_annual: float = 0.0,
    premises: dict[str, Any] | None = None,
) -> dict[str, Any]:
    p = {**DEFAULT_PREMISES, **(premises or {})}
    months = p["pj_paid_months"]
    taxes = monthly_invoice * p["pj_tax_rate"]
    net_month = monthly_invoice - taxes - p["pj_accountant_monthly"] - p["pj_private_health_monthly"]
    annual = months * net_month + 12 * benefits_monthly + bonus_annual * (1 - p["pj_tax_rate"])
    return {
        "regime": "PJ",
        "monthly_invoice": monthly_invoice,
        "taxes_monthly": round(taxes, 2),
        "accountant_monthly": p["pj_accountant_monthly"],
        "net_monthly": round(net_month, 2),
        "paid_months": months,
        "benefits_annual": round(12 * benefits_monthly, 2),
        "annual_net": round(annual, 2),
        "monthly_equivalent": round(annual / 12, 2),
    }


def pj_equivalent_to_clt(
    clt_monthly_gross: float,
    clt_benefits: float = 0.0,
    premises: dict[str, Any] | None = None,
    target_annual: float | None = None,
) -> float:
    """Faturamento PJ mensal que empata com o CLT (busca binária)."""
    target = (
        target_annual
        if target_annual is not None
        else clt_annual(clt_monthly_gross, clt_benefits, premises=premises)["annual_net"]
    )
    lo, hi = 0.0, clt_monthly_gross * 4
    for _ in range(60):
        mid = (lo + hi) / 2
        if pj_annual(mid, premises=premises)["annual_net"] < target:
            lo = mid
        else:
            hi = mid
    return round(hi, 2)


def annualize(
    regime: str,
    base: float,
    period: str,
    benefits_monthly: float,
    bonus_annual: float,
    premises: dict[str, Any] | None = None,
    plr_salaries: float = 0.0,
    pension_employee_rate: float = 0.0,
    pension_match_rate: float = 0.0,
    pension_match_cap: float = 0.0,
    employee_costs_monthly: float = 0.0,
) -> dict[str, Any]:
    monthly = base / 12 if period == "year" else base
    if regime == "PJ":
        out = pj_annual(monthly, benefits_monthly, bonus_annual + plr_salaries * monthly, premises)
    else:
        out = clt_annual(
            monthly,
            benefits_monthly,
            bonus_annual,
            premises,
            plr_salaries * monthly,
            pension_employee_rate,
            pension_match_rate,
            pension_match_cap,
            employee_costs_monthly,
        )
        out["pj_equivalent_invoice"] = pj_equivalent_to_clt(monthly, premises=premises, target_annual=out["annual_net"])
    out["premises"] = {**DEFAULT_PREMISES, **(premises or {})}
    return out


def current_package(cfg: dict[str, Any], premises: dict[str, Any] | None = None) -> dict[str, Any]:
    """Remuneração atual (linha de base das comparações), a partir da configuração editável."""
    monthly_benefits = sum(
        float(cfg.get(k) or 0) for k in ("meal_monthly", "health_monthly_estimate", "wellhub_monthly_estimate", "other_monthly")
    )
    return annualize(
        cfg.get("regime") or "CLT",
        float(cfg.get("monthly_gross") or 0),
        "month",
        monthly_benefits,
        0.0,
        premises,
        plr_salaries=float(cfg.get("plr_salaries") or 0),
        pension_employee_rate=float(cfg.get("pension_employee_rate") or 0),
        pension_match_rate=float(cfg.get("pension_match_rate") or 0),
        pension_match_cap=float(cfg.get("pension_match_cap") or 0),
        employee_costs_monthly=float(cfg.get("health_employee_cost_monthly") or 0),
    )
