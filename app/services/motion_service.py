import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any

from app.auth.security import utcnow_iso
from app.db.sqlite import create_connection
from app.services.analysis_ai_service import AnalysisAIService
from app.services.asset_service import AssetService
from app.services.job_service import JobService
from app.services.project_service import ProjectService
from app.workflows.motion_extraction import MOTION_EXTRACTION_STEPS

logger = logging.getLogger(__name__)

MOTION_KEYWORDS = {
    "walk_in": ["走进", "走入", "步入", "进来", "walk in", "stride", "enter"],
    "push_door": ["推门", "开门", "push door", "open door"],
    "turn_back": ["回头", "转身", "look back", "turn back"],
    "approach": ["靠近", "走向", "逼近", "approach", "walk toward"],
    "stare": ["凝视", "注视", "盯", "stare", "gaze"],
    "sit_down": ["坐下", "落座", "sit down"],
    "stand_up": ["站起", "起身", "stand up"],
    "slap": ["扇", "打耳光", "slap"],
    "embrace": ["拥抱", "抱住", "embrace", "hug"],
    "collapse": ["瘫坐", "倒下", "崩溃", "collapse"],
    "throw": ["扔", "摔", "砸", "throw", "slam"],
    "kneel": ["跪", "kneel"],
}

ACTION_LABEL_MAPPING = {
    "walk_in": "walk_in",
    "push_door": "push_door_enter",
    "turn_back": "pause_and_turn",
    "approach": "slow_approach",
    "stare": "stand_and_stare",
    "sit_down": "sit_down_strongly",
    "stand_up": "look_down_then_up",
    "slap": "slap",
    "embrace": "embrace",
    "collapse": "collapse",
    "throw": "throw_object",
    "kneel": "kneel_down",
}

SCENE_HINTS = {
    "office": ["办公室", "office", "工位", "会议室"],
    "corridor": ["走廊", "corridor", "过道"],
    "meeting_room": ["会议室", "meeting room"],
    "villa": ["别墅", "villa"],
    "hospital": ["医院", "hospital"],
    "street_night": ["街头", "street", "夜", "night"],
    "elevator": ["电梯", "elevator"],
    "rooftop": ["楼顶", "roof", "rooftop"],
    "bar_club": ["酒吧", "bar", "club"],
    "parking_lot": ["停车场", "parking"],
    "court_room": ["法庭", "court"],
    "banquet_hall": ["宴会厅", "banquet"],
    "bedroom": ["卧室", "bedroom"],
    "car_interior": ["车内", "车里", "car"],
    "rain_outdoor": ["雨", "rain"],
}

EMOTION_HINTS = {
    "anger": ["生气", "愤怒", "怒", "aggressive", "angry"],
    "pressure": ["压迫", "紧张", "逼迫", "pressure"],
    "indifference": ["冷淡", "冷漠", "indifference"],
    "sadness": ["难过", "悲伤", "sad", "哭"],
    "restraint": ["克制", "隐忍", "restraint"],
    "desperation": ["绝望", "崩溃", "desperate"],
    "contempt": ["轻蔑", "不屑", "contempt"],
    "shock": ["震惊", "惊讶", "shock"],
    "relief": ["松了口气", "释然", "relief"],
    "jealousy": ["嫉妒", "jealous"],
    "determination": ["坚定", "果断", "determination"],
}

TEMPERAMENT_HINTS = {
    "cold_dominant": ["冷", "强势", "压迫"],
    "gentle_but_strong": ["温柔", "克制", "坚定"],
    "broken_fragile": ["脆弱", "崩溃", "难过"],
    "scheming": ["算计", "心机"],
    "noble_calm": ["高贵", "冷静", "从容"],
    "aggressive": ["攻击", "愤怒", "冲上前"],
    "playful_confident": ["自信", "俏皮"],
    "silent_power": ["沉默", "压迫感", "无声"],
    "desperate_dignity": ["绝望", "体面"],
}


