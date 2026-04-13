"""
Video Create workflow: Generating completely new creative videos from text/image.
"""
import logging
from typing import Any

from app.workflows.engine import (
    TaskStepDefinition,
    WorkflowContext,
    WorkflowDefinition,
    WorkflowRegistry,
)

logger = logging.getLogger(__name__)

CREATE_TASK_STEPS = (
    TaskStepDefinition(
        "define_objective",
        "确认创作目标",
        "基于用户输入的指令（如：宠物带货视频）解析创作的主题、受众与带货意图。",
    ),
    TaskStepDefinition(
        "generate_script",
        "生成创作脚本",
        "AI 构造创意剧本、分镜描述和推荐口播内容。",
    ),
    TaskStepDefinition(
        "select_style_reference",
        "选择参考风格",
        "关联视觉风格参考，包括配色方案、运镜风格等素材预置。",
    ),
    TaskStepDefinition(
        "generate_video",
        "执行视频生成",
        "调用视频生成引擎完成初版视频生成。",
    ),
    TaskStepDefinition(
        "post_production",
        "后期合成处理",
        "完成背景音乐（BGM）匹配、字幕压制与节奏校正。",
    ),
    TaskStepDefinition(
        "finish",
        "全部完成",
        "视频创作工作流全部步骤已完成。",
    ),
)


@WorkflowRegistry.register
class CreateWorkflow(WorkflowDefinition):
    """6-step video creation workflow."""

    workflow_type = "create"

    def __init__(self):
        super().__init__()
        self._setup_steps()

    def _setup_steps(self) -> None:
        from app.services.project_service import ProjectService
        self._service = ProjectService()

        steps_config = [
            (CREATE_TASK_STEPS[0], self._define_objective, True),
            (CREATE_TASK_STEPS[1], self._generate_script, True),
            (CREATE_TASK_STEPS[2], self._select_style_reference, True),
            (CREATE_TASK_STEPS[3], self._generate_video, True),
            (CREATE_TASK_STEPS[4], self._post_production, True),
            (CREATE_TASK_STEPS[5], self._finish, True),
        ]
        for definition, handler, append_msg in steps_config:
            self.register_step(definition, handler, append_status_message=append_msg)

    async def _define_objective(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_create_define_objective(project_id=ctx.project_id)

    async def _generate_script(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_create_generate_script(
            project_id=ctx.project_id,
            context=self._build_legacy_context(ctx),
        )

    async def _select_style_reference(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_create_select_style(
            project_id=ctx.project_id,
            context=self._build_legacy_context(ctx),
        )

    async def _generate_video(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_create_generate_video(
            project_id=ctx.project_id,
            context=self._build_legacy_context(ctx),
        )

    async def _post_production(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_create_post_production(
            project_id=ctx.project_id,
            context=self._build_legacy_context(ctx),
        )

    async def _finish(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_create_finish(
            project_id=ctx.project_id,
            context=self._build_legacy_context(ctx),
        )

    def _build_legacy_context(self, ctx: WorkflowContext) -> dict[str, Any]:
        legacy: dict[str, Any] = {}
        for step_key in (
            "define_objective",
            "generate_script",
            "select_style_reference",
            "generate_video",
            "post_production",
        ):
            if step_key in ctx:
                legacy[step_key] = ctx[step_key]
        return legacy
