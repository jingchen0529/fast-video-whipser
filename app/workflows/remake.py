"""
Video Remake workflow: copying motion assets into new creative videos.
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
        "select_source_asset",
        "选择动作资产",
        "从库中选择作为复刻参照的动作资产（Motion Asset）。",
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
        "evaluate_copyright_distance",
        "版权风险评估",
        "通过视觉相似度对生成结果进行版权距离评估，确保原创性合规。",
    ),
    TaskStepDefinition(
        "save_result",
        "保存复刻结果",
        "将生成的视频资产入库，并关联原始参考资产的血缘关系。",
    ),
)


@WorkflowRegistry.register
class RemakeWorkflow(WorkflowDefinition):
    """6-step video remake workflow."""

    workflow_type = "remake"

    def __init__(self):
        super().__init__()
        self._setup_steps()

    def _setup_steps(self) -> None:
        from app.services.project_service import ProjectService
        self._service = ProjectService()

        steps_config = [
            (REMAKE_TASK_STEPS[0], self._select_source_asset, True),
            (REMAKE_TASK_STEPS[1], self._define_remake_intent, True),
            (REMAKE_TASK_STEPS[2], self._build_remake_prompt, True),
            (REMAKE_TASK_STEPS[3], self._generate_video, True),
            (REMAKE_TASK_STEPS[4], self._evaluate_copyright_distance, True),
            (REMAKE_TASK_STEPS[5], self._save_result, True),
        ]
        for definition, handler, append_msg in steps_config:
            self.register_step(definition, handler, append_status_message=append_msg)

    async def _select_source_asset(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_remake_select_source(project_id=ctx.project_id)

    async def _define_remake_intent(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_remake_define_intent(project_id=ctx.project_id)

    async def _build_remake_prompt(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_remake_build_prompt(project_id=ctx.project_id)

    async def _generate_video(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_remake_generate_video(project_id=ctx.project_id)

    async def _evaluate_copyright_distance(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_remake_evaluate_copyright(project_id=ctx.project_id)

    async def _save_result(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_remake_save_result(project_id=ctx.project_id)
