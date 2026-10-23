from tracker.core.humanize import humanize


def test_removes_ai_punctuation_but_keeps_facts() -> None:
    t = humanize("Minha experiência: **5 anos** com Python — inclusive Spark; também Kafka - e AWS.")
    assert ":" not in t and "—" not in t and ";" not in t and " - " not in t and "**" not in t
    assert "5 anos" in t and "Python" in t and "Spark" in t and "Kafka" in t


def test_keeps_compounds_ranges_times_and_links() -> None:
    t = humanize("Pós-graduação, 5-7 anos, reunião às 14:30, veja https://github.com/x")
    assert "Pós-graduação" in t and "5-7" in t and "14:30" in t and "https://github.com/x" in t


def test_strips_list_markers_and_cliches() -> None:
    t = humanize("- Construí pipelines\n- Além disso, reduzi custos")
    assert not t.startswith("-") and "Além disso" not in t and "Reduzi custos" in t
