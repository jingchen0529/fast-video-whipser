from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("idx_jobs_project_id", "project_id"),
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_job_type", "job_type"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True,
    )
    trigger_message_id: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    job_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    input_asset_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True,
    )
    output_asset_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True,
    )
    parent_job_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True,
    )
    source_job_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
    started_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    finished_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # -- relationships --
    parent_job: Mapped[Job | None] = relationship(
        remote_side=[id], foreign_keys=[parent_job_id],
    )
    source_job: Mapped[Job | None] = relationship(
        remote_side=[id], foreign_keys=[source_job_id],
    )


class TaskQueueItem(Base):
    __tablename__ = "task_queue"
    __table_args__ = (
        Index("idx_task_queue_status", "status"),
        Index("idx_task_queue_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    finished_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
