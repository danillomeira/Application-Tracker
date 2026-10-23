"""Fatos derivados do currículo mestre: skills, aliases, períodos, anos por skill, números."""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from tracker.modules.profile.schemas import Education, Experience, MasterProfile

MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9+#.]+", " ", text)
    return re.sub(r"\s+", " ", text).strip(" .")


def skill_index(master: MasterProfile) -> dict[str, str]:
    """Mapa forma-normalizada → skill canônica (inclui aliases, base e sub-itens)."""
    idx: dict[str, str] = {}

    def add(form: str, canonical: str) -> None:
        n = norm(form)
        if n:
            idx.setdefault(n, canonical)

    all_skills: list[str] = [s for items in master.skills.values() for s in items]
    for e in master.experience:
        all_skills.extend(e.skills)
    for p in master.projects:
        all_skills.extend(p.skills)
    for s in all_skills:
        add(s, s)
        base = re.sub(r"\(.*?\)", "", s).strip()
        add(base, s)
        for inner in re.findall(r"\((.*?)\)", s):
            for part in re.split(r"[,/]", inner):
                add(part, s)
        for part in re.split(r"\s+(?:and|e)\s+|/", base):
            if len(part.strip()) > 1:
                add(part, s)
    for canonical, aliases in master.skill_aliases.items():
        add(canonical, canonical)
        for a in aliases:
            add(a, canonical)
    return idx


def has_skill(master: MasterProfile, skill: str, idx: dict[str, str] | None = None) -> str | None:
    idx = idx if idx is not None else skill_index(master)
    n = norm(skill)
    if n in idx:
        return idx[n]
    base = norm(re.sub(r"\(.*?\)", "", skill))
    return idx.get(base)


def parse_month(value: str | None, *, end: bool = False) -> date | None:
    if not value:
        return None
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?", str(value))
    if not m:
        return None
    year = int(m.group(1))
    if m.group(2):
        return date(year, int(m.group(2)), 1)
    return date(year, 12, 1) if end else date(year, 1, 1)


def period(start: str | None, end: str | None, today: date | None = None) -> tuple[date, date] | None:
    s = parse_month(start)
    if s is None:
        return None
    e = (parse_month(end, end=True) if end else None) or today or date.today()
    return s, e


def _months(a: date, b: date) -> int:
    return max(0, (b.year - a.year) * 12 + (b.month - a.month) + 1)


def _union_months(intervals: list[tuple[date, date]]) -> int:
    if not intervals:
        return 0
    intervals = sorted(intervals)
    total = 0
    cur_s, cur_e = intervals[0]
    for s, e in intervals[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += _months(cur_s, cur_e)
            cur_s, cur_e = s, e
    return total + _months(cur_s, cur_e)


PROFESSIONAL_TYPES = {"employment", "internship", "residency", None}


def total_years(master: MasterProfile, today: date | None = None) -> float:
    spans = [p for e in master.experience if e.type in PROFESSIONAL_TYPES and (p := period(e.start, e.end, today))]
    if not spans:
        return 0.0
    first = min(s for s, _ in spans)
    last = max(e for _, e in spans)
    return round(_months(first, last) / 12, 1)


def experience_mentions(exp: Experience, skill: str) -> bool:
    n = norm(skill)
    base = norm(re.sub(r"\(.*?\)", "", skill))
    if any(norm(s) in (n, base) for s in exp.skills):
        return True
    text = norm(" ".join(exp.bullets_en + exp.facts + exp.extra_facts))
    pattern = rf"(?<![a-z0-9]){re.escape(base or n)}(?![a-z0-9])"
    return bool(base or n) and re.search(pattern, text) is not None


def years_for_skill(master: MasterProfile, skill: str, today: date | None = None) -> float:
    """Anos de experiência com a skill: união dos períodos das experiências que a usam."""
    canonical = has_skill(master, skill)
    names = {skill}
    if canonical:
        names.add(canonical)
        names.update(a for a, c in skill_index(master).items() if c == canonical)
    spans = []
    for e in master.experience:
        if e.type == "residency":
            continue
        if any(experience_mentions(e, n) for n in names):
            p = period(e.start, e.end, today)
            if p:
                spans.append(p)
    return round(_union_months(spans) / 12, 1)


def format_month(value: str | None, lang: str = "en") -> str:
    d = parse_month(value)
    if d is None:
        return ""
    if re.match(r"^\d{4}$", str(value)):
        return str(d.year)
    months = MONTHS_EN if lang == "en" else MONTHS_PT
    return f"{months[d.month - 1]} {d.year}"


def format_period(start: str | None, end: str | None, lang: str = "en", show_end: bool = True) -> str:
    present = "Present" if lang == "en" else "Atual"
    s = format_month(start, lang)
    e = format_month(end, lang) if end else present
    if not show_end and not end:
        e = present
    return f"{s} -- {e}" if s else e


def education_period(ed: Education, lang: str = "en") -> str:
    return format_period(ed.start, ed.end, lang)


_NUM = re.compile(r"(?<![\w.])~?(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)\s*(mil|k|thousand)?", re.I)


def numbers_in(text: str) -> set[str]:
    """Números normalizados ('10,000', '10 mil', '~10k' → '10000'; '5x' → '5')."""
    out: set[str] = set()
    for m in _NUM.finditer(text):
        raw, mult = m.group(1), m.group(2)
        val = float(re.sub(r"[.,]", "", raw)) if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw) else float(raw.replace(",", "."))
        if mult:
            val *= 1000
        out.add(str(int(val)) if val == int(val) else str(val))
    return out


PLACEHOLDER = re.compile(r"confirmar|a confirmar|todo\b|preencher", re.I)


def master_text(master: MasterProfile) -> str:
    """Texto do mestre que vale como fonte de fatos: sem dados de contato (e-mail, telefone e links
    não provam skill nem métrica) e sem marcadores "confirmar …" do importador."""
    parts: list[str] = []

    def walk(v: object) -> None:
        if isinstance(v, str):
            if not PLACEHOLDER.search(v):
                parts.append(v)
        elif isinstance(v, dict):
            for x in v.values():  # pyright: ignore[reportUnknownVariableType]
                walk(x)  # pyright: ignore[reportUnknownArgumentType]
        elif isinstance(v, list):
            for x in v:  # pyright: ignore[reportUnknownVariableType]
                walk(x)  # pyright: ignore[reportUnknownArgumentType]
        elif v is not None:
            parts.append(str(v))

    walk(master.model_dump(mode="json", exclude={"contact"}))
    return " \n ".join(parts)


def master_numbers(master: MasterProfile) -> set[str]:
    nums = numbers_in(master_text(master))
    for e in master.experience:
        for v in (e.start, e.end):
            d = parse_month(v)
            if d:
                nums.add(str(d.year))
    return nums
