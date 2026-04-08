import json
import sqlite3
import uuid
from typing import Any

from fastapi import HTTPException

from app.auth.security import utcnow_iso
from app.db.sqlite import create_connection
from app.services.asset_service import AssetService
from app.services.job_service import JobService
from app.services.video_analysis_service import VideoAnalysisService


class ConversationService:
    JOB_MESSAGE_TYPES = {
        "video_analysis_request",
        "video_remake_request",
        "motion_extract_request",
    }

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
        validated_assets: list[dict] = []

        if message_type in self.JOB_MESSAGE_TYPES:
            validated_assets = self._ensure_dispatch_assets(
                user_id=user_id,
                message_type=message_type,
                asset_ids=asset_ids,
            )

        connection = create_connection()
        try:
            conversation = self._get_owned_conversation(connection, conversation_id, user_id)
            if conversation is None:
                raise ValueError("会话不存在或无权访问。")

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
                    "user",
                    message_type,
                    content,
                    json.dumps(
                        {
                            "asset_ids": asset_ids,
                            "options": options,
                        },
                        ensure_ascii=False,
                    ),
                    reply_to_message_id,
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
            connection.commit()
        finally:
            connection.close()

        job = None
        if message_type in self.JOB_MESSAGE_TYPES:
            job = JobService().create_job_from_message(
                conversation_id=conversation_id,
                trigger_message_id=message_id,
                message_type=message_type,
                asset_ids=[asset["id"] for asset in validated_assets],
                options=options,
            )

            if job["job_type"] == "video_analysis":
                VideoAnalysisService().run_analysis_job(job_id=job["id"])

        return {
            "message_id": message_id,
            "job": job,
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

    def _ensure_dispatch_assets(
        self,
        *,
        user_id: str,
        message_type: str,
        asset_ids: list[str],
    ) -> list[dict]:
        normalized_ids = [asset_id.strip() for asset_id in asset_ids if asset_id and asset_id.strip()]
        if not normalized_ids:
            raise HTTPException(
                status_code=400,
                detail=f"{message_type} 至少需要一个输入资产。",
            )

        return AssetService().ensure_accessible_assets(
            asset_ids=normalized_ids,
            owner_user_id=user_id,
        )
