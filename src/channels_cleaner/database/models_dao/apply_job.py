from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from channels_cleaner.database.models import ApplyJob
from channels_cleaner.enums import JobStatus


class ApplyJobDAO:
    session: AsyncSession

    async def create_job(self, account_id: int, total: int, now: datetime) -> ApplyJob:
        job = ApplyJob(account_id=account_id, status=JobStatus.RUNNING, total=total, started_at=now)
        self.session.add(job)

        # The id comes from SQLite: the job's events carry it from the start
        await self.session.flush()
        return job

    async def update_job(
        self,
        job_id: int,
        *,
        done: int,
        failed: int,
        status: JobStatus | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        statement = update(ApplyJob).where(ApplyJob.id == job_id).values(done=done, failed=failed)

        if status is not None:
            statement = statement.values(status=status, finished_at=finished_at)

        await self.session.execute(statement)

    async def interrupt_running_jobs(self, now: datetime) -> None:
        statement = (
            update(ApplyJob)
            .where(ApplyJob.status == JobStatus.RUNNING)
            .values(status=JobStatus.INTERRUPTED, finished_at=now)
        )

        await self.session.execute(statement)
