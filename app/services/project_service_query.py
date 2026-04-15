"""Project query and persistence helpers."""
from app.services.project_service_shared import *  # noqa: F401,F403


class ProjectQueryMixin:
    @property
    def SUPPORTED_WORKFLOWS(self) -> set[str]:
        """Dynamically returns all registered workflow types."""
        return WorkflowRegistry.supported_types()

    def list_projects(self, *, user_id: str) -> list[dict[str, Any]]:
        session = _get_session()
        try:
            rows = ProjectRepository(session).list_by_user(user_id)
            return [self._row_to_project_list_item(row) for row in rows]
        finally:
            session.close()

    def get_project_detail(
        self,
        *,
        project_id: int,
        user_id: str,
    ) -> dict[str, Any] | None:
        session = _get_session()
        try:
            project_obj = ProjectRepository(session).get_by_id_and_owner(
                project_id=project_id,
                user_id=user_id,
            )
            if project_obj is None:
                return None

            item = self._row_to_project_detail(project_obj)
            item["shot_segments"] = self._load_shot_segments(
                session=session,
                project_id=project_id,
            )
            item["storyboard"] = self._load_latest_storyboard(
                session=session,
                project_id=project_id,
            ) or self._build_legacy_storyboard(
                timeline_segments=item["timeline_segments"],
                video_generation=item["video_generation"],
            )
            self._ensure_project_task_steps(
                session=session,
                project_id=project_id,
                workflow_type=item["workflow_type"],
            )
            item["task_steps"] = self._load_project_steps(
                session=session,
                project_id=project_id,
            )
            item["messages"] = self._load_project_messages(
                session=session,
                project_id=project_id,
            )
            return item
        finally:
            session.close()

    def _row_to_project_list_item(self, row: Project) -> dict[str, Any]:
        return {
            "id": row.id,
            "title": row.title or "",
            "source_url": row.source_url or "",
            "source_platform": row.source_platform or "local",
            "workflow_type": row.workflow_type or "analysis",
            "source_type": row.source_type or "upload",
            "source_name": row.source_name or "",
            "status": row.status or "queued",
            "media_url": row.media_url,
            "generated_media_url": row.generated_media_url,
            "objective": row.objective or "",
            "summary": row.summary or "",
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _row_to_project_detail(self, row: Project) -> dict[str, Any]:
        item = self._row_to_project_list_item(row)
        item["script_overview"] = self._load_json_field(
            row.script_overview_json,
            DEFAULT_SCRIPT_OVERVIEW,
        )
        item["ecommerce_analysis"] = self._load_json_field(
            row.ecommerce_analysis_json,
            DEFAULT_ECOMMERCE_ANALYSIS,
        )
        item["source_analysis"] = self._load_json_field(
            row.source_analysis_json,
            DEFAULT_SOURCE_ANALYSIS,
        )
        item["timeline_segments"] = self._load_json_field(
            row.timeline_segments_json,
            [],
        )
        item["video_generation"] = self._load_json_field(
            row.video_generation_json,
            DEFAULT_VIDEO_GENERATION,
        )
        item["source_asset_id"] = row.source_asset_id
        item["user_id"] = row.user_id
        item["shot_segments"] = []
        item["storyboard"] = deepcopy(DEFAULT_STORYBOARD)
        item["messages"] = []
        return item

    def _load_project_steps(
        self,
        *,
        session: Session,
        project_id: int,
    ) -> list[dict[str, Any]]:
        rows = ProjectTaskStepRepository(session).list_by_project(project_id)
        return [
            {
                "id": r.id,
                "step_key": r.step_key,
                "title": r.title,
                "detail": r.detail,
                "status": r.status,
                "error_detail": r.error_detail,
                "display_order": r.display_order,
                "updated_at": r.updated_at,
            }
            for r in rows
        ]

    def _ensure_project_task_steps(
        self,
        *,
        session: Session,
        project_id: int,
        workflow_type: str,
    ) -> None:
        step_repo = ProjectTaskStepRepository(session)
        step_definitions = self._get_step_definitions(workflow_type)
        expected_step_keys = [definition.step_key for definition in step_definitions]
        existing_rows_orm = step_repo.list_by_project(project_id)
        existing_rows = [
            {
                "step_key": r.step_key,
                "title": r.title,
                "detail": r.detail,
                "status": r.status,
                "error_detail": r.error_detail,
                "output_json": r.output_json,
                "display_order": r.display_order,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in existing_rows_orm
        ]
        current_step_keys = [row.get("step_key") for row in existing_rows]

        if current_step_keys == expected_step_keys:
            return

        rebuilt_rows = self._rebuild_project_task_steps(
            project_id=project_id,
            workflow_type=workflow_type,
            existing_rows=existing_rows,
        )
        now = utcnow_ms()
        step_repo.delete_by_project(project_id)
        rebuilt_step_rows: list[ProjectTaskStep] = []
        for row in rebuilt_rows:
            rebuilt_step_rows.append(ProjectTaskStep(
                project_id=project_id,
                step_key=row["step_key"],
                title=row["title"],
                detail=row["detail"],
                status=row["status"],
                error_detail=row.get("error_detail"),
                output_json=row.get("output_json"),
                display_order=row["display_order"],
                created_at=row.get("created_at") or now,
                updated_at=row.get("updated_at") or now,
            ))
        step_repo.add_many(rebuilt_step_rows)
        session.commit()

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
        now = utcnow_ms()
        rows_by_key = {
            str(row.get("step_key") or "").strip(): row
            for row in existing_rows
            if str(row.get("step_key") or "").strip()
        }

        if workflow_type == "analysis":
            legacy_analyze_row = rows_by_key.get("analyze_video_content")
            if legacy_analyze_row is not None and definition.step_key in {
                "segment_video_shots",
                "generate_storyboard",
            }:
                detail = {
                    "segment_video_shots": "旧版任务兼容补齐：已根据历史项目状态补齐镜头切分步骤，并沿用既有画面分析进度。",
                    "generate_storyboard": "旧版任务兼容补齐：已根据历史项目状态补齐分镜生成步骤，并沿用既有画面分析进度。",
                }[definition.step_key]
                return {
                    "step_key": definition.step_key,
                    "title": definition.title,
                    "detail": detail,
                    "status": legacy_analyze_row.get("status") or "pending",
                    "error_detail": legacy_analyze_row.get("error_detail"),
                    "output_json": legacy_analyze_row.get("output_json"),
                    "display_order": display_order,
                    "created_at": legacy_analyze_row.get("created_at") or now,
                    "updated_at": legacy_analyze_row.get("updated_at") or now,
                }

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
        now = utcnow_ms()
        session = _get_session()
        try:
            step_repo = ProjectTaskStepRepository(session)
            project_repo = ProjectRepository(session)
            step = step_repo.get_by_step_key(project_id, step_key)
            if step is not None:
                step.status = status
                step.detail = detail
                step.error_detail = error_detail
                if output is not None:
                    step.output_json = json.dumps(output, ensure_ascii=False)
                step.updated_at = now

            project_obj = project_repo.get_by_id(project_id)
            if project_obj is not None:
                project_obj.updated_at = now

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _update_project(
        self,
        *,
        project_id: int,
        **fields: Any,
    ) -> None:
        if not fields:
            return

        now = utcnow_ms()
        session = _get_session()
        try:
            project_obj = ProjectRepository(session).get_by_id(project_id)
            if project_obj is None:
                return
            for field_name, value in fields.items():
                if field_name in JSON_PROJECT_COLUMNS:
                    setattr(project_obj, JSON_PROJECT_COLUMNS[field_name], json.dumps(value, ensure_ascii=False))
                else:
                    setattr(project_obj, field_name, value)
            project_obj.updated_at = now
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _append_project_message_record(
        self,
        *,
        session: Session,
        project_id: int,
        role: str,
        message_type: str,
        content: str,
        content_json: dict[str, Any] | None = None,
        created_at: int | None = None,
        reply_to_message_id: str | None = None,
    ) -> str:
        now = created_at or utcnow_ms()
        message_repo = ProjectMessageRepository(session)
        project_repo = ProjectRepository(session)
        latest_ts = message_repo.get_max_created_at(project_id) or 0
        if int(latest_ts) >= now:
            now = int(latest_ts) + 1
        message_id = uuid.uuid4().hex
        msg = ProjectMessage(
            id=message_id,
            project_id=project_id,
            role=role,
            message_type=message_type,
            content=content,
            content_json=json.dumps(content_json, ensure_ascii=False) if content_json is not None else None,
            reply_to_message_id=reply_to_message_id,
            created_at=now,
        )
        message_repo.add(msg)
        session.flush()
        # Update project updated_at
        project_obj = project_repo.get_by_id(project_id)
        if project_obj is not None:
            project_obj.updated_at = now
        return message_id

    def _append_project_message(
        self,
        *,
        project_id: int,
        role: str,
        message_type: str,
        content: str,
        content_json: dict[str, Any] | None = None,
    ) -> str | None:
        project = self._get_project_for_execution(project_id=project_id)
        if project is None:
            return None

        session = _get_session()
        try:
            message_id = self._append_project_message_record(
                session=session,
                project_id=project_id,
                role=role,
                message_type=message_type,
                content=content,
                content_json=content_json,
            )
            session.commit()
            return message_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _load_project_messages(
        self,
        *,
        session: Session,
        project_id: int,
    ) -> list[dict[str, Any]]:
        rows = ProjectMessageRepository(session).list_by_project(project_id)
        items: list[dict[str, Any]] = []
        for row in rows:
            item: dict[str, Any] = {
                "id": row.id,
                "role": row.role,
                "message_type": row.message_type,
                "content": row.content,
                "content_json": self._load_json_field(row.content_json, {}) if row.content_json else None,
                "reply_to_message_id": row.reply_to_message_id,
                "created_at": row.created_at,
            }
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
            "remake": "视频复刻",
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

    def _build_workflow_acceptance_message(
        self,
        *,
        workflow_type: str,
        objective: str,
    ) -> str:
        if workflow_type == "remake":
            remake_intent = self._parse_remake_objective(objective)["intent_label"]
            return (
                f"收到，我会先确认参考素材和复刻意图，再调用系统配置的视频模型执行{remake_intent}，"
                "最后把结果写回资产库。"
            )
        if workflow_type == "create":
            return "收到，我会先拆解创作目标并生成脚本，再调用视频模型产出初版素材。"
        return "收到，我会先提取视频链接并完成脚本分析，然后把拆解结果和优化建议整理给你。"

    def _require_project(self, *, project_id: int) -> dict[str, Any]:
        project = self._get_project_for_execution(project_id=project_id)
        if project is None:
            raise ValueError("项目不存在。")
        return project

    def _get_project_for_execution(self, *, project_id: int) -> dict[str, Any] | None:
        session = _get_session()
        try:
            project_obj = ProjectRepository(session).get_by_id(project_id)
            if project_obj is None:
                return None
            return self._row_to_project_detail(project_obj)
        finally:
            session.close()

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

    async def add_followup_message(
        self,
        *,
        project_id: int,
        user_id: str,
        content: str,
    ) -> dict[str, Any]:
        session = _get_session()
        try:
            project_obj = ProjectRepository(session).get_by_id_and_owner(
                project_id=project_id,
                user_id=user_id,
            )
            if project_obj is None:
                raise HTTPException(status_code=404, detail="项目不存在。")

            project_data = self._row_to_project_detail(project_obj)
            now = utcnow_ms()

            # Append user message
            self._append_project_message_record(
                session=session,
                project_id=project_id,
                role="user",
                message_type="chat_question",
                content=content,
                created_at=now,
            )

            # Load history for AI
            history = self._load_project_messages(
                session=session,
                project_id=project_id,
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
            ai_created_at = utcnow_ms()
            ai_message_id = self._append_project_message_record(
                session=session,
                project_id=project_id,
                role="assistant",
                message_type="chat_reply",
                content=ai_reply["content"],
                content_json={
                    "provider": ai_reply["provider"],
                    "model": ai_reply["model"],
                },
                created_at=ai_created_at,
            )

            session.commit()

            return {
                "id": ai_message_id,
                "role": "assistant",
                "content": ai_reply["content"],
                "created_at": ai_created_at,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_project_title(self, *, project_id: int, user_id: str, title: str) -> bool:
        project = self.get_project_detail(project_id=project_id, user_id=user_id)
        if not project:
            return False
        self._update_project(project_id=project_id, title=title)
        return True

    def delete_project(self, *, project_id: int, user_id: str) -> bool:
        session = _get_session()
        try:
            project_repo = ProjectRepository(session)
            project_obj = project_repo.get_by_id_and_owner(project_id, user_id)
            if not project_obj:
                return False

            ProjectMessageRepository(session).delete_by_project(project_id)
            ProjectTaskStepRepository(session).delete_by_project(project_id)
            project_repo.delete(project_obj)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
