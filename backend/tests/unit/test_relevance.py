"""Filtro de relevância sem IA (cargo, senioridade e local), com locais reais vistos nos boards."""

from __future__ import annotations

import pytest

from tracker.modules.jobs.normalize import RawJob, normalize_title
from tracker.modules.jobs.relevance import filter_relevant, location_ok, matches

TERMS = [normalize_title(t) for t in ["data engineer", "engenheiro de dados", "backend", "software engineer", "machine learning"]]


@pytest.mark.parametrize(
    "location",
    [
        "Brazil",
        "São Paulo, SP",
        "Belo Horizonte, MG; Curitiba, PR; Recife, PE",
        "Remoto",
        "São Paulo ou Teletrabalho",
        "Brazil (Remote)",
        "Home based - Worldwide",
        "Home Based - Americas; Home based - EMEA",
        "Remote, Global",
        "LATAM",
    ],
)
def test_locations_open_to_brazil(location: str) -> None:
    assert location_ok(location, brazilian_company=False)


@pytest.mark.parametrize(
    "location",
    [
        "San Francisco, CA",
        "Remote - USA",
        "Remote Canada",
        "Bengaluru, India",
        "London, United Kingdom",
        "US-CA-Menlo Park",
        "Home based - EMEA",
        "Remote Spain",
    ],
)
def test_locations_closed_to_brazil(location: str) -> None:
    assert not location_ok(location, brazilian_company=False)


def test_ambiguous_location_depends_on_company() -> None:
    for loc in (None, "", "Remote", "Hybrid", "N/A"):
        assert location_ok(loc, brazilian_company=True)
        assert not location_ok(loc, brazilian_company=False)


def test_worldwide_only_when_international() -> None:
    assert not location_ok("Home based - Worldwide", brazilian_company=False, international=False)
    assert location_ok("São Paulo", brazilian_company=False, international=False)


def test_title_match_and_exclusions() -> None:
    def raw(title: str, loc: str | None = "Brazil") -> RawJob:
        return RawJob(source="x", external_id=title, title=title, company_name="X", location=loc)

    raws = [
        raw("Engenheiro de Dados Pleno"),
        raw("Senior Backend Software Engineer"),
        raw("Estágio em Engenharia de Dados"),
        raw("Engineering Manager, Data Engineer"),
        raw("Data Engineer", "Remote - USA"),
        raw("Product Designer"),
    ]
    kept = [r.title for r in filter_relevant(raws, TERMS, brazilian_company=False)]
    assert kept == ["Engenheiro de Dados Pleno", "Senior Backend Software Engineer"]
    # sem informar a empresa, o local não é filtrado (ex.: importação manual)
    assert "Data Engineer" in [r.title for r in filter_relevant(raws, TERMS)]
    assert matches("Pessoa Engenheira de Software Sênior", [normalize_title("engenheira de software")])
