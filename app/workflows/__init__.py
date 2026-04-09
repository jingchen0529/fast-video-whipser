"""
Workflow engine and definitions.

Import this package to ensure all workflows are registered with the WorkflowRegistry.
"""
from app.workflows.engine import (
    TaskStepDefinition,
    StepResult,
    WorkflowContext,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowRegistry,
    UNSUPPORTED_WORKFLOW_STEPS,
)
from app.workflows.analysis import AnalysisWorkflow, ANALYSIS_TASK_STEPS
from app.workflows.remake import RemakeWorkflow, REMAKE_TASK_STEPS
from app.workflows.create import CreateWorkflow, CREATE_TASK_STEPS

__all__ = [
    "TaskStepDefinition",
    "StepResult",
    "WorkflowContext",
    "WorkflowDefinition",
    "WorkflowEngine",
    "WorkflowRegistry",
    "AnalysisWorkflow",
    "ANALYSIS_TASK_STEPS",
    "RemakeWorkflow",
    "REMAKE_TASK_STEPS",
    "CreateWorkflow",
    "CREATE_TASK_STEPS",
    "UNSUPPORTED_WORKFLOW_STEPS",
]
