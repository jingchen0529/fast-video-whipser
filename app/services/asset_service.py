import json
import uuid
from collections.abc import Iterable

from fastapi import HTTPException
from sqlalchemy import func, select, delete as sa_delete
from sqlalchemy.orm import Session

from app.auth.security import utcnow_ms
from app.db.session import get_db_session
from app.models.asset import MediaAsset, MotionAsset


MAX_MOTION_ASSET_LIST_LIMIT = 1000


def _get_session() -> Session:
    """获取一个独立的数据库 Session（用于非 FastAPI 依赖注入场景）。"""
    gen = get_db_session()
    return next(gen)


class AssetService:

    @staticmethod
    def _asset_to_dict(asset: MediaAsset) -> dict:
        metadata_json = asset.metadata_json
        if isinstance(metadata_json, str):
            try:
                metadata_json = json.loads(metadata_json)
            except (json.JSONDecodeError, TypeError):
                metadata_json = {}
        return {
            "id": asset.id,
            "owner_user_id": asset.owner_user_id,
            "asset_type": asset.asset_type,
            "source_type": asset.source_type,
            "file_name": asset.file_name,
            "file_path": asset.file_path,
            "mime_type": asset.mime_type,
            "duration_ms": asset.duration_ms,
            "width": asset.width,
            "height": asset.height,
            "size_bytes": asset.size_bytes,
            "sha256": asset.sha256,
            "thumbnail_path": asset.thumbnail_path,
            "metadata_json": metadata_json or {},
            "created_at": asset.created_at,
            "updated_at": asset.updated_at,
        }

    @staticmethod
    def _motion_to_dict(motion: MotionAsset) -> dict:
        metadata_json = motion.metadata_json
        if isinstance(metadata_json, str):
            try:
                metadata_json = json.loads(metadata_json)
            except (json.JSONDecodeError, TypeError):
                metadata_json = {}
        thumbnail_asset_id = None
        thumbnail_path = None
        if isinstance(metadata_json, dict):
            thumbnail_asset_id = metadata_json.get("thumbnail_asset_id")
            thumbnail_path = metadata_json.get("thumbnail_path")

        source_video_asset = None
        if motion.source_video_asset:
            sv = motion.source_video_asset
            source_video_asset = {
                "id": sv.id,
                "asset_type": sv.asset_type,
                "source_type": sv.source_type,
                "file_name": sv.file_name,
                "thumbnail_path": sv.thumbnail_path,
                "metadata_json": json.loads(sv.metadata_json) if sv.metadata_json else {},
            }

        clip_asset = None
        if motion.clip_asset:
            ca = motion.clip_asset
            clip_asset = {
                "id": ca.id,
                "asset_type": ca.asset_type,
                "source_type": ca.source_type,
                "file_name": ca.file_name,
                "thumbnail_path": ca.thumbnail_path,
                "metadata_json": json.loads(ca.metadata_json) if ca.metadata_json else {},
            }

        return {
            "id": motion.id,
            "project_id": motion.project_id,
            "source_video_asset_id": motion.source_video_asset_id,
            "clip_asset_id": motion.clip_asset_id,
            "job_id": motion.job_id,
            "start_ms": motion.start_ms,
            "end_ms": motion.end_ms,
            "thumbnail_asset_id": thumbnail_asset_id,
            "thumbnail_path": thumbnail_path,
            "action_summary": motion.action_summary,
            "action_label": motion.action_label,
            "entrance_style": motion.entrance_style,
            "emotion_label": motion.emotion_label,
            "temperament_label": motion.temperament_label,
            "scene_label": motion.scene_label,
            "camera_motion": motion.camera_motion,
            "camera_shot": motion.camera_shot,
            "confidence": motion.confidence,
            "asset_candidate": motion.asset_candidate,
            "review_status": motion.review_status,
            "copyright_risk_level": motion.copyright_risk_level,
            "origin": motion.origin,
            "metadata_json": metadata_json or {},
            "source_video_asset": source_video_asset,
            "clip_asset": clip_asset,
            "created_at": motion.created_at,
            "updated_at": motion.updated_at,
        }

    def create_asset(
        self,
        *,
        owner_user_id: str | None,
        asset_type: str,
        source_type: str,
        file_name: str,
        file_path: str,
        mime_type: str | None,
        size_bytes: int | None,
        duration_ms: int | None = None,
        width: int | None = None,
        height: int | None = None,
        thumbnail_path: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        now = utcnow_ms()
        asset_id = uuid.uuid4().hex

        session = _get_session()
        try:
            asset = MediaAsset(
                id=asset_id,
                owner_user_id=owner_user_id,
                asset_type=asset_type,
                source_type=source_type,
                file_name=file_name,
                file_path=file_path,
                mime_type=mime_type,
                duration_ms=duration_ms,
                width=width,
                height=height,
                size_bytes=size_bytes,
                thumbnail_path=thumbnail_path,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
            session.add(asset)
            session.commit()
            return self._asset_to_dict(asset)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_asset(self, *, asset_id: str, owner_user_id: str | None = None) -> dict | None:
        session = _get_session()
        try:
            q = select(MediaAsset).where(MediaAsset.id == asset_id)
            if owner_user_id is not None:
                q = q.where(
                    (MediaAsset.owner_user_id == owner_user_id) | (MediaAsset.owner_user_id.is_(None))
                )
            asset = session.scalar(q)
            return self._asset_to_dict(asset) if asset else None
        finally:
            session.close()

    def list_media_assets(
        self,
        *,
        asset_type: str | None = None,
        source_type: str | None = None,
        owner_user_id: str | None = None,
        keyword: str | None = None,
        sort: str = "newest",
        page: int = 1,
        page_size: int = 40,
    ) -> dict:
        session = _get_session()
        try:
            q = select(MediaAsset)
            if asset_type:
                q = q.where(MediaAsset.asset_type == asset_type.strip())
            if source_type:
                q = q.where(MediaAsset.source_type == source_type.strip())
            if owner_user_id:
                q = q.where(
                    (MediaAsset.owner_user_id == owner_user_id.strip())
                    | (MediaAsset.owner_user_id.is_(None))
                )
            if keyword:
                q = q.where(MediaAsset.file_name.like(f"%{keyword.strip()}%"))

            total = session.scalar(
                select(func.count()).select_from(q.subquery())
            ) or 0

            if sort == "newest":
                q = q.order_by(MediaAsset.created_at.desc())
            else:
                q = q.order_by(MediaAsset.created_at.asc())

            safe_page = max(1, page)
            safe_size = max(1, min(page_size, 100))
            offset = (safe_page - 1) * safe_size
            q = q.limit(safe_size).offset(offset)

            rows = session.scalars(q).all()
            return {
                "items": [self._asset_to_dict(r) for r in rows],
                "total": total,
                "page": safe_page,
                "page_size": safe_size,
            }
        finally:
            session.close()

    def get_storage_usage(self, *, owner_user_id: str | None = None) -> dict:
        session = _get_session()
        try:
            q = select(func.coalesce(func.sum(MediaAsset.size_bytes), 0))
            if owner_user_id:
                q = q.where(
                    (MediaAsset.owner_user_id == owner_user_id.strip())
                    | (MediaAsset.owner_user_id.is_(None))
                )
            used = session.scalar(q) or 0
            return {
                "used_bytes": used,
                "total_bytes": 1 * 1024 * 1024 * 1024,
            }
        finally:
            session.close()

    def list_accessible_assets(
        self,
        *,
        asset_ids: Iterable[str],
        owner_user_id: str | None = None,
    ) -> list[dict]:
        normalized_ids = [aid.strip() for aid in asset_ids if aid and aid.strip()]
        if not normalized_ids:
            return []

        session = _get_session()
        try:
            q = select(MediaAsset).where(MediaAsset.id.in_(normalized_ids))
            if owner_user_id is not None:
                q = q.where(
                    (MediaAsset.owner_user_id == owner_user_id)
                    | (MediaAsset.owner_user_id.is_(None))
                )
            rows = session.scalars(q).all()
            asset_map = {r.id: self._asset_to_dict(r) for r in rows}
            return [asset_map[aid] for aid in normalized_ids if aid in asset_map]
        finally:
            session.close()

    def ensure_accessible_assets(
        self,
        *,
        asset_ids: Iterable[str],
        owner_user_id: str | None = None,
    ) -> list[dict]:
        normalized_ids = [aid.strip() for aid in asset_ids if aid and aid.strip()]
        assets = self.list_accessible_assets(
            asset_ids=normalized_ids,
            owner_user_id=owner_user_id,
        )
        asset_map = {a["id"]: a for a in assets}
        missing = [aid for aid in normalized_ids if aid not in asset_map]
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"以下资产不存在或无权访问: {', '.join(missing)}",
            )
        return [asset_map[aid] for aid in normalized_ids]

    def create_motion_assets_from_analysis(
        self,
        *,
        source_video_asset_id: str | None,
        project_id: int | None = None,
        job_id: str | None,
        clips: list[dict],
        owner_user_id: str | None = None,
        origin: str = "ai_generated",
    ) -> list[dict]:
        if not clips:
            return []

        now = utcnow_ms()
        session = _get_session()
        try:
            items: list[dict] = []
            for clip in clips:
                motion_asset_id = uuid.uuid4().hex
                metadata = {
                    "confidence": clip.get("confidence"),
                    "asset_candidate": clip.get("asset_candidate", True),
                    "analysis_source": "video_analysis",
                }
                if isinstance(clip.get("metadata_json"), dict):
                    metadata.update(clip["metadata_json"])
                thumbnail_asset_id = metadata.get("thumbnail_asset_id") if isinstance(metadata, dict) else None
                thumbnail_path = metadata.get("thumbnail_path") if isinstance(metadata, dict) else None

                motion = MotionAsset(
                    id=motion_asset_id,
                    source_video_asset_id=source_video_asset_id,
                    clip_asset_id=clip.get("clip_asset_id"),
                    project_id=project_id,
                    job_id=job_id,
                    owner_user_id=owner_user_id,
                    start_ms=clip["start_ms"],
                    end_ms=clip["end_ms"],
                    action_summary=clip["action_summary"],
                    action_label=clip.get("action_label"),
                    entrance_style=clip.get("entrance_style"),
                    emotion_label=clip.get("emotion_label"),
                    temperament_label=clip.get("temperament_label"),
                    scene_label=clip.get("scene_label"),
                    camera_motion=clip.get("camera_motion"),
                    camera_shot=clip.get("camera_shot"),
                    confidence=float(clip.get("confidence") or 0.0),
                    asset_candidate=bool(clip.get("asset_candidate", True)),
                    origin=origin,
                    review_status=clip.get("review_status", "auto_tagged"),
                    copyright_risk_level=clip.get("copyright_risk_level", "unknown"),
                    metadata_json=json.dumps(metadata, ensure_ascii=False),
                    created_at=now,
                    updated_at=now,
                )
                session.add(motion)
                items.append({
                    "id": motion_asset_id,
                    "source_video_asset_id": source_video_asset_id,
                    "clip_asset_id": clip.get("clip_asset_id"),
                    "project_id": project_id,
                    "job_id": job_id,
                    "owner_user_id": owner_user_id,
                    "start_ms": clip["start_ms"],
                    "end_ms": clip["end_ms"],
                    "thumbnail_asset_id": thumbnail_asset_id,
                    "thumbnail_path": thumbnail_path,
                    "action_summary": clip["action_summary"],
                    "action_label": clip.get("action_label"),
                    "entrance_style": clip.get("entrance_style"),
                    "emotion_label": clip.get("emotion_label"),
                    "temperament_label": clip.get("temperament_label"),
                    "scene_label": clip.get("scene_label"),
                    "camera_motion": clip.get("camera_motion"),
                    "camera_shot": clip.get("camera_shot"),
                    "confidence": float(clip.get("confidence") or 0.0),
                    "asset_candidate": bool(clip.get("asset_candidate", True)),
                    "origin": origin,
                    "review_status": clip.get("review_status", "auto_tagged"),
                    "copyright_risk_level": clip.get("copyright_risk_level", "unknown"),
                    "metadata_json": metadata,
                    "created_at": now,
                    "updated_at": now,
                })
            session.commit()
            return items
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def review_motion_asset(
        self,
        *,
        motion_asset_id: str,
        action: str,
        comment: str | None = None,
        reviewer_id: str | None = None,
    ) -> dict | None:
        normalized_action = (action or "").strip().lower()
        if normalized_action not in {"approve", "reject"}:
            raise ValueError("动作资产审核动作仅支持 approve 或 reject。")

        next_status = "approved" if normalized_action == "approve" else "rejected"
        now = utcnow_ms()

        session = _get_session()
        try:
            motion = session.get(MotionAsset, motion_asset_id)
            if motion is None:
                return None

            metadata = {}
            if motion.metadata_json:
                try:
                    metadata = json.loads(motion.metadata_json)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

            review_history = metadata.get("review_history")
            if not isinstance(review_history, list):
                review_history = []
            review_history.append({
                "action": normalized_action,
                "status": next_status,
                "comment": (comment or "").strip(),
                "reviewer_id": reviewer_id,
                "reviewed_at": now,
            })
            metadata["review_history"] = review_history
            if reviewer_id:
                metadata["last_reviewer_id"] = reviewer_id
            if comment:
                metadata["last_review_comment"] = comment.strip()

            motion.review_status = next_status
            motion.metadata_json = json.dumps(metadata, ensure_ascii=False)
            motion.updated_at = now
            session.commit()
            session.refresh(motion)
            return self._motion_to_dict(motion)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def batch_review_motion_assets(
        self,
        *,
        asset_ids: list[str],
        action: str,
        reviewer_id: str | None = None,
        comment: str | None = None,
    ) -> int:
        count = 0
        for motion_asset_id in asset_ids:
            result = self.review_motion_asset(
                motion_asset_id=motion_asset_id,
                action=action,
                comment=comment,
                reviewer_id=reviewer_id,
            )
            if result is not None:
                count += 1
        return count

    def list_motion_assets(
        self,
        *,
        source_video_asset_id: str | None = None,
        action_label: str | None = None,
        scene_label: str | None = None,
        review_status: str | None = None,
        origin: str | None = None,
        keyword: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        session = _get_session()
        try:
            from sqlalchemy.orm import selectinload
            q = select(MotionAsset).options(
                selectinload(MotionAsset.source_video_asset),
                selectinload(MotionAsset.clip_asset),
            )
            if source_video_asset_id:
                q = q.where(MotionAsset.source_video_asset_id == source_video_asset_id.strip())
            if action_label:
                q = q.where(MotionAsset.action_label == action_label.strip())
            if scene_label:
                q = q.where(MotionAsset.scene_label == scene_label.strip())
            if review_status:
                q = q.where(MotionAsset.review_status == review_status.strip())
            if origin:
                q = q.where(MotionAsset.origin == origin.strip())
            if keyword:
                q = q.where(MotionAsset.action_summary.like(f"%{keyword.strip()}%"))

            safe_limit = max(1, min(limit, MAX_MOTION_ASSET_LIST_LIMIT))
            q = q.order_by(MotionAsset.created_at.desc()).limit(safe_limit)
            rows = session.scalars(q).all()
            return [self._motion_to_dict(r) for r in rows]
        finally:
            session.close()

    def delete_asset(self, *, asset_id: str, owner_user_id: str | None = None) -> bool:
        session = _get_session()
        try:
            q = sa_delete(MediaAsset).where(MediaAsset.id == asset_id)
            if owner_user_id:
                q = q.where(
                    (MediaAsset.owner_user_id == owner_user_id.strip())
                    | (MediaAsset.owner_user_id.is_(None))
                )
            result = session.execute(q)
            session.commit()
            return result.rowcount > 0
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_assets_batch(self, *, asset_ids: list[str], owner_user_id: str | None = None) -> int:
        if not asset_ids:
            return 0
        session = _get_session()
        try:
            q = sa_delete(MediaAsset).where(MediaAsset.id.in_(asset_ids))
            if owner_user_id:
                q = q.where(
                    (MediaAsset.owner_user_id == owner_user_id.strip())
                    | (MediaAsset.owner_user_id.is_(None))
                )
            result = session.execute(q)
            session.commit()
            return result.rowcount
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_motion_asset(self, *, motion_asset_id: str) -> dict | None:
        session = _get_session()
        try:
            from sqlalchemy.orm import selectinload
            q = (
                select(MotionAsset)
                .options(
                    selectinload(MotionAsset.source_video_asset),
                    selectinload(MotionAsset.clip_asset),
                )
                .where(MotionAsset.id == motion_asset_id)
            )
            motion = session.scalar(q)
            return self._motion_to_dict(motion) if motion else None
        finally:
            session.close()
