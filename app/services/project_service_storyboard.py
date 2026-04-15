"""Storyboard and shot-segment helpers for project workflows."""
from app.services.project_service_shared import *  # noqa: F401,F403


class ProjectStoryboardMixin:
    def _load_shot_segments(
        self,
        *,
        session: Session,
        project_id: int,
    ) -> list[dict[str, Any]]:
        rows = ShotSegmentRepository(session).list_by_project(project_id)
        return [self._serialize_shot_segment(self._shot_segment_to_dict(r)) for r in rows]

    @staticmethod
    def _shot_segment_to_dict(r: ShotSegment) -> dict[str, Any]:
        return {
            "id": r.id,
            "project_id": r.project_id,
            "source_video_asset_id": r.source_video_asset_id,
            "job_id": r.job_id,
            "owner_user_id": r.owner_user_id,
            "segment_index": r.segment_index,
            "start_ms": r.start_ms,
            "end_ms": r.end_ms,
            "duration_ms": r.duration_ms,
            "start_frame": r.start_frame,
            "end_frame": r.end_frame,
            "boundary_in_type": r.boundary_in_type,
            "boundary_out_type": r.boundary_out_type,
            "detector_name": r.detector_name,
            "detector_version": r.detector_version,
            "detector_config_json": r.detector_config_json,
            "keyframe_asset_ids_json": r.keyframe_asset_ids_json,
            "transcript_text": r.transcript_text,
            "ocr_text": r.ocr_text,
            "visual_summary": r.visual_summary,
            "title": r.title,
            "shot_type_code": r.shot_type_code,
            "camera_angle_code": r.camera_angle_code,
            "camera_motion_code": r.camera_motion_code,
            "scene_label": r.scene_label,
            "confidence": r.confidence,
            "lighting_code": r.lighting_code,
            "dominant_color": r.dominant_color,
            "people_count": r.people_count,
            "face_regions_json": r.face_regions_json,
            "tags_json": r.tags_json,
            "metadata_json": r.metadata_json,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }

    def _load_shot_segments_for_project(self, *, project_id: int) -> list[dict[str, Any]]:
        session = _get_session()
        try:
            return self._load_shot_segments(
                session=session,
                project_id=project_id,
            )
        finally:
            session.close()

    def _serialize_shot_segment(self, item: dict[str, Any]) -> dict[str, Any]:
        item["detector_config_json"] = self._load_json_field(item.get("detector_config_json"), {})
        item["keyframe_asset_ids_json"] = self._load_json_field(item.get("keyframe_asset_ids_json"), [])
        item["metadata_json"] = self._load_json_field(item.get("metadata_json"), {})
        item["shot_type_label"] = self._shot_type_label(item.get("shot_type_code"))
        item["camera_angle_label"] = self._camera_angle_label(item.get("camera_angle_code"))
        item["camera_motion_label"] = self._camera_motion_label(item.get("camera_motion_code"))
        return item

    def _load_latest_storyboard(
        self,
        *,
        session: Session,
        project_id: int,
    ) -> dict[str, Any] | None:
        storyboard_repo = StoryboardRepository(session)
        shot_segment_repo = ShotSegmentRepository(session)
        storyboard_obj = storyboard_repo.get_latest_by_project(project_id)
        if storyboard_obj is None:
            return None

        storyboard: dict[str, Any] = {
            "id": storyboard_obj.id,
            "project_id": storyboard_obj.project_id,
            "job_id": storyboard_obj.job_id,
            "source_video_asset_id": storyboard_obj.source_video_asset_id,
            "owner_user_id": storyboard_obj.owner_user_id,
            "version_no": storyboard_obj.version_no,
            "status": storyboard_obj.status,
            "generator_provider": storyboard_obj.generator_provider,
            "generator_model": storyboard_obj.generator_model,
            "prompt_version": storyboard_obj.prompt_version,
            "summary": storyboard_obj.summary,
            "item_count": storyboard_obj.item_count,
            "metadata_json": self._load_json_field(storyboard_obj.metadata_json, {}),
            "created_at": storyboard_obj.created_at,
            "updated_at": storyboard_obj.updated_at,
        }

        item_rows = storyboard_repo.list_items(storyboard_obj.id)

        items: list[dict[str, Any]] = []
        for item_obj in item_rows:
            item: dict[str, Any] = {
                "id": item_obj.id,
                "storyboard_id": item_obj.storyboard_id,
                "item_index": item_obj.item_index,
                "title": item_obj.title,
                "start_ms": item_obj.start_ms,
                "end_ms": item_obj.end_ms,
                "duration_ms": item_obj.duration_ms,
                "shot_type_code": item_obj.shot_type_code,
                "camera_angle_code": item_obj.camera_angle_code,
                "camera_motion_code": item_obj.camera_motion_code,
                "visual_description": item_obj.visual_description,
                "transcript_excerpt": item_obj.transcript_excerpt,
                "ocr_excerpt": item_obj.ocr_excerpt,
                "confidence": item_obj.confidence,
                "review_status": item_obj.review_status,
                "metadata_json": self._load_json_field(item_obj.metadata_json, {}),
                "created_at": item_obj.created_at,
                "updated_at": item_obj.updated_at,
            }
            source_links = storyboard_repo.list_item_segments(item_obj.id)
            item["source_segment_ids"] = [link.shot_segment_id for link in source_links]
            # Need segment_index for each — load them
            seg_ids = [link.shot_segment_id for link in source_links]
            if seg_ids:
                seg_index_map = {
                    r.id: r.segment_index
                    for r in shot_segment_repo.get_by_ids(seg_ids)
                }
                item["source_segment_indexes"] = [seg_index_map.get(sid, 0) for sid in seg_ids]
            else:
                item["source_segment_indexes"] = []
            item["shot_type_label"] = self._shot_type_label(item_obj.shot_type_code)
            item["camera_angle_label"] = self._camera_angle_label(item_obj.camera_angle_code)
            item["camera_motion_label"] = self._camera_motion_label(item_obj.camera_motion_code)
            items.append(item)

        storyboard["items"] = items
        return storyboard

    def _build_legacy_storyboard(
        self,
        *,
        timeline_segments: list[dict[str, Any]],
        video_generation: dict[str, Any],
    ) -> dict[str, Any]:
        raw_storyboard = video_generation.get("storyboard")
        raw_items = raw_storyboard if isinstance(raw_storyboard, list) else (
            raw_storyboard.get("items") if isinstance(raw_storyboard, dict) else []
        )
        summary = (
            str(raw_storyboard.get("summary") or "").strip()
            if isinstance(raw_storyboard, dict)
            else ""
        )
        if isinstance(raw_items, list) and raw_items:
            items: list[dict[str, Any]] = []
            for index, raw_item in enumerate(raw_items, start=1):
                if not isinstance(raw_item, dict):
                    continue
                shot_type_code = raw_item.get("shot_type_code") or raw_item.get("shot_type") or "medium"
                camera_angle_code = raw_item.get("camera_angle_code") or raw_item.get("camera_angle") or "eye_level"
                camera_motion_code = raw_item.get("camera_motion_code") or raw_item.get("camera_motion") or "static"
                item = {
                    "id": raw_item.get("id") or f"legacy-storyboard-{index}",
                    "item_index": int(raw_item.get("item_index") or index),
                    "title": raw_item.get("title") or f"分镜 {index}",
                    "start_ms": int(raw_item.get("start_ms") or 0),
                    "end_ms": int(raw_item.get("end_ms") or raw_item.get("start_ms") or 0),
                    "duration_ms": max(
                        0,
                        int(raw_item.get("end_ms") or raw_item.get("start_ms") or 0)
                        - int(raw_item.get("start_ms") or 0),
                    ),
                    "shot_type_code": shot_type_code,
                    "camera_angle_code": camera_angle_code,
                    "camera_motion_code": camera_motion_code,
                    "visual_description": raw_item.get("visual_description") or raw_item.get("description") or "",
                    "transcript_excerpt": raw_item.get("transcript_excerpt") or "",
                    "ocr_excerpt": raw_item.get("ocr_excerpt") or "",
                    "confidence": float(raw_item.get("confidence") or 0.6),
                    "source_segment_ids": [],
                    "source_segment_indexes": raw_item.get("source_segment_indexes") or [],
                    "shot_type_label": self._shot_type_label(shot_type_code),
                    "camera_angle_label": self._camera_angle_label(camera_angle_code),
                    "camera_motion_label": self._camera_motion_label(camera_motion_code),
                }
                items.append(item)
            return {
                "id": None,
                "version_no": 0,
                "status": "legacy",
                "summary": summary or f"已回放 {len(items)} 条历史分镜。",
                "items": items,
            }

        return deepcopy(DEFAULT_STORYBOARD)

    async def _detect_shot_segments(
        self,
        *,
        project: dict[str, Any],
        source_asset: dict[str, Any],
        video_meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        file_path = str(source_asset.get("file_path") or "").strip()
        if not file_path or not os.path.exists(file_path):
            return []

        from app.utils.process_pool import run_in_process, run_shot_detection_worker

        try:
            threshold = 27.0
            min_scene_len = 15
            
            raw_scenes = await run_in_process(
                run_shot_detection_worker,
                file_path,
                threshold,
                min_scene_len,
            )

            if not raw_scenes:
                return []

            return [
                {
                    "segment_index": index,
                    "start_ms": scene["start_ms"],
                    "end_ms": scene["end_ms"],
                    "duration_ms": scene["duration_ms"],
                    "start_frame": scene["start_frame"],
                    "end_frame": scene["end_frame"],
                    "boundary_in_type": "cut",
                    "boundary_out_type": "cut",
                    "detector_name": "pyscenedetect",
                    "detector_version": None,
                    "detector_config_json": {"threshold": threshold, "min_scene_len": min_scene_len},
                    "keyframe_asset_ids_json": [],
                    "transcript_text": "",
                    "ocr_text": "",
                    "title": None,
                    "visual_summary": None,
                    "shot_type_code": None,
                    "camera_angle_code": None,
                    "camera_motion_code": None,
                    "scene_label": None,
                    "confidence": 0.82,
                    "metadata_json": {
                        "objective": project.get("objective") or "",
                    },
                }
                for index, scene in enumerate(raw_scenes, start=1)
            ]
        except Exception as exc:
            logger.warning("PySceneDetect shot detection failed for %s: %s", file_path, exc)
            return []

    def _build_fallback_shot_segments(
        self,
        *,
        video_meta: dict[str, Any],
        objective: str,
        source_name: str,
    ) -> list[dict[str, Any]]:
        duration_ms = max(4000, int(video_meta.get("duration_ms") or 32000))
        segment_count = 4 if duration_ms >= 18000 else 3 if duration_ms >= 9000 else 2
        interval = max(1000, duration_ms // segment_count)
        items: list[dict[str, Any]] = []
        for index in range(segment_count):
            start_ms = index * interval
            end_ms = duration_ms if index == segment_count - 1 else min(duration_ms, (index + 1) * interval)
            items.append(
                {
                    "segment_index": index + 1,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "duration_ms": max(0, end_ms - start_ms),
                    "start_frame": None,
                    "end_frame": None,
                    "boundary_in_type": "cut",
                    "boundary_out_type": "cut",
                    "detector_name": "pyscenedetect_fallback",
                    "detector_version": None,
                    "detector_config_json": {"strategy": "duration_split"},
                    "keyframe_asset_ids_json": [],
                    "transcript_text": "",
                    "ocr_text": "",
                    "title": self._build_shot_title(
                        index=index,
                        total=segment_count,
                        objective=objective,
                        source_name=source_name,
                    ),
                    "visual_summary": self._build_shot_visual_summary(
                        index=index,
                        total=segment_count,
                        objective=objective,
                        source_name=source_name,
                    ),
                    "shot_type_code": self._fallback_shot_type(index=index, total=segment_count),
                    "camera_angle_code": self._fallback_camera_angle(index=index, total=segment_count),
                    "camera_motion_code": self._fallback_camera_motion(index=index, total=segment_count),
                    "scene_label": None,
                    "confidence": 0.55,
                    "metadata_json": {"fallback": True},
                }
            )
        return items

    def _enrich_shot_segments(
        self,
        *,
        shot_segments: list[dict[str, Any]],
        video_meta: dict[str, Any],
        objective: str,
        source_name: str,
    ) -> list[dict[str, Any]]:
        if not shot_segments:
            return []

        total = len(shot_segments)
        enriched: list[dict[str, Any]] = []
        for index, raw_segment in enumerate(sorted(shot_segments, key=lambda item: int(item.get("segment_index") or 0) or int(item.get("start_ms") or 0)), start=1):
            segment = dict(raw_segment)
            segment["segment_index"] = index
            segment["start_ms"] = int(segment.get("start_ms") or 0)
            segment["end_ms"] = max(segment["start_ms"], int(segment.get("end_ms") or segment["start_ms"]))
            segment["duration_ms"] = max(0, int(segment.get("duration_ms") or segment["end_ms"] - segment["start_ms"]))
            segment["keyframe_asset_ids_json"] = segment.get("keyframe_asset_ids_json") or []
            segment["detector_config_json"] = segment.get("detector_config_json") or {}
            segment["metadata_json"] = segment.get("metadata_json") or {}
            segment["title"] = (segment.get("title") or "").strip() or self._build_shot_title(
                index=index - 1,
                total=total,
                objective=objective,
                source_name=source_name,
            )
            segment["shot_type_code"] = (segment.get("shot_type_code") or "").strip() or self._fallback_shot_type(index=index - 1, total=total)
            segment["camera_angle_code"] = (segment.get("camera_angle_code") or "").strip() or self._fallback_camera_angle(index=index - 1, total=total)
            segment["camera_motion_code"] = (segment.get("camera_motion_code") or "").strip() or self._fallback_camera_motion(index=index - 1, total=total)
            segment["visual_summary"] = (segment.get("visual_summary") or "").strip() or self._build_shot_visual_summary(
                index=index - 1,
                total=total,
                objective=objective,
                source_name=source_name,
            )
            segment["confidence"] = float(segment.get("confidence") or 0.7)
            enriched.append(segment)
        return enriched

    def _replace_shot_segments(
        self,
        *,
        project_id: int,
        project: dict[str, Any],
        source_asset: dict[str, Any],
        shot_segments: list[dict[str, Any]],
        preserve_transcript: bool = False,
    ) -> list[dict[str, Any]]:
        now = utcnow_ms()
        session = _get_session()
        try:
            shot_segment_repo = ShotSegmentRepository(session)
            preserved_by_index: dict[int, dict[str, Any]] = {}
            if preserve_transcript:
                existing_rows = shot_segment_repo.list_by_project(project_id)
                preserved_by_index = {
                    int(r.segment_index): {
                        "transcript_text": r.transcript_text,
                        "ocr_text": r.ocr_text,
                        "metadata_json": r.metadata_json,
                    }
                    for r in existing_rows
                }

            shot_segment_repo.delete_by_project(project_id)

            inserted: list[dict[str, Any]] = []
            for index, raw_segment in enumerate(shot_segments, start=1):
                preserved = preserved_by_index.get(index, {})
                segment_id = str(raw_segment.get("id") or uuid.uuid4().hex)
                transcript_text = (
                    raw_segment.get("transcript_text")
                    if raw_segment.get("transcript_text") not in {None, ""}
                    else preserved.get("transcript_text") or ""
                )
                ocr_text = (
                    raw_segment.get("ocr_text")
                    if raw_segment.get("ocr_text") not in {None, ""}
                    else preserved.get("ocr_text") or ""
                )
                metadata_json = raw_segment.get("metadata_json")
                if metadata_json is None or metadata_json == "":
                    metadata_json = self._load_json_field(preserved.get("metadata_json"), {})

                payload = {
                    "id": segment_id,
                    "project_id": project_id,
                    "job_id": None,
                    "source_video_asset_id": source_asset["id"],
                    "owner_user_id": project["user_id"],
                    "segment_index": int(raw_segment.get("segment_index") or index),
                    "start_ms": int(raw_segment.get("start_ms") or 0),
                    "end_ms": max(
                        int(raw_segment.get("start_ms") or 0),
                        int(raw_segment.get("end_ms") or raw_segment.get("start_ms") or 0),
                    ),
                    "duration_ms": max(
                        0,
                        int(raw_segment.get("duration_ms") or 0)
                        or (
                            int(raw_segment.get("end_ms") or raw_segment.get("start_ms") or 0)
                            - int(raw_segment.get("start_ms") or 0)
                        ),
                    ),
                    "start_frame": raw_segment.get("start_frame"),
                    "end_frame": raw_segment.get("end_frame"),
                    "boundary_in_type": raw_segment.get("boundary_in_type") or "cut",
                    "boundary_out_type": raw_segment.get("boundary_out_type") or "cut",
                    "detector_name": raw_segment.get("detector_name") or "pyscenedetect",
                    "detector_version": raw_segment.get("detector_version"),
                    "detector_config_json": raw_segment.get("detector_config_json") or {},
                    "keyframe_asset_ids_json": raw_segment.get("keyframe_asset_ids_json") or [],
                    "transcript_text": transcript_text,
                    "ocr_text": ocr_text,
                    "visual_summary": raw_segment.get("visual_summary"),
                    "title": raw_segment.get("title"),
                    "shot_type_code": raw_segment.get("shot_type_code"),
                    "camera_angle_code": raw_segment.get("camera_angle_code"),
                    "camera_motion_code": raw_segment.get("camera_motion_code"),
                    "scene_label": raw_segment.get("scene_label"),
                    "confidence": float(raw_segment.get("confidence") or 0.0),
                    "metadata_json": metadata_json or {},
                    "created_at": now,
                    "updated_at": now,
                }
                seg_obj = ShotSegment(
                    id=payload["id"],
                    project_id=payload["project_id"],
                    job_id=payload["job_id"],
                    source_video_asset_id=payload["source_video_asset_id"],
                    owner_user_id=payload["owner_user_id"],
                    segment_index=payload["segment_index"],
                    start_ms=payload["start_ms"],
                    end_ms=payload["end_ms"],
                    duration_ms=payload["duration_ms"],
                    start_frame=payload["start_frame"],
                    end_frame=payload["end_frame"],
                    boundary_in_type=payload["boundary_in_type"],
                    boundary_out_type=payload["boundary_out_type"],
                    detector_name=payload["detector_name"],
                    detector_version=payload["detector_version"],
                    detector_config_json=json.dumps(payload["detector_config_json"], ensure_ascii=False),
                    keyframe_asset_ids_json=json.dumps(payload["keyframe_asset_ids_json"], ensure_ascii=False),
                    transcript_text=payload["transcript_text"],
                    ocr_text=payload["ocr_text"],
                    visual_summary=payload["visual_summary"],
                    title=payload["title"],
                    shot_type_code=payload["shot_type_code"],
                    camera_angle_code=payload["camera_angle_code"],
                    camera_motion_code=payload["camera_motion_code"],
                    scene_label=payload["scene_label"],
                    confidence=payload["confidence"],
                    metadata_json=json.dumps(payload["metadata_json"], ensure_ascii=False),
                    created_at=payload["created_at"],
                    updated_at=payload["updated_at"],
                )
                shot_segment_repo.add(seg_obj)
                inserted.append(payload)

            session.commit()
            return [self._serialize_shot_segment(item) for item in inserted]
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _sync_shot_segments_with_timeline_segments(
        self,
        *,
        project_id: int,
        timeline_segments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        session = _get_session()
        try:
            shot_segment_repo = ShotSegmentRepository(session)
            shot_segments = self._load_shot_segments(
                session=session,
                project_id=project_id,
            )
            now = utcnow_ms()
            for shot_segment in shot_segments:
                transcript_text = self._collect_timeline_text_for_range(
                    start_ms=int(shot_segment.get("start_ms") or 0),
                    end_ms=int(shot_segment.get("end_ms") or 0),
                    timeline_segments=timeline_segments,
                )
                seg_obj = shot_segment_repo.get_by_id(shot_segment["id"])
                if seg_obj is not None:
                    seg_obj.transcript_text = transcript_text
                    seg_obj.updated_at = now
                shot_segment["transcript_text"] = transcript_text
            session.commit()
            return shot_segments
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _collect_timeline_text_for_range(
        self,
        *,
        start_ms: int,
        end_ms: int,
        timeline_segments: list[dict[str, Any]],
    ) -> str:
        fragments: list[str] = []
        for segment in timeline_segments:
            segment_start = int(segment.get("start_ms") or 0)
            segment_end = int(segment.get("end_ms") or segment_start)
            overlaps = segment_end > start_ms and segment_start < end_ms
            if overlaps and segment.get("content"):
                fragments.append(str(segment["content"]).strip())
        return " ".join(fragment for fragment in fragments if fragment).strip()

    def _build_storyboard_generation_context(
        self,
        *,
        shot_segments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "segment_index": int(segment.get("segment_index") or 0),
                "start_ms": int(segment.get("start_ms") or 0),
                "end_ms": int(segment.get("end_ms") or 0),
                "title": segment.get("title") or "",
                "visual_summary": segment.get("visual_summary") or "",
                "transcript_text": segment.get("transcript_text") or "",
                "ocr_text": segment.get("ocr_text") or "",
                "shot_type_code": segment.get("shot_type_code") or "medium",
                "camera_angle_code": segment.get("camera_angle_code") or "eye_level",
                "camera_motion_code": segment.get("camera_motion_code") or "static",
                "confidence": float(segment.get("confidence") or 0.6),
            }
            for segment in shot_segments
        ]

    def _normalize_storyboard_payload(
        self,
        *,
        payload: dict[str, Any],
        shot_segments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raw_items = []
        shot_map = {
            int(segment.get("segment_index") or 0): segment
            for segment in shot_segments
        }
        normalized_items: list[dict[str, Any]] = []
        for index, raw_item in enumerate(raw_items, start=1):
            if not isinstance(raw_item, dict):
                continue
            source_segment_indexes = raw_item.get("source_segment_indexes")
            if not isinstance(source_segment_indexes, list) or not source_segment_indexes:
                source_segment_indexes = [index] if index in shot_map else []
            normalized_source_segment_indexes: list[int] = []
            for item in source_segment_indexes:
                try:
                    normalized_index = int(item)
                except (TypeError, ValueError):
                    continue
                if normalized_index in shot_map:
                    normalized_source_segment_indexes.append(normalized_index)
            source_segment_indexes = normalized_source_segment_indexes
            if not source_segment_indexes and shot_map:
                source_segment_indexes = [min(index, len(shot_map))]
            source_segments = [shot_map[item] for item in source_segment_indexes if item in shot_map]
            first_source = source_segments[0] if source_segments else {}
            start_ms = min((int(segment.get("start_ms") or 0) for segment in source_segments), default=int(raw_item.get("start_ms") or 0))
            end_ms = max((int(segment.get("end_ms") or 0) for segment in source_segments), default=int(raw_item.get("end_ms") or start_ms))
            transcript_excerpt = " ".join(
                str(segment.get("transcript_text") or "").strip()
                for segment in source_segments
                if str(segment.get("transcript_text") or "").strip()
            ).strip()
            ocr_excerpt = " ".join(
                str(segment.get("ocr_text") or "").strip()
                for segment in source_segments
                if str(segment.get("ocr_text") or "").strip()
            ).strip()
            shot_type_code = str(raw_item.get("shot_type_code") or first_source.get("shot_type_code") or "medium").strip()
            camera_angle_code = str(raw_item.get("camera_angle_code") or first_source.get("camera_angle_code") or "eye_level").strip()
            camera_motion_code = str(raw_item.get("camera_motion_code") or first_source.get("camera_motion_code") or "static").strip()
            visual_description = str(raw_item.get("visual_description") or transcript_excerpt or first_source.get("visual_summary") or "").strip()
            if not visual_description:
                visual_description = "该分镜以主体展示和节奏推进为主。"
            normalized_items.append(
                {
                    "item_index": index,
                    "title": str(raw_item.get("title") or first_source.get("title") or f"分镜 {index}").strip()[:24] or f"分镜 {index}",
                    "start_ms": start_ms,
                    "end_ms": max(start_ms, end_ms),
                    "duration_ms": max(0, end_ms - start_ms),
                    "shot_type_code": shot_type_code,
                    "camera_angle_code": camera_angle_code,
                    "camera_motion_code": camera_motion_code,
                    "visual_description": visual_description,
                    "transcript_excerpt": transcript_excerpt,
                    "ocr_excerpt": ocr_excerpt,
                    "confidence": float(raw_item.get("confidence") or first_source.get("confidence") or 0.7),
                    "source_segment_indexes": source_segment_indexes,
                    "review_status": "auto_generated",
                    "metadata_json": {},
                }
            )
        if not normalized_items:
            fallback = self._build_legacy_storyboard(
                timeline_segments=[
                    {
                        "start_ms": segment.get("start_ms"),
                        "end_ms": segment.get("end_ms"),
                        "content": segment.get("visual_summary") or segment.get("transcript_text") or segment.get("title") or "",
                    }
                    for segment in shot_segments
                ],
                video_generation={},
            )
            return {
                "summary": fallback["summary"],
                "items": fallback["items"],
            }
        return {
            "summary": str(payload.get("summary") or f"共生成 {len(normalized_items)} 条结构化分镜。").strip(),
            "items": normalized_items,
        }

    def _replace_storyboard(
        self,
        *,
        project_id: int,
        project: dict[str, Any],
        source_asset: dict[str, Any],
        storyboard_payload: dict[str, Any],
        provider: str | None,
        model: str | None,
        used_remote: bool,
    ) -> dict[str, Any]:
        now = utcnow_ms()
        session = _get_session()
        try:
            storyboard_repo = StoryboardRepository(session)
            max_version = storyboard_repo.get_max_version(project_id)
            version_no = int(max_version) + 1
            storyboard_id = uuid.uuid4().hex
            items = storyboard_payload.get("items") or []

            sb_obj = Storyboard(
                id=storyboard_id,
                project_id=project_id,
                job_id=None,
                source_video_asset_id=source_asset["id"],
                owner_user_id=project["user_id"],
                version_no=version_no,
                status="generated",
                generator_provider=provider,
                generator_model=model,
                prompt_version="storyboard_v1",
                summary=storyboard_payload.get("summary") or "",
                item_count=len(items),
                metadata_json=json.dumps({"used_remote": used_remote}, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
            storyboard_repo.add(sb_obj)

            shot_segments = self._load_shot_segments(session=session, project_id=project_id)
            shot_id_by_index = {
                int(segment.get("segment_index") or 0): segment["id"]
                for segment in shot_segments
            }

            normalized_items: list[dict[str, Any]] = []
            for raw_item in items:
                item_id = uuid.uuid4().hex
                source_segment_indexes = raw_item.get("source_segment_indexes") or []
                metadata_json = raw_item.get("metadata_json") or {}
                item_obj = StoryboardItem(
                    id=item_id,
                    storyboard_id=storyboard_id,
                    item_index=int(raw_item.get("item_index") or 0),
                    title=raw_item.get("title") or "",
                    start_ms=int(raw_item.get("start_ms") or 0),
                    end_ms=int(raw_item.get("end_ms") or 0),
                    duration_ms=int(raw_item.get("duration_ms") or 0),
                    shot_type_code=raw_item.get("shot_type_code"),
                    camera_angle_code=raw_item.get("camera_angle_code"),
                    camera_motion_code=raw_item.get("camera_motion_code"),
                    visual_description=raw_item.get("visual_description") or "",
                    transcript_excerpt=raw_item.get("transcript_excerpt") or "",
                    ocr_excerpt=raw_item.get("ocr_excerpt") or "",
                    confidence=float(raw_item.get("confidence") or 0.0),
                    review_status=raw_item.get("review_status") or "auto_generated",
                    metadata_json=json.dumps(metadata_json, ensure_ascii=False),
                    created_at=now,
                    updated_at=now,
                )
                storyboard_repo.add_item(item_obj)
                for display_order, segment_index in enumerate(source_segment_indexes, start=1):
                    shot_segment_id = shot_id_by_index.get(int(segment_index))
                    if not shot_segment_id:
                        continue
                    storyboard_repo.add_item_segment(
                        StoryboardItemSegment(
                            storyboard_item_id=item_id,
                            shot_segment_id=shot_segment_id,
                            display_order=display_order,
                        )
                    )
                normalized_item = dict(raw_item)
                normalized_item["id"] = item_id
                normalized_item["shot_type_label"] = self._shot_type_label(raw_item.get("shot_type_code"))
                normalized_item["camera_angle_label"] = self._camera_angle_label(raw_item.get("camera_angle_code"))
                normalized_item["camera_motion_label"] = self._camera_motion_label(raw_item.get("camera_motion_code"))
                normalized_item["source_segment_ids"] = [
                    shot_id_by_index[int(segment_index)]
                    for segment_index in source_segment_indexes
                    if int(segment_index) in shot_id_by_index
                ]
                normalized_items.append(normalized_item)

            session.commit()
            return {
                "id": storyboard_id,
                "project_id": project_id,
                "version_no": version_no,
                "status": "generated",
                "summary": storyboard_payload.get("summary") or "",
                "items": normalized_items,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _build_shot_title(
        self,
        *,
        index: int,
        total: int,
        objective: str,
        source_name: str,
    ) -> str:
        if index == 0:
            return "开场引入镜头"
        if index == total - 1:
            return "结尾收束镜头"
        if total >= 4 and index == total - 2:
            return "卖点强化镜头"
        target = (objective or source_name or "主体内容").strip()
        return f"{target[:8] or '主体'}展示镜头"

    def _build_shot_visual_summary(
        self,
        *,
        index: int,
        total: int,
        objective: str,
        source_name: str,
    ) -> str:
        target = (objective or source_name or "当前素材").strip()
        if index == 0:
            return f"视频开场快速建立主题，围绕“{target[:16] or '当前素材'}”进行主体引入。"
        if index == total - 1:
            return "结尾通过收束式镜头完成信息闭环，并准备承接行动召唤。"
        if index == 1:
            return "中段通过主体展示与动作推进承接卖点信息，节奏保持连续。"
        return "镜头以主体与细节补充为主，用于延续叙事和卖点表达。"

    def _fallback_shot_type(self, *, index: int, total: int) -> str:
        if index == 0:
            return "wide"
        if index == total - 1:
            return "medium"
        return "close_up" if index % 2 else "medium"

    def _fallback_camera_angle(self, *, index: int, total: int) -> str:
        if index == 1 and total >= 3:
            return "high_angle"
        if index == total - 1 and total >= 2:
            return "side_angle"
        return "eye_level"

    def _fallback_camera_motion(self, *, index: int, total: int) -> str:
        if index == 0:
            return "static"
        if index == total - 1:
            return "static"
        return "tracking" if index % 2 else "pan"

    def _build_video_meta(
        self,
        *,
        project: dict[str, Any],
        source_asset: dict[str, Any],
        video_info: dict[str, Any],
    ) -> dict[str, Any]:
        width = (
            source_asset.get("width")
            or video_info.get("width")
            or 1080
        )
        height = (
            source_asset.get("height")
            or video_info.get("height")
            or 1920
        )
        duration_ms = (
            source_asset.get("duration_ms")
            or video_info.get("duration_ms")
            or 32000
        )
        return {
            "duration_ms": duration_ms,
            "width": width,
            "height": height,
            "size_bytes": source_asset.get("size_bytes") or 0,
            "source_name": project["source_name"],
        }

    def _build_visual_features(
        self,
        *,
        video_meta: dict[str, Any],
        shot_segments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        width = int(video_meta.get("width") or 1080)
        height = int(video_meta.get("height") or 1920)
        orientation = "portrait" if height >= width else "landscape"
        shot_segment_count = len(shot_segments or [])
        average_duration_ms = 0
        if shot_segments:
            average_duration_ms = sum(
                int(segment.get("duration_ms") or 0)
                for segment in shot_segments
            ) // max(1, shot_segment_count)
        shot_density = "high" if shot_segment_count >= 8 else "medium" if shot_segment_count >= 4 else "low"
        scene_pace = "fast" if average_duration_ms and average_duration_ms < 2500 else "medium" if average_duration_ms and average_duration_ms < 4500 else "steady"
        return {
            "orientation": orientation,
            "resolution": f"{width}x{height}",
            "frame_rate": "30fps",
            "keyframe_count": max(shot_segment_count, 1),
            "shot_density": shot_density,
            "scene_pace": scene_pace,
            "lighting": "bright",
            "contrast": "medium",
            "saturation": "medium_high",
            "color_temperature": "neutral_warm",
            "framing_focus": "subject_forward",
            "camera_motion": "mixed",
            "dominant_palette": ["#0F172A", "#E2E8F0", "#2563EB"],
            "summary": f"共识别 {shot_segment_count or 1} 个镜头段，整体节奏为 {scene_pace}，镜头围绕主体与卖点推进。",
        }
