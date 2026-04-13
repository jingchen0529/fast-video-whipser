import json
import uuid

from app.auth.security import utcnow_iso
from app.db.sqlite import create_connection


class JobService:
    def create_job(
        self,
        *,
        job_type: str,
        conversation_id: str | None = None,
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
        now = utcnow_iso()
        job_id = uuid.uuid4().hex

        connection = create_connection()
        try:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, conversation_id, trigger_message_id, job_type, status, progress,
                    input_asset_id, output_asset_id, parent_job_id, source_job_id,
                    error_message, result_json, created_at, updated_at, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    conversation_id,
                    trigger_message_id,
                    job_type,
                    status,
                    progress,
                    input_asset_id,
                    output_asset_id,
                    parent_job_id,
                    source_job_id,
                    error_message,
                    json.dumps(result or {}, ensure_ascii=False),
                    now,
                    now,
                    now if status == "running" else None,
                    now if status in {"succeeded", "failed", "cancelled"} else None,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        return {
            "id": job_id,
            "conversation_id": conversation_id,
            "trigger_message_id": trigger_message_id,
            "job_type": job_type,
            "status": status,
            "progress": progress,
            "input_asset_id": input_asset_id,
            "output_asset_id": output_asset_id,
            "parent_job_id": parent_job_id,
            "source_job_id": source_job_id,
            "error_message": error_message,
            "result_json": result or {},
            "created_at": now,
            "updated_at": now,
            "started_at": now if status == "running" else None,
            "finished_at": now if status in {"succeeded", "failed", "cancelled"} else None,
        }

    def get_job(self, *, job_id: str) -> dict | None:
        connection = create_connection()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                return None

            job = dict(row)
            if job.get("result_json"):
                job["result_json"] = json.loads(job["result_json"])
            return job
        finally:
            connection.close()

    def update_job_status(
        self,
        *,
        job_id: str,
        status: str,
        progress: int,
        result: dict | None = None,
        error_message: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> None:
        now = utcnow_iso()

        connection = create_connection()
        try:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?,
                    progress = ?,
                    result_json = COALESCE(?, result_json),
                    error_message = COALESCE(?, error_message),
                    started_at = COALESCE(?, started_at),
                    finished_at = COALESCE(?, finished_at),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    progress,
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    error_message,
                    started_at,
                    finished_at,
                    now,
                    job_id,
                ),
            )
            connection.commit()
        finally:
            connection.close()
