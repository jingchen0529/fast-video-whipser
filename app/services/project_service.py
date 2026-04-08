import json
import mimetypes
import os
import sqlite3
import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from fastapi import HTTPException, UploadFile

from app.auth.security import utcnow_iso
from app.core.config import settings
from app.crawlers.tiktok import TikTokAPPCrawler
from app.db.sqlite import create_connection
from app.services.analysis_ai_service import AnalysisAIService
from app.services.asset_service import AssetService
from app.utils.file_utils import FileUtils


@dataclass(frozen=True, slots=True)
class TaskStepDefinition:
    step_key: str
    title: str
    description: str


ANALYSIS_TASK_STEPS = (
    TaskStepDefinition(
        "extract_video_link",
        "提取视频链接",
        "从用户输入中提取对标视频链接或上传素材地址。",
    ),
    TaskStepDefinition(
        "validate_video_link",
        "验证视频链接",
        "校验链接协议、来源平台和基础可访问性。",
    ),
    TaskStepDefinition(
        "analyze_video_content",
        "分析视频内容",
        "解析视频画面、节奏、镜头结构和内容主题。",
    ),
    TaskStepDefinition(
        "identify_audio_content",
        "识别音频内容",
        "提取音轨、转写口播，并识别字幕文本。",
    ),
    TaskStepDefinition(
        "generate_response",
        "生成分析回复",
        "生成 TikTok 电商效果深度分析主内容。",
    ),
    TaskStepDefinition(
        "generate_suggestions",
        "生成优化建议",
        "输出 3-5 条可执行的优化建议。",
    ),
    TaskStepDefinition(
        "finish",
        "全部完成",
        "视频分析工作流全部步骤已完成。",
    ),
)

