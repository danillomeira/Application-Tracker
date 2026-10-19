"""Aplicação Celery: filas, roteamento e agenda (Beat). docs/04 §2."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from tracker.core.config import get_settings

TASK_MODULES = [
    "tracker.modules.platform.tasks",
    "tracker.modules.profile.tasks",
    "tracker.modules.resumes.tasks",
    "tracker.modules.jobs.tasks",
    "tracker.modules.companies.tasks",
    "tracker.modules.scoring.tasks",
    "tracker.modules.offers.tasks",
    "tracker.modules.people.tasks",
    "tracker.modules.applications.tasks",
    "tracker.modules.inbox.tasks",
    "tracker.modules.calendar.tasks",
    "tracker.modules.interviews.tasks",
    "tracker.modules.notifications.tasks",
    "tracker.modules.analytics.tasks",
]

celery_app = Celery("tracker", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.update(
    include=TASK_MODULES,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=get_settings().user_timezone,
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_routes={
        "ai.*": {"queue": "ai"},
        "ingest.*": {"queue": "ingest"},
        "docs.*": {"queue": "docs"},
        "batch.*": {"queue": "batch"},
    },
    beat_schedule={
        "saved-searches": {"task": "ingest.run_due_saved_searches", "schedule": crontab(minute="*/15")},
        "poll-monitored-companies": {
            "task": "ingest.poll_monitored_companies",
            "schedule": crontab(minute=7, hour="*/6"),
        },
        "gmail-poll": {"task": "ingest.gmail_sync", "schedule": crontab(minute="*/5")},
        "gmail-watch-renew": {
            "task": "ingest.gmail_watch_renew",
            "schedule": crontab(minute=0, hour=3, day_of_week="*/6"),
        },
        "ghosted": {"task": "applications.mark_ghosted", "schedule": crontab(minute=30, hour=6)},
        "followups": {"task": "applications.suggest_followups", "schedule": crontab(minute=0, hour=9)},
        "pending-expire": {"task": "applications.expire_pending", "schedule": crontab(minute="*/30")},
        "daily-digest": {"task": "notifications.daily_digest", "schedule": crontab(minute=0, hour=8)},
        "weekly-report": {"task": "ai.weekly_report", "schedule": crontab(minute=0, hour=8, day_of_week=1)},
        "inbox-retention": {"task": "inbox.apply_retention", "schedule": crontab(minute=15, hour=4)},
        "artifact-retention": {"task": "platform.artifact_retention", "schedule": crontab(minute=30, hour=4)},
        "backup": {"task": "platform.backup", "schedule": crontab(minute=0, hour=2)},
        "calendar-reminders": {"task": "calendar.study_blocks", "schedule": crontab(minute=0, hour="*/2")},
    },
)
