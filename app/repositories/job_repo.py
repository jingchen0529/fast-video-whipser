"""
Job repository — low-level ORM queries for Job and TaskQueueItem.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job, TaskQueueItem


class JobRepository:
    """Query helpers for the ``jobs`` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, job_id: str) -> Job | None:
        return self._session.get(Job, job_id)

    def list_by_project(self, project_id: int) -> list[Job]:
        return list(
            self._session.scalars(
                select(Job)
                .where(Job.project_id == project_id)
                .order_by(Job.created_at.asc())
            ).all()
        )

    def list_by_status(self, status: str, limit: int = 100) -> list[Job]:
        return list(
            self._session.scalars(
                select(Job)
                .where(Job.status == status)
                .order_by(Job.created_at.asc())
                .limit(limit)
            ).all()
        )

    def list_by_type(self, job_type: str, limit: int = 100) -> list[Job]:
        return list(
            self._session.scalars(
                select(Job)
                .where(Job.job_type == job_type)
                .order_by(Job.created_at.desc())
                .limit(limit)
            ).all()
        )

    def list_children(self, parent_job_id: str) -> list[Job]:
        return list(
            self._session.scalars(
                select(Job)
                .where(Job.parent_job_id == parent_job_id)
                .order_by(Job.created_at.asc())
            ).all()
        )


class TaskQueueRepository:
    """Query helpers for the ``task_queue`` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, task_id: str) -> TaskQueueItem | None:
        return self._session.get(TaskQueueItem, task_id)

    def claim_next(self) -> TaskQueueItem | None:
        """Return the oldest queued task (does NOT update status — caller must do that)."""
        return self._session.scalar(
            select(TaskQueueItem)
            .where(TaskQueueItem.status == "queued")
            .order_by(TaskQueueItem.created_at.asc())
        )

    def list_by_status(self, status: str, limit: int = 50) -> list[TaskQueueItem]:
        return list(
            self._session.scalars(
                select(TaskQueueItem)
                .where(TaskQueueItem.status == status)
                .order_by(TaskQueueItem.created_at.asc())
                .limit(limit)
            ).all()
        )