class MotionService:
    def __init__(self) -> None:
        self._project_service = ProjectService()
        self._asset_service = AssetService()
        self._job_service = JobService()
        self._analysis_ai_service = AnalysisAIService()

    async def run_job(
        self,
        *,
        job_id: str,
        project_id: int,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        project = self._project_service._get_project_for_execution(project_id=project_id)
        if project is None:
            raise ValueError("目标项目不存在，无法执行动作提取。")

        result = {
            "project_id": project_id,
            "source_video_asset_id": project.get("source_asset_id"),
            "candidate_count": 0,
            "tagged_count": 0,
            "saved_count": 0,
            "asset_ids": [],
            "items": [],
            "steps": [
                {
                    "step_key": definition.step_key,
                    "title": definition.title,
                    "detail": definition.description,
                    "status": "pending",
                    "error_detail": None,
                }
                for definition in MOTION_EXTRACTION_STEPS
            ],
        }
        started_at = utcnow_iso()
        self._job_service.update_job_status(
            job_id=job_id,
            status="running",
            progress=1,
            result=result,
            started_at=started_at,
        )

        context: dict[str, Any] = {}
        step_handlers = {
            "validate_analysis_data": self.step_validate_analysis,
            "coarse_filter_shots": self.step_coarse_filter,
            "tag_candidates": self.step_tag_candidates,
            "generate_thumbnails": self.step_generate_thumbnails,
            "save_motion_assets": self.step_save_assets,
            "finish": self.step_finish,
        }

        try:
            for index, definition in enumerate(MOTION_EXTRACTION_STEPS, start=1):
                self._set_step_state(
                    result=result,
                    step_key=definition.step_key,
                    status="running",
                    detail=definition.description,
                )
                self._job_service.update_job_status(
                    job_id=job_id,
                    status="running",
                    progress=max(1, int((index - 1) * 100 / len(MOTION_EXTRACTION_STEPS))),
                    result=result,
                )

                step_result = await step_handlers[definition.step_key](
                    project=project,
                    context=context,
                    job_id=job_id,
                    owner_user_id=owner_user_id,
                )
                context[definition.step_key] = step_result
                for field_key in ("source_video_asset_id", "candidate_count", "tagged_count", "saved_count", "asset_ids", "items"):
                    if field_key in step_result:
                        result[field_key] = step_result[field_key]
                self._set_step_state(
                    result=result,
                    step_key=definition.step_key,
                    status="completed",
                    detail=step_result.get("detail") or definition.title,
                )
                self._job_service.update_job_status(
                    job_id=job_id,
                    status="running",
                    progress=int(index * 100 / len(MOTION_EXTRACTION_STEPS)),
                    result=result,
                )
        except Exception as exc:
            error_detail = str(exc).strip() or "动作提取失败。"
            logger.exception("Motion extraction failed: project_id=%s job_id=%s", project_id, job_id)
            self._set_step_state(
                result=result,
                step_key=next(
                    (
                        item["step_key"]
                        for item in result["steps"]
                        if item["status"] == "running"
                    ),
                    "finish",
                ),
                status="failed",
                detail=error_detail,
                error_detail=error_detail,
            )
            result["error_detail"] = error_detail
            self._job_service.update_job_status(
                job_id=job_id,
                status="failed",
                progress=max(1, max((idx for idx, _ in enumerate(result["steps"], start=1)), default=1)),
                result=result,
                error_message=error_detail,
                finished_at=utcnow_iso(),
            )
            self._append_project_message(
                project_id=project_id,
                message_type="workflow_error",
                content=error_detail,
                content_json={"job_id": job_id, "workflow_type": "motion_extraction"},
            )
            raise

        self._job_service.update_job_status(
            job_id=job_id,
            status="succeeded",
            progress=100,
            result=result,
            finished_at=utcnow_iso(),
        )
        self._append_project_message(
            project_id=project_id,
            message_type="motion_extraction_result",
            content=result.get("steps", [])[-1].get("detail") or "动作提取完成。",
            content_json={
                "job_id": job_id,
                "workflow_type": "motion_extraction",
                "saved_count": result.get("saved_count", 0),
                "asset_ids": result.get("asset_ids", []),
            },
        )
        return result

    async def step_validate_analysis(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
        job_id: str,
        owner_user_id: str | None,
    ) -> dict[str, Any]:
        shot_segments = self._project_service._load_shot_segments_for_project(
            project_id=project["id"],
        )
        if not shot_segments:
            raise ValueError("该项目尚未完成视频分析，请先生成 shot_segments 后再执行动作提取。")

        connection = create_connection()
        try:
            storyboard = self._project_service._load_latest_storyboard(
                connection=connection,
                project_id=project["id"],
            )
        finally:
            connection.close()

        source_video_asset_id = (
            project.get("source_asset_id")
            or next(
                (
                    item.get("source_video_asset_id")
                    for item in shot_segments
                    if item.get("source_video_asset_id")
                ),
                None,
            )
        )
        source_asset = (
            self._asset_service.get_asset(asset_id=source_video_asset_id)
            if source_video_asset_id
            else None
        )
        storyboard_count = len((storyboard or {}).get("items") or [])
        detail = f"数据就绪：{len(shot_segments)} 个镜头片段，{storyboard_count} 条分镜描述。"
        if not storyboard_count:
            detail += " 当前未检测到结构化分镜，后续将回退为镜头文本组合。"
        return {
            "detail": detail,
            "shot_segments": shot_segments,
            "storyboard": storyboard or {"summary": "", "items": []},
            "shot_count": len(shot_segments),
            "storyboard_count": storyboard_count,
            "source_video_asset_id": source_video_asset_id,
            "source_asset": source_asset,
        }

    async def step_coarse_filter(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
        job_id: str,
        owner_user_id: str | None,
    ) -> dict[str, Any]:
        validated = context["validate_analysis_data"]
        shot_segments = validated.get("shot_segments") or []
        storyboard_items = (validated.get("storyboard") or {}).get("items") or []
        storyboard_index = self._build_storyboard_index(storyboard_items)

        candidates: list[dict[str, Any]] = []
        for segment in shot_segments:
            segment_index = int(segment.get("segment_index") or 0)
            related_items = storyboard_index.get(segment_index, [])
            combined_text = self._build_candidate_text(segment=segment, storyboard_items=related_items)
            is_candidate, matched_labels = self._coarse_filter_candidate(
                start_ms=int(segment.get("start_ms") or 0),
                end_ms=int(segment.get("end_ms") or 0),
                text=combined_text,
            )
            if not is_candidate:
                continue

            candidates.append(
                {
                    "source_shot_segment_id": segment.get("id"),
                    "segment_index": segment_index,
                    "start_ms": int(segment.get("start_ms") or 0),
                    "end_ms": int(segment.get("end_ms") or 0),
                    "duration_ms": int(segment.get("duration_ms") or 0),
                    "transcript_text": str(segment.get("transcript_text") or "").strip(),
                    "ocr_text": str(segment.get("ocr_text") or "").strip(),
                    "visual_summary": str(segment.get("visual_summary") or "").strip(),
                    "title": str(segment.get("title") or "").strip(),
                    "scene_label": str(segment.get("scene_label") or "").strip(),
                    "shot_type_code": str(segment.get("shot_type_code") or "").strip(),
                    "camera_motion_code": str(segment.get("camera_motion_code") or "").strip(),
                    "camera_angle_code": str(segment.get("camera_angle_code") or "").strip(),
                    "storyboard_text": " ".join(
                        str(item.get("visual_description") or "").strip()
                        for item in related_items
                        if str(item.get("visual_description") or "").strip()
                    ).strip(),
                    "combined_text": combined_text,
                    "matched_labels": matched_labels,
                }
            )

        return {
            "detail": f"粗筛完成：从 {len(shot_segments)} 个镜头中筛出 {len(candidates)} 个候选。",
            "total_shots": len(shot_segments),
            "candidate_count": len(candidates),
            "candidates": candidates,
            "source_video_asset_id": validated.get("source_video_asset_id"),
        }

    async def step_tag_candidates(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
        job_id: str,
        owner_user_id: str | None,
    ) -> dict[str, Any]:
        candidates = context["coarse_filter_shots"].get("candidates") or []
        tagged_results: list[dict[str, Any]] = []

        for candidate in candidates:
            fallback_tags = self._build_fallback_tags(candidate=candidate)
            ai_result = await self._analysis_ai_service.generate_motion_tags_reply(
                source_name=project.get("source_name") or project.get("title") or "视频片段",
                candidate=candidate,
                fallback_payload=fallback_tags,
            )
            tags = ai_result.get("payload") or fallback_tags
            confidence = self._safe_float(tags.get("confidence"), default=0.0)
            is_high_value = bool(tags.get("is_high_value", False))
            if not is_high_value or confidence < 0.6:
                continue

            tagged_results.append(
                {
                    **candidate,
                    "tags": tags,
                    "provider": ai_result.get("provider"),
                    "model": ai_result.get("model"),
                    "used_remote": bool(ai_result.get("used_remote")),
                }
            )

        return {
            "detail": f"精标完成：{len(tagged_results)} 个高价值动作片段。",
            "tagged_count": len(tagged_results),
            "tagged_results": tagged_results,
            "source_video_asset_id": context["coarse_filter_shots"].get("source_video_asset_id"),
        }

    async def step_generate_thumbnails(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
        job_id: str,
        owner_user_id: str | None,
    ) -> dict[str, Any]:
        tagged_results = context["tag_candidates"].get("tagged_results") or []
        source_asset = context["validate_analysis_data"].get("source_asset") or {}
        file_path = str(source_asset.get("file_path") or "").strip()
        ffmpeg_bin = shutil.which("ffmpeg")
        if not tagged_results:
            return {
                "detail": "没有高价值候选片段，跳过缩略图生成。",
                "thumbnails": {},
            }
        if not ffmpeg_bin or not file_path or not Path(file_path).exists():
            return {
                "detail": "当前环境缺少可用的 ffmpeg 或源视频文件，已跳过缩略图生成。",
                "thumbnails": {},
            }

        thumbnails: dict[str, str] = {}
        for item in tagged_results:
            thumbnail_path = await self._extract_thumbnail(
                ffmpeg_bin=ffmpeg_bin,
                source_file=file_path,
                project_id=project["id"],
                segment_id=str(item.get("source_shot_segment_id") or item.get("segment_index") or ""),
                timestamp_ms=(int(item.get("start_ms") or 0) + int(item.get("end_ms") or 0)) // 2,
            )
            if thumbnail_path:
                thumbnails[str(item.get("source_shot_segment_id") or "")] = thumbnail_path

        return {
            "detail": f"已生成 {len(thumbnails)} 张缩略图。",
            "thumbnails": thumbnails,
        }

    async def step_save_assets(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
        job_id: str,
        owner_user_id: str | None,
    ) -> dict[str, Any]:
        tagged_results = context["tag_candidates"].get("tagged_results") or []
        thumbnails = context["generate_thumbnails"].get("thumbnails") or {}
        source_video_asset_id = context["validate_analysis_data"].get("source_video_asset_id")
        if not tagged_results:
            return {
                "detail": "没有符合条件的动作片段，未写入动作资产。",
                "saved_count": 0,
                "asset_ids": [],
                "items": [],
                "source_video_asset_id": source_video_asset_id,
            }

        clips: list[dict[str, Any]] = []
        for item in tagged_results:
            tags = item.get("tags") or {}
            source_shot_segment_id = str(item.get("source_shot_segment_id") or "")
            clips.append(
                {
                    "start_ms": int(item.get("start_ms") or 0),
                    "end_ms": int(item.get("end_ms") or 0),
                    "action_summary": str(tags.get("action_summary") or "").strip() or self._build_fallback_summary(item),
                    "action_label": str(tags.get("action_label") or "").strip() or None,
                    "entrance_style": str(tags.get("entrance_style") or "").strip() or None,
                    "emotion_label": str(tags.get("emotion_label") or "").strip() or None,
                    "temperament_label": str(tags.get("temperament_label") or "").strip() or None,
                    "scene_label": str(tags.get("scene_label") or "").strip() or None,
                    "camera_motion": str(tags.get("camera_motion") or item.get("camera_motion_code") or "").strip() or None,
                    "camera_shot": str(tags.get("camera_shot") or item.get("shot_type_code") or "").strip() or None,
                    "confidence": self._safe_float(tags.get("confidence"), default=0.75),
                    "asset_candidate": True,
                    "review_status": "auto_tagged",
                    "copyright_risk_level": "unknown",
                    "metadata_json": {
                        "matched_labels": item.get("matched_labels") or [],
                        "project_id": project["id"],
                        "source_shot_segment_id": source_shot_segment_id,
                        "thumbnail_path": thumbnails.get(source_shot_segment_id),
                        "analysis_source": "motion_extraction",
                        "used_remote": bool(item.get("used_remote")),
                        "provider": item.get("provider"),
                        "model": item.get("model"),
                    },
                }
            )

        saved_assets = self._asset_service.create_motion_assets_from_analysis(
            source_video_asset_id=source_video_asset_id,
            conversation_id=project.get("conversation_id"),
            job_id=job_id,
            owner_user_id=owner_user_id or project.get("user_id"),
            clips=clips,
            origin="ai_generated",
        )
        return {
            "detail": f"已保存 {len(saved_assets)} 个动作资产到资产库。",
            "saved_count": len(saved_assets),
            "asset_ids": [item["id"] for item in saved_assets],
            "items": saved_assets,
            "source_video_asset_id": source_video_asset_id,
        }

    async def step_finish(
        self,
        *,
        project: dict[str, Any],
        context: dict[str, Any],
        job_id: str,
        owner_user_id: str | None,
    ) -> dict[str, Any]:
        saved_count = int(context.get("save_motion_assets", {}).get("saved_count") or 0)
        return {
            "detail": f"动作资产提取完成，共沉淀 {saved_count} 条动作资产。",
            "saved_count": saved_count,
            "asset_ids": context.get("save_motion_assets", {}).get("asset_ids") or [],
            "items": context.get("save_motion_assets", {}).get("items") or [],
            "source_video_asset_id": context.get("save_motion_assets", {}).get("source_video_asset_id"),
        }

    def _set_step_state(
        self,
        *,
        result: dict[str, Any],
        step_key: str,
        status: str,
        detail: str,
        error_detail: str | None = None,
    ) -> None:
        for item in result.get("steps", []):
            if item["step_key"] != step_key:
                continue
            item["status"] = status
            item["detail"] = detail
            item["error_detail"] = error_detail
            break

    def _append_project_message(
        self,
        *,
        project_id: int,
        message_type: str,
        content: str,
        content_json: dict[str, Any] | None = None,
    ) -> None:
        self._project_service._append_project_message(
            project_id=project_id,
            role="assistant",
            message_type=message_type,
            content=content,
            content_json=content_json,
        )

    def _build_storyboard_index(self, storyboard_items: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        indexed: dict[int, list[dict[str, Any]]] = {}
        for item in storyboard_items:
            for raw_index in item.get("source_segment_indexes") or []:
                try:
                    segment_index = int(raw_index)
                except (TypeError, ValueError):
                    continue
                indexed.setdefault(segment_index, []).append(item)
        return indexed

    def _build_candidate_text(
        self,
        *,
        segment: dict[str, Any],
        storyboard_items: list[dict[str, Any]],
    ) -> str:
        parts: list[str] = []
        for key in ("title", "visual_summary", "transcript_text", "ocr_text", "scene_label"):
            value = str(segment.get(key) or "").strip()
            if value:
                parts.append(value)
        for item in storyboard_items:
            for key in ("title", "visual_description", "transcript_excerpt", "ocr_excerpt"):
                value = str(item.get(key) or "").strip()
                if value:
                    parts.append(value)
        normalized_parts: list[str] = []
        seen: set[str] = set()
        for part in parts:
            lowered = part.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized_parts.append(part)
        return " ".join(normalized_parts).strip()

    def _coarse_filter_candidate(
        self,
        *,
        start_ms: int,
        end_ms: int,
        text: str,
    ) -> tuple[bool, list[str]]:
        duration = max(0, end_ms - start_ms)
        if duration < 1000 or duration > 8000:
            return False, []

        lowered = (text or "").lower()
        matched: list[str] = []
        for label, keywords in MOTION_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                matched.append(label)
        return bool(matched), matched

    def _build_fallback_tags(self, *, candidate: dict[str, Any]) -> dict[str, Any]:
        matched_labels = candidate.get("matched_labels") or []
        primary_label = matched_labels[0] if matched_labels else "stare"
        action_label = ACTION_LABEL_MAPPING.get(primary_label, "stand_and_stare")
        text = str(candidate.get("combined_text") or "").strip()
        scene_label = self._infer_label(text=text, mapping=SCENE_HINTS, default=candidate.get("scene_label") or "office")
        emotion_label = self._infer_label(text=text, mapping=EMOTION_HINTS, default="determination")
        temperament_label = self._infer_label(text=text, mapping=TEMPERAMENT_HINTS, default="silent_power")
        camera_motion = str(candidate.get("camera_motion_code") or "static").strip() or "static"
        camera_shot = str(candidate.get("shot_type_code") or "medium").strip() or "medium"
        return {
            "action_label": action_label,
            "entrance_style": "camera_follow_entry" if primary_label in {"walk_in", "approach"} else "door_entry" if primary_label == "push_door" else None,
            "emotion_label": emotion_label,
            "temperament_label": temperament_label,
            "scene_label": scene_label,
            "camera_motion": camera_motion,
            "camera_shot": camera_shot,
            "action_summary": self._build_fallback_summary(candidate),
            "confidence": 0.76 if len(matched_labels) == 1 else 0.88,
            "is_high_value": True,
        }

    def _build_fallback_summary(self, candidate: dict[str, Any]) -> str:
        shot_title = str(candidate.get("title") or candidate.get("visual_summary") or "").strip()
        text = str(candidate.get("combined_text") or "").strip()
        if shot_title:
            return f"角色在该片段中围绕“{shot_title}”完成关键动作，镜头以{candidate.get('camera_motion_code') or 'static'}方式推进。"
        if text:
            trimmed = text[:60]
            return f"角色在该片段中完成关键动作推进，核心信息为：{trimmed}。"
        return "角色在该片段中完成关键动作推进，镜头强调动作节奏与情绪变化。"

    def _infer_label(
        self,
        *,
        text: str,
        mapping: dict[str, list[str]],
        default: str,
    ) -> str:
        lowered = (text or "").lower()
        for label, keywords in mapping.items():
            if any(keyword in lowered for keyword in keywords):
                return label
        return default

    async def _extract_thumbnail(
        self,
        *,
        ffmpeg_bin: str,
        source_file: str,
        project_id: int,
        segment_id: str,
        timestamp_ms: int,
    ) -> str | None:
        output_dir = Path.cwd() / "uploads" / "motion-thumbnails"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{project_id}-{segment_id}.jpg"
        command = [
            ffmpeg_bin,
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{max(timestamp_ms, 0) / 1000:.3f}",
            "-i",
            source_file,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
        except Exception:
            logger.debug("Thumbnail extraction skipped for %s", source_file, exc_info=True)
            return None

        if process.returncode != 0 or not output_path.exists():
            logger.debug(
                "ffmpeg thumbnail extraction failed for %s: %s",
                source_file,
                stderr.decode("utf-8", errors="ignore").strip(),
            )
            return None
        return str(output_path)

    @staticmethod
    def _safe_float(value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
