"""Facade for the split ProjectService implementation."""
from app.services.project_service_shared import *  # noqa: F401,F403
from app.services.project_service_provider import ProjectProviderMixin
from app.services.project_service_query import ProjectQueryMixin
from app.services.project_service_storyboard import ProjectStoryboardMixin
from app.services.project_service_workflow import ProjectWorkflowMixin


class ProjectService(
    ProjectWorkflowMixin,
    ProjectProviderMixin,
    ProjectStoryboardMixin,
    ProjectQueryMixin,
):
    """Composite project service split by responsibility."""

    pass


__all__ = [name for name in globals() if not name.startswith("__")]
