"""
Asset repository — low-level ORM queries for MediaAsset and MotionAsset.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.asset import MediaAsset, MotionAsset


class MediaAssetRepository:
    """Query helpers for the ``media_assets`` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, asset_id: str) -> MediaAsset | None:
        return self._session.get(MediaAsset, asset_id)

    def get_by_id_and_owner(
        self, asset_id: str, owner_user_id: str | None = None
    ) -> MediaAsset | None:
        stmt = select(MediaAsset).where(MediaAsset.id == asset_id)
        if owner_user_id is not None:
            stmt = stmt.where(MediaAsset.owner_user_id == owner_user_id)
        return self._session.scalar(stmt)

    def list_by_owner(
        self,
        owner_user_id: str | None = None,
        asset_type: str | None = None,
        source_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MediaAsset]:
        stmt = select(MediaAsset)
        if owner_user_id is not None:
            stmt = stmt.where(MediaAsset.owner_user_id == owner_user_id)
        if asset_type is not None:
            stmt = stmt.where(MediaAsset.asset_type == asset_type)
        if source_type is not None:
            stmt = stmt.where(MediaAsset.source_type == source_type)
        stmt = stmt.order_by(MediaAsset.created_at.desc()).limit(limit).offset(offset)
        return list(self._session.scalars(stmt).all())

    def get_storage_usage(self, owner_user_id: str | None = None) -> dict:
        stmt = select(
            func.count(MediaAsset.id).label("file_count"),
            func.coalesce(func.sum(MediaAsset.size_bytes), 0).label("total_bytes"),
        )
        if owner_user_id is not None:
            stmt = stmt.where(MediaAsset.owner_user_id == owner_user_id)
        row = self._session.execute(stmt).one()
        return {"file_count": row.file_count, "total_bytes": row.total_bytes}

    def list_by_ids(self, asset_ids: list[str]) -> list[MediaAsset]:
        if not asset_ids:
            return []
        return list(
            self._session.scalars(
                select(MediaAsset).where(MediaAsset.id.in_(asset_ids))
            ).all()
        )


class MotionAssetRepository:
    """Query helpers for the ``motion_assets`` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, motion_asset_id: str) -> MotionAsset | None:
        return self._session.get(MotionAsset, motion_asset_id)

    def list_by_project(self, project_id: int) -> list[MotionAsset]:
        return list(
            self._session.scalars(
                select(MotionAsset)
                .where(MotionAsset.project_id == project_id)
                .order_by(MotionAsset.start_ms.asc())
            ).all()
        )

    def list_by_owner(
        self,
        owner_user_id: str | None = None,
        review_status: str | None = None,
        action_label: str | None = None,
        scene_label: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MotionAsset]:
        stmt = select(MotionAsset)
        if owner_user_id is not None:
            stmt = stmt.where(MotionAsset.owner_user_id == owner_user_id)
        if review_status is not None:
            stmt = stmt.where(MotionAsset.review_status == review_status)
        if action_label is not None:
            stmt = stmt.where(MotionAsset.action_label == action_label)
        if scene_label is not None:
            stmt = stmt.where(MotionAsset.scene_label == scene_label)
        stmt = stmt.order_by(MotionAsset.created_at.desc()).limit(limit).offset(offset)
        return list(self._session.scalars(stmt).all())

    def list_by_source_video(self, source_video_asset_id: str) -> list[MotionAsset]:
        return list(
            self._session.scalars(
                select(MotionAsset)
                .where(MotionAsset.source_video_asset_id == source_video_asset_id)
                .order_by(MotionAsset.start_ms.asc())
            ).all()
        )
