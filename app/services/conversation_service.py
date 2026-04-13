import json
import sqlite3
import uuid
from typing import Any

from app.auth.security import utcnow_iso
from app.db.sqlite import create_connection
from app.services.asset_service import AssetService


class ConversationService:
    def _build_default_motion_clips(self) -> list[dict[str, Any]]:
        return [
            {
                "start_ms": 0,
                "end_ms": 2600,
                "action_summary": "角色快速出场并完成第一轮视线吸引。",
                "action_label": "出场亮相",
                "entrance_style": "直接切入",
                "emotion_label": "自信",
                "temperament_label": "利落",
                "scene_label": "室内讲解",
                "camera_motion": "static",
                "camera_shot": "medium",
                "review_status": "auto_tagged",
                "copyright_risk_level": "unknown",
            },
            {
                "start_ms": 2600,
                "end_ms": 6100,
                "action_summary": "人物通过手势和动作强化核心卖点说明。",
                "action_label": "手势讲解",
                "entrance_style": "承接推进",
                "emotion_label": "积极",
                "temperament_label": "亲和",
                "scene_label": "产品展示",
                "camera_motion": "tracking",
                "camera_shot": "medium_close",
                "review_status": "auto_tagged",
                "copyright_risk_level": "unknown",
            },
            {
                "start_ms": 6100,
                "end_ms": 9800,
                "action_summary": "结尾动作落在结果展示和行动引导上。",
                "action_label": "收束引导",
                "entrance_style": "节奏收束",
                "emotion_label": "坚定",
                "temperament_label": "专业",
                "scene_label": "结果展示",
                "camera_motion": "push_in",
                "camera_shot": "close_up",
                "review_status": "auto_tagged",
                "copyright_risk_level": "unknown",
            },
        ]

    def _create_job(
        self,
        *,
        connection: sqlite3.Connection,
        conversation_id: str,
        trigger_message_id: str,
        input_asset_id: str | None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utcnow_iso()
        job_id = uuid.uuid4().hex
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
                "video_analysis",
                "succeeded",
                100,
                input_asset_id,
                None,
                None,
                None,
                None,
                json.dumps(result or {}, ensure_ascii=False),
                now,
                now,
                now,
                now,
            ),
        )
        return {
            "id": job_id,
            "conversation_id": conversation_id,
            "trigger_message_id": trigger_message_id,
            "job_type": "video_analysis",
            "status": "succeeded",
            "progress": 100,
            "input_asset_id": input_asset_id,
            "output_asset_id": None,
            "error_message": None,
            "result_json": result or {},
            "created_at": now,
            "updated_at": now,
            "started_at": now,
            "finished_at": now,
        }

    def _append_message(
        self,
        *,
        connection: sqlite3.Connection,
        conversation_id: str,
        role: str,
        message_type: str,
        content: str,
        created_at: str,
        content_json: dict[str, Any] | None = None,
        reply_to_message_id: str | None = None,
    ) -> str:
        message_id = uuid.uuid4().hex
        connection.execute(
            """
            INSERT INTO conversation_messages (
                id, conversation_id, role, message_type,
                content, content_json, reply_to_message_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conversation_id,
                role,
                message_type,
                content,
                json.dumps(content_json, ensure_ascii=False) if content_json is not None else None,
                reply_to_message_id,
                created_at,
            ),
        )
        return message_id

    def create_conversation(
        self,
        *,
        user_id: str,
        title: str,
        conversation_type: str = "mixed",
        source_video_id: str | None = None,
    ) -> dict:
        now = utcnow_iso()
        conversation_id = uuid.uuid4().hex

        connection = create_connection()
        try:
            connection.execute(
                """
                INSERT INTO conversations (
                    id, title, user_id, conversation_type,
                    source_video_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    title,
                    user_id,
                    conversation_type,
                    source_video_id,
                    "active",
                    now,
                    now,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        return {
            "id": conversation_id,
            "title": title,
            "conversation_type": conversation_type,
            "source_video_id": source_video_id,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }

    def list_conversations(self, *, user_id: str) -> list[dict]:
        connection = create_connection()
        try:
            rows = connection.execute(
                """
                SELECT id, title, conversation_type, source_video_id, status, created_at, updated_at
                FROM conversations
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def list_messages(self, *, conversation_id: str, user_id: str) -> list[dict]:
        connection = create_connection()
        try:
            conversation = self._get_owned_conversation(connection, conversation_id, user_id)
            if conversation is None:
                raise ValueError("会话不存在或无权访问。")

            rows = connection.execute(
                """
                SELECT id, role, message_type, content, content_json, reply_to_message_id, created_at
                FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                """,
                (conversation_id,),
            ).fetchall()

            items = []
            for row in rows:
                item = dict(row)
                if item["content_json"]:
                    item["content_json"] = json.loads(item["content_json"])
                items.append(item)
            return items
        finally:
            connection.close()

    def create_message_and_dispatch(
        self,
        *,
        conversation_id: str,
        user_id: str,
        message_type: str,
        content: str,
        asset_ids: list[str],
        options: dict[str, Any],
        reply_to_message_id: str | None,
    ) -> dict:
        now = utcnow_iso()
        message_id = uuid.uuid4().hex
        accessible_assets: list[dict[str, Any]] = []
        normalized_message_type = (message_type or "").strip()

        if normalized_message_type == "video_analysis_request":
            accessible_assets = AssetService().ensure_accessible_assets(
                asset_ids=asset_ids,
                owner_user_id=user_id,
            )

        connection = create_connection()
        try:
            conversation = self._get_owned_conversation(connection, conversation_id, user_id)
            if conversation is None:
                raise ValueError("会话不存在或无权访问。")

            message_id = self._append_message(
                connection=connection,
                conversation_id=conversation_id,
                role="user",
                message_type=normalized_message_type,
                content=content,
                created_at=now,
                content_json={
                    "asset_ids": asset_ids,
                    "options": options,
                },
                reply_to_message_id=reply_to_message_id,
            )

            connection.execute(
                """
                UPDATE conversations
                SET updated_at = ?
                WHERE id = ?
                """,
                (now, conversation_id),
            )
            connection.commit()
        finally:
            connection.close()

        job: dict[str, Any] | None = None
        if normalized_message_type == "video_analysis_request":
            source_asset = accessible_assets[0]
            motion_assets = AssetService().create_motion_assets_from_analysis(
                source_video_asset_id=source_asset["id"],
                conversation_id=conversation_id,
                job_id=None,
                clips=self._build_default_motion_clips(),
            )
            job_result = {
                "motion_asset_ids": [item["id"] for item in motion_assets],
                "motion_asset_count": len(motion_assets),
                "source_video_asset_id": source_asset["id"],
                "options": options,
            }
            followup_now = utcnow_iso()
            connection = create_connection()
            try:
                job = self._create_job(
                    connection=connection,
                    conversation_id=conversation_id,
                    trigger_message_id=message_id,
                    input_asset_id=source_asset["id"],
                    result=job_result,
                )
                if motion_assets:
                    connection.execute(
                        """
                        UPDATE motion_assets
                        SET job_id = ?
                        WHERE id IN ({placeholders})
                        """.format(
                            placeholders=", ".join("?" for _ in motion_assets),
                        ),
                        (job["id"], *(item["id"] for item in motion_assets)),
                    )
                self._append_message(
                    connection=connection,
                    conversation_id=conversation_id,
                    role="assistant",
                    message_type="job_status",
                    content="已创建视频分析任务，正在整理动作资产候选。",
                    created_at=followup_now,
                    content_json={
                        "job": job,
                    },
                    reply_to_message_id=message_id,
                )
                self._append_message(
                    connection=connection,
                    conversation_id=conversation_id,
                    role="assistant",
                    message_type="video_analysis_result",
                    content=f"已生成 {len(motion_assets)} 条动作资产候选，可直接进入动态资产继续筛选。",
                    created_at=followup_now,
                    content_json={
                        "job": job,
                        "motion_assets": motion_assets,
                    },
                    reply_to_message_id=message_id,
                )
                connection.execute(
                    """
                    UPDATE conversations
                    SET updated_at = ?
                    WHERE id = ?
                    """,
                    (followup_now, conversation_id),
                )
                connection.commit()
            finally:
                connection.close()

        return {
            "message_id": message_id,
            "job": job if normalized_message_type == "video_analysis_request" else None,
        }

    def _get_owned_conversation(
        self,
        connection: sqlite3.Connection,
        conversation_id: str,
        user_id: str,
    ) -> dict | None:
        row = connection.execute(
            """
            SELECT *
            FROM conversations
            WHERE id = ? AND user_id = ?
            """,
            (conversation_id, user_id),
        ).fetchone()
        return dict(row) if row else None
