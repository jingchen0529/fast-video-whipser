import json
import uuid

from app.auth.security import utcnow_iso
from app.db.sqlite import create_connection


MESSAGE_TYPE_TO_JOB_TYPE = {
    "video_analysis_request": "video_analysis",
    "video_remake_request": "video_remake",
    "motion_extract_request": "motion_extraction",
}


class JobService:
    def create_job_from_message(
        self,
        *,
        conversation_id: str,
        trigger_message_id: str,
        message_type: str,
        asset_ids: list[str],
        options: dict,
    ) -> dict:
        now = utcnow_iso()
        job_id = uuid.uuid4().hex
        job_type = MESSAGE_TYPE_TO_JOB_TYPE[message_type]
        input_asset_id = asset_ids[0] if asset_ids else None

        connection = create_connection()
        try:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, conversation_id, trigger_message_id, job_type,
                    status, progress, input_asset_id, result_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    conversation_id,
                    trigger_message_id,
                    job_type,
                    "queued",
                    0,
                    input_asset_id,
                    json.dumps(
                        {
                            "asset_ids": asset_ids,
                            "options": options,
                        },
                        ensure_ascii=False,
                    ),
                    now,
                    now,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        return {
            "id": job_id,
            "job_type": job_type,
            "status": "queued",
            "progress": 0,
            "input_asset_id": input_asset_id,
            "created_at": now,
            "updated_at": now,
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
