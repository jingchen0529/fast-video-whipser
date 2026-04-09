import json

from app.auth.security import utcnow_iso
from app.db.sqlite import create_connection


class JobService:
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
