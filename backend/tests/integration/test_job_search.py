from __future__ import annotations

from httpx import AsyncClient

from tracker.modules.jobs import service as job_service
from tracker.modules.jobs.normalize import RawJob


async def test_job_search_matches_programming_language_source_tags(client: AsyncClient, session) -> None:
    job, _ = await job_service.upsert_job(
        session,
        RawJob(
            source="remoteok",
            external_id="golang-tagged-job",
            title="Backend Engineer",
            company_name="Globex",
            description_text="Build reliable backend services.",
            work_model="remote",
            raw={"tags": ["Golang", "Backend"]},
        ),
    )
    await session.commit()

    response = await client.get("/api/v1/jobs", params={"q": "go", "status": "open"})

    assert response.status_code == 200
    assert str(job.id) in {row["id"] for row in response.json()}
