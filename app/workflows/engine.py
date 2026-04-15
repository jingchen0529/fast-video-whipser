"""
Generic workflow engine supporting pluggable step chains.
"""
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.auth.security import utcnow_iso

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TaskStepDefinition:
    """Defines a single step in a workflow."""
    step_key: str
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class StepResult:
    """Result returned by a step handler."""
    detail: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {**self.data, "detail": self.detail}


class WorkflowContext:
    """Mutable context passed through the workflow execution."""

    def __init__(self, project_id: int, project: dict[str, Any]):
        self.project_id = project_id
        self.project = project
        self._results: dict[str, dict[str, Any]] = {}

    def set_result(self, step_key: str, result: dict[str, Any]) -> None:
        self._results[step_key] = result

    def get_result(self, step_key: str) -> dict[str, Any]:
        return self._results.get(step_key, {})

    def __getitem__(self, step_key: str) -> dict[str, Any]:
        return self.get_result(step_key)

    def __contains__(self, step_key: str) -> bool:
        return step_key in self._results


StepHandler = Callable[[WorkflowContext], Awaitable[dict[str, Any]]]


class WorkflowDefinition:
    """
    A named workflow with an ordered list of step definitions and handlers.
    Subclass this or use `register_step` to build a workflow.
    """

    workflow_type: str = ""

    def __init__(self):
        self._steps: list[tuple[TaskStepDefinition, StepHandler, bool]] = []

    def register_step(
        self,
        definition: TaskStepDefinition,
        handler: StepHandler,
        *,
        append_status_message: bool = True,
    ) -> None:
        """Register a step definition with its async handler."""
        self._steps.append((definition, handler, append_status_message))

    @property
    def step_definitions(self) -> tuple[TaskStepDefinition, ...]:
        return tuple(defn for defn, _, _ in self._steps)

    @property
    def steps(self) -> list[tuple[TaskStepDefinition, StepHandler, bool]]:
        return list(self._steps)


class WorkflowRegistry:
    """Global registry of workflow definitions, keyed by workflow_type."""

    _workflows: dict[str, type[WorkflowDefinition]] = {}

    @classmethod
    def register(cls, workflow_class: type[WorkflowDefinition]) -> type[WorkflowDefinition]:
        """Decorator or direct call to register a workflow class."""
        wf_type = workflow_class.workflow_type
        if not wf_type:
            raise ValueError(f"WorkflowDefinition subclass {workflow_class.__name__} must set workflow_type")
        cls._workflows[wf_type] = workflow_class
        return workflow_class

    @classmethod
    def get(cls, workflow_type: str) -> type[WorkflowDefinition] | None:
        return cls._workflows.get(workflow_type)

    @classmethod
    def supported_types(cls) -> set[str]:
        return set(cls._workflows.keys())

    @classmethod
    def get_step_definitions(cls, workflow_type: str) -> tuple[TaskStepDefinition, ...]:
        """Return step definitions for a workflow type, or fallback unsupported steps."""
        wf_class = cls.get(workflow_type)
        if wf_class is None:
            return UNSUPPORTED_WORKFLOW_STEPS
        return wf_class().step_definitions


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


class WorkflowEngine:
    """
    Executes a workflow by running its registered steps in sequence.
    Handles step status updates, error handling, and project messages.
    """

    def __init__(self):
        from app.services.project_service import ProjectService
        self._project_service = ProjectService()

    async def run(self, *, project_id: int) -> None:
        """Execute the workflow for a given project."""
        project = self._get_project(project_id)
        if project is None:
            return

        workflow_type = project.get("workflow_type", "analysis")
        wf_class = WorkflowRegistry.get(workflow_type)

        if wf_class is None:
            message = "当前仅接入分析脚本工作流，复刻爆款和创作爆款工作流稍后接入。"
            self._fail_unsupported_workflow(project_id=project_id, message=message)
            return

        workflow = wf_class()
        ctx = WorkflowContext(project_id=project_id, project=project)

        try:
            for definition, handler, append_status_message in workflow.steps:
                result = await self._execute_step(
                    project_id=project_id,
                    definition=definition,
                    handler=handler,
                    ctx=ctx,
                    append_status_message=append_status_message,
                )
                ctx.set_result(definition.step_key, result)
        except Exception:
            # _execute_step already handles failure recording
            return

    async def _execute_step(
        self,
        *,
        project_id: int,
        definition: TaskStepDefinition,
        handler: StepHandler,
        ctx: WorkflowContext,
        append_status_message: bool = True,
    ) -> dict[str, Any]:
        self._set_step_status(
            project_id=project_id,
            step_key=definition.step_key,
            status="in_progress",
            detail=definition.description,
        )

        try:
            result = await handler(ctx)
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

    def _fail_unsupported_workflow(self, *, project_id: int, message: str) -> None:
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

    # ── Delegate to ProjectService for DB operations ──

    def _get_project(self, project_id: int) -> dict[str, Any] | None:
        return self._project_service._get_project_for_execution(project_id=project_id)

    def _set_step_status(self, **kwargs) -> None:
        self._project_service._set_step_status(**kwargs)

    def _update_project(self, **kwargs) -> None:
        self._project_service._update_project(**kwargs)

    def _append_project_message(self, **kwargs) -> None:
        self._project_service._append_project_message(**kwargs)
