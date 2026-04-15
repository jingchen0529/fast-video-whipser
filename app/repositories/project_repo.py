"""
Project repository — low-level ORM queries for Project, ProjectMessage,
ProjectTaskStep, ShotSegment, Storyboard, StoryboardItem, StoryboardItemSegment.
"""
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.project import (
    Project,
    ProjectMessage,
    ProjectTaskStep,
    ShotSegment,
    Storyboard,
    StoryboardItem,
    StoryboardItemSegment,
)


class ProjectRepository:
    """Query helpers for the ``projects`` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, project_id: int) -> Project | None:
        return self._session.get(Project, project_id)

    def add(self, project: Project) -> Project:
        self._session.add(project)
        return project

    def delete(self, project: Project) -> None:
        self._session.delete(project)

    def get_by_id_and_owner(self, project_id: int, user_id: str) -> Project | None:
        return self._session.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id,
            )
        )

    def list_by_user(self, user_id: str) -> list[Project]:
        return list(
            self._session.scalars(
                select(Project)
                .where(Project.user_id == user_id)
                .order_by(Project.updated_at.desc(), Project.id.desc())
            ).all()
        )


class ProjectMessageRepository:
    """Query helpers for the ``project_messages`` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, message: ProjectMessage) -> ProjectMessage:
        self._session.add(message)
        return message

    def delete_by_project(self, project_id: int) -> None:
        self._session.execute(
            delete(ProjectMessage).where(ProjectMessage.project_id == project_id)
        )

    def list_by_project(self, project_id: int) -> list[ProjectMessage]:
        return list(
            self._session.scalars(
                select(ProjectMessage)
                .where(ProjectMessage.project_id == project_id)
                .order_by(ProjectMessage.created_at.asc())
            ).all()
        )

    def get_max_created_at(self, project_id: int) -> int:
        result = self._session.scalar(
            select(func.coalesce(func.max(ProjectMessage.created_at), 0))
            .where(ProjectMessage.project_id == project_id)
        )
        return int(result or 0)


class ProjectTaskStepRepository:
    """Query helpers for the ``project_task_steps`` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, step: ProjectTaskStep) -> ProjectTaskStep:
        self._session.add(step)
        return step

    def add_many(self, steps: list[ProjectTaskStep]) -> None:
        for step in steps:
            self._session.add(step)

    def delete_by_project(self, project_id: int) -> None:
        self._session.execute(
            delete(ProjectTaskStep).where(ProjectTaskStep.project_id == project_id)
        )

    def list_by_project(self, project_id: int) -> list[ProjectTaskStep]:
        return list(
            self._session.scalars(
                select(ProjectTaskStep)
                .where(ProjectTaskStep.project_id == project_id)
                .order_by(ProjectTaskStep.display_order.asc())
            ).all()
        )

    def get_by_step_key(self, project_id: int, step_key: str) -> ProjectTaskStep | None:
        return self._session.scalar(
            select(ProjectTaskStep).where(
                ProjectTaskStep.project_id == project_id,
                ProjectTaskStep.step_key == step_key,
            )
        )


class ShotSegmentRepository:
    """Query helpers for the ``shot_segments`` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, segment: ShotSegment) -> ShotSegment:
        self._session.add(segment)
        return segment

    def get_by_id(self, segment_id: str) -> ShotSegment | None:
        return self._session.get(ShotSegment, segment_id)

    def delete_by_project(self, project_id: int) -> None:
        segment_ids = list(
            self._session.scalars(
                select(ShotSegment.id).where(ShotSegment.project_id == project_id)
            ).all()
        )
        if segment_ids:
            self._session.execute(
                delete(StoryboardItemSegment).where(
                    StoryboardItemSegment.shot_segment_id.in_(segment_ids)
                )
            )
        self._session.execute(
            delete(ShotSegment).where(ShotSegment.project_id == project_id)
        )

    def list_by_project(self, project_id: int) -> list[ShotSegment]:
        return list(
            self._session.scalars(
                select(ShotSegment)
                .where(ShotSegment.project_id == project_id)
                .order_by(
                    ShotSegment.segment_index.asc(),
                    ShotSegment.start_ms.asc(),
                    ShotSegment.id.asc(),
                )
            ).all()
        )

    def get_by_ids(self, segment_ids: list[str]) -> list[ShotSegment]:
        if not segment_ids:
            return []
        return list(
            self._session.scalars(
                select(ShotSegment).where(ShotSegment.id.in_(segment_ids))
            ).all()
        )


class StoryboardRepository:
    """Query helpers for the ``storyboards`` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, storyboard: Storyboard) -> Storyboard:
        self._session.add(storyboard)
        return storyboard

    def add_item(self, item: StoryboardItem) -> StoryboardItem:
        self._session.add(item)
        return item

    def add_item_segment(self, link: StoryboardItemSegment) -> StoryboardItemSegment:
        self._session.add(link)
        return link

    def get_latest_by_project(self, project_id: int) -> Storyboard | None:
        return self._session.scalar(
            select(Storyboard)
            .where(Storyboard.project_id == project_id)
            .order_by(Storyboard.version_no.desc(), Storyboard.created_at.desc())
        )

    def get_max_version(self, project_id: int) -> int:
        result = self._session.scalar(
            select(func.coalesce(func.max(Storyboard.version_no), 0))
            .where(Storyboard.project_id == project_id)
        )
        return int(result or 0)

    def list_items(self, storyboard_id: str) -> list[StoryboardItem]:
        return list(
            self._session.scalars(
                select(StoryboardItem)
                .where(StoryboardItem.storyboard_id == storyboard_id)
                .order_by(
                    StoryboardItem.item_index.asc(),
                    StoryboardItem.start_ms.asc(),
                    StoryboardItem.id.asc(),
                )
            ).all()
        )

    def list_item_segments(self, storyboard_item_id: str) -> list[StoryboardItemSegment]:
        return list(
            self._session.scalars(
                select(StoryboardItemSegment)
                .where(StoryboardItemSegment.storyboard_item_id == storyboard_item_id)
                .order_by(StoryboardItemSegment.display_order.asc())
            ).all()
        )
