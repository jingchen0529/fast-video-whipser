"""
Analysis workflow: the 9-step video analysis pipeline.
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
        "segment_video_shots",
        "切分镜头片段",
        "基于 PySceneDetect 切分视频镜头，并生成基础镜头段。",
    ),
    TaskStepDefinition(
        "analyze_video_content",
        "分析视频内容",
        "提取镜头特征，整理画面节奏、运镜和内容主题。",
    ),
    TaskStepDefinition(
        "identify_audio_content",
        "识别音频内容",
        "提取音轨、转写口播，并识别字幕文本。",
    ),
    TaskStepDefinition(
        "generate_storyboard",
        "生成分镜结构",
        "结合镜头段、脚本和画面特征生成结构化分镜表。",
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


@WorkflowRegistry.register
class AnalysisWorkflow(WorkflowDefinition):
    """9-step video analysis workflow."""

    workflow_type = "analysis"

    def __init__(self):
        super().__init__()
        self._setup_steps()

    def _setup_steps(self) -> None:
        from app.services.project_service import ProjectService
        self._service = ProjectService()

        steps_config = [
            (ANALYSIS_TASK_STEPS[0], self._extract_video_link, True),
            (ANALYSIS_TASK_STEPS[1], self._validate_video_link, True),
            (ANALYSIS_TASK_STEPS[2], self._segment_video_shots, True),
            (ANALYSIS_TASK_STEPS[3], self._analyze_video_content, True),
            (ANALYSIS_TASK_STEPS[4], self._identify_audio_content, True),
            (ANALYSIS_TASK_STEPS[5], self._generate_storyboard, True),
            (ANALYSIS_TASK_STEPS[6], self._generate_response, False),
            (ANALYSIS_TASK_STEPS[7], self._generate_suggestions, False),
            (ANALYSIS_TASK_STEPS[8], self._finish, True),
        ]
        for definition, handler, append_msg in steps_config:
            self.register_step(definition, handler, append_status_message=append_msg)

    async def _extract_video_link(self, ctx: WorkflowContext) -> dict[str, Any]:
        return await self._service._step_extract_video_link(project_id=ctx.project_id)

    async def _validate_video_link(self, ctx: WorkflowContext) -> dict[str, Any]:
        # Build legacy context dict that _step_validate_video_link expects
        context = self._build_legacy_context(ctx)
        return await self._service._step_validate_video_link(
            project_id=ctx.project_id,
            context=context,
        )

    async def _segment_video_shots(self, ctx: WorkflowContext) -> dict[str, Any]:
        context = self._build_legacy_context(ctx)
        return await self._service._step_segment_video_shots(
            project_id=ctx.project_id,
            context=context,
        )

    async def _analyze_video_content(self, ctx: WorkflowContext) -> dict[str, Any]:
        context = self._build_legacy_context(ctx)
        return await self._service._step_analyze_video_content(
            project_id=ctx.project_id,
            context=context,
        )

    async def _identify_audio_content(self, ctx: WorkflowContext) -> dict[str, Any]:
        context = self._build_legacy_context(ctx)
        return await self._service._step_identify_audio_content(
            project_id=ctx.project_id,
            context=context,
        )

    async def _generate_storyboard(self, ctx: WorkflowContext) -> dict[str, Any]:
        context = self._build_legacy_context(ctx)
        return await self._service._step_generate_storyboard(
            project_id=ctx.project_id,
            context=context,
        )

    async def _generate_response(self, ctx: WorkflowContext) -> dict[str, Any]:
        context = self._build_legacy_context(ctx)
        return await self._service._step_generate_response(
            project_id=ctx.project_id,
            context=context,
        )

    async def _generate_suggestions(self, ctx: WorkflowContext) -> dict[str, Any]:
        context = self._build_legacy_context(ctx)
        return await self._service._step_generate_suggestions(
            project_id=ctx.project_id,
            context=context,
        )

    async def _finish(self, ctx: WorkflowContext) -> dict[str, Any]:
        context = self._build_legacy_context(ctx)
        return await self._service._step_finish(
            project_id=ctx.project_id,
            context=context,
        )

    def _build_legacy_context(self, ctx: WorkflowContext) -> dict[str, Any]:
        """Convert WorkflowContext to the legacy dict format expected by step methods."""
        legacy: dict[str, Any] = {}
        for step_key in (
            "extract_video_link",
            "validate_video_link",
            "segment_video_shots",
            "analyze_video_content",
            "identify_audio_content",
            "generate_storyboard",
            "generate_response",
            "generate_suggestions",
        ):
            if step_key in ctx:
                legacy[step_key] = ctx[step_key]
        return legacy
