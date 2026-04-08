import json
import uuid

from app.auth.security import utcnow_iso
from app.db.sqlite import create_connection
from app.services.asset_service import AssetService
from app.services.job_service import JobService


class VideoAnalysisService:
    def run_analysis_job(self, *, job_id: str) -> dict:
        connection = create_connection()
        try:
            job_row = connection.execute(
                """
                SELECT *
                FROM jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
            if job_row is None:
                raise ValueError("任务不存在。")

            job = dict(job_row)
            started_at = utcnow_iso()

            JobService().update_job_status(
                job_id=job_id,
                status="running",
                progress=15,
                started_at=started_at,
            )

            result = self._build_mock_result()
            motion_assets = AssetService().create_motion_assets_from_analysis(
                source_video_asset_id=job["input_asset_id"],
                conversation_id=job["conversation_id"],
                job_id=job_id,
                clips=result["clips"],
            )
            result["motion_assets"] = motion_assets

            finished_at = utcnow_iso()
            JobService().update_job_status(
                job_id=job_id,
                status="succeeded",
                progress=100,
                result=result,
                finished_at=finished_at,
            )

            self._write_assistant_messages(
                connection=connection,
                conversation_id=job["conversation_id"],
                result=result,
            )

            connection.commit()
            return result
        finally:
            connection.close()

    def _build_mock_result(self) -> dict:
        return {
            "summary": "已完成基础视频分析，检测到 3 个候选人物动作片段。",
            "clip_count": 3,
            "video_meta": {
                "duration_ms": 38120,
                "width": 1080,
                "height": 1920,
                "size_bytes": 12456789,
            },
            "clips": [
                {
                    "start_ms": 1200,
                    "end_ms": 4200,
                    "action_summary": "男性角色推门进入办公室，停顿半拍后向镜头方向稳步走近。",
                    "action_label": "walk_in",
                    "entrance_style": "push_door_and_pause",
                    "emotion_label": "cold_dominant",
                    "temperament_label": "bossy",
                    "scene_label": "office",
                    "camera_motion": "tracking",
                    "camera_shot": "medium_full",
                    "review_status": "auto_tagged",
                    "copyright_risk_level": "medium",
                    "asset_candidate": True,
                    "confidence": 0.91,
                },
                {
                    "start_ms": 8600,
                    "end_ms": 11400,
                    "action_summary": "人物停下脚步后转身回看，视线压向走廊另一端。",
                    "action_label": "pause_and_turn",
                    "entrance_style": "stop_and_glance",
                    "emotion_label": "dominant",
                    "temperament_label": "controlled",
                    "scene_label": "corridor",
                    "camera_motion": "static",
                    "camera_shot": "medium",
                    "review_status": "auto_tagged",
                    "copyright_risk_level": "medium",
                    "asset_candidate": True,
                    "confidence": 0.88,
                },
                {
                    "start_ms": 15000,
                    "end_ms": 18100,
                    "action_summary": "角色缓慢逼近目标人物，镜头轻推形成压迫感。",
                    "action_label": "approach_target",
                    "entrance_style": "slow_approach",
                    "emotion_label": "pressuring",
                    "temperament_label": "aggressive",
                    "scene_label": "meeting_room",
                    "camera_motion": "push_in",
                    "camera_shot": "medium_close",
                    "review_status": "auto_tagged",
                    "copyright_risk_level": "high",
                    "asset_candidate": True,
                    "confidence": 0.86,
                },
            ],
        }

    def _write_assistant_messages(
        self,
        *,
        connection,
        conversation_id: str,
        result: dict,
    ) -> None:
        now = utcnow_iso()

        connection.execute(
            """
            INSERT INTO conversation_messages (
                id, conversation_id, role, message_type, content, content_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                conversation_id,
                "assistant",
                "job_status",
                "视频分析任务已完成。",
                json.dumps(
                    {
                        "status": "succeeded",
                        "progress": 100,
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )

        connection.execute(
            """
            INSERT INTO conversation_messages (
                id, conversation_id, role, message_type, content, content_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                conversation_id,
                "assistant",
                "video_analysis_result",
                result["summary"],
                json.dumps(result, ensure_ascii=False),
                now,
            ),
        )

        connection.execute(
            """
            UPDATE conversations
            SET updated_at = ?
            WHERE id = ?
            """,
            (now, conversation_id),
        )
