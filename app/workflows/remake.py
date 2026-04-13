"""
Video Remake workflow: remaking videos from uploaded or linked references.
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

REMAKE_TASK_STEPS = (
    TaskStepDefinition(
        "extract_video_link",
        "提取视频链接",
        "从用户输入中提取复刻参考视频链接或上传素材地址。",
    ),
    TaskStepDefinition(
        "validate_video_link",
        "验证视频链接",
        "校验参考视频链接协议、来源平台和基础可访问性；上传素材则直接确认可用。",
    ),
    TaskStepDefinition(
        "analyze_reference_video",
        "分析参考视频",
        "提取参考视频的节奏、镜头、主体和卖点结构，作为复刻生成的输入基础。",
    ),
    TaskStepDefinition(
        "define_remake_intent",
        "确认复刻意图",
        "对比参考视频，确认需要保留的元素（如动作、节奏）与需要改写的元素（如风格、场景）。",
    ),
    TaskStepDefinition(
        "build_remake_prompt",
        "构造生成指令",
        "结合动作特征、镜头语言与用户指令，生成用于视频 AI 的结构化 Prompt。",
    ),
    TaskStepDefinition(
        "generate_video",
        "执行视频生成",
        "调用视频生成引擎（如 Kling/Runway）进行创作，这一步可能需要 1-3 分钟。",
    ),
    TaskStepDefinition(
        "poll_generation_result",
        "轮询生成结果",
        "持续查询第三方视频生成任务状态，成功后下载结果并准备入库。",
    ),
    TaskStepDefinition(
        "finish",
        "全部完成",
        "将复刻视频写入动态资产并更新项目为完成状态。",
    ),
)


@WorkflowRegistry.register
class RemakeWorkflow(WorkflowDefinition):
    """8-step video remake workflow."""

    workflow_type = "remake"

    def __init__(self):
        super().__init__()
        self._setup_steps()

    def _setup_steps(self) -> None:
        from app.services.project_service import ProjectService
        self._service = ProjectService()

        steps_config = [
            (REMAKE_TASK_STEPS[0], self._extract_video_link, True),
            (REMAKE_TASK_STEPS[1], self._validate_video_link, True),
            (REMAKE_TASK_STEPS[2], self._analyze_reference_video, True),
            (REMAKE_TASK_STEPS[3], self._define_remake_intent, True),
            (REMAKE_TASK_STEPS[4], self._build_remake_prompt, True),
            (REMAKE_TASK_STEPS[5], self._generate_video, True),
            (REMAKE_TASK_STEPS[6], self._poll_generation_result, True),
            (REMAKE_TASK_STEPS[7], self._finish, True),
        ]
        for definition, handler, append_msg in steps_config:
            self.register_step(definition, handler, append_status_message=append_msg)

    async def _extract_video_link(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_extract_video_link(project_id=ctx.project_id)

    async def _validate_video_link(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_validate_video_link(
            project_id=ctx.project_id,
            context=self._build_legacy_context(ctx),
        )

    async def _analyze_reference_video(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_remake_analyze_reference(
            project_id=ctx.project_id,
            context=self._build_legacy_context(ctx),
        )

    async def _define_remake_intent(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_remake_define_intent(
            project_id=ctx.project_id,
            context=self._build_legacy_context(ctx),
        )

    async def _build_remake_prompt(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_remake_build_prompt(
            project_id=ctx.project_id,
            context=self._build_legacy_context(ctx),
        )

    async def _generate_video(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_remake_generate_video(
            project_id=ctx.project_id,
            context=self._build_legacy_context(ctx),
        )

    async def _poll_generation_result(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_remake_poll_generation_result(
            project_id=ctx.project_id,
            context=self._build_legacy_context(ctx),
        )

    async def _finish(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_remake_finish(
            project_id=ctx.project_id,
            context=self._build_legacy_context(ctx),
        )

    def _build_legacy_context(self, ctx: WorkflowContext) -> dict[str, Any]:
        legacy: dict[str, Any] = {}
        for step_key in (
            "extract_video_link",
            "validate_video_link",
            "analyze_reference_video",
            "define_remake_intent",
            "build_remake_prompt",
            "generate_video",
            "poll_generation_result",
        ):
            if step_key in ctx:
                legacy[step_key] = ctx[step_key]
        return legacy
