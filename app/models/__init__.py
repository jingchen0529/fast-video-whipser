"""
ORM model registry.

Import all model modules here so their table metadata is registered
with Base.metadata.
"""

from app.db.base import Base

from app.models.auth import (
    AuthRateLimit,
    AuthSession,
    Menu,
    RefreshToken,
    Role,
    RoleMenu,
    User,
    UserRole,
)
from app.models.job import (
    Job,
    TaskQueueItem,
)
from app.models.asset import (
    MediaAsset,
    MotionAsset,
    SystemSetting,
)
from app.models.project import (
    Project,
    ProjectMessage,
    ProjectTaskStep,
    ShotSegment,
    Storyboard,
    StoryboardItem,
    StoryboardItemSegment,
)

__all__ = [
    "Base",
    # auth
    "User",
    "Role",
    "UserRole",
    "Menu",
    "RoleMenu",
    "RefreshToken",
    "AuthSession",
    "AuthRateLimit",
    # job
    "Job",
    "TaskQueueItem",
    # asset
    "MediaAsset",
    "MotionAsset",
    "SystemSetting",
    # project
    "Project",
    "ProjectMessage",
    "ProjectTaskStep",
    "ShotSegment",
    "Storyboard",
    "StoryboardItem",
    "StoryboardItemSegment",
]
