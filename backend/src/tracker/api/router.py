"""Agrega as rotas de todos os módulos sob /api/v1."""

from __future__ import annotations

from fastapi import APIRouter

from tracker.modules.agent_gateway import router as agent
from tracker.modules.analytics import router as insights
from tracker.modules.analytics.dashboard import router as dashboard_router
from tracker.modules.applications import router as applications
from tracker.modules.assistant.router import router as assistant_router
from tracker.modules.auth.router import router as auth_router
from tracker.modules.calendar.router import router as calendar_router
from tracker.modules.companies.router import router as companies_router
from tracker.modules.inbox import router as inbox
from tracker.modules.interviews import router as interviews
from tracker.modules.jobs import router as jobs
from tracker.modules.notifications.telegram_bot import router as telegram_router
from tracker.modules.offers.router import router as offers_router
from tracker.modules.onboarding.router import router as onboarding_router
from tracker.modules.people.router import router as people_router
from tracker.modules.platform.data_router import router as data_router
from tracker.modules.platform.integrations_router import router as integrations_router
from tracker.modules.platform.router import router as platform_router
from tracker.modules.profile import router as profile
from tracker.modules.resumes.router import router as resumes_router
from tracker.modules.scoring.router import router as scoring_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(platform_router)
api_router.include_router(profile.router)
api_router.include_router(profile.answers_router)
api_router.include_router(profile.blocklist_router)
api_router.include_router(profile.documents_router)
api_router.include_router(resumes_router)
api_router.include_router(jobs.router)
api_router.include_router(jobs.searches_router)
api_router.include_router(companies_router)
api_router.include_router(scoring_router)
api_router.include_router(applications.router)
api_router.include_router(applications.review_router)
api_router.include_router(dashboard_router)
api_router.include_router(inbox.router)
api_router.include_router(inbox.drafts_router)
api_router.include_router(inbox.webhooks_router)
api_router.include_router(calendar_router)
api_router.include_router(integrations_router)
api_router.include_router(telegram_router)
api_router.include_router(interviews.router)
api_router.include_router(interviews.mock_router)
api_router.include_router(interviews.assessments_router)
api_router.include_router(agent.router)
api_router.include_router(agent.user_router)
api_router.include_router(people_router)
api_router.include_router(data_router)
api_router.include_router(offers_router)
api_router.include_router(insights.router)
api_router.include_router(insights.github_router)
api_router.include_router(assistant_router)
api_router.include_router(onboarding_router)
