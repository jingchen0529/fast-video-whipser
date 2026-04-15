import json
import uuid

from sqlalchemy import select

from app.auth.security import utcnow_ms
from app.db.session import get_db_session
from app.models.job import Job


def _get_session():
    gen = get_db_session()
    return next(gen)


class JobService:
    @staticmethod
    def _job_to_dict(job: Job) -> dict:
        result_json = job.result_json
        if isinstance(result_json, str):
            try:
                result_json = json.loads(result_json)
            except (json.JSONDecodeError, TypeError):
                result_json = {}
        return {
            "id": job.id,
            "project_id": job.project_id,
            "trigger_message_id": job.trigger_message_id,
            "job_type": job.job_type,
            "status": job.status,
            "progress": job.progress,
            "input_asset_id": job.input_asset_id,
            "output_asset_id": job.output_asset_id,
            "parent_job_id": job.parent_job_id,
            "source_job_id": job.source_job_id,
            "error_message": job.error_message,
            "result_json": result_json or {},
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }

    def create_job(
        self,
        *,
        job_type: str,
        project_id: int | None = None,
        trigger_message_id: str | None = None,
        input_asset_id: str | None = None,
        output_asset_id: str | None = None,
        parent_job_id: str | None = None,
        source_job_id: str | None = None,
        status: str = "queued",
        progress: int = 0,
        result: dict | None = None,
        error_message: str | None = None,
    ) -> dict:
        now = utcnow_ms()
        job_id = uuid.uuid4().hex

        session = _get_session()
        try:
            job = Job(
                id=job_id,
                project_id=project_id,
                trigger_message_id=trigger_message_id,
                job_type=job_type,
                status=status,
                progress=progress,
                input_asset_id=input_asset_id,
                output_asset_id=output_asset_id,
                parent_job_id=parent_job_id,
                source_job_id=source_job_id,
                error_message=error_message,
                result_json=json.dumps(result or {}, ensure_ascii=False),
                created_at=now,
                updated_at=now,
                started_at=now if status == "running" else None,
                finished_at=now if status in {"succeeded", "failed", "cancelled"} else None,
            )
            session.add(job)
            session.commit()
            return self._job_to_dict(job)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_job(self, *, job_id: str) -> dict | None:
        session = _get_session()
        try:
            job = session.get(Job, job_id)
            return self._job_to_dict(job) if job else None
        finally:
            session.close()

    def update_job_status(
        self,
        *,
        job_id: str,
        status: str,
        progress: int,
        result: dict | None = None,
        error_message: str | None = None,
        started_at: int | None = None,
        finished_at: int | None = None,
    ) -> None:
        now = utcnow_ms()
        session = _get_session()
        try:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.status = status
            job.progress = progress
            if result is not None:
                job.result_json = json.dumps(result, ensure_ascii=False)
            if error_message is not None:
                job.error_message = error_message
            if started_at is not None and job.started_at is None:
                job.started_at = started_at
            if finished_at is not None and job.finished_at is None:
                job.finished_at = finished_at
            job.updated_at = now
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
