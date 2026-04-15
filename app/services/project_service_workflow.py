"""Workflow orchestration and domain helpers for project workflows."""
from app.services.project_service_shared import *  # noqa: F401,F403


class ProjectWorkflowMixin:
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

        now = utcnow_ms()
        session = _get_session()
        try:
            project_repo = ProjectRepository(session)
            step_repo = ProjectTaskStepRepository(session)
            project_obj = Project(
                user_id=user_id,
                title=title,
                source_url=extracted_source_url,
                source_platform=source_platform,
                workflow_type=normalized_workflow,
                source_type=source_type,
                source_name=source_name,
                status="running",
                media_url=media_url,
                objective=normalized_objective,
                summary="任务已创建，准备启动分析工作流。",
                source_asset_id=source_asset_id,
                script_overview_json=json.dumps(DEFAULT_SCRIPT_OVERVIEW, ensure_ascii=False),
                ecommerce_analysis_json=json.dumps(DEFAULT_ECOMMERCE_ANALYSIS, ensure_ascii=False),
                source_analysis_json=json.dumps(DEFAULT_SOURCE_ANALYSIS, ensure_ascii=False),
                timeline_segments_json=json.dumps([], ensure_ascii=False),
                video_generation_json=json.dumps(DEFAULT_VIDEO_GENERATION, ensure_ascii=False),
                error_message=None,
                created_at=now,
                updated_at=now,
            )
            project_repo.add(project_obj)
            session.flush()  # get auto-incremented id
            project_id = int(project_obj.id)

            user_request = self._build_user_request_message(
                objective=normalized_objective,
                source_name=source_name,
                source_url=extracted_source_url,
                workflow_type=normalized_workflow,
            )
            self._append_project_message_record(
                session=session,
                project_id=project_id,
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
            self._append_project_message_record(
                session=session,
                project_id=project_id,
                role="assistant",
                message_type="workflow_status",
                content=self._build_workflow_acceptance_message(
                    workflow_type=normalized_workflow,
                    objective=normalized_objective,
                ),
                content_json={
                    "project_id": project_id,
                    "workflow_type": normalized_workflow,
                    "status": "accepted",
                },
                created_at=now,
            )
            step_definitions = self._get_step_definitions(normalized_workflow)
            step_rows: list[ProjectTaskStep] = []
            for index, definition in enumerate(step_definitions, start=1):
                is_first_step = index == 1
                step_rows.append(
                    ProjectTaskStep(
                        project_id=project_id,
                        step_key=definition.step_key,
                        title=definition.title,
                        detail=definition.description,
                        status="in_progress" if is_first_step else "pending",
                        error_detail=None,
                        output_json=None,
                        display_order=index,
                        created_at=now,
                        updated_at=now,
                    )
                )
            step_repo.add_many(step_rows)

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        project = self.get_project_detail(project_id=project_id, user_id=user_id)
        if project is None:
            raise HTTPException(status_code=500, detail="项目创建失败。")
        return project

    async def run_project_workflow(self, *, project_id: int) -> None:
        """Delegate workflow execution to the WorkflowEngine."""
        from app.workflows.engine import WorkflowEngine
        engine = WorkflowEngine()
        await engine.run(project_id=project_id)

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
        shot_segments = await self._detect_shot_segments(
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

    async def _step_remake_select_source(self, *, project_id: int) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        source_asset = await self._ensure_source_asset(
            project=project,
            context={},
        )
        intent = self._parse_remake_objective(project.get("objective") or "")
        public_url = source_asset.get("public_url") or self._extract_asset_public_url(source_asset)
        video_generation = self._update_video_generation_state(
            project_id=project_id,
            project=project,
            status="preparing",
            provider=None,
            model=None,
            objective=intent["intent_label"],
            asset_type="video",
            asset_name=None,
            asset_url=None,
            output_asset_id=None,
            prompt=None,
            provider_task_id=None,
            result_video_url=None,
            error_detail=None,
            reference_frames=[public_url] if public_url else [],
        )
        detail = f"已确认参考素材 {source_asset['file_name']}，后续将基于该素材的节奏和镜头结构执行{intent['intent_label']}。"
        self._update_project(
            project_id=project_id,
            summary=detail,
            media_url=public_url or project.get("media_url"),
            source_asset_id=source_asset["id"],
            video_generation=video_generation,
        )
        return {
            "source_asset_id": source_asset["id"],
            "reference_frames": video_generation.get("reference_frames") or [],
            "intent": intent,
            "detail": detail,
        }

    async def _step_remake_analyze_reference(
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
        intent = self._parse_remake_objective(project.get("objective") or "")
        public_url = source_asset.get("public_url") or self._extract_asset_public_url(source_asset)
        preparing_generation = self._update_video_generation_state(
            project_id=project_id,
            project=project,
            status="preparing",
            provider=None,
            model=None,
            objective=intent["intent_label"],
            asset_type="video",
            asset_name=None,
            asset_url=None,
            output_asset_id=None,
            prompt=None,
            provider_task_id=None,
            result_video_url=None,
            error_detail=None,
            reference_frames=[public_url] if public_url else [],
        )
        video_meta = self._build_video_meta(
            project=project,
            source_asset=source_asset,
            video_info={},
        )
        shot_segments = await self._detect_shot_segments(
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
        shot_segments = self._enrich_shot_segments(
            shot_segments=shot_segments,
            video_meta=video_meta,
            objective=project["objective"],
            source_name=project["source_name"],
        )
        timeline_segments: list[dict[str, Any]] = []
        script_overview = deepcopy(DEFAULT_SCRIPT_OVERVIEW)
        transcription_failed = False
        try:
            transcription_result = await self._transcribe_source_media(
                project=project,
                source_asset=source_asset,
            )
            timeline_segments = transcription_result.get("timeline_segments") or []
            script_overview = self._build_script_overview(
                timeline_segments=timeline_segments,
                video_desc=project["objective"] or project["source_name"],
            )
        except Exception as exc:
            transcription_failed = True
            logger.warning("Reference transcription skipped for project %s: %s", project_id, exc)
        if not timeline_segments:
            timeline_segments = self._build_reference_fallback_timeline_segments(
                shot_segments=shot_segments,
                objective=project["objective"],
                source_name=project["source_name"],
            )
            script_overview = self._build_script_overview(
                timeline_segments=timeline_segments,
                video_desc=project["objective"] or project["source_name"],
            )

        storyboard = self._build_reference_storyboard(
            shot_segments=shot_segments,
            objective=project["objective"],
            source_name=project["source_name"],
        )
        source_analysis = {
            "reference_frames": [],
            "visual_features": self._build_visual_features(
                video_meta=video_meta,
                shot_segments=shot_segments,
            ),
            "shot_segment_count": len(shot_segments),
            "reference_summary": storyboard.get("summary") or "",
        }
        video_generation = self._update_video_generation_state(
            project_id=project_id,
            project=project,
            status="analyzing_reference",
            objective=preparing_generation.get("objective"),
            reference_frames=preparing_generation.get("reference_frames") or [],
            storyboard=storyboard,
        )
        detail = f"已完成参考视频分析，整理出 {len(shot_segments)} 个镜头段和可用于生成的视频结构信息。"
        if transcription_failed and timeline_segments:
            detail += " 音频脚本未识别到有效口播，已根据镜头描述回填参考脚本。"
        self._update_project(
            project_id=project_id,
            source_analysis=source_analysis,
            script_overview=script_overview,
            timeline_segments=timeline_segments,
            summary=detail,
            video_generation=video_generation,
        )
        return {
            "video_meta": video_meta,
            "shot_segments": shot_segments,
            "timeline_segments": timeline_segments,
            "script_overview": script_overview,
            "source_analysis": source_analysis,
            "storyboard": storyboard,
            "detail": detail,
        }

    async def _step_remake_define_intent(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        intent = self._parse_remake_objective(project.get("objective") or "")
        video_generation = self._update_video_generation_state(
            project_id=project_id,
            project=project,
            objective=intent["intent_label"],
        )
        keep_text = "、".join(intent["keep_items"]) if intent["keep_items"] else "镜头节奏"
        change_text = "、".join(intent["change_items"]) if intent["change_items"] else "人物与场景"
        detail = f"已确认复刻意图：保留 {keep_text}，改写 {change_text}。"
        self._update_project(
            project_id=project_id,
            summary=detail,
            video_generation=video_generation,
        )
        return {
            "intent": intent,
            "detail": detail,
        }

    async def _step_remake_build_prompt(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        intent = (
            context.get("define_remake_intent", {}).get("intent")
            or self._parse_remake_objective(project.get("objective") or "")
        )
        source_analysis = context.get("analyze_reference_video", {}).get("source_analysis") or DEFAULT_SOURCE_ANALYSIS
        storyboard = context.get("analyze_reference_video", {}).get("storyboard") or deepcopy(DEFAULT_STORYBOARD)
        script_overview = context.get("analyze_reference_video", {}).get("script_overview") or deepcopy(DEFAULT_SCRIPT_OVERVIEW)
        video_meta = context.get("analyze_reference_video", {}).get("video_meta") or {
            "width": 1080,
            "height": 1920,
            "duration_ms": 5000,
        }
        source_asset = None
        if project.get("source_asset_id"):
            source_asset = AssetService().get_asset(asset_id=project["source_asset_id"])

        aspect_ratio = self._aspect_ratio_from_meta(
            width=video_meta.get("width"),
            height=video_meta.get("height"),
        )
        duration_seconds = self._duration_seconds_from_meta(video_meta.get("duration_ms"))
        resolution = self._resolution_from_aspect_ratio(aspect_ratio)
        prompt = self._build_remake_prompt(
            intent=intent,
            source_analysis=source_analysis,
            storyboard=storyboard,
            script_overview=script_overview,
        )
        negative_prompt = self._build_default_negative_prompt(intent_label=intent["intent_label"])
        source_url = self._extract_generation_source_url(
            project=project,
            source_asset=source_asset,
        )
        reference_frames = self._filter_remote_media_urls(
            (self._load_video_generation_state(project=project).get("reference_frames") or [])
        )
        request_payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration_seconds": duration_seconds,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "reference_frames": reference_frames,
            "source_url": source_url,
            "storyboard": storyboard,
            "script": script_overview,
            "mode": "remake",
            "objective": intent["intent_label"],
        }
        video_generation = self._update_video_generation_state(
            project_id=project_id,
            project=project,
            prompt=prompt,
            storyboard=storyboard,
            script=script_overview,
            status="prompt_ready",
            error_detail=None,
        )
        detail = "已结合参考视频结构、保留项和改写项构造出可直接提交给视频模型的生成指令。"
        self._update_project(
            project_id=project_id,
            summary=detail,
            video_generation=video_generation,
        )
        return {
            "request_payload": request_payload,
            "detail": detail,
        }

    async def _step_remake_generate_video(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        request_payload = context.get("build_remake_prompt", {}).get("request_payload") or {}
        if not request_payload:
            raise ValueError("缺少视频生成指令，无法提交复刻任务。")
        provider = self._resolve_video_generation_provider()
        submit_result = await self._submit_video_generation_task(
            provider=provider,
            request_payload=request_payload,
        )
        video_generation = self._update_video_generation_state(
            project_id=project_id,
            project=project,
            status="running",
            provider=provider["provider"],
            model=provider["display_model"],
            asset_type="video",
            prompt=request_payload.get("prompt"),
            provider_task_id=submit_result.get("provider_task_id"),
            result_video_url=submit_result.get("result_video_url"),
            error_detail=None,
        )
        detail = (
            f"已向 {provider['label']} 提交视频生成任务。"
            if submit_result.get("provider_task_id")
            else f"{provider['label']} 已直接返回生成结果，准备下载入库。"
        )
        self._update_project(
            project_id=project_id,
            summary=detail,
            video_generation=video_generation,
        )
        return {
            "provider": provider,
            "submit_result": submit_result,
            "request_payload": request_payload,
            "detail": detail,
        }

    async def _step_remake_poll_generation_result(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        current_generation = self._load_video_generation_state(project=project)
        request_payload = (
            context.get("build_remake_prompt", {}).get("request_payload")
            or {}
        )
        provider = context.get("generate_video", {}).get("provider")
        if not provider:
            provider = self._resolve_video_generation_provider(
                preferred_provider=str(current_generation.get("provider") or ""),
            )
        poll_result = await self._wait_for_video_generation_result(
            provider=provider,
            provider_task_id=str(current_generation.get("provider_task_id") or ""),
            existing_result_url=str(current_generation.get("result_video_url") or ""),
        )
        asset = await self._persist_generated_video_asset(
            project=project,
            request_payload=request_payload,
            provider=provider,
            generation_result=poll_result,
        )
        video_generation = self._update_video_generation_state(
            project_id=project_id,
            project=project,
            status="succeeded",
            provider=provider["provider"],
            model=provider["display_model"],
            asset_type="video",
            asset_name=asset["file_name"],
            asset_url=asset["public_url"],
            output_asset_id=asset["id"],
            result_video_url=poll_result.get("result_video_url"),
            error_detail=None,
        )
        detail = "视频生成完成，结果已下载并写入资产库。"
        self._update_project(
            project_id=project_id,
            generated_media_url=asset["public_url"],
            summary=detail,
            video_generation=video_generation,
        )
        self._append_project_message(
            project_id=project_id,
            role="assistant",
            message_type="video_generation_result",
            content="复刻视频已生成完成。",
            content_json={
                "result_video_url": poll_result.get("result_video_url"),
                "asset_url": asset["public_url"],
                "output_asset_id": asset["id"],
                "provider": provider["provider"],
                "model": provider["display_model"],
            },
        )
        return {
            "asset": asset,
            "generation_result": poll_result,
            "detail": detail,
        }

    async def _step_remake_finish(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        final_summary = "视频复刻工作流已完成，生成结果已入库到资产库。"
        self._update_project(
            project_id=project_id,
            status="succeeded",
            summary=final_summary,
            error_message=None,
        )
        return {"detail": final_summary}

    async def _step_create_define_objective(self, *, project_id: int) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        creative_brief = self._parse_create_objective(project.get("objective") or "")
        project_reference_frames: list[str] = []
        if project.get("media_url"):
            project_reference_frames = [project["media_url"]]
        video_generation = self._update_video_generation_state(
            project_id=project_id,
            project=project,
            status="preparing",
            objective="爆款创作",
            asset_type="video",
            reference_frames=project_reference_frames,
            error_detail=None,
            asset_name=None,
            asset_url=None,
            output_asset_id=None,
            result_video_url=None,
            provider=None,
            model=None,
            provider_task_id=None,
        )
        detail = "已解析创作目标，确认视频类型、目标人群和商品卖点。"
        self._update_project(
            project_id=project_id,
            summary=detail,
            video_generation=video_generation,
        )
        return {
            "creative_brief": creative_brief,
            "detail": detail,
        }

    async def _step_create_generate_script(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        creative_brief = (
            context.get("define_objective", {}).get("creative_brief")
            or self._parse_create_objective(project.get("objective") or "")
        )
        timeline_segments = self._build_create_timeline_segments(
            creative_brief=creative_brief,
        )
        script_overview = self._build_script_overview(
            timeline_segments=timeline_segments,
            video_desc=creative_brief.get("product_name") or project["objective"],
        )
        storyboard = self._build_create_storyboard(
            timeline_segments=timeline_segments,
            creative_brief=creative_brief,
        )
        prompt = self._build_create_prompt(
            creative_brief=creative_brief,
            storyboard=storyboard,
        )
        video_generation = self._update_video_generation_state(
            project_id=project_id,
            project=project,
            script=script_overview,
            storyboard=storyboard,
            prompt=prompt,
            status="script_ready",
        )
        detail = "已生成创作脚本、时间轴和基础分镜，可直接用于调用视频模型。"
        self._update_project(
            project_id=project_id,
            script_overview=script_overview,
            timeline_segments=timeline_segments,
            summary=detail,
            video_generation=video_generation,
        )
        return {
            "creative_brief": creative_brief,
            "timeline_segments": timeline_segments,
            "script_overview": script_overview,
            "storyboard": storyboard,
            "prompt": prompt,
            "detail": detail,
        }

    async def _step_create_select_style(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        creative_brief = (
            context.get("generate_script", {}).get("creative_brief")
            or context.get("define_objective", {}).get("creative_brief")
            or self._parse_create_objective(project.get("objective") or "")
        )
        reference_frames = list(
            self._load_video_generation_state(project=project).get("reference_frames") or []
        )
        style_profile = {
            "video_type": creative_brief.get("video_type"),
            "style_preference": creative_brief.get("style_preference"),
            "target_audience": creative_brief.get("target_audience"),
            "reference_mode": "local_reference" if reference_frames else "prompt_only",
        }
        detail = (
            "已关联上传素材作为风格参考。"
            if reference_frames
            else "未提供额外参考素材，本次将按创作 Brief 直接生成。"
        )
        video_generation = self._update_video_generation_state(
            project_id=project_id,
            project=project,
            reference_frames=reference_frames,
        )
        self._update_project(
            project_id=project_id,
            summary=detail,
            video_generation=video_generation,
        )
        return {
            "style_profile": style_profile,
            "reference_frames": reference_frames,
            "detail": detail,
        }

    async def _step_create_generate_video(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        creative_brief = (
            context.get("generate_script", {}).get("creative_brief")
            or context.get("define_objective", {}).get("creative_brief")
            or self._parse_create_objective(project.get("objective") or "")
        )
        storyboard = context.get("generate_script", {}).get("storyboard") or deepcopy(DEFAULT_STORYBOARD)
        script_overview = context.get("generate_script", {}).get("script_overview") or deepcopy(DEFAULT_SCRIPT_OVERVIEW)
        prompt = (
            context.get("generate_script", {}).get("prompt")
            or self._load_video_generation_state(project=project).get("prompt")
            or self._build_create_prompt(
                creative_brief=creative_brief,
                storyboard=storyboard,
            )
        )
        aspect_ratio = "9:16"
        duration_seconds = 5
        resolution = self._resolution_from_aspect_ratio(aspect_ratio)
        request_payload = {
            "prompt": prompt,
            "negative_prompt": self._build_default_negative_prompt(intent_label="爆款创作"),
            "duration_seconds": duration_seconds,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "reference_frames": self._filter_remote_media_urls(
                context.get("select_style_reference", {}).get("reference_frames") or []
            ),
            "source_url": "",
            "storyboard": storyboard,
            "script": script_overview,
            "mode": "create",
            "objective": "爆款创作",
        }
        provider = self._resolve_video_generation_provider()
        submit_result = await self._submit_video_generation_task(
            provider=provider,
            request_payload=request_payload,
        )
        project = self._require_project(project_id=project_id)
        running_generation = self._update_video_generation_state(
            project_id=project_id,
            project=project,
            status="running",
            provider=provider["provider"],
            model=provider["display_model"],
            prompt=prompt,
            storyboard=storyboard,
            script=script_overview,
            provider_task_id=submit_result.get("provider_task_id"),
            result_video_url=submit_result.get("result_video_url"),
            error_detail=None,
        )
        self._update_project(
            project_id=project_id,
            summary=f"已向 {provider['label']} 提交创作视频生成任务。",
            video_generation=running_generation,
        )
        poll_result = await self._wait_for_video_generation_result(
            provider=provider,
            provider_task_id=str(running_generation.get("provider_task_id") or ""),
            existing_result_url=str(running_generation.get("result_video_url") or ""),
        )
        project = self._require_project(project_id=project_id)
        asset = await self._persist_generated_video_asset(
            project=project,
            request_payload=request_payload,
            provider=provider,
            generation_result=poll_result,
        )
        video_generation = self._update_video_generation_state(
            project_id=project_id,
            project=project,
            status="succeeded",
            provider=provider["provider"],
            model=provider["display_model"],
            asset_type="video",
            asset_name=asset["file_name"],
            asset_url=asset["public_url"],
            output_asset_id=asset["id"],
            result_video_url=poll_result.get("result_video_url"),
            error_detail=None,
        )
        detail = "创作视频已生成完成，并已写入资产库。"
        self._update_project(
            project_id=project_id,
            generated_media_url=asset["public_url"],
            summary=detail,
            video_generation=video_generation,
        )
        self._append_project_message(
            project_id=project_id,
            role="assistant",
            message_type="video_generation_result",
            content="创作视频已生成完成。",
            content_json={
                "result_video_url": poll_result.get("result_video_url"),
                "asset_url": asset["public_url"],
                "output_asset_id": asset["id"],
                "provider": provider["provider"],
                "model": provider["display_model"],
            },
        )
        return {
            "provider": provider,
            "asset": asset,
            "generation_result": poll_result,
            "detail": detail,
        }

    async def _step_create_post_production(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project = self._require_project(project_id=project_id)
        video_generation = self._load_video_generation_state(project=project)
        detail = (
            "已完成生成结果整理，当前版本沿用模型返回的成片音轨，并保留后续字幕压制扩展位。"
        )
        self._update_project(
            project_id=project_id,
            summary=detail,
            video_generation=video_generation,
        )
        return {"detail": detail}

    async def _step_create_finish(
        self,
        *,
        project_id: int,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        final_summary = "爆款创作工作流已完成，生成结果已入库到资产库。"
        self._update_project(
            project_id=project_id,
            status="succeeded",
            summary=final_summary,
            error_message=None,
        )
        return {"detail": final_summary}

    def _parse_key_value_objective(self, objective: str) -> dict[str, str]:
        pairs: dict[str, str] = {}
        for raw_line in (objective or "").splitlines():
            line = raw_line.strip().strip("；;")
            if not line:
                continue
            delimiter = "：" if "：" in line else ":" if ":" in line else None
            if not delimiter:
                continue
            key, value = line.split(delimiter, 1)
            normalized_key = key.strip()
            normalized_value = value.strip()
            if normalized_key and normalized_value:
                pairs[normalized_key] = normalized_value
        return pairs

    def _split_structured_values(self, raw_value: str | None) -> list[str]:
        normalized = str(raw_value or "").strip()
        if not normalized:
            return []
        items = re.split(r"[、,，/|；;]+", normalized)
        return [item.strip() for item in items if item and item.strip()]

    def _parse_remake_objective(self, objective: str) -> dict[str, Any]:
        kv_pairs = self._parse_key_value_objective(objective)
        task_type_text = (
            kv_pairs.get("任务类型")
            or kv_pairs.get("类型")
            or objective
        )
        intent_key = "viral_remake" if "爆款" in task_type_text or "viral" in task_type_text.lower() else "video_remake"
        keep_items = self._split_structured_values(kv_pairs.get("保留项") or kv_pairs.get("保留"))
        change_items = self._split_structured_values(kv_pairs.get("改写项") or kv_pairs.get("改动项"))
        return {
            "intent_key": intent_key,
            "intent_label": REMAKE_INTENT_LABELS.get(intent_key, "视频复刻"),
            "keep_items": keep_items or ["镜头节奏", "卖点结构"],
            "change_items": change_items or ["人物设定", "场景风格"],
            "target_platform": kv_pairs.get("目标平台") or "TikTok",
            "target_audience": kv_pairs.get("目标人群") or kv_pairs.get("目标客群") or "",
            "product_name": kv_pairs.get("商品名称") or "",
            "selling_points": self._split_structured_values(
                kv_pairs.get("商品卖点") or kv_pairs.get("卖点")
            ),
            "style_preference": kv_pairs.get("风格偏好") or kv_pairs.get("视频风格") or "",
            "raw_objective": (objective or "").strip(),
        }

    def _parse_create_objective(self, objective: str) -> dict[str, Any]:
        kv_pairs = self._parse_key_value_objective(objective)
        selling_points = self._split_structured_values(
            kv_pairs.get("我的商品卖点")
            or kv_pairs.get("商品卖点")
            or kv_pairs.get("卖点")
        )
        product_name = (
            kv_pairs.get("我的商品名称")
            or kv_pairs.get("商品名称")
            or "目标商品"
        )
        return {
            "video_type": kv_pairs.get("我希望创作的视频类型") or kv_pairs.get("视频类型") or "UGC种草",
            "target_audience": kv_pairs.get("我的目标客群") or kv_pairs.get("目标客群") or kv_pairs.get("目标人群") or "",
            "product_name": product_name,
            "selling_points": selling_points or [objective.strip() or "突出核心卖点"],
            "style_preference": kv_pairs.get("我倾向的视频风格") or kv_pairs.get("风格偏好") or "真实口播 + 生活化场景",
            "hook": kv_pairs.get("开场钩子") or "",
            "raw_objective": (objective or "").strip(),
        }

    def _build_create_timeline_segments(
        self,
        *,
        creative_brief: dict[str, Any],
    ) -> list[dict[str, Any]]:
        product_name = creative_brief.get("product_name") or "产品"
        selling_points = creative_brief.get("selling_points") or ["核心卖点"]
        hook = creative_brief.get("hook") or f"{product_name}最值得被记住的好处"
        style = creative_brief.get("style_preference") or "真实口播"
        segment_texts = [
            f"开场直接抛出钩子：{hook}，用 {style} 的镜头感迅速吸引停留。",
            f"中段展示 {product_name} 的核心使用场景，重点突出 {selling_points[0]}。",
            f"继续强化转化理由，补充 {'、'.join(selling_points[1:] or selling_points[:1])} 等细节证明。",
            f"结尾给出明确行动召唤，强调 {product_name} 适合谁以及为什么现在就要尝试。",
        ]
        durations = ((0, 3000), (3000, 9000), (9000, 15000), (15000, 21000))
        speakers = ("旁白", "口播", "口播", "旁白")
        return [
            {
                "id": index,
                "segment_type": "script",
                "speaker": speakers[index - 1],
                "start_ms": start_ms,
                "end_ms": end_ms,
                "content": content,
            }
            for index, ((start_ms, end_ms), content) in enumerate(
                zip(durations, segment_texts),
                start=1,
            )
        ]

    def _build_create_storyboard(
        self,
        *,
        timeline_segments: list[dict[str, Any]],
        creative_brief: dict[str, Any],
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for index, segment in enumerate(timeline_segments, start=1):
            items.append(
                {
                    "item_index": index,
                    "title": f"创作分镜 {index}",
                    "start_ms": int(segment.get("start_ms") or 0),
                    "end_ms": int(segment.get("end_ms") or 0),
                    "duration_ms": max(
                        0,
                        int(segment.get("end_ms") or 0) - int(segment.get("start_ms") or 0),
                    ),
                    "shot_type_code": "medium" if index in {2, 3} else "wide",
                    "camera_angle_code": "eye_level",
                    "camera_motion_code": "tracking" if index == 2 else "static",
                    "visual_description": (
                        f"{creative_brief.get('style_preference') or '生活化'} 场景下展示 "
                        f"{creative_brief.get('product_name') or '产品'}，对应文案：{segment.get('content') or ''}"
                    ),
                    "source_segment_indexes": [index],
                    "confidence": 0.76,
                }
            )
        return {
            "summary": f"围绕 {creative_brief.get('product_name') or '目标商品'} 生成 {len(items)} 条创作分镜。",
            "items": items,
        }

    def _build_reference_storyboard(
        self,
        *,
        shot_segments: list[dict[str, Any]],
        objective: str,
        source_name: str,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for index, segment in enumerate(shot_segments[:8], start=1):
            items.append(
                {
                    "item_index": index,
                    "title": segment.get("title") or self._build_shot_title(
                        index=index - 1,
                        total=max(len(shot_segments), 1),
                        objective=objective,
                        source_name=source_name,
                    ),
                    "start_ms": int(segment.get("start_ms") or 0),
                    "end_ms": int(segment.get("end_ms") or 0),
                    "duration_ms": int(segment.get("duration_ms") or 0),
                    "shot_type_code": segment.get("shot_type_code") or "medium",
                    "camera_angle_code": segment.get("camera_angle_code") or "eye_level",
                    "camera_motion_code": segment.get("camera_motion_code") or "static",
                    "visual_description": segment.get("visual_summary") or "",
                    "source_segment_indexes": [int(segment.get("segment_index") or index)],
                    "confidence": float(segment.get("confidence") or 0.7),
                }
            )
        summary = (
            f"已根据参考视频整理出 {len(items)} 条关键镜头，可用于保留节奏和卖点结构。"
            if items
            else "未提取到有效参考镜头，已退回文本描述生成。"
        )
        return {
            "summary": summary,
            "items": items,
        }

    def _build_create_prompt(
        self,
        *,
        creative_brief: dict[str, Any],
        storyboard: dict[str, Any],
    ) -> str:
        selling_points = "、".join(creative_brief.get("selling_points") or ["核心卖点"])
        storyboard_lines = [
            f"{item.get('item_index')}. {item.get('title')}: {item.get('visual_description')}"
            for item in (storyboard.get("items") or [])[:6]
        ]
        return "\n".join(
            [
                "请生成一条适合 TikTok/短视频平台投放的竖屏商业短视频。",
                f"视频类型：{creative_brief.get('video_type') or 'UGC种草'}",
                f"目标人群：{creative_brief.get('target_audience') or '泛目标消费人群'}",
                f"商品名称：{creative_brief.get('product_name') or '目标商品'}",
                f"核心卖点：{selling_points}",
                f"风格偏好：{creative_brief.get('style_preference') or '真实口播 + 快节奏镜头'}",
                "分镜要求：",
                *storyboard_lines,
                "请突出真实使用感、明确利益点和结尾行动召唤，整体节奏紧凑，适合短视频转化。",
            ]
        ).strip()

    def _build_remake_prompt(
        self,
        *,
        intent: dict[str, Any],
        source_analysis: dict[str, Any],
        storyboard: dict[str, Any],
        script_overview: dict[str, Any],
    ) -> str:
        keep_text = "、".join(intent.get("keep_items") or ["节奏结构"])
        change_text = "、".join(intent.get("change_items") or ["人物与场景"])
        storyboard_lines = [
            f"{item.get('item_index')}. {item.get('title')}: {item.get('visual_description')}"
            for item in (storyboard.get("items") or [])[:6]
        ]
        visual_summary = (
            (source_analysis.get("visual_features") or {}).get("summary")
            or "参考视频节奏紧凑，镜头围绕主体和卖点推进。"
        )
        script_text = (script_overview.get("full_text") or "").strip()
        return "\n".join(
            [
                f"任务目标：{intent.get('intent_label') or '视频复刻'}",
                f"保留项：{keep_text}",
                f"改写项：{change_text}",
                f"目标平台：{intent.get('target_platform') or 'TikTok'}",
                f"目标人群：{intent.get('target_audience') or '泛电商受众'}",
                (
                    f"商品卖点：{'、'.join(intent.get('selling_points') or [])}"
                    if intent.get("selling_points")
                    else ""
                ),
                f"风格偏好：{intent.get('style_preference') or '真实口播 + 生活化场景'}",
                f"参考视频视觉特征：{visual_summary}",
                "参考分镜：",
                *storyboard_lines,
                f"参考脚本：{script_text or '未识别到完整脚本，按镜头节奏和卖点结构重构。'}",
                "请在不复制原视频人物和具体场景的前提下，保留其节奏和卖点推进逻辑，生成原创版本。",
            ]
        ).strip()

    def _build_reference_fallback_timeline_segments(
        self,
        *,
        shot_segments: list[dict[str, Any]],
        objective: str,
        source_name: str,
    ) -> list[dict[str, Any]]:
        fallback_segments: list[dict[str, Any]] = []
        seen_contents: set[str] = set()
        for segment in shot_segments[:8]:
            candidates = (
                str(segment.get("transcript_text") or "").strip(),
                str(segment.get("ocr_text") or "").strip(),
                str(segment.get("visual_summary") or "").strip(),
                str(segment.get("title") or "").strip(),
            )
            content = next((item for item in candidates if item), "")
            normalized_content = content.strip()
            if not normalized_content or normalized_content in seen_contents:
                continue
            seen_contents.add(normalized_content)
            start_ms = int(segment.get("start_ms") or 0)
            end_ms = max(start_ms, int(segment.get("end_ms") or start_ms))
            fallback_segments.append(
                {
                    "id": len(fallback_segments) + 1,
                    "segment_type": "caption",
                    "speaker": "画面",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "content": normalized_content,
                }
            )

        if fallback_segments:
            return fallback_segments

        fallback_content = (
            str(objective or "").strip()
            or str(source_name or "").strip()
            or "参考视频以主体展示和卖点推进为主。"
        )
        return [
            {
                "id": 1,
                "segment_type": "caption",
                "speaker": "画面",
                "start_ms": 0,
                "end_ms": 1000,
                "content": fallback_content,
            }
        ]

    def _build_default_negative_prompt(self, *, intent_label: str) -> str:
        return (
            f"避免低清晰度、避免明显畸变、避免多余肢体、避免字幕乱码、避免直接复制原视频人物肖像，"
            f"保持 {intent_label} 的原创表达。"
        )

    def _aspect_ratio_from_meta(self, *, width: Any, height: Any) -> str:
        safe_width = self._safe_int(width)
        safe_height = self._safe_int(height)
        if safe_width <= 0 or safe_height <= 0:
            return "9:16"
        if safe_width == safe_height:
            return "1:1"
        return "9:16" if safe_height > safe_width else "16:9"

    def _duration_seconds_from_meta(self, duration_ms: Any) -> int:
        safe_duration_ms = self._safe_int(duration_ms)
        if safe_duration_ms <= 0:
            return 5
        return max(4, min(12, round(safe_duration_ms / 1000)))

    def _resolution_from_aspect_ratio(self, aspect_ratio: str) -> str:
        return "720P" if aspect_ratio in {"9:16", "16:9", "1:1"} else "720P"

    def _safe_int(self, value: Any) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
