"""Alertas de vagas do LinkedIn (texto do e-mail) → vagas."""

from __future__ import annotations

from datetime import UTC, datetime

from tracker.integrations.google.gmail import ParsedEmail
from tracker.modules.inbox.linkedin_alerts import is_linkedin_alert, parse_alert

BODY = """Your job alert for data engineer in Brazil
12 new jobs match your preferences.

Data Engineer
Nubank
São Paulo, Brazil (Remote)
Easy Apply
View job: https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc%3D%3D&refId=x

---------------------------------------------------------

Senior Analytics Engineer
Globex Corporation
Brazil
Actively recruiting
View job: https://www.linkedin.com/comm/jobs/view/4098765432/?trackingId=def

---------------------------------------------------------

See all jobs: https://www.linkedin.com/comm/jobs/search?keywords=data
"""


def mail(body: str = BODY, sender: str = "jobalerts-noreply@linkedin.com") -> ParsedEmail:
    return ParsedEmail(gmail_id="m1", thread_id="t1", from_addr=sender, from_name="LinkedIn Job Alerts", to_addrs=["voce@exemplo.com"],
                       subject="Data Engineer: Nubank e mais", snippet="", body_text=body, received_at=datetime.now(UTC))  # fmt: skip


def test_detects_only_linkedin_alerts() -> None:
    assert is_linkedin_alert(mail())
    assert not is_linkedin_alert(mail(sender="recruiter@nubank.com.br"))
    assert not is_linkedin_alert(mail(body="Oi, tudo bem?"))


def test_parses_title_company_location_and_easy_apply() -> None:
    jobs = parse_alert(mail())
    assert [(j.external_id, j.title, j.company, j.location, j.easy_apply) for j in jobs] == [
        ("4012345678", "Data Engineer", "Nubank", "São Paulo, Brazil (Remote)", True),
        ("4098765432", "Senior Analytics Engineer", "Globex Corporation", "Brazil", False),
    ]
