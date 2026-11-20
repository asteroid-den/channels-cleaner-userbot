from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from channels_cleaner.database.models.base import Base
from channels_cleaner.enums import JobStatus


class ApplyJob(Base):
    """One run of the apply job, for the results screen."""

    __tablename__ = "apply_jobs"
    # AUTOINCREMENT, as the table was created: ids of deleted jobs are not handed out again
    __table_args__ = {"sqlite_autoincrement": True}  # noqa: RUF012

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int]
    status: Mapped[JobStatus]
    total: Mapped[int]
    done: Mapped[int] = mapped_column(default=0)
    failed: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
