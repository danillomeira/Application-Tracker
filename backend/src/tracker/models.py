"""Importa todos os modelos (Alembic e criação de metadata)."""

from tracker.core.db import Base
from tracker.modules.agent_gateway.models import AgentJob
from tracker.modules.applications.models import (
    Application,
    ApplicationAnswer,
    ApplicationEvent,
    DailyQuota,
    PendingQuestion,
)
from tracker.modules.calendar.models import CalendarEvent
from tracker.modules.companies.models import Company, CompanyProfile, CompanySignal
from tracker.modules.inbox.models import Draft, EmailMessage, LinkedinMessage
from tracker.modules.interviews.models import (
    Assessment,
    Interview,
    InterviewDossier,
    InterviewQuestionLog,
    MockSession,
)
from tracker.modules.jobs.models import Job, JobFeedback, JobSnapshot, JobSource, SavedSearch
from tracker.modules.offers.models import Offer
from tracker.modules.people.models import Person, PersonApplication
from tracker.modules.platform.models import (
    AiCall,
    AuditLog,
    BrowserSessionMeta,
    IntegrationState,
    Notification,
    OAuthCredential,
    Setting,
    TaskRun,
)
from tracker.modules.profile.models import (
    AnswerBankEntry,
    BlocklistEntry,
    Document,
    MasterProfileVersion,
    Preference,
    ProfileImport,
    Reference,
    StarStory,
)
from tracker.modules.resumes.models import ResumeRender, ResumeTemplate, ResumeVariant
from tracker.modules.scoring.models import JobScore, ScoringWeights

__all__ = [
    "AgentJob",
    "AiCall",
    "AnswerBankEntry",
    "Application",
    "ApplicationAnswer",
    "ApplicationEvent",
    "Assessment",
    "AuditLog",
    "Base",
    "BlocklistEntry",
    "BrowserSessionMeta",
    "CalendarEvent",
    "Company",
    "CompanyProfile",
    "CompanySignal",
    "DailyQuota",
    "Document",
    "Draft",
    "EmailMessage",
    "IntegrationState",
    "Interview",
    "InterviewDossier",
    "InterviewQuestionLog",
    "Job",
    "JobFeedback",
    "JobScore",
    "JobSnapshot",
    "JobSource",
    "LinkedinMessage",
    "MasterProfileVersion",
    "MockSession",
    "Notification",
    "OAuthCredential",
    "Offer",
    "PendingQuestion",
    "Person",
    "PersonApplication",
    "Preference",
    "ProfileImport",
    "Reference",
    "ResumeRender",
    "ResumeTemplate",
    "ResumeVariant",
    "SavedSearch",
    "ScoringWeights",
    "Setting",
    "StarStory",
    "TaskRun",
]
