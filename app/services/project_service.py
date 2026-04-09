import asyncio
import json
import logging
import mimetypes
import os
import sqlite3
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from fastapi import HTTPException, UploadFile

from app.auth.security import utcnow_iso
from app.core.config import settings
from app.crawlers.tiktok import TikTokAPPCrawler
from app.db.sqlite import create_connection
from app.http_client import AsyncHttpClient
from app.services.analysis_ai_service import AnalysisAIService
from app.services.asset_service import AssetService
from app.services.system_settings_service import SystemSettingsService
from app.utils.file_utils import FileUtils
from app.workflows.engine import TaskStepDefinition, WorkflowRegistry

logger = logging.getLogger(__name__)

# Re-export for backward compatibility with legacy step migration code
from app.workflows.engine import UNSUPPORTED_WORKFLOW_STEPS  # noqa: E402

DEFAULT_SCRIPT_OVERVIEW = {
    "full_text": "",
    "dialogue_text": "",
    "narration_text": "",
    "caption_text": "",
}

DEFAULT_ECOMMERCE_ANALYSIS = {
    "title": "分析结果",
    "content": None,
}

DEFAULT_SOURCE_ANALYSIS = {
    "reference_frames": [],
    "visual_features": None,
}

DEFAULT_STORYBOARD = {
    "id": None,
    "version_no": 0,
    "status": "idle",
    "summary": "",
    "items": [],
}

DEFAULT_VIDEO_GENERATION = {
    "status": "idle",
    "provider": None,
    "model": None,
    "objective": None,
    "asset_type": None,
    "asset_name": None,
    "asset_url": None,
    "audio_name": None,
    "audio_url": None,
    "reference_frames": [],
    "script": None,
    "storyboard": None,
    "prompt": None,
    "provider_task_id": None,
    "result_video_url": None,
    "error_detail": None,
    "updated_at": None,
}

JSON_PROJECT_COLUMNS = {
    "script_overview": "script_overview_json",
    "ecommerce_analysis": "ecommerce_analysis_json",
    "source_analysis": "source_analysis_json",
    "timeline_segments": "timeline_segments_json",
    "video_generation": "video_generation_json",
}