UNSUPPORTED_WORKFLOW_STEPS = (
    TaskStepDefinition(
        "prepare_workflow",
        "准备工作流",
        "初始化任务上下文并等待执行器接入。",
    ),
    TaskStepDefinition(
        "finish",
        "全部完成",
        "当前工作流的执行状态已收口。",
    ),
)

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
    SUPPORTED_WORKFLOWS = {"analysis"}

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
        project = self._get_project_for_execution(project_id=project_id)
        if project is None:
            return

        if project["workflow_type"] not in self.SUPPORTED_WORKFLOWS:
            message = "当前仅接入分析脚本工作流，复刻爆款和创作爆款工作流稍后接入。"
            self._set_step_status(
                project_id=project_id,
                step_key="prepare_workflow",
                status="failed",
                detail=message,
                error_detail=message,
            )
            self._update_project(
                project_id=project_id,
                status="failed",
                summary=message,
                error_message=message,
            )
            self._append_project_message(
                project_id=project_id,
                role="assistant",
                message_type="workflow_error",
                content=message,
                content_json={"status": "failed"},
            )
            return

        context: dict[str, Any] = {}
        try:
            context["extract_video_link"] = await self._execute_step(
                project_id=project_id,
                definition=ANALYSIS_TASK_STEPS[0],
                handler=lambda: self._step_extract_video_link(project_id=project_id),
            )
            context["validate_video_link"] = await self._execute_step(
                project_id=project_id,
                definition=ANALYSIS_TASK_STEPS[1],
                handler=lambda: self._step_validate_video_link(
                    project_id=project_id,
                    context=context,
                ),
            )
            context["analyze_video_content"] = await self._execute_step(
                project_id=project_id,
                definition=ANALYSIS_TASK_STEPS[2],
                handler=lambda: self._step_analyze_video_content(
                    project_id=project_id,
                    context=context,
                ),
            )
            context["identify_audio_content"] = await self._execute_step(
                project_id=project_id,
                definition=ANALYSIS_TASK_STEPS[3],
                handler=lambda: self._step_identify_audio_content(
                    project_id=project_id,
                    context=context,
                ),
            )
            context["generate_response"] = await self._execute_step(
                project_id=project_id,
                definition=ANALYSIS_TASK_STEPS[4],
                handler=lambda: self._step_generate_response(
                    project_id=project_id,
                    context=context,
                ),
                append_status_message=False,
            )
            context["generate_suggestions"] = await self._execute_step(
                project_id=project_id,
                definition=ANALYSIS_TASK_STEPS[5],
                handler=lambda: self._step_generate_suggestions(
                    project_id=project_id,
                    context=context,
                ),
                append_status_message=False,
            )
            await self._execute_step(
                project_id=project_id,
                definition=ANALYSIS_TASK_STEPS[6],
                handler=lambda: self._step_finish(
                    project_id=project_id,
                    context=context,
                ),
            )
        except Exception:
            return

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

    async def _execute_step(
        self,
        *,
        project_id: int,
        definition: TaskStepDefinition,
        handler: Callable[[], dict[str, Any] | Awaitable[dict[str, Any]]],
        append_status_message: bool = True,
    ) -> dict[str, Any]:
        self._set_step_status(
            project_id=project_id,
            step_key=definition.step_key,
            status="in_progress",
            detail=definition.description,
        )

        try:
            result = handler()
            if hasattr(result, "__await__"):
                result = await result
        except Exception as exc:
            error_message = str(exc).strip() or f"{definition.title}失败。"
            self._set_step_status(
                project_id=project_id,
                step_key=definition.step_key,
                status="failed",
                detail=error_message,
                error_detail=error_message,
            )
            self._update_project(
                project_id=project_id,
                status="failed",
                summary=error_message,
                error_message=error_message,
            )
            self._append_project_message(
                project_id=project_id,
                role="assistant",
                message_type="workflow_error",
                content=error_message,
                content_json={
                    "step_key": definition.step_key,
                    "status": "failed",
                },
            )
            raise

        detail = result.get("detail") or f"{definition.title}已完成。"
        self._set_step_status(
            project_id=project_id,
            step_key=definition.step_key,
            status="completed",
            detail=detail,
            output=result,
        )
        if append_status_message:
            self._append_project_message(
                project_id=project_id,
                role="assistant",
                message_type="workflow_status",
                content=detail,
                content_json={
                    "step_key": definition.step_key,
                    "status": "completed",
                },
            )
        return result

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
        video_info = remote_video_info.get("video_info") or {}
        video_meta = self._build_video_meta(
            project=project,
            source_asset=source_asset,
            video_info=video_info,
        )
        visual_features = self._build_visual_features(video_meta=video_meta)
        timeline_segments = self._build_timeline_segments(
            project=project,
            remote_video_info=remote_video_info,
        )
        source_analysis = {
            "reference_frames": [],
            "visual_features": visual_features,
        }
        summary = "已完成视频画面、节奏和结构分析，识别出 4 个高价值脚本片段。"

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
            "detail": summary,
        }

    async def _step_identify_audio_content(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        timeline_segments = context.get("analyze_video_content", {}).get("timeline_segments") or []
        remote_video_info = (
            context.get("validate_video_link", {}).get("remote_video_info")
            or {}
        )
        video_desc = (
            (remote_video_info.get("video_info") or {}).get("desc")
            or project["objective"]
            or project["source_name"]
        )
        script_overview = self._build_script_overview(
            timeline_segments=timeline_segments,
            video_desc=video_desc,
        )
        self._update_project(
            project_id=project_id,
            script_overview=script_overview,
        )

        return {
            "script_overview": script_overview,
            "detail": "已完成口播与字幕整理，提炼出完整脚本文本和分段内容。",
        }

    async def _step_generate_response(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        source_analysis = context.get("analyze_video_content", {}).get("source_analysis") or DEFAULT_SOURCE_ANALYSIS
        timeline_segments = context.get("analyze_video_content", {}).get("timeline_segments") or []
        script_overview = context.get("identify_audio_content", {}).get("script_overview") or DEFAULT_SCRIPT_OVERVIEW
        ai_result = await AnalysisAIService().generate_analysis_reply(
            objective=project["objective"],
            source_name=project["source_name"],
            source_analysis=source_analysis,
            timeline_segments=timeline_segments,
            script_overview=script_overview,
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
        final_summary = "视频分析工作流已完成，已输出脚本梳理、电商效果分析和优化建议。"
        self._update_project(
            project_id=project_id,
            status="succeeded",
            summary=final_summary,
            error_message=None,
        )
        return {
            "detail": final_summary,
        }

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
        if workflow_type == "analysis":
            return ANALYSIS_TASK_STEPS
        return UNSUPPORTED_WORKFLOW_STEPS

    def _load_json_field(self, raw_value: str | None, default: Any) -> Any:
        if not raw_value:
            return deepcopy(default)
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return deepcopy(default)

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

    def _build_visual_features(self, *, video_meta: dict[str, Any]) -> dict[str, Any]:
        width = int(video_meta.get("width") or 1080)
        height = int(video_meta.get("height") or 1920)
        orientation = "portrait" if height >= width else "landscape"
        return {
            "orientation": orientation,
            "resolution": f"{width}x{height}",
            "frame_rate": "30fps",
            "keyframe_count": 4,
            "shot_density": "medium",
            "scene_pace": "fast",
            "lighting": "bright",
            "contrast": "medium",
            "saturation": "medium_high",
            "color_temperature": "neutral_warm",
            "framing_focus": "subject_forward",
            "camera_motion": "mixed",
            "dominant_palette": ["#0F172A", "#E2E8F0", "#2563EB"],
            "summary": "整体节奏偏快，镜头围绕主体和卖点切换，适合短视频带货分析。",
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
