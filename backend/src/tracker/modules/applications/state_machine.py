"""Máquina de estados das candidaturas (docs/05 §5)."""

from __future__ import annotations

STATUSES = [
    "discovered",
    "queued",
    "in_progress",
    "needs_input",
    "awaiting_review",
    "submitted",
    "under_review",
    "interviewing",
    "assessment",
    "offer",
    "accepted",
    "declined",
    "rejected",
    "ghosted",
    "skipped",
    "blocked",
    "withdrawn",
]

ACTIVE = {
    "discovered",
    "queued",
    "in_progress",
    "needs_input",
    "awaiting_review",
    "submitted",
    "under_review",
    "interviewing",
    "assessment",
    "offer",
    "ghosted",
}
SENT = {
    "submitted",
    "under_review",
    "interviewing",
    "assessment",
    "offer",
    "accepted",
    "declined",
    "rejected",
    "ghosted",
    "withdrawn",
}
RESPONDED = {"interviewing", "assessment", "offer", "accepted", "declined", "rejected"}
POSITIVE = {"interviewing", "assessment", "offer", "accepted", "declined"}

TRANSITIONS: dict[str, set[str]] = {
    "discovered": {"queued", "skipped", "blocked", "submitted", "awaiting_review"},
    "queued": {"in_progress", "skipped", "blocked", "discovered", "submitted", "awaiting_review"},
    "in_progress": {"needs_input", "awaiting_review", "submitted", "queued", "skipped"},
    "needs_input": {"in_progress", "queued", "skipped"},
    "awaiting_review": {"submitted", "in_progress", "queued", "skipped"},
    "submitted": {"under_review", "interviewing", "assessment", "offer", "rejected", "ghosted"},
    "under_review": {"interviewing", "assessment", "offer", "rejected", "ghosted"},
    "interviewing": {"assessment", "offer", "rejected", "ghosted", "interviewing"},
    "assessment": {"interviewing", "offer", "rejected", "ghosted"},
    "offer": {"accepted", "declined", "rejected"},
    "ghosted": {"under_review", "interviewing", "assessment", "offer", "rejected"},
    "accepted": set(),
    "declined": set(),
    "rejected": {"interviewing"},  # reabertura rara: empresa volta atrás
    "skipped": {"discovered", "queued"},
    "blocked": {"discovered"},
    "withdrawn": set(),
}
for _s in ACTIVE:
    TRANSITIONS[_s].add("withdrawn")


class InvalidTransition(ValueError):
    pass


def can_transition(current: str, new: str) -> bool:
    return new in TRANSITIONS.get(current, set())


def check(current: str, new: str) -> None:
    if not can_transition(current, new):
        raise InvalidTransition(f"transição inválida: {current} → {new}")