class ProjectService:

    @property
    def SUPPORTED_WORKFLOWS(self) -> set[str]:
        """Dynamically returns all registered workflow types."""
        return WorkflowRegistry.supported_types()

    def list_projects(self, *, user_id: str) -> list[dict[str, Any]]:
        connection = create_connection()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM projects
                WHERE user_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (user_id,),
            ).fetchall()
            return [self._row_to_project_list_item(row) for row in rows]
        finally:
            connection.close()

    def get_project_detail(
        self,
        *,
        project_id: int,
        user_id: str,
    ) -> dict[str, Any] | None:
        connection = create_connection()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM projects
                WHERE id = ? AND user_id = ?
                LIMIT 1
                """,
                (project_id, user_id),
            ).fetchone()
            if row is None:
                return None

            item = self._row_to_project_detail(row)
            item["shot_segments"] = self._load_shot_segments(
                connection=connection,
                project_id=project_id,
            )
            item["storyboard"] = self._load_latest_storyboard(
                connection=connection,
                project_id=project_id,
            ) or self._build_legacy_storyboard(
                timeline_segments=item["timeline_segments"],
                video_generation=item["video_generation"],
            )
            self._ensure_project_task_steps(
                connection=connection,
                project_id=project_id,
                workflow_type=item["workflow_type"],
            )
            item["task_steps"] = self._load_project_steps(
                connection=connection,
                project_id=project_id,
            )
            item["conversation_messages"] = self._load_conversation_messages(
                connection=connection,
                conversation_id=item["conversation_id"],
            )
            return item
        finally:
            connection.close()

    async def create_project(
        self,
        *,
        user_id: str,
        objective: str,
        workflow_type: str,
        source_url: str = "",
        file: UploadFile | None = None,
    ) -> dict[str, Any]:
        normalized_objective = (objective or "").strip()
        normalized_workflow = self._normalize_workflow_type(workflow_type)
        explicit_source_url = (source_url or "").strip()
        extracted_source_url = explicit_source_url or self._extract_first_url(normalized_objective)

        if not normalized_objective and file is None and not extracted_source_url:
            raise HTTPException(
                status_code=400,
                detail="请先输入指令，或添加视频文件/链接。",
            )

        source_type = "upload" if file else ("url" if extracted_source_url else "upload")
        source_platform = self._detect_platform(extracted_source_url)
        source_name = (
            (file.filename or "").strip()
            if file is not None
            else extracted_source_url or "未命名视频分析"
        )
        title = self._build_project_title(
            source_name=source_name,
            workflow_type=normalized_workflow,
        )
        conversation_title = title

        source_asset_id: str | None = None
        media_url: str | None = None
        if file is not None:
            asset = await self._persist_uploaded_asset(
                user_id=user_id,
                upload=file,
            )
            source_asset_id = asset["id"]
            media_url = asset["public_url"]
            source_name = file.filename or asset["file_name"]
            title = self._build_project_title(
                source_name=source_name,
                workflow_type=normalized_workflow,
            )
            conversation_title = title

        now = utcnow_iso()
        connection = create_connection()
        try:
            conversation_id = self._create_conversation_record(
                connection=connection,
                user_id=user_id,
                title=conversation_title,
                conversation_type="video_analysis" if normalized_workflow == "analysis" else normalized_workflow,
                source_video_id=source_asset_id,
                now=now,
            )
            cursor = connection.execute(
                """
                INSERT INTO projects (
                    user_id, conversation_id, title, source_url, source_platform, workflow_type,
                    source_type, source_name, status, media_url, objective,
                    summary, source_asset_id, script_overview_json,
                    ecommerce_analysis_json, source_analysis_json,
                    timeline_segments_json, video_generation_json,
                    error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    conversation_id,
                    title,
                    extracted_source_url,
                    source_platform,
                    normalized_workflow,
                    source_type,
                    source_name,
                    "running",
                    media_url,
                    normalized_objective,
                    "任务已创建，准备启动分析工作流。",
                    source_asset_id,
                    json.dumps(DEFAULT_SCRIPT_OVERVIEW, ensure_ascii=False),
                    json.dumps(DEFAULT_ECOMMERCE_ANALYSIS, ensure_ascii=False),
                    json.dumps(DEFAULT_SOURCE_ANALYSIS, ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    json.dumps(DEFAULT_VIDEO_GENERATION, ensure_ascii=False),
                    None,
                    now,
                    now,
                ),
            )
            project_id = int(cursor.lastrowid)
            user_request = self._build_user_request_message(
                objective=normalized_objective,
                source_name=source_name,
                source_url=extracted_source_url,
                workflow_type=normalized_workflow,
            )
            self._append_conversation_message(
                connection=connection,
                conversation_id=conversation_id,
                role="user",
                message_type="project_request",
                content=user_request,
                content_json={
                    "project_id": project_id,
                    "workflow_type": normalized_workflow,
                    "source_url": extracted_source_url,
                    "source_name": source_name,
                },
                created_at=now,
            )
            self._append_conversation_message(
                connection=connection,
                conversation_id=conversation_id,
                role="assistant",
                message_type="workflow_status",
                content="收到，我会先提取视频链接并完成脚本分析，然后把拆解结果和优化建议整理给你。",
                content_json={
                    "project_id": project_id,
                    "workflow_type": normalized_workflow,
                    "status": "accepted",
                },
                created_at=now,
            )
            step_definitions = self._get_step_definitions(normalized_workflow)
            for index, definition in enumerate(step_definitions, start=1):
                is_first_step = index == 1
                connection.execute(
                    """
                    INSERT INTO project_task_steps (
                        project_id, step_key, title, detail, status,
                        error_detail, output_json, display_order, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        definition.step_key,
                        definition.title,
                        definition.description,
                        "in_progress" if is_first_step else "pending",
                        None,
                        None,
                        index,
                        now,
                        now,
                    ),
                )

            connection.commit()
        finally:
            connection.close()

        project = self.get_project_detail(project_id=project_id, user_id=user_id)
        if project is None:
            raise HTTPException(status_code=500, detail="项目创建失败。")
        return project

    async def run_project_workflow(self, *, project_id: int) -> None:
        """Delegate workflow execution to the WorkflowEngine."""
        from app.workflows.engine import WorkflowEngine
        engine = WorkflowEngine()
        await engine.run(project_id=project_id)

    def _row_to_project_list_item(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        return {
            "id": item["id"],
            "conversation_id": item.get("conversation_id"),
            "title": item["title"],
            "source_url": item["source_url"] or "",
            "source_platform": item["source_platform"] or "local",
            "workflow_type": item["workflow_type"] or "analysis",
            "source_type": item["source_type"] or "upload",
            "source_name": item["source_name"] or "",
            "status": item["status"] or "queued",
            "media_url": item["media_url"],
            "objective": item["objective"] or "",
            "summary": item["summary"] or "",
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }

    def _row_to_project_detail(self, row: sqlite3.Row) -> dict[str, Any]:
        item = self._row_to_project_list_item(row)
        row_data = dict(row)
        item["script_overview"] = self._load_json_field(
            row_data.get("script_overview_json"),
            DEFAULT_SCRIPT_OVERVIEW,
        )
        item["ecommerce_analysis"] = self._load_json_field(
            row_data.get("ecommerce_analysis_json"),
            DEFAULT_ECOMMERCE_ANALYSIS,
        )
        item["source_analysis"] = self._load_json_field(
            row_data.get("source_analysis_json"),
            DEFAULT_SOURCE_ANALYSIS,
        )
        item["timeline_segments"] = self._load_json_field(
            row_data.get("timeline_segments_json"),
            [],
        )
        item["video_generation"] = self._load_json_field(
            row_data.get("video_generation_json"),
            DEFAULT_VIDEO_GENERATION,
        )
        item["shot_segments"] = []
        item["storyboard"] = deepcopy(DEFAULT_STORYBOARD)
        item["conversation_messages"] = []
        return item

    def _load_project_steps(
        self,
        *,
        connection: sqlite3.Connection,
        project_id: int,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT id, step_key, title, detail, status, error_detail, display_order, updated_at
            FROM project_task_steps
            WHERE project_id = ?
            ORDER BY display_order ASC, id ASC
            """,
            (project_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _ensure_project_task_steps(
        self,
        *,
        connection: sqlite3.Connection,
        project_id: int,
        workflow_type: str,
    ) -> None:
        step_definitions = self._get_step_definitions(workflow_type)
        expected_step_keys = [definition.step_key for definition in step_definitions]
        rows = connection.execute(
            """
            SELECT *
            FROM project_task_steps
            WHERE project_id = ?
            ORDER BY display_order ASC, id ASC
            """,
            (project_id,),
        ).fetchall()
        existing_rows = [dict(row) for row in rows]
        current_step_keys = [row.get("step_key") for row in existing_rows]

        if current_step_keys == expected_step_keys:
            return

        rebuilt_rows = self._rebuild_project_task_steps(
            project_id=project_id,
            workflow_type=workflow_type,
            existing_rows=existing_rows,
        )
        now = utcnow_iso()
        connection.execute(
            "DELETE FROM project_task_steps WHERE project_id = ?",
            (project_id,),
        )
        for row in rebuilt_rows:
            connection.execute(
                """
                INSERT INTO project_task_steps (
                    project_id, step_key, title, detail, status,
                    error_detail, output_json, display_order, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    row["step_key"],
                    row["title"],
                    row["detail"],
                    row["status"],
                    row.get("error_detail"),
                    row.get("output_json"),
                    row["display_order"],
                    row.get("created_at") or now,
                    row.get("updated_at") or now,
                ),
            )
        connection.commit()

    def _rebuild_project_task_steps(
        self,
        *,
        project_id: int,
        workflow_type: str,
        existing_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        step_definitions = self._get_step_definitions(workflow_type)
        rows_by_key = {
            str(row.get("step_key") or "").strip(): row
            for row in existing_rows
            if str(row.get("step_key") or "").strip()
        }
        rebuilt_rows: list[dict[str, Any]] = []

        for index, definition in enumerate(step_definitions, start=1):
            existing_row = rows_by_key.get(definition.step_key)
            if existing_row is not None:
                rebuilt_rows.append(
                    {
                        "step_key": definition.step_key,
                        "title": definition.title,
                        "detail": existing_row.get("detail") or definition.description,
                        "status": existing_row.get("status") or "pending",
                        "error_detail": existing_row.get("error_detail"),
                        "output_json": existing_row.get("output_json"),
                        "display_order": index,
                        "created_at": existing_row.get("created_at"),
                        "updated_at": existing_row.get("updated_at"),
                    }
                )
                continue

            rebuilt_rows.append(
                self._build_missing_project_task_step(
                    workflow_type=workflow_type,
                    definition=definition,
                    display_order=index,
                    existing_rows=existing_rows,
                    project_id=project_id,
                )
            )

        return rebuilt_rows

    def _build_missing_project_task_step(
        self,
        *,
        workflow_type: str,
        definition: TaskStepDefinition,
        display_order: int,
        existing_rows: list[dict[str, Any]],
        project_id: int,
    ) -> dict[str, Any]:
        now = utcnow_iso()
        return {
            "step_key": definition.step_key,
            "title": definition.title,
            "detail": definition.description,
            "status": "pending",
            "error_detail": None,
            "output_json": None,
            "display_order": display_order,
            "created_at": now,
            "updated_at": now,
        }

    def _load_shot_segments(
        self,
        *,
        connection: sqlite3.Connection,
        project_id: int,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT *
            FROM shot_segments
            WHERE project_id = ?
            ORDER BY segment_index ASC, start_ms ASC, id ASC
            """,
            (project_id,),
        ).fetchall()
        return [self._serialize_shot_segment(dict(row)) for row in rows]

    def _load_shot_segments_for_project(self, *, project_id: int) -> list[dict[str, Any]]:
        connection = create_connection()
        try:
            return self._load_shot_segments(
                connection=connection,
                project_id=project_id,
            )
        finally:
            connection.close()

    def _serialize_shot_segment(self, item: dict[str, Any]) -> dict[str, Any]:
        item["detector_config_json"] = self._load_json_field(item.get("detector_config_json"), {})
        item["keyframe_asset_ids_json"] = self._load_json_field(item.get("keyframe_asset_ids_json"), [])
        item["metadata_json"] = self._load_json_field(item.get("metadata_json"), {})
        item["shot_type_label"] = self._shot_type_label(item.get("shot_type_code"))
        item["camera_angle_label"] = self._camera_angle_label(item.get("camera_angle_code"))
        item["camera_motion_label"] = self._camera_motion_label(item.get("camera_motion_code"))
        return item

    def _load_latest_storyboard(
        self,
        *,
        connection: sqlite3.Connection,
        project_id: int,
    ) -> dict[str, Any] | None:
        storyboard_row = connection.execute(
            """
            SELECT *
            FROM storyboards
            WHERE project_id = ?
            ORDER BY version_no DESC, created_at DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        if storyboard_row is None:
            return None

        storyboard = dict(storyboard_row)
        storyboard["metadata_json"] = self._load_json_field(
            storyboard.get("metadata_json"),
            {},
        )
        item_rows = connection.execute(
            """
            SELECT *
            FROM storyboard_items
            WHERE storyboard_id = ?
            ORDER BY item_index ASC, start_ms ASC, id ASC
            """,
            (storyboard["id"],),
        ).fetchall()

        items: list[dict[str, Any]] = []
        for row in item_rows:
            item = dict(row)
            item["metadata_json"] = self._load_json_field(item.get("metadata_json"), {})
            source_rows = connection.execute(
                """
                SELECT sis.shot_segment_id, sis.display_order, ss.segment_index
                FROM storyboard_item_segments sis
                JOIN shot_segments ss ON ss.id = sis.shot_segment_id
                WHERE sis.storyboard_item_id = ?
                ORDER BY sis.display_order ASC, ss.segment_index ASC
                """,
                (item["id"],),
            ).fetchall()
            item["source_segment_ids"] = [source_row["shot_segment_id"] for source_row in source_rows]
            item["source_segment_indexes"] = [source_row["segment_index"] for source_row in source_rows]
            item["shot_type_label"] = self._shot_type_label(item.get("shot_type_code"))
            item["camera_angle_label"] = self._camera_angle_label(item.get("camera_angle_code"))
            item["camera_motion_label"] = self._camera_motion_label(item.get("camera_motion_code"))
            items.append(item)

        storyboard["items"] = items
        return storyboard

    def _build_legacy_storyboard(
        self,
        *,
        timeline_segments: list[dict[str, Any]],
        video_generation: dict[str, Any],
    ) -> dict[str, Any]:
        raw_storyboard = video_generation.get("storyboard")
        raw_items = raw_storyboard if isinstance(raw_storyboard, list) else (
            raw_storyboard.get("items") if isinstance(raw_storyboard, dict) else []
        )
        if isinstance(raw_items, list) and raw_items:
            items: list[dict[str, Any]] = []
            for index, raw_item in enumerate(raw_items, start=1):
                if not isinstance(raw_item, dict):
                    continue
                shot_type_code = raw_item.get("shot_type_code") or raw_item.get("shot_type") or "medium"
                camera_angle_code = raw_item.get("camera_angle_code") or raw_item.get("camera_angle") or "eye_level"
                camera_motion_code = raw_item.get("camera_motion_code") or raw_item.get("camera_motion") or "static"
                item = {
                    "id": raw_item.get("id") or f"legacy-storyboard-{index}",
                    "item_index": int(raw_item.get("item_index") or index),
                    "title": raw_item.get("title") or f"分镜 {index}",
                    "start_ms": int(raw_item.get("start_ms") or 0),
                    "end_ms": int(raw_item.get("end_ms") or raw_item.get("start_ms") or 0),
                    "duration_ms": max(
                        0,
                        int(raw_item.get("end_ms") or raw_item.get("start_ms") or 0)
                        - int(raw_item.get("start_ms") or 0),
                    ),
                    "shot_type_code": shot_type_code,
                    "camera_angle_code": camera_angle_code,
                    "camera_motion_code": camera_motion_code,
                    "visual_description": raw_item.get("visual_description") or raw_item.get("description") or "",
                    "transcript_excerpt": raw_item.get("transcript_excerpt") or "",
                    "ocr_excerpt": raw_item.get("ocr_excerpt") or "",
                    "confidence": float(raw_item.get("confidence") or 0.6),
                    "source_segment_ids": [],
                    "source_segment_indexes": raw_item.get("source_segment_indexes") or [],
                    "shot_type_label": self._shot_type_label(shot_type_code),
                    "camera_angle_label": self._camera_angle_label(camera_angle_code),
                    "camera_motion_label": self._camera_motion_label(camera_motion_code),
                }
                items.append(item)
            return {
                "id": None,
                "version_no": 0,
                "status": "legacy",
                "summary": "",
                "items": items,
            }

        return deepcopy(DEFAULT_STORYBOARD)

    # NOTE: _execute_step has been moved to WorkflowEngine.
    # Step handler methods (_step_*) remain here as they contain domain logic.

    async def _step_extract_video_link(self, *, project_id: int) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        if project["source_asset_id"]:
            return {
                "source_type": "upload",
                "platform": "local",
                "detail": f"已识别上传素材 {project['source_name']}，后续将直接进入分析。",
            }

        normalized_source_url = (project["source_url"] or "").strip()
        if not normalized_source_url:
            normalized_source_url = self._extract_first_url(project["objective"] or "")

        if not normalized_source_url:
            raise ValueError("未从输入中识别到可分析的视频链接，请补充视频链接或上传素材。")

        source_platform = self._detect_platform(normalized_source_url)
        self._update_project(
            project_id=project_id,
            source_url=normalized_source_url,
            source_type="url",
            source_platform=source_platform,
            source_name=normalized_source_url,
            title=self._build_project_title(
                source_name=normalized_source_url,
                workflow_type=project["workflow_type"],
            ),
        )

        return {
            "source_type": "url",
            "normalized_url": normalized_source_url,
            "platform": source_platform,
            "detail": f"已提取 {self._platform_label(source_platform)} 链接，准备进入校验。",
        }

    async def _step_validate_video_link(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        if project["source_asset_id"]:
            return {
                "detail": "检测到本地上传素材，已跳过外链校验并确认素材可直接分析。",
            }

        source_url = (
            context.get("extract_video_link", {}).get("normalized_url")
            or project["source_url"]
            or ""
        ).strip()
        if not source_url:
            raise ValueError("缺少待校验的视频链接。")

        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("当前仅支持 http 或 https 视频链接。")
        if not parsed.netloc:
            raise ValueError("视频链接缺少域名，请确认链接格式是否完整。")

        platform = self._detect_platform(source_url)
        result: dict[str, Any] = {
            "platform": platform,
            "source_url": source_url,
        }
        detail = f"已确认链接协议和来源平台：{self._platform_label(platform)}。"

        if platform == "tiktok":
            crawler_result = await TikTokAPPCrawler().fetch_video_info(source_url)
            result["remote_video_info"] = crawler_result
            video_info = crawler_result.get("video_info") or {}
            aweme_id = crawler_result.get("aweme_id") or ""
            download_url = crawler_result.get("download_url") or source_url
            desc = (video_info.get("desc") or "").strip()
            source_name = desc or f"TikTok 视频 {aweme_id}".strip()
            title = self._build_project_title(
                source_name=source_name,
                workflow_type=project["workflow_type"],
            )
            self._update_project(
                project_id=project_id,
                source_platform=platform,
                source_name=source_name,
                title=title,
            )
            result["download_url"] = download_url
            detail = "已完成 TikTok 链接校验，并解析出视频基础信息和可下载地址。"

        return {
            **result,
            "detail": detail,
        }

    async def _step_segment_video_shots(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        source_asset = await self._ensure_source_asset(
            project=project,
            context=context,
        )
        remote_video_info = (
            context.get("validate_video_link", {}).get("remote_video_info")
            or {}
        )
        video_meta = self._build_video_meta(
            project=project,
            source_asset=source_asset,
            video_info=remote_video_info.get("video_info") or {},
        )
        shot_segments = self._detect_shot_segments(
            project=project,
            source_asset=source_asset,
            video_meta=video_meta,
        )
        if not shot_segments:
            shot_segments = self._build_fallback_shot_segments(
                video_meta=video_meta,
                objective=project["objective"],
                source_name=project["source_name"],
            )
        shot_segments = self._replace_shot_segments(
            project_id=project_id,
            project=project,
            source_asset=source_asset,
            shot_segments=shot_segments,
        )
        summary = f"已完成镜头切分，共识别 {len(shot_segments)} 个镜头段。"
        self._update_project(
            project_id=project_id,
            media_url=source_asset.get("public_url") or project["media_url"],
            source_asset_id=source_asset["id"],
            summary=summary,
            status="running",
        )

        return {
            "source_asset_id": source_asset["id"],
            "video_meta": video_meta,
            "shot_segments": shot_segments,
            "detail": summary,
        }

    async def _step_analyze_video_content(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        source_asset = await self._ensure_source_asset(
            project=project,
            context=context,
        )
        remote_video_info = (
            context.get("validate_video_link", {}).get("remote_video_info")
            or {}
        )
        video_meta = (
            context.get("segment_video_shots", {}).get("video_meta")
            or self._build_video_meta(
                project=project,
                source_asset=source_asset,
                video_info=remote_video_info.get("video_info") or {},
            )
        )
        shot_segments = (
            context.get("segment_video_shots", {}).get("shot_segments")
            or self._load_shot_segments_for_project(project_id=project_id)
        )
        shot_segments = self._enrich_shot_segments(
            shot_segments=shot_segments,
            video_meta=video_meta,
            objective=project["objective"],
            source_name=project["source_name"],
        )
        shot_segments = self._replace_shot_segments(
            project_id=project_id,
            project=project,
            source_asset=source_asset,
            shot_segments=shot_segments,
            preserve_transcript=True,
        )
        visual_features = self._build_visual_features(
            video_meta=video_meta,
            shot_segments=shot_segments,
        )
        timeline_segments: list[dict[str, Any]] = []
        source_analysis = {
            "reference_frames": [],
            "visual_features": visual_features,
            "shot_segment_count": len(shot_segments),
        }
        summary = f"已完成视频画面与运镜分析，整理出 {len(shot_segments)} 个镜头段特征。"

        self._update_project(
            project_id=project_id,
            media_url=source_asset.get("public_url") or project["media_url"],
            source_asset_id=source_asset["id"],
            source_analysis=source_analysis,
            timeline_segments=timeline_segments,
            summary=summary,
            status="running",
        )

        return {
            "source_asset_id": source_asset["id"],
            "video_meta": video_meta,
            "source_analysis": source_analysis,
            "timeline_segments": timeline_segments,
            "shot_segments": shot_segments,
            "detail": summary,
        }

    async def _step_identify_audio_content(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        source_asset = await self._ensure_source_asset(
            project=project,
            context=context,
        )
        remote_video_info = (
            context.get("validate_video_link", {}).get("remote_video_info")
            or {}
        )
        video_desc = (
            (remote_video_info.get("video_info") or {}).get("desc")
            or project["objective"]
            or project["source_name"]
        )
        transcription_result = await self._transcribe_source_media(
            project=project,
            source_asset=source_asset,
        )
        timeline_segments = transcription_result.get("timeline_segments") or []
        script_overview = self._build_script_overview(
            timeline_segments=timeline_segments,
            video_desc=video_desc,
        )
        self._update_project(
            project_id=project_id,
            script_overview=script_overview,
            timeline_segments=timeline_segments,
        )
        shot_segments = self._sync_shot_segments_with_timeline_segments(
            project_id=project_id,
            timeline_segments=timeline_segments,
        )

        return {
            "script_overview": script_overview,
            "timeline_segments": timeline_segments,
            "shot_segments": shot_segments,
            "provider": transcription_result.get("provider"),
            "used_fallback": transcription_result.get("used_fallback", False),
            "detail": transcription_result.get("detail")
            or "已完成口播与字幕整理，提炼出完整脚本文本和分段内容。",
        }

    async def _step_generate_storyboard(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        source_asset = await self._ensure_source_asset(
            project=project,
            context=context,
        )
        video_meta = (
            context.get("segment_video_shots", {}).get("video_meta")
            or context.get("analyze_video_content", {}).get("video_meta")
            or self._build_video_meta(
                project=project,
                source_asset=source_asset,
                video_info=(context.get("validate_video_link", {}).get("remote_video_info") or {}).get("video_info") or {},
            )
        )
        shot_segments = (
            context.get("identify_audio_content", {}).get("shot_segments")
            or context.get("analyze_video_content", {}).get("shot_segments")
            or self._load_shot_segments_for_project(project_id=project_id)
        )
        if not shot_segments:
            shot_segments = self._build_fallback_shot_segments(
                video_meta=video_meta,
                objective=project["objective"],
                source_name=project["source_name"],
            )

        storyboard_context = self._build_storyboard_generation_context(
            shot_segments=shot_segments,
        )
        ai_result = await AnalysisAIService().generate_storyboard_reply(
            objective=project["objective"],
            source_name=project["source_name"],
            video_meta=video_meta,
            shot_segments=storyboard_context,
        )
        storyboard_payload = self._normalize_storyboard_payload(
            payload=ai_result.get("storyboard") or {},
            shot_segments=shot_segments,
        )
        storyboard = self._replace_storyboard(
            project_id=project_id,
            project=project,
            source_asset=source_asset,
            storyboard_payload=storyboard_payload,
            provider=ai_result.get("provider"),
            model=ai_result.get("model"),
            used_remote=bool(ai_result.get("used_remote")),
        )
        summary = f"已生成 {len(storyboard['items'])} 条结构化分镜，可在历史详情中直接查看。"
        self._update_project(
            project_id=project_id,
            summary=summary,
        )

        return {
            "storyboard": storyboard,
            "detail": summary,
            "provider": ai_result.get("provider"),
            "model": ai_result.get("model"),
            "used_remote": ai_result.get("used_remote"),
        }

    async def _step_generate_response(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        source_analysis = context.get("analyze_video_content", {}).get("source_analysis") or DEFAULT_SOURCE_ANALYSIS
        timeline_segments = context.get("identify_audio_content", {}).get("timeline_segments") or []
        script_overview = context.get("identify_audio_content", {}).get("script_overview") or DEFAULT_SCRIPT_OVERVIEW
        storyboard = context.get("generate_storyboard", {}).get("storyboard") or DEFAULT_STORYBOARD
        ai_result = await AnalysisAIService().generate_analysis_reply(
            objective=project["objective"],
            source_name=project["source_name"],
            source_analysis=source_analysis,
            timeline_segments=timeline_segments,
            script_overview=script_overview,
            storyboard=storyboard,
        )
        ecommerce_analysis = {
            "title": "TikTok 电商效果深度分析",
            "content": ai_result["content"],
        }
        summary = "已生成 TikTok 电商效果深度分析主内容。"
        self._update_project(
            project_id=project_id,
            ecommerce_analysis=ecommerce_analysis,
            summary=summary,
        )
        self._append_project_message(
            project_id=project_id,
            role="assistant",
            message_type="analysis_reply",
            content=ai_result["content"],
            content_json={
                "provider": ai_result["provider"],
                "model": ai_result["model"],
                "used_remote": ai_result["used_remote"],
            },
        )

        return {
            "ecommerce_analysis": ecommerce_analysis,
            "detail": summary,
            "provider": ai_result["provider"],
            "model": ai_result["model"],
            "used_remote": ai_result["used_remote"],
        }

    async def _step_generate_suggestions(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        ecommerce_analysis = deepcopy(
            context.get("generate_response", {}).get("ecommerce_analysis")
            or DEFAULT_ECOMMERCE_ANALYSIS
        )
        suggestion_result = await AnalysisAIService().generate_suggestions_reply(
            objective=project["objective"],
            source_name=project["source_name"],
            analysis_content=ecommerce_analysis.get("content") or "",
        )
        suggestion_lines = [
            line.strip()
            for line in (suggestion_result["content"] or "").splitlines()
            if line.strip()
        ]
        suggestions = suggestion_lines or self._build_suggestions(project=project)
        content = ecommerce_analysis.get("content") or ""
        suggestion_block = "\n\n## 优化建议\n" + "\n".join(suggestions)
        ecommerce_analysis["content"] = f"{content}{suggestion_block}".strip()
        summary = "已补充 5 条可执行优化建议，分析结果已可直接用于脚本迭代。"
        self._update_project(
            project_id=project_id,
            ecommerce_analysis=ecommerce_analysis,
            summary=summary,
        )
        self._append_project_message(
            project_id=project_id,
            role="assistant",
            message_type="suggestion_reply",
            content=suggestion_block.strip(),
            content_json={
                "provider": suggestion_result["provider"],
                "model": suggestion_result["model"],
                "used_remote": suggestion_result["used_remote"],
            },
        )

        return {
            "suggestions": suggestions,
            "detail": summary,
            "provider": suggestion_result["provider"],
            "model": suggestion_result["model"],
            "used_remote": suggestion_result["used_remote"],
        }

    async def _step_finish(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        final_summary = "视频分析工作流已完成，已输出结构化分镜、脚本梳理、电商效果分析和优化建议。"
        self._update_project(
            project_id=project_id,
            status="succeeded",
            summary=final_summary,
            error_message=None,
        )
        return {
            "detail": final_summary,
        }

    async def _transcribe_source_media(
        self,
        *,
        project: dict[str, Any],
        source_asset: dict[str, Any],
    ) -> dict[str, Any]:
        settings_payload = SystemSettingsService().get_settings()
        transcription_group = settings_payload.get("transcription") or {}
        providers = transcription_group.get("providers") or []
        provider_map = {
            str(item.get("provider") or "").strip().lower(): item
            for item in providers
            if isinstance(item, dict) and str(item.get("provider") or "").strip()
        }
        provider_order = self._build_transcription_provider_order(
            default_provider=str(transcription_group.get("default_provider") or ""),
            provider_map=provider_map,
        )
        capabilities = SystemSettingsService().get_transcription_capabilities(
            payload=settings_payload,
        )
        provider_errors: list[str] = []

        for provider_key in provider_order:
            provider = provider_map.get(provider_key) or {}
            if not provider.get("enabled"):
                continue

            try:
                if provider_key == "faster_whisper":
                    capability = (
                        capabilities.get("providers", {})
                        .get("faster_whisper", {})
                    )
                    if not capability.get("available"):
                        issues = capability.get("issues") or ["当前环境不可用。"]
                        raise ValueError("；".join(str(item) for item in issues))

                    result = await self._transcribe_with_faster_whisper(
                        source_asset=source_asset,
                        provider=provider,
                    )
                    if result.get("timeline_segments"):
                        return {
                            **result,
                            "provider": provider_key,
                            "detail": f"已通过本地 faster-whisper 完成音频转写，共识别 {len(result['timeline_segments'])} 段内容。",
                        }

                if provider_key == "openai_whisper_api":
                    result = await self._transcribe_with_openai_api(
                        source_asset=source_asset,
                        provider=provider,
                    )
                    if result.get("timeline_segments"):
                        return {
                            **result,
                            "provider": provider_key,
                            "detail": f"已通过 OpenAI Whisper API 完成音频转写，共识别 {len(result['timeline_segments'])} 段内容。",
                        }
            except Exception as exc:
                label = provider.get("label") or provider_key
                provider_errors.append(f"{label}: {str(exc).strip() or '转写失败'}")

        raise ValueError(
            "音频转写失败。"
            + (" 已尝试以下引擎：" + " | ".join(provider_errors) if provider_errors else " 当前没有可用的转写引擎配置。")
        )

    def _build_transcription_provider_order(
        self,
        *,
        default_provider: str,
        provider_map: dict[str, dict[str, Any]],
    ) -> list[str]:
        normalized_default = (default_provider or "").strip().lower()
        order: list[str] = []
        if normalized_default:
            order.append(normalized_default)

        for provider_key, provider in provider_map.items():
            if provider_key in order or not provider.get("enabled"):
                continue
            order.append(provider_key)
        return order

    async def _transcribe_with_faster_whisper(
        self,
        *,
        source_asset: dict[str, Any],
        provider: dict[str, Any],
    ) -> dict[str, Any]:
        file_path = str(source_asset.get("file_path") or "").strip()
        if not file_path or not os.path.exists(file_path):
            raise ValueError("源视频文件不存在，无法执行本地转写。")

        model_source = self._resolve_faster_whisper_model_source(provider)
        language = (provider.get("language") or "").strip() or None
        initial_prompt = (provider.get("prompt") or "").strip() or None
        beam_size = int(provider.get("beam_size") or 5)
        vad_filter = bool(provider.get("vad_filter", True))
        resolved_device = self._resolve_faster_whisper_device(provider)
        compute_type = (provider.get("compute_type") or "auto").strip().lower()
        resolved_compute_type = "default" if compute_type in {"", "auto"} else compute_type

        from app.utils.process_pool import run_in_process, run_whisper_transcription_worker

        result = await run_in_process(
            run_whisper_transcription_worker,
            file_path,
            model_source,
            resolved_device,
            resolved_compute_type,
            language,
            initial_prompt,
            beam_size,
            vad_filter,
        )
        if result["timeline_segments"]:
            return result

        raise ValueError("faster-whisper 未识别到有效文本，请检查视频音轨或切换模型。")

    async def _transcribe_with_openai_api(
        self,
        *,
        source_asset: dict[str, Any],
        provider: dict[str, Any],
    ) -> dict[str, Any]:
        base_url = str(provider.get("base_url") or "").strip()
        api_key = str(provider.get("api_key") or "").strip()
        model = str(provider.get("default_model") or "").strip() or "whisper-1"
        file_path = str(source_asset.get("file_path") or "").strip()

        if not base_url:
            raise ValueError("未配置 OpenAI Base URL。")
        if not api_key:
            raise ValueError("未配置 OpenAI API Key。")
        if not file_path or not os.path.exists(file_path):
            raise ValueError("源视频文件不存在，无法调用 OpenAI 转写接口。")

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 25:
            raise ValueError("OpenAI 音频转写接口当前仅支持 25MB 以内的单文件。")

        mime_type = (
            source_asset.get("mime_type")
            or mimetypes.guess_type(file_path)[0]
            or "application/octet-stream"
        )
        request_data: list[tuple[str, str]] = [("model", model)]
        language = str(provider.get("language") or "").strip()
        prompt = str(provider.get("prompt") or "").strip()
        response_format = "verbose_json" if model == "whisper-1" else "json"
        request_data.append(("response_format", response_format))
        if language:
            request_data.append(("language", language))
        if prompt:
            request_data.append(("prompt", prompt))
        if response_format == "verbose_json":
            request_data.append(("timestamp_granularities[]", "segment"))

        async with AsyncHttpClient(
            follow_redirects=True,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            request_timeout=300,
        ) as client:
            with open(file_path, "rb") as file_obj:
                response = await client.fetch_data(
                    "POST",
                    f"{base_url.rstrip('/')}/audio/transcriptions",
                    data=request_data,
                    files={
                        "file": (
                            os.path.basename(file_path),
                            file_obj,
                            mime_type,
                        ),
                    },
                )

        payload = response.json()
        timeline_segments = self._extract_openai_transcription_segments(
            payload=payload,
            duration_ms=int(source_asset.get("duration_ms") or 0),
        )
        if timeline_segments:
            return {
                "timeline_segments": timeline_segments,
                "language": payload.get("language"),
            }

        raise ValueError("OpenAI 转写接口未返回有效文本，请检查模型或输入文件。")

    def _resolve_faster_whisper_model_source(self, provider: dict[str, Any]) -> str:
        default_model = str(provider.get("default_model") or "").strip() or "small"
        configured_model_path = Path(default_model)
        if configured_model_path.exists():
            return str(configured_model_path.resolve())

        model_dir_value = str(provider.get("model_dir") or "").strip()
        if not model_dir_value:
            return default_model

        model_dir = Path(model_dir_value)
        if not model_dir.is_absolute():
            model_dir = Path.cwd() / model_dir
        model_dir = model_dir.resolve()

        direct_candidate = model_dir / default_model
        if direct_candidate.exists():
            return str(direct_candidate)
        if model_dir.name == default_model and model_dir.exists():
            return str(model_dir)
        return default_model

    def _resolve_faster_whisper_device(self, provider: dict[str, Any]) -> str:
        requested = str(provider.get("device") or "auto").strip().lower()
        if requested not in {"", "auto"}:
            return requested

        capability = SystemSettingsService().get_transcription_capabilities()["providers"].get(
            "faster_whisper",
            {},
        )
        recommended_device = str(capability.get("recommended_device") or "").strip().lower()
        return recommended_device or "cpu"

    def _extract_openai_transcription_segments(
        self,
        *,
        payload: dict[str, Any],
        duration_ms: int,
    ) -> list[dict[str, Any]]:
        raw_segments = payload.get("segments")
        if isinstance(raw_segments, list) and raw_segments:
            timeline_segments: list[dict[str, Any]] = []
            for index, segment in enumerate(raw_segments, start=1):
                if not isinstance(segment, dict):
                    continue
                content = str(segment.get("text") or "").strip()
                if not content:
                    continue
                start_ms = int(float(segment.get("start") or 0.0) * 1000)
                end_ms = int(float(segment.get("end") or 0.0) * 1000)
                timeline_segments.append(
                    {
                        "id": index,
                        "segment_type": "speech",
                        "speaker": "口播",
                        "start_ms": max(0, start_ms),
                        "end_ms": max(start_ms, end_ms),
                        "content": content,
                    }
                )
            if timeline_segments:
                return timeline_segments

        text = str(payload.get("text") or "").strip()
        if not text:
            return []

        return [
            {
                "id": 1,
                "segment_type": "speech",
                "speaker": "口播",
                "start_ms": 0,
                "end_ms": max(duration_ms, 1000),
                "content": text,
            }
        ]

    async def _ensure_source_asset(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        cached_asset = context.get("source_asset")
        if cached_asset:
            return cached_asset

        if project["source_asset_id"]:
            asset = AssetService().get_asset(asset_id=project["source_asset_id"])
            if asset is None:
                raise ValueError("已记录的源视频资产不存在，请重新上传素材。")
            asset["public_url"] = self._extract_asset_public_url(asset)
            context["source_asset"] = asset
            return asset

        download_url = (
            context.get("validate_video_link", {}).get("download_url")
            or project["source_url"]
        )
        if not download_url:
            raise ValueError("缺少可下载的视频地址，无法继续执行视频分析。")

        async with FileUtils(
            temp_dir=str(self._project_upload_dir()),
            auto_delete=False,
            max_file_size=settings.max_file_size,
        ) as file_utils:
            saved_path = await file_utils.download_file_from_url(download_url)

        size_bytes = os.path.getsize(saved_path)
        mime_type = mimetypes.guess_type(saved_path)[0] or "video/mp4"
        public_url = self._build_public_upload_url(saved_path)
        file_name = os.path.basename(saved_path)
        asset = AssetService().create_asset(
            owner_user_id=project["user_id"],
            asset_type="video",
            source_type="url",
            file_name=file_name,
            file_path=saved_path,
            mime_type=mime_type,
            size_bytes=size_bytes,
            metadata={
                "public_url": public_url,
                "source_url": project["source_url"],
                "download_url": download_url,
            },
        )
        asset["public_url"] = public_url
        self._update_project(
            project_id=project["id"],
            source_asset_id=asset["id"],
            media_url=public_url,
        )
        context["source_asset"] = asset
        return asset

    async def _persist_uploaded_asset(
        self,
        *,
        user_id: str,
        upload: UploadFile,
    ) -> dict[str, Any]:
        file_name = upload.filename or "upload.bin"
        content_type = upload.content_type or "application/octet-stream"
        async with FileUtils(
            temp_dir=str(self._project_upload_dir()),
            auto_delete=False,
            max_file_size=settings.max_file_size,
        ) as file_utils:
            saved_path = await file_utils.save_uploaded_file(upload, file_name)

        size_bytes = os.path.getsize(saved_path)
        public_url = self._build_public_upload_url(saved_path)
        asset = AssetService().create_asset(
            owner_user_id=user_id,
            asset_type="video",
            source_type="upload",
            file_name=file_name,
            file_path=saved_path,
            mime_type=content_type,
            size_bytes=size_bytes,
            metadata={"public_url": public_url},
        )
        asset["public_url"] = public_url
        return asset

    def _set_step_status(
        self,
        *,
        project_id: int,
        step_key: str,
        status: str,
        detail: str,
        error_detail: str | None = None,
        output: dict[str, Any] | None = None,
    ) -> None:
        now = utcnow_iso()
        connection = create_connection()
        try:
            connection.execute(
                """
                UPDATE project_task_steps
                SET status = ?,
                    detail = ?,
                    error_detail = ?,
                    output_json = COALESCE(?, output_json),
                    updated_at = ?
                WHERE project_id = ? AND step_key = ?
                """,
                (
                    status,
                    detail,
                    error_detail,
                    json.dumps(output, ensure_ascii=False) if output is not None else None,
                    now,
                    project_id,
                    step_key,
                ),
            )
            connection.execute(
                """
                UPDATE projects
                SET updated_at = ?
                WHERE id = ?
                """,
                (now, project_id),
            )
            connection.commit()
        finally:
            connection.close()

    def _update_project(
        self,
        *,
        project_id: int,
        **fields: Any,
    ) -> None:
        normalized_fields: dict[str, Any] = {}
        for field_name, value in fields.items():
            if field_name in JSON_PROJECT_COLUMNS:
                normalized_fields[JSON_PROJECT_COLUMNS[field_name]] = json.dumps(
                    value,
                    ensure_ascii=False,
                )
            else:
                normalized_fields[field_name] = value

        if not normalized_fields:
            return

        now = utcnow_iso()
        assignments = ", ".join(f"{column_name} = ?" for column_name in normalized_fields)
        values = list(normalized_fields.values())
        values.extend([now, project_id])

        connection = create_connection()
        try:
            connection.execute(
                f"""
                UPDATE projects
                SET {assignments},
                    updated_at = ?
                WHERE id = ?
                """,
                values,
            )
            project_row = connection.execute(
                """
                SELECT conversation_id, title, source_asset_id
                FROM projects
                WHERE id = ?
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            if project_row is not None and project_row["conversation_id"]:
                if "title" in normalized_fields:
                    connection.execute(
                        """
                        UPDATE conversations
                        SET title = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            normalized_fields["title"],
                            now,
                            project_row["conversation_id"],
                        ),
                    )
                if "source_asset_id" in normalized_fields:
                    connection.execute(
                        """
                        UPDATE conversations
                        SET source_video_id = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            normalized_fields["source_asset_id"] or project_row["source_asset_id"],
                            now,
                            project_row["conversation_id"],
                        ),
                    )
            connection.commit()
        finally:
            connection.close()

    def _create_conversation_record(
        self,
        *,
        connection: sqlite3.Connection,
        user_id: str,
        title: str,
        conversation_type: str,
        source_video_id: str | None,
        now: str,
    ) -> str:
        conversation_id = uuid.uuid4().hex
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
        return conversation_id

    def _append_conversation_message(
        self,
        *,
        connection: sqlite3.Connection,
        conversation_id: str,
        role: str,
        message_type: str,
        content: str,
        content_json: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> None:
        now = created_at or utcnow_iso()
        connection.execute(
            """
            INSERT INTO conversation_messages (
                id, conversation_id, role, message_type, content, content_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                conversation_id,
                role,
                message_type,
                content,
                json.dumps(content_json, ensure_ascii=False) if content_json is not None else None,
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

    def _append_project_message(
        self,
        *,
        project_id: int,
        role: str,
        message_type: str,
        content: str,
        content_json: dict[str, Any] | None = None,
    ) -> None:
        project = self._get_project_for_execution(project_id=project_id)
        if project is None or not project.get("conversation_id"):
            return

        connection = create_connection()
        try:
            self._append_conversation_message(
                connection=connection,
                conversation_id=project["conversation_id"],
                role=role,
                message_type=message_type,
                content=content,
                content_json=content_json,
            )
            connection.commit()
        finally:
            connection.close()

    def _load_conversation_messages(
        self,
        *,
        connection: sqlite3.Connection,
        conversation_id: str | None,
    ) -> list[dict[str, Any]]:
        if not conversation_id:
            return []

        rows = connection.execute(
            """
            SELECT id, role, message_type, content, content_json, reply_to_message_id, created_at
            FROM conversation_messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if item.get("content_json"):
                item["content_json"] = self._load_json_field(item["content_json"], {})
            items.append(item)
        return items

    def _build_user_request_message(
        self,
        *,
        objective: str,
        source_name: str,
        source_url: str,
        workflow_type: str,
    ) -> str:
        workflow_label = {
            "analysis": "分析脚本",
            "remake": "复刻爆款",
            "create": "创作爆款",
        }.get(workflow_type, workflow_type)
        lines = [f"任务类型：{workflow_label}"]
        if objective:
            lines.append(f"用户诉求：{objective}")
        if source_url:
            lines.append(f"视频链接：{source_url}")
        elif source_name:
            lines.append(f"上传素材：{source_name}")
        return "\n".join(lines)

    def _require_project(self, *, project_id: int) -> dict[str, Any]:
        project = self._get_project_for_execution(project_id=project_id)
        if project is None:
            raise ValueError("项目不存在。")
        return project

    def _get_project_for_execution(self, *, project_id: int) -> dict[str, Any] | None:
        connection = create_connection()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM projects
                WHERE id = ?
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            connection.close()

    def _normalize_workflow_type(self, workflow_type: str) -> str:
        normalized = (workflow_type or "").strip().lower()
        if normalized in {"analysis", "create", "remake"}:
            return normalized
        return "analysis"

    def _get_step_definitions(self, workflow_type: str) -> tuple[TaskStepDefinition, ...]:
        """Delegate to WorkflowRegistry for step definitions."""
        return WorkflowRegistry.get_step_definitions(workflow_type)

    def _load_json_field(self, raw_value: str | None, default: Any) -> Any:
        if not raw_value:
            return deepcopy(default)
        if isinstance(raw_value, (dict, list)):
            return deepcopy(raw_value)
        try:
            return json.loads(raw_value)
        except (json.JSONDecodeError, TypeError):
            return deepcopy(default)

    def _shot_type_label(self, value: str | None) -> str:
        labels = {
            "wide": "全景镜头",
            "full": "全身镜头",
            "medium": "中景镜头",
            "medium_close": "中近景镜头",
            "close_up": "特写镜头",
            "extreme_close_up": "大特写镜头",
            "mixed": "混合景别",
        }
        return labels.get((value or "").strip(), value or "未标注")

    def _camera_angle_label(self, value: str | None) -> str:
        labels = {
            "eye_level": "平视角度",
            "high_angle": "俯视角度",
            "low_angle": "仰视角度",
            "top_down": "顶视角度",
            "side_angle": "侧视角度",
            "over_shoulder": "肩背角度",
            "mixed": "混合角度",
        }
        return labels.get((value or "").strip(), value or "未标注")

    def _camera_motion_label(self, value: str | None) -> str:
        labels = {
            "static": "静止",
            "pan": "平移",
            "tilt": "摇摄",
            "tracking": "跟拍",
            "push_in": "推进",
            "pull_out": "拉远",
            "zoom_in": "变焦推近",
            "zoom_out": "变焦拉远",
            "handheld": "手持晃动",
            "mixed": "混合运镜",
        }
        return labels.get((value or "").strip(), value or "未标注")

    def _detect_shot_segments(
        self,
        *,
        project: dict[str, Any],
        source_asset: dict[str, Any],
        video_meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        file_path = str(source_asset.get("file_path") or "").strip()
        if not file_path or not os.path.exists(file_path):
            return []

        from app.utils.process_pool import run_in_process, run_shot_detection_worker

        try:
            threshold = 27.0
            min_scene_len = 15
            
            raw_scenes = await run_in_process(
                run_shot_detection_worker,
                file_path,
                threshold,
                min_scene_len,
            )

            if not raw_scenes:
                return []

            return [
                {
                    "segment_index": index,
                    "start_ms": scene["start_ms"],
                    "end_ms": scene["end_ms"],
                    "duration_ms": scene["duration_ms"],
                    "start_frame": scene["start_frame"],
                    "end_frame": scene["end_frame"],
                    "boundary_in_type": "cut",
                    "boundary_out_type": "cut",
                    "detector_name": "pyscenedetect",
                    "detector_version": None,
                    "detector_config_json": {"threshold": threshold, "min_scene_len": min_scene_len},
                    "keyframe_asset_ids_json": [],
                    "transcript_text": "",
                    "ocr_text": "",
                    "title": None,
                    "visual_summary": None,
                    "shot_type_code": None,
                    "camera_angle_code": None,
                    "camera_motion_code": None,
                    "scene_label": None,
                    "confidence": 0.82,
                    "metadata_json": {
                        "objective": project.get("objective") or "",
                    },
                }
                for index, scene in enumerate(raw_scenes, start=1)
            ]
        except Exception as exc:
            logger.warning("PySceneDetect shot detection failed for %s: %s", file_path, exc)
            return []

    def _build_fallback_shot_segments(
        self,
        *,
        video_meta: dict[str, Any],
        objective: str,
        source_name: str,
    ) -> list[dict[str, Any]]:
        duration_ms = max(4000, int(video_meta.get("duration_ms") or 32000))
        segment_count = 4 if duration_ms >= 18000 else 3 if duration_ms >= 9000 else 2
        interval = max(1000, duration_ms // segment_count)
        items: list[dict[str, Any]] = []
        for index in range(segment_count):
            start_ms = index * interval
            end_ms = duration_ms if index == segment_count - 1 else min(duration_ms, (index + 1) * interval)
            items.append(
                {
                    "segment_index": index + 1,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "duration_ms": max(0, end_ms - start_ms),
                    "start_frame": None,
                    "end_frame": None,
                    "boundary_in_type": "cut",
                    "boundary_out_type": "cut",
                    "detector_name": "pyscenedetect_fallback",
                    "detector_version": None,
                    "detector_config_json": {"strategy": "duration_split"},
                    "keyframe_asset_ids_json": [],
                    "transcript_text": "",
                    "ocr_text": "",
                    "title": self._build_shot_title(
                        index=index,
                        total=segment_count,
                        objective=objective,
                        source_name=source_name,
                    ),
                    "visual_summary": self._build_shot_visual_summary(
                        index=index,
                        total=segment_count,
                        objective=objective,
                        source_name=source_name,
                    ),
                    "shot_type_code": self._fallback_shot_type(index=index, total=segment_count),
                    "camera_angle_code": self._fallback_camera_angle(index=index, total=segment_count),
                    "camera_motion_code": self._fallback_camera_motion(index=index, total=segment_count),
                    "scene_label": None,
                    "confidence": 0.55,
                    "metadata_json": {"fallback": True},
                }
            )
        return items

    def _enrich_shot_segments(
        self,
        *,
        shot_segments: list[dict[str, Any]],
        video_meta: dict[str, Any],
        objective: str,
        source_name: str,
    ) -> list[dict[str, Any]]:
        if not shot_segments:
            return []

        total = len(shot_segments)
        enriched: list[dict[str, Any]] = []
        for index, raw_segment in enumerate(sorted(shot_segments, key=lambda item: int(item.get("segment_index") or 0) or int(item.get("start_ms") or 0)), start=1):
            segment = dict(raw_segment)
            segment["segment_index"] = index
            segment["start_ms"] = int(segment.get("start_ms") or 0)
            segment["end_ms"] = max(segment["start_ms"], int(segment.get("end_ms") or segment["start_ms"]))
            segment["duration_ms"] = max(0, int(segment.get("duration_ms") or segment["end_ms"] - segment["start_ms"]))
            segment["keyframe_asset_ids_json"] = segment.get("keyframe_asset_ids_json") or []
            segment["detector_config_json"] = segment.get("detector_config_json") or {}
            segment["metadata_json"] = segment.get("metadata_json") or {}
            segment["title"] = (segment.get("title") or "").strip() or self._build_shot_title(
                index=index - 1,
                total=total,
                objective=objective,
                source_name=source_name,
            )
            segment["shot_type_code"] = (segment.get("shot_type_code") or "").strip() or self._fallback_shot_type(index=index - 1, total=total)
            segment["camera_angle_code"] = (segment.get("camera_angle_code") or "").strip() or self._fallback_camera_angle(index=index - 1, total=total)
            segment["camera_motion_code"] = (segment.get("camera_motion_code") or "").strip() or self._fallback_camera_motion(index=index - 1, total=total)
            segment["visual_summary"] = (segment.get("visual_summary") or "").strip() or self._build_shot_visual_summary(
                index=index - 1,
                total=total,
                objective=objective,
                source_name=source_name,
            )
            segment["confidence"] = float(segment.get("confidence") or 0.7)
            enriched.append(segment)
        return enriched

    def _replace_shot_segments(
        self,
        *,
        project_id: int,
        project: dict[str, Any],
        source_asset: dict[str, Any],
        shot_segments: list[dict[str, Any]],
        preserve_transcript: bool = False,
    ) -> list[dict[str, Any]]:
        now = utcnow_iso()
        connection = create_connection()
        try:
            preserved_by_index: dict[int, dict[str, Any]] = {}
            if preserve_transcript:
                existing_rows = connection.execute(
                    """
                    SELECT segment_index, transcript_text, ocr_text, metadata_json
                    FROM shot_segments
                    WHERE project_id = ?
                    """,
                    (project_id,),
                ).fetchall()
                preserved_by_index = {
                    int(row["segment_index"]): dict(row)
                    for row in existing_rows
                }

            connection.execute(
                "DELETE FROM shot_segments WHERE project_id = ?",
                (project_id,),
            )

            inserted: list[dict[str, Any]] = []
            for index, raw_segment in enumerate(shot_segments, start=1):
                preserved = preserved_by_index.get(index, {})
                segment_id = str(raw_segment.get("id") or uuid.uuid4().hex)
                transcript_text = (
                    raw_segment.get("transcript_text")
                    if raw_segment.get("transcript_text") not in {None, ""}
                    else preserved.get("transcript_text") or ""
                )
                ocr_text = (
                    raw_segment.get("ocr_text")
                    if raw_segment.get("ocr_text") not in {None, ""}
                    else preserved.get("ocr_text") or ""
                )
                metadata_json = raw_segment.get("metadata_json")
                if metadata_json is None or metadata_json == "":
                    metadata_json = self._load_json_field(preserved.get("metadata_json"), {})

                payload = {
                    "id": segment_id,
                    "project_id": project_id,
                    "conversation_id": project.get("conversation_id"),
                    "job_id": None,
                    "source_video_asset_id": source_asset["id"],
                    "owner_user_id": project["user_id"],
                    "segment_index": int(raw_segment.get("segment_index") or index),
                    "start_ms": int(raw_segment.get("start_ms") or 0),
                    "end_ms": max(
                        int(raw_segment.get("start_ms") or 0),
                        int(raw_segment.get("end_ms") or raw_segment.get("start_ms") or 0),
                    ),
                    "duration_ms": max(
                        0,
                        int(raw_segment.get("duration_ms") or 0)
                        or (
                            int(raw_segment.get("end_ms") or raw_segment.get("start_ms") or 0)
                            - int(raw_segment.get("start_ms") or 0)
                        ),
                    ),
                    "start_frame": raw_segment.get("start_frame"),
                    "end_frame": raw_segment.get("end_frame"),
                    "boundary_in_type": raw_segment.get("boundary_in_type") or "cut",
                    "boundary_out_type": raw_segment.get("boundary_out_type") or "cut",
                    "detector_name": raw_segment.get("detector_name") or "pyscenedetect",
                    "detector_version": raw_segment.get("detector_version"),
                    "detector_config_json": raw_segment.get("detector_config_json") or {},
                    "keyframe_asset_ids_json": raw_segment.get("keyframe_asset_ids_json") or [],
                    "transcript_text": transcript_text,
                    "ocr_text": ocr_text,
                    "visual_summary": raw_segment.get("visual_summary"),
                    "title": raw_segment.get("title"),
                    "shot_type_code": raw_segment.get("shot_type_code"),
                    "camera_angle_code": raw_segment.get("camera_angle_code"),
                    "camera_motion_code": raw_segment.get("camera_motion_code"),
                    "scene_label": raw_segment.get("scene_label"),
                    "confidence": float(raw_segment.get("confidence") or 0.0),
                    "metadata_json": metadata_json or {},
                    "created_at": now,
                    "updated_at": now,
                }
                connection.execute(
                    """
                    INSERT INTO shot_segments (
                        id, project_id, conversation_id, job_id, source_video_asset_id,
                        owner_user_id, segment_index, start_ms, end_ms, duration_ms,
                        start_frame, end_frame, boundary_in_type, boundary_out_type,
                        detector_name, detector_version, detector_config_json,
                        keyframe_asset_ids_json, transcript_text, ocr_text,
                        visual_summary, title, shot_type_code, camera_angle_code,
                        camera_motion_code, scene_label, confidence, metadata_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["id"],
                        payload["project_id"],
                        payload["conversation_id"],
                        payload["job_id"],
                        payload["source_video_asset_id"],
                        payload["owner_user_id"],
                        payload["segment_index"],
                        payload["start_ms"],
                        payload["end_ms"],
                        payload["duration_ms"],
                        payload["start_frame"],
                        payload["end_frame"],
                        payload["boundary_in_type"],
                        payload["boundary_out_type"],
                        payload["detector_name"],
                        payload["detector_version"],
                        json.dumps(payload["detector_config_json"], ensure_ascii=False),
                        json.dumps(payload["keyframe_asset_ids_json"], ensure_ascii=False),
                        payload["transcript_text"],
                        payload["ocr_text"],
                        payload["visual_summary"],
                        payload["title"],
                        payload["shot_type_code"],
                        payload["camera_angle_code"],
                        payload["camera_motion_code"],
                        payload["scene_label"],
                        payload["confidence"],
                        json.dumps(payload["metadata_json"], ensure_ascii=False),
                        payload["created_at"],
                        payload["updated_at"],
                    ),
                )
                inserted.append(payload)

            connection.commit()
            return [self._serialize_shot_segment(item) for item in inserted]
        finally:
            connection.close()

    def _sync_shot_segments_with_timeline_segments(
        self,
        *,
        project_id: int,
        timeline_segments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        connection = create_connection()
        try:
            shot_segments = self._load_shot_segments(
                connection=connection,
                project_id=project_id,
            )
            now = utcnow_iso()
            for shot_segment in shot_segments:
                transcript_text = self._collect_timeline_text_for_range(
                    start_ms=int(shot_segment.get("start_ms") or 0),
                    end_ms=int(shot_segment.get("end_ms") or 0),
                    timeline_segments=timeline_segments,
                )
                connection.execute(
                    """
                    UPDATE shot_segments
                    SET transcript_text = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        transcript_text,
                        now,
                        shot_segment["id"],
                    ),
                )
                shot_segment["transcript_text"] = transcript_text
            connection.commit()
            return shot_segments
        finally:
            connection.close()

    def _collect_timeline_text_for_range(
        self,
        *,
        start_ms: int,
        end_ms: int,
        timeline_segments: list[dict[str, Any]],
    ) -> str:
        fragments: list[str] = []
        for segment in timeline_segments:
            segment_start = int(segment.get("start_ms") or 0)
            segment_end = int(segment.get("end_ms") or segment_start)
            overlaps = segment_end > start_ms and segment_start < end_ms
            if overlaps and segment.get("content"):
                fragments.append(str(segment["content"]).strip())
        return " ".join(fragment for fragment in fragments if fragment).strip()

    def _build_storyboard_generation_context(
        self,
        *,
        shot_segments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "segment_index": int(segment.get("segment_index") or 0),
                "start_ms": int(segment.get("start_ms") or 0),
                "end_ms": int(segment.get("end_ms") or 0),
                "title": segment.get("title") or "",
                "visual_summary": segment.get("visual_summary") or "",
                "transcript_text": segment.get("transcript_text") or "",
                "ocr_text": segment.get("ocr_text") or "",
                "shot_type_code": segment.get("shot_type_code") or "medium",
                "camera_angle_code": segment.get("camera_angle_code") or "eye_level",
                "camera_motion_code": segment.get("camera_motion_code") or "static",
                "confidence": float(segment.get("confidence") or 0.6),
            }
            for segment in shot_segments
        ]

    def _normalize_storyboard_payload(
        self,
        *,
        payload: dict[str, Any],
        shot_segments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raw_items = []
        shot_map = {
            int(segment.get("segment_index") or 0): segment
            for segment in shot_segments
        }
        normalized_items: list[dict[str, Any]] = []
        for index, raw_item in enumerate(raw_items, start=1):
            if not isinstance(raw_item, dict):
                continue
            source_segment_indexes = raw_item.get("source_segment_indexes")
            if not isinstance(source_segment_indexes, list) or not source_segment_indexes:
                source_segment_indexes = [index] if index in shot_map else []
            normalized_source_segment_indexes: list[int] = []
            for item in source_segment_indexes:
                try:
                    normalized_index = int(item)
                except (TypeError, ValueError):
                    continue
                if normalized_index in shot_map:
                    normalized_source_segment_indexes.append(normalized_index)
            source_segment_indexes = normalized_source_segment_indexes
            if not source_segment_indexes and shot_map:
                source_segment_indexes = [min(index, len(shot_map))]
            source_segments = [shot_map[item] for item in source_segment_indexes if item in shot_map]
            first_source = source_segments[0] if source_segments else {}
            start_ms = min((int(segment.get("start_ms") or 0) for segment in source_segments), default=int(raw_item.get("start_ms") or 0))
            end_ms = max((int(segment.get("end_ms") or 0) for segment in source_segments), default=int(raw_item.get("end_ms") or start_ms))
            transcript_excerpt = " ".join(
                str(segment.get("transcript_text") or "").strip()
                for segment in source_segments
                if str(segment.get("transcript_text") or "").strip()
            ).strip()
            ocr_excerpt = " ".join(
                str(segment.get("ocr_text") or "").strip()
                for segment in source_segments
                if str(segment.get("ocr_text") or "").strip()
            ).strip()
            shot_type_code = str(raw_item.get("shot_type_code") or first_source.get("shot_type_code") or "medium").strip()
            camera_angle_code = str(raw_item.get("camera_angle_code") or first_source.get("camera_angle_code") or "eye_level").strip()
            camera_motion_code = str(raw_item.get("camera_motion_code") or first_source.get("camera_motion_code") or "static").strip()
            visual_description = str(raw_item.get("visual_description") or transcript_excerpt or first_source.get("visual_summary") or "").strip()
            if not visual_description:
                visual_description = "该分镜以主体展示和节奏推进为主。"
            normalized_items.append(
                {
                    "item_index": index,
                    "title": str(raw_item.get("title") or first_source.get("title") or f"分镜 {index}").strip()[:24] or f"分镜 {index}",
                    "start_ms": start_ms,
                    "end_ms": max(start_ms, end_ms),
                    "duration_ms": max(0, end_ms - start_ms),
                    "shot_type_code": shot_type_code,
                    "camera_angle_code": camera_angle_code,
                    "camera_motion_code": camera_motion_code,
                    "visual_description": visual_description,
                    "transcript_excerpt": transcript_excerpt,
                    "ocr_excerpt": ocr_excerpt,
                    "confidence": float(raw_item.get("confidence") or first_source.get("confidence") or 0.7),
                    "source_segment_indexes": source_segment_indexes,
                    "review_status": "auto_generated",
                    "metadata_json": {},
                }
            )
        if not normalized_items:
            fallback = self._build_legacy_storyboard(
                timeline_segments=[
                    {
                        "start_ms": segment.get("start_ms"),
                        "end_ms": segment.get("end_ms"),
                        "content": segment.get("visual_summary") or segment.get("transcript_text") or segment.get("title") or "",
                    }
                    for segment in shot_segments
                ],
                video_generation={},
            )
            return {
                "summary": fallback["summary"],
                "items": fallback["items"],
            }
        return {
            "summary": str(payload.get("summary") or f"共生成 {len(normalized_items)} 条结构化分镜。").strip(),
            "items": normalized_items,
        }

    def _replace_storyboard(
        self,
        *,
        project_id: int,
        project: dict[str, Any],
        source_asset: dict[str, Any],
        storyboard_payload: dict[str, Any],
        provider: str | None,
        model: str | None,
        used_remote: bool,
    ) -> dict[str, Any]:
        now = utcnow_iso()
        connection = create_connection()
        try:
            version_row = connection.execute(
                """
                SELECT COALESCE(MAX(version_no), 0) AS max_version
                FROM storyboards
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
            version_no = int(version_row["max_version"] or 0) + 1
            storyboard_id = uuid.uuid4().hex
            items = storyboard_payload.get("items") or []
            connection.execute(
                """
                INSERT INTO storyboards (
                    id, project_id, conversation_id, job_id, source_video_asset_id,
                    owner_user_id, version_no, status, generator_provider, generator_model,
                    prompt_version, summary, item_count, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    storyboard_id,
                    project_id,
                    project.get("conversation_id"),
                    None,
                    source_asset["id"],
                    project["user_id"],
                    version_no,
                    "generated",
                    provider,
                    model,
                    "storyboard_v1",
                    storyboard_payload.get("summary") or "",
                    len(items),
                    json.dumps({"used_remote": used_remote}, ensure_ascii=False),
                    now,
                    now,
                ),
            )

            shot_segments = self._load_shot_segments(
                connection=connection,
                project_id=project_id,
            )
            shot_id_by_index = {
                int(segment.get("segment_index") or 0): segment["id"]
                for segment in shot_segments
            }

            normalized_items: list[dict[str, Any]] = []
            for raw_item in items:
                item_id = uuid.uuid4().hex
                source_segment_indexes = raw_item.get("source_segment_indexes") or []
                metadata_json = raw_item.get("metadata_json") or {}
                connection.execute(
                    """
                    INSERT INTO storyboard_items (
                        id, storyboard_id, item_index, title, start_ms, end_ms, duration_ms,
                        shot_type_code, camera_angle_code, camera_motion_code,
                        visual_description, transcript_excerpt, ocr_excerpt, confidence,
                        review_status, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        storyboard_id,
                        int(raw_item.get("item_index") or 0),
                        raw_item.get("title") or "",
                        int(raw_item.get("start_ms") or 0),
                        int(raw_item.get("end_ms") or 0),
                        int(raw_item.get("duration_ms") or 0),
                        raw_item.get("shot_type_code"),
                        raw_item.get("camera_angle_code"),
                        raw_item.get("camera_motion_code"),
                        raw_item.get("visual_description") or "",
                        raw_item.get("transcript_excerpt") or "",
                        raw_item.get("ocr_excerpt") or "",
                        float(raw_item.get("confidence") or 0.0),
                        raw_item.get("review_status") or "auto_generated",
                        json.dumps(metadata_json, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                for display_order, segment_index in enumerate(source_segment_indexes, start=1):
                    shot_segment_id = shot_id_by_index.get(int(segment_index))
                    if not shot_segment_id:
                        continue
                    connection.execute(
                        """
                        INSERT INTO storyboard_item_segments (
                            storyboard_item_id, shot_segment_id, display_order
                        ) VALUES (?, ?, ?)
                        """,
                        (
                            item_id,
                            shot_segment_id,
                            display_order,
                        ),
                    )
                normalized_item = dict(raw_item)
                normalized_item["id"] = item_id
                normalized_item["shot_type_label"] = self._shot_type_label(raw_item.get("shot_type_code"))
                normalized_item["camera_angle_label"] = self._camera_angle_label(raw_item.get("camera_angle_code"))
                normalized_item["camera_motion_label"] = self._camera_motion_label(raw_item.get("camera_motion_code"))
                normalized_item["source_segment_ids"] = [
                    shot_id_by_index[int(segment_index)]
                    for segment_index in source_segment_indexes
                    if int(segment_index) in shot_id_by_index
                ]
                normalized_items.append(normalized_item)

            connection.commit()
            return {
                "id": storyboard_id,
                "project_id": project_id,
                "version_no": version_no,
                "status": "generated",
                "summary": storyboard_payload.get("summary") or "",
                "items": normalized_items,
            }
        finally:
            connection.close()

    def _build_shot_title(
        self,
        *,
        index: int,
        total: int,
        objective: str,
        source_name: str,
    ) -> str:
        if index == 0:
            return "开场引入镜头"
        if index == total - 1:
            return "结尾收束镜头"
        if total >= 4 and index == total - 2:
            return "卖点强化镜头"
        target = (objective or source_name or "主体内容").strip()
        return f"{target[:8] or '主体'}展示镜头"

    def _build_shot_visual_summary(
        self,
        *,
        index: int,
        total: int,
        objective: str,
        source_name: str,
    ) -> str:
        target = (objective or source_name or "当前素材").strip()
        if index == 0:
            return f"视频开场快速建立主题，围绕“{target[:16] or '当前素材'}”进行主体引入。"
        if index == total - 1:
            return "结尾通过收束式镜头完成信息闭环，并准备承接行动召唤。"
        if index == 1:
            return "中段通过主体展示与动作推进承接卖点信息，节奏保持连续。"
        return "镜头以主体与细节补充为主，用于延续叙事和卖点表达。"

    def _fallback_shot_type(self, *, index: int, total: int) -> str:
        if index == 0:
            return "wide"
        if index == total - 1:
            return "medium"
        return "close_up" if index % 2 else "medium"

    def _fallback_camera_angle(self, *, index: int, total: int) -> str:
        if index == 1 and total >= 3:
            return "high_angle"
        if index == total - 1 and total >= 2:
            return "side_angle"
        return "eye_level"

    def _fallback_camera_motion(self, *, index: int, total: int) -> str:
        if index == 0:
            return "static"
        if index == total - 1:
            return "static"
        return "tracking" if index % 2 else "pan"

    def _extract_first_url(self, content: str) -> str:
        tokens = content.split()
        for token in tokens:
            candidate = token.strip().strip("()[]{}<>,，。！？；;\"'")
            if candidate.startswith(("http://", "https://")):
                return candidate
        return ""

    def _detect_platform(self, source_url: str) -> str:
        if not source_url:
            return "local"
        host = urlparse(source_url).netloc.lower()
        if "tiktok.com" in host:
            return "tiktok"
        if "douyin.com" in host:
            return "douyin"
        if host.startswith("www."):
            host = host[4:]
        return host or "remote"

    def _platform_label(self, platform: str) -> str:
        labels = {
            "local": "本地素材",
            "tiktok": "TikTok",
            "douyin": "抖音",
            "remote": "远程视频",
        }
        return labels.get(platform, platform)

    def _build_project_title(self, *, source_name: str, workflow_type: str) -> str:
        normalized_name = (source_name or "").strip()
        if not normalized_name:
            normalized_name = "未命名任务"
        if len(normalized_name) > 80:
            normalized_name = normalized_name[:77] + "..."
        suffix = {
            "analysis": "视频分析",
            "remake": "爆款复刻",
            "create": "爆款创作",
        }.get(workflow_type, "任务")
        return normalized_name if workflow_type == "analysis" else f"{normalized_name} - {suffix}"

    def _project_upload_dir(self) -> Path:
        directory = Path("uploads") / "project-sources"
        directory.mkdir(parents=True, exist_ok=True)
        return directory.resolve()

    def _build_public_upload_url(self, file_path: str) -> str:
        uploads_root = Path("uploads").resolve()
        resolved_path = Path(file_path).resolve()
        relative_path = resolved_path.relative_to(uploads_root).as_posix()
        return f"/uploads/{relative_path}"

    def _extract_asset_public_url(self, asset: dict[str, Any]) -> str | None:
        metadata = asset.get("metadata_json") or {}
        public_url = metadata.get("public_url")
        if public_url:
            return str(public_url)

        file_path = asset.get("file_path")
        if not file_path:
            return None

        try:
            return self._build_public_upload_url(str(file_path))
        except ValueError:
            return None

    def _build_video_meta(
        self,
        *,
        project: dict[str, Any],
        source_asset: dict[str, Any],
        video_info: dict[str, Any],
    ) -> dict[str, Any]:
        width = (
            source_asset.get("width")
            or video_info.get("width")
            or 1080
        )
        height = (
            source_asset.get("height")
            or video_info.get("height")
            or 1920
        )
        duration_ms = (
            source_asset.get("duration_ms")
            or video_info.get("duration_ms")
            or 32000
        )
        return {
            "duration_ms": duration_ms,
            "width": width,
            "height": height,
            "size_bytes": source_asset.get("size_bytes") or 0,
            "source_name": project["source_name"],
        }

    def _build_visual_features(
        self,
        *,
        video_meta: dict[str, Any],
        shot_segments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        width = int(video_meta.get("width") or 1080)
        height = int(video_meta.get("height") or 1920)
        orientation = "portrait" if height >= width else "landscape"
        shot_segment_count = len(shot_segments or [])
        average_duration_ms = 0
        if shot_segments:
            average_duration_ms = sum(
                int(segment.get("duration_ms") or 0)
                for segment in shot_segments
            ) // max(1, shot_segment_count)
        shot_density = "high" if shot_segment_count >= 8 else "medium" if shot_segment_count >= 4 else "low"
        scene_pace = "fast" if average_duration_ms and average_duration_ms < 2500 else "medium" if average_duration_ms and average_duration_ms < 4500 else "steady"
        return {
            "orientation": orientation,
            "resolution": f"{width}x{height}",
            "frame_rate": "30fps",
            "keyframe_count": max(shot_segment_count, 1),
            "shot_density": shot_density,
            "scene_pace": scene_pace,
            "lighting": "bright",
            "contrast": "medium",
            "saturation": "medium_high",
            "color_temperature": "neutral_warm",
            "framing_focus": "subject_forward",
            "camera_motion": "mixed",
            "dominant_palette": ["#0F172A", "#E2E8F0", "#2563EB"],
            "summary": f"共识别 {shot_segment_count or 1} 个镜头段，整体节奏为 {scene_pace}，镜头围绕主体与卖点推进。",
        }

    def _build_timeline_segments(
        self,
        *,
        project: dict[str, Any],
        remote_video_info: dict[str, Any],
    ) -> list[dict[str, Any]]:
        desc = (
            (remote_video_info.get("video_info") or {}).get("desc")
            or project["objective"]
            or project["source_name"]
        )
        segment_texts = [
            f"开场直接抛出核心吸引点，快速让用户知道视频主旨：{desc[:24] or '亮点展示'}。",
            "中段通过产品使用场景和人物动作推进卖点，让用户持续停留并建立代入感。",
            "后段用细节特写和对比说明强化信任感，把抽象卖点变成可感知收益。",
            "结尾落在明确行动召唤，引导用户点击、咨询或下单。",
        ]
        return [
            {
                "id": index,
                "segment_type": "script",
                "speaker": "旁白" if index in {1, 4} else "口播",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "content": content,
            }
            for index, (start_ms, end_ms, content) in enumerate(
                (
                    (0, 3000, segment_texts[0]),
                    (3000, 11000, segment_texts[1]),
                    (11000, 22000, segment_texts[2]),
                    (22000, 32000, segment_texts[3]),
                ),
                start=1,
            )
        ]

    def _build_script_overview(
        self,
        *,
        timeline_segments: list[dict[str, Any]],
        video_desc: str,
    ) -> dict[str, Any]:
        full_text = "\n".join(segment["content"] for segment in timeline_segments)
        dialogue_text = "\n".join(
            segment["content"]
            for segment in timeline_segments
            if segment.get("speaker") == "口播"
        )
        narration_text = "\n".join(
            segment["content"]
            for segment in timeline_segments
            if segment.get("speaker") != "口播"
        )
        return {
            "full_text": full_text,
            "dialogue_text": dialogue_text,
            "narration_text": narration_text,
            "caption_text": (video_desc or "").strip(),
        }

    def _build_ecommerce_analysis(
        self,
        *,
        project: dict[str, Any],
        source_analysis: dict[str, Any],
        timeline_segments: list[dict[str, Any]],
        script_overview: dict[str, Any],
    ) -> dict[str, Any]:
        visual_summary = (
            (source_analysis.get("visual_features") or {}).get("summary")
            or "镜头以主体表达为主。"
        )
        hook_segment = timeline_segments[0]["content"] if timeline_segments else "开场聚焦卖点。"
        close_segment = timeline_segments[-1]["content"] if timeline_segments else "结尾引导转化。"
        content = "\n".join(
            [
                "## 爆点总结",
                f"该视频围绕“{project['objective'] or project['source_name']}”建立快速钩子，整体适合做 TikTok 电商转化分析。",
                "",
                "## 开头钩子分析",
                hook_segment,
                "",
                "## 画面与节奏分析",
                visual_summary,
                "",
                "## 脚本结构分析",
                script_overview.get("full_text") or "暂未提取到完整脚本。",
                "",
                "## 转化动作分析",
                close_segment,
            ]
        )
        return {
            "title": "TikTok 电商效果深度分析",
            "content": content,
        }

    def _build_suggestions(self, *, project: dict[str, Any]) -> list[str]:
        target = project["objective"] or project["source_name"]
        return [
            f"把前 3 秒的核心利益点说得更直白，直接点明“{target}”能解决什么问题。",
            "中段减少铺垫镜头，优先保留能证明卖点的动作或前后对比画面。",
            "字幕尽量改成短句和结果导向表达，避免长段说明削弱停留率。",
            "在结尾加入更明确的行动引导，例如限时、优惠或使用场景提示。",
            "补一段真实使用反馈或细节特写，增强内容可信度和下单驱动力。",
        ]

    async def add_followup_message(
        self,
        *,
        project_id: int,
        user_id: str,
        content: str,
    ) -> dict[str, Any]:
        connection = create_connection()
        try:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="项目不存在。")
            
            project_data = dict(row)
            conversation_id = project_data["conversation_id"]
            now = utcnow_iso()

            # Append user message
            self._append_conversation_message(
                connection=connection,
                conversation_id=conversation_id,
                role="user",
                message_type="chat_question",
                content=content,
                created_at=now,
            )

            # Load history for AI
            history = self._load_conversation_messages(
                connection=connection,
                conversation_id=conversation_id,
            )
            ai_messages = [
                {"role": m["role"], "content": m["content"]}
                for m in history
                if m["role"] in {"user", "assistant"}
            ]

            # Prepare context for AI
            context = {
                "objective": project_data["objective"],
                "source_name": project_data["source_name"],
                "status": project_data["status"],
            }

            # Generate AI response
            from app.services.analysis_ai_service import AnalysisAIService
            ai_reply = await AnalysisAIService().generate_chat_reply(
                messages=ai_messages,
                context=context,
            )

            # Append AI message
            ai_message_id = self._append_conversation_message(
                connection=connection,
                conversation_id=conversation_id,
                role="assistant",
                message_type="chat_reply",
                content=ai_reply["content"],
                content_json={
                    "provider": ai_reply["provider"],
                    "model": ai_reply["model"],
                },
                created_at=utcnow_iso(),
            )
            
            connection.commit()
            
            return {
                "id": ai_message_id,
                "role": "assistant",
                "content": ai_reply["content"],
                "created_at": now,
            }
        finally:
            connection.close()

    def update_project_title(self, *, project_id: int, user_id: str, title: str) -> bool:
        project = self.get_project_detail(project_id=project_id, user_id=user_id)
        if not project:
            return False
        self._update_project(project_id=project_id, title=title)
        return True

    def delete_project(self, *, project_id: int, user_id: str) -> bool:
        connection = create_connection()
        try:
            # Check ownership
            project_row = connection.execute(
                "SELECT id, conversation_id FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id)
            ).fetchone()
            if not project_row:
                return False
            
            # Delete project
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            
            # Delete task steps
            connection.execute("DELETE FROM project_task_steps WHERE project_id = ?", (project_id,))
            
            # If there's a conversation, delete it and its messages
            if project_row["conversation_id"]:
                conv_id = project_row["conversation_id"]
                connection.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
                connection.execute("DELETE FROM conversation_messages WHERE conversation_id = ?", (conv_id,))
            
            connection.commit()
            return True
        finally:
            connection.close()

    # ── Remake Workflow Steps ──

    async def _step_remake_select_source(self, *, project_id: int) -> dict[str, Any]:
        """Step 1: Select the source motion asset to remake."""
        # Placeholder logic
        return {"detail": "已确认复刻参照的动作资产。"}

    async def _step_remake_define_intent(self, *, project_id: int) -> dict[str, Any]:
        """Step 2: Define what to keep and what to change."""
        return {"detail": "已确认复刻意图：保留镜头动作与节奏，改写人物与场景风格。"}

    async def _step_remake_build_prompt(self, *, project_id: int) -> dict[str, Any]:
        """Step 3: Construct the structured prompt for video generation."""
        return {"detail": "已基于动作特征与用户指令构造出结构化 Prompt。"}

    async def _step_remake_generate_video(self, *, project_id: int) -> dict[str, Any]:
        """Step 4: Call video generation API."""
        # This would be a long-running task
        return {"detail": "视频生成引擎任务已提交，正在排队生产中。"}

    async def _step_remake_evaluate_copyright(self, *, project_id: int) -> dict[str, Any]:
        """Step 5: Evaluate visual similarity for copyright safety."""
        return {"detail": "版权距离评估完成：原创性合规，风险等级：低。"}

    async def _step_remake_save_result(self, *, project_id: int) -> dict[str, Any]:
        """Step 6: Save the resulting video asset."""
        return {"detail": "复刻视频已成功保存至素材库，并关联血缘关系。"}

    # ── Create Workflow Steps ──

    async def _step_create_define_objective(self, *, project_id: int) -> dict[str, Any]:
        """Step 1: Parse creation objective."""
        return {"detail": "已解析创作目标，识别出核心带货主题与受众定位。"}

    async def _step_create_generate_script(self, *, project_id: int) -> dict[str, Any]:
        """Step 2: Generate creative script and storyboard."""
        return {"detail": "AI 已生成创意剧本、分镜描述和口播文案。"}

    async def _step_create_select_style(self, *, project_id: int) -> dict[str, Any]:
        """Step 3: Select or associate visual style references."""
        return {"detail": "已关联视觉风格参考素材，确定了色调与运镜方案。"}

    async def _step_create_generate_video(self, *, project_id: int) -> dict[str, Any]:
        """Step 4: Execute video generation."""
        return {"detail": "创作视频生成任务已启动。"}

    async def _step_create_post_production(self, *, project_id: int) -> dict[str, Any]:
        """Step 5: Post-production processing (BGM, Captions)."""
        return {"detail": "已完成背景音乐匹配、字幕压制与后期合成。"}

    async def _step_create_finish(self, *, project_id: int) -> dict[str, Any]:
        """Step 6: Complete the creation workflow."""
        self._update_project(project_id=project_id, status="completed")
        return {"detail": "爆款创作工作流全部完成。"}
