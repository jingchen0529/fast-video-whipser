import json
import uuid
from collections.abc import Iterable

from fastapi import HTTPException

from app.auth.security import utcnow_iso
from app.db.sqlite import create_connection


class AssetService:
    @staticmethod
    def _extract_related_asset_from_row(row, prefix: str) -> dict | None:
        asset_id = row[f"{prefix}_id"] if f"{prefix}_id" in row.keys() else None
        if not asset_id:
            return None
        metadata_raw = row[f"{prefix}_metadata_json"] if f"{prefix}_metadata_json" in row.keys() else None
        metadata = json.loads(metadata_raw) if metadata_raw else {}
        return {
            "id": asset_id,
            "asset_type": row[f"{prefix}_asset_type"] if f"{prefix}_asset_type" in row.keys() else None,
            "source_type": row[f"{prefix}_source_type"] if f"{prefix}_source_type" in row.keys() else None,
            "file_name": row[f"{prefix}_file_name"] if f"{prefix}_file_name" in row.keys() else None,
            "thumbnail_path": row[f"{prefix}_thumbnail_path"] if f"{prefix}_thumbnail_path" in row.keys() else None,
            "metadata_json": metadata,
        }

    @staticmethod
    def _row_to_asset(row) -> dict:
        asset = dict(row)
        if asset.get("metadata_json"):
            asset["metadata_json"] = json.loads(asset["metadata_json"])
        return asset

    @staticmethod
    def _row_to_motion_asset(row) -> dict:
        item = dict(row)
        if item.get("metadata_json"):
            item["metadata_json"] = json.loads(item["metadata_json"])
        item["source_video_asset"] = AssetService._extract_related_asset_from_row(
            row,
            "source_video_related",
        )
        item["clip_asset"] = AssetService._extract_related_asset_from_row(
            row,
            "clip_related",
        )
        for key in list(item.keys()):
            if key.startswith("source_video_related_") or key.startswith("clip_related_"):
                item.pop(key, None)
        item.pop("owner_user_id", None)
        return item

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
        now = utcnow_iso()
        asset_id = uuid.uuid4().hex

        connection = create_connection()
        try:
            connection.execute(
                """
                INSERT INTO media_assets (
                    id, owner_user_id, asset_type, source_type,
                    file_name, file_path, mime_type, duration_ms,
                    width, height, size_bytes, thumbnail_path,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    owner_user_id,
                    asset_type,
                    source_type,
                    file_name,
                    file_path,
                    mime_type,
                    duration_ms,
                    width,
                    height,
                    size_bytes,
                    thumbnail_path,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        return {
            "id": asset_id,
            "asset_type": asset_type,
            "source_type": source_type,
            "file_name": file_name,
            "file_path": file_path,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "duration_ms": duration_ms,
            "width": width,
            "height": height,
            "thumbnail_path": thumbnail_path,
            "created_at": now,
            "updated_at": now,
        }

    def get_asset(self, *, asset_id: str, owner_user_id: str | None = None) -> dict | None:
        clauses = ["id = ?"]
        params: list[object] = [asset_id]
        if owner_user_id is not None:
            clauses.append("(owner_user_id = ? OR owner_user_id IS NULL)")
            params.append(owner_user_id)
        where = " AND ".join(clauses)

        connection = create_connection()
        try:
            row = connection.execute(
                f"""
                SELECT *
                FROM media_assets
                WHERE {where}
                """,
                params,
            ).fetchone()
            return self._row_to_asset(row) if row is not None else None
        finally:
            connection.close()

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
        clauses = ["1 = 1"]
        params: list[object] = []

        if asset_type:
            clauses.append("asset_type = ?")
            params.append(asset_type.strip())
        if source_type:
            clauses.append("source_type = ?")
            params.append(source_type.strip())
        if owner_user_id:
            clauses.append("(owner_user_id = ? OR owner_user_id IS NULL)")
            params.append(owner_user_id.strip())
        if keyword:
            clauses.append("file_name LIKE ?")
            params.append(f"%{keyword.strip()}%")

        order = "created_at DESC" if sort == "newest" else "created_at ASC"
        where = " AND ".join(clauses)

        connection = create_connection()
        try:
            total = connection.execute(
                f"SELECT COUNT(*) AS cnt FROM media_assets WHERE {where}",
                params,
            ).fetchone()["cnt"]

            safe_page = max(1, page)
            safe_size = max(1, min(page_size, 100))
            offset = (safe_page - 1) * safe_size

            rows = connection.execute(
                f"""
                SELECT *
                FROM media_assets
                WHERE {where}
                ORDER BY {order}
                LIMIT ? OFFSET ?
                """,
                [*params, safe_size, offset],
            ).fetchall()
            return {
                "items": [self._row_to_asset(row) for row in rows],
                "total": total,
                "page": safe_page,
                "page_size": safe_size,
            }
        finally:
            connection.close()

    def get_storage_usage(self, *, owner_user_id: str | None = None) -> dict:
        clauses = ["1 = 1"]
        params: list[object] = []
        if owner_user_id:
            clauses.append("(owner_user_id = ? OR owner_user_id IS NULL)")
            params.append(owner_user_id.strip())
        where = " AND ".join(clauses)

        connection = create_connection()
        try:
            row = connection.execute(
                f"SELECT COALESCE(SUM(size_bytes), 0) AS used FROM media_assets WHERE {where}",
                params,
            ).fetchone()
            return {
                "used_bytes": row["used"] if row is not None else 0,
                "total_bytes": 1 * 1024 * 1024 * 1024,
            }
        finally:
            connection.close()

    def list_accessible_assets(
        self,
        *,
        asset_ids: Iterable[str],
        owner_user_id: str | None = None,
    ) -> list[dict]:
        normalized_ids = [asset_id.strip() for asset_id in asset_ids if asset_id and asset_id.strip()]
        if not normalized_ids:
            return []

        placeholders = ", ".join("?" for _ in normalized_ids)
        query = f"""
            SELECT *
            FROM media_assets
            WHERE id IN ({placeholders})
        """
        params: list[str] = list(normalized_ids)
        if owner_user_id is not None:
            query += " AND (owner_user_id = ? OR owner_user_id IS NULL)"
            params.append(owner_user_id)

        connection = create_connection()
        try:
            rows = connection.execute(query, params).fetchall()
            asset_map = {
                row["id"]: self._row_to_asset(row)
                for row in rows
            }
            return [
                asset_map[asset_id]
                for asset_id in normalized_ids
                if asset_id in asset_map
            ]
        finally:
            connection.close()

    def ensure_accessible_assets(
        self,
        *,
        asset_ids: Iterable[str],
        owner_user_id: str | None = None,
    ) -> list[dict]:
        normalized_ids = [asset_id.strip() for asset_id in asset_ids if asset_id and asset_id.strip()]
        assets = self.list_accessible_assets(
            asset_ids=normalized_ids,
            owner_user_id=owner_user_id,
        )
        asset_map = {asset["id"]: asset for asset in assets}
        missing_asset_ids = [
            asset_id
            for asset_id in normalized_ids
            if asset_id not in asset_map
        ]
        if missing_asset_ids:
            raise HTTPException(
                status_code=404,
                detail=f"以下资产不存在或无权访问: {', '.join(missing_asset_ids)}",
            )
        return [asset_map[asset_id] for asset_id in normalized_ids]

    def create_motion_assets_from_analysis(
        self,
        *,
        source_video_asset_id: str | None,
        conversation_id: str | None,
        job_id: str | None,
        clips: list[dict],
        owner_user_id: str | None = None,
        origin: str = "ai_generated",
    ) -> list[dict]:
        if not clips:
            return []

        now = utcnow_iso()
        connection = create_connection()
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
                connection.execute(
                    """
                    INSERT INTO motion_assets (
                        id, source_video_asset_id, clip_asset_id, conversation_id, job_id,
                        owner_user_id, start_ms, end_ms, action_summary, action_label,
                        entrance_style, emotion_label, temperament_label, scene_label,
                        camera_motion, camera_shot, origin, review_status, copyright_risk_level,
                        metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        motion_asset_id,
                        source_video_asset_id,
                        clip.get("clip_asset_id"),
                        conversation_id,
                        job_id,
                        owner_user_id,
                        clip["start_ms"],
                        clip["end_ms"],
                        clip["action_summary"],
                        clip.get("action_label"),
                        clip.get("entrance_style"),
                        clip.get("emotion_label"),
                        clip.get("temperament_label"),
                        clip.get("scene_label"),
                        clip.get("camera_motion"),
                        clip.get("camera_shot"),
                        origin,
                        clip.get("review_status", "auto_tagged"),
                        clip.get("copyright_risk_level", "unknown"),
                        json.dumps(metadata, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                items.append(
                    {
                        "id": motion_asset_id,
                        "source_video_asset_id": source_video_asset_id,
                        "clip_asset_id": clip.get("clip_asset_id"),
                        "conversation_id": conversation_id,
                        "job_id": job_id,
                        "owner_user_id": owner_user_id,
                        "start_ms": clip["start_ms"],
                        "end_ms": clip["end_ms"],
                        "action_summary": clip["action_summary"],
                        "action_label": clip.get("action_label"),
                        "entrance_style": clip.get("entrance_style"),
                        "emotion_label": clip.get("emotion_label"),
                        "temperament_label": clip.get("temperament_label"),
                        "scene_label": clip.get("scene_label"),
                        "camera_motion": clip.get("camera_motion"),
                        "camera_shot": clip.get("camera_shot"),
                        "origin": origin,
                        "review_status": clip.get("review_status", "auto_tagged"),
                        "copyright_risk_level": clip.get("copyright_risk_level", "unknown"),
                        "metadata_json": metadata,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
            connection.commit()
            return items
        finally:
            connection.close()

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
        now = utcnow_iso()

        connection = create_connection()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM motion_assets
                WHERE id = ?
                LIMIT 1
                """,
                (motion_asset_id,),
            ).fetchone()
            if row is None:
                return None

            item = dict(row)
            metadata = json.loads(item["metadata_json"]) if item.get("metadata_json") else {}
            review_history = metadata.get("review_history")
            if not isinstance(review_history, list):
                review_history = []
            review_history.append(
                {
                    "action": normalized_action,
                    "status": next_status,
                    "comment": (comment or "").strip(),
                    "reviewer_id": reviewer_id,
                    "reviewed_at": now,
                }
            )
            metadata["review_history"] = review_history
            if reviewer_id:
                metadata["last_reviewer_id"] = reviewer_id
            if comment:
                metadata["last_review_comment"] = comment.strip()

            connection.execute(
                """
                UPDATE motion_assets
                SET review_status = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_status,
                    json.dumps(metadata, ensure_ascii=False),
                    now,
                    motion_asset_id,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        return self.get_motion_asset(motion_asset_id=motion_asset_id)

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
        clauses = ["1 = 1"]
        params: list[object] = []

        if source_video_asset_id:
            clauses.append("source_video_asset_id = ?")
            params.append(source_video_asset_id.strip())
        if action_label:
            clauses.append("action_label = ?")
            params.append(action_label.strip())
        if scene_label:
            clauses.append("scene_label = ?")
            params.append(scene_label.strip())
        if review_status:
            clauses.append("review_status = ?")
            params.append(review_status.strip())
        if origin:
            clauses.append("origin = ?")
            params.append(origin.strip())
        if keyword:
            clauses.append("action_summary LIKE ?")
            params.append(f"%{keyword.strip()}%")

        safe_limit = max(1, min(limit, 100))
        params.append(safe_limit)

        connection = create_connection()
        try:
            rows = connection.execute(
                f"""
                SELECT
                    motion_assets.*,
                    source_video.id AS source_video_related_id,
                    source_video.asset_type AS source_video_related_asset_type,
                    source_video.source_type AS source_video_related_source_type,
                    source_video.file_name AS source_video_related_file_name,
                    source_video.thumbnail_path AS source_video_related_thumbnail_path,
                    source_video.metadata_json AS source_video_related_metadata_json,
                    clip.id AS clip_related_id,
                    clip.asset_type AS clip_related_asset_type,
                    clip.source_type AS clip_related_source_type,
                    clip.file_name AS clip_related_file_name,
                    clip.thumbnail_path AS clip_related_thumbnail_path,
                    clip.metadata_json AS clip_related_metadata_json
                FROM motion_assets
                LEFT JOIN media_assets AS source_video
                    ON source_video.id = motion_assets.source_video_asset_id
                LEFT JOIN media_assets AS clip
                    ON clip.id = motion_assets.clip_asset_id
                WHERE {' AND '.join(clauses)}
                ORDER BY motion_assets.created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [self._row_to_motion_asset(row) for row in rows]
        finally:
            connection.close()

    def delete_asset(self, *, asset_id: str, owner_user_id: str | None = None) -> bool:
        clauses = ["id = ?"]
        params: list[object] = [asset_id]
        if owner_user_id:
            clauses.append("(owner_user_id = ? OR owner_user_id IS NULL)")
            params.append(owner_user_id.strip())
        where = " AND ".join(clauses)

        connection = create_connection()
        try:
            cursor = connection.execute(
                f"DELETE FROM media_assets WHERE {where}",
                params,
            )
            connection.commit()
            return cursor.rowcount > 0
        finally:
            connection.close()

    def delete_assets_batch(self, *, asset_ids: list[str], owner_user_id: str | None = None) -> int:
        if not asset_ids:
            return 0
        placeholders = ", ".join("?" for _ in asset_ids)
        params: list[object] = list(asset_ids)
        owner_clause = ""
        if owner_user_id:
            owner_clause = " AND (owner_user_id = ? OR owner_user_id IS NULL)"
            params.append(owner_user_id.strip())
        connection = create_connection()
        try:
            cursor = connection.execute(
                f"DELETE FROM media_assets WHERE id IN ({placeholders}){owner_clause}",
                params,
            )
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def get_motion_asset(
        self,
        *,
        motion_asset_id: str,
    ) -> dict | None:
        clauses = ["motion_assets.id = ?"]
        params: list[object] = [motion_asset_id]

        connection = create_connection()
        try:
            row = connection.execute(
                f"""
                SELECT
                    motion_assets.*,
                    source_video.id AS source_video_related_id,
                    source_video.asset_type AS source_video_related_asset_type,
                    source_video.source_type AS source_video_related_source_type,
                    source_video.file_name AS source_video_related_file_name,
                    source_video.thumbnail_path AS source_video_related_thumbnail_path,
                    source_video.metadata_json AS source_video_related_metadata_json,
                    clip.id AS clip_related_id,
                    clip.asset_type AS clip_related_asset_type,
                    clip.source_type AS clip_related_source_type,
                    clip.file_name AS clip_related_file_name,
                    clip.thumbnail_path AS clip_related_thumbnail_path,
                    clip.metadata_json AS clip_related_metadata_json
                FROM motion_assets
                LEFT JOIN media_assets AS source_video
                    ON source_video.id = motion_assets.source_video_asset_id
                LEFT JOIN media_assets AS clip
                    ON clip.id = motion_assets.clip_asset_id
                WHERE {' AND '.join(clauses)}
                LIMIT 1
                """,
                params,
            ).fetchone()
            return self._row_to_motion_asset(row) if row is not None else None
        finally:
            connection.close()
