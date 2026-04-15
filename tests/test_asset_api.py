from io import BytesIO

from app.services.asset_service import AssetService
from app.services.analysis_ai_service import AnalysisAIService
from app.services.motion_service import MotionService
from app.services.project_service import ProjectService
from tests.test_auth_api import _build_test_client, _csrf_headers, _login


def test_upload_asset_requires_auth(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        response = client.post(
            "/api/assets/upload",
            files={
                "file": ("test.mp4", BytesIO(b"fake-video-bytes"), "video/mp4"),
            },
        )

        assert response.status_code == 401


def test_upload_asset_success(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        response = client.post(
            "/api/assets/upload",
            headers=_csrf_headers(client),
            files={
                "file": ("test.mp4", BytesIO(b"fake-video-bytes"), "video/mp4"),
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["id"]
        assert body["data"]["file_name"] == "test.mp4"
        assert body["data"]["source_type"] == "upload"
        assert body["data"]["asset_type"] == "video"


def test_list_assets_includes_generated_assets_for_current_user_only(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200
        admin_user_id = login_response.json()["data"]["user"]["id"]

        upload_response = client.post(
            "/api/assets/upload",
            headers=_csrf_headers(client),
            files={
                "file": ("upload-video.mp4", BytesIO(b"fake-upload-video"), "video/mp4"),
            },
        )
        assert upload_response.status_code == 200
        upload_asset = upload_response.json()["data"]

        generated_path = tmp_path / "generated-remake.mp4"
        generated_path.write_bytes(b"fake-generated-video")
        generated_asset = AssetService().create_asset(
            owner_user_id=admin_user_id,
            asset_type="video",
            source_type="generated",
            file_name="generated-remake.mp4",
            file_path=str(generated_path),
            mime_type="video/mp4",
            size_bytes=generated_path.stat().st_size,
        )

        other_user_path = tmp_path / "other-user-video.mp4"
        other_user_path.write_bytes(b"fake-other-user-video")
        create_user_response = client.post(
            "/api/auth/users",
            json={
                "username": "asset_member_list",
                "email": "asset_member_list@example.com",
                "password": "Member12345!",
                "display_name": "Asset Member List",
                "role_codes": ["user"],
                "is_active": True,
                "is_superuser": False,
            },
            headers=_csrf_headers(client),
        )
        assert create_user_response.status_code == 200
        other_user_id = create_user_response.json()["data"]["id"]
        AssetService().create_asset(
            owner_user_id=other_user_id,
            asset_type="video",
            source_type="generated",
            file_name="other-user-video.mp4",
            file_path=str(other_user_path),
            mime_type="video/mp4",
            size_bytes=other_user_path.stat().st_size,
        )

        list_response = client.get("/api/assets")

        assert list_response.status_code == 200
        items = list_response.json()["data"]["items"]
        returned_ids = {item["id"] for item in items}
        returned_sources = {item["source_type"] for item in items}

        assert upload_asset["id"] in returned_ids
        assert generated_asset["id"] in returned_ids
        assert returned_sources >= {"upload", "generated"}
        assert all(item["file_name"] != "other-user-video.mp4" for item in items)


def test_asset_file_and_delete_are_scoped_to_current_user(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        create_user_response = client.post(
            "/api/auth/users",
            json={
                "username": "asset_member",
                "email": "asset_member@example.com",
                "password": "Member12345!",
                "display_name": "Asset Member",
                "role_codes": ["user"],
                "is_active": True,
                "is_superuser": False,
            },
            headers=_csrf_headers(client),
        )
        assert create_user_response.status_code == 200
        other_user_id = create_user_response.json()["data"]["id"]

        other_user_path = tmp_path / "other-user-secret.mp4"
        other_user_path.write_bytes(b"private-video")
        other_asset = AssetService().create_asset(
            owner_user_id=other_user_id,
            asset_type="video",
            source_type="generated",
            file_name="other-user-secret.mp4",
            file_path=str(other_user_path),
            mime_type="video/mp4",
            size_bytes=other_user_path.stat().st_size,
        )

        file_response = client.get(f"/api/assets/file/{other_asset['id']}")
        delete_response = client.delete(
            f"/api/assets/{other_asset['id']}",
            headers=_csrf_headers(client),
        )

        assert file_response.status_code == 404
        assert delete_response.status_code == 404


def test_list_motion_assets_after_video_analysis(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200
        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 200
        current_user_id = me_response.json()["data"]["id"]

        upload_response = client.post(
            "/api/assets/upload",
            headers=_csrf_headers(client),
            files={
                "file": ("analysis-source.mp4", BytesIO(b"fake-video-bytes"), "video/mp4"),
            },
        )
        assert upload_response.status_code == 200
        asset_id = upload_response.json()["data"]["id"]

        created_items = AssetService().create_motion_assets_from_analysis(
            source_video_asset_id=asset_id,
            project_id=None,
            job_id=None,
            owner_user_id=current_user_id,
            clips=[
                {
                    "start_ms": 0,
                    "end_ms": 2600,
                    "action_summary": "角色快速出场并完成第一轮视线吸引。",
                    "action_label": "entrance_hook",
                    "emotion_label": "confident",
                    "scene_label": "indoor",
                    "camera_motion": "static",
                    "camera_shot": "medium",
                    "confidence": 0.73,
                    "asset_candidate": True,
                    "review_status": "auto_tagged",
                },
                {
                    "start_ms": 2600,
                    "end_ms": 6100,
                    "action_summary": "人物通过手势和动作强化核心卖点说明。",
                    "action_label": "gesture_explain",
                    "emotion_label": "active",
                    "scene_label": "product_showcase",
                    "camera_motion": "tracking",
                    "camera_shot": "medium_close",
                    "review_status": "auto_tagged",
                },
                {
                    "start_ms": 6100,
                    "end_ms": 9800,
                    "action_summary": "结尾动作落在结果展示和行动引导上。",
                    "action_label": "cta_close",
                    "emotion_label": "firm",
                    "scene_label": "result",
                    "camera_motion": "push_in",
                    "camera_shot": "close_up",
                    "review_status": "auto_tagged",
                },
            ],
        )
        assert len(created_items) == 3

        list_response = client.get("/api/assets/motions")
        assert list_response.status_code == 200
        list_body = list_response.json()
        assert len(list_body["data"]["items"]) == 3
        first_item = list_body["data"]["items"][0]
        assert first_item["source_video_asset_id"] == asset_id
        assert first_item["review_status"] == "auto_tagged"
        assert first_item["action_summary"]
        assert "owner_user_id" not in first_item

        detail_response = client.get(f"/api/assets/motions/{first_item['id']}")
        assert detail_response.status_code == 200
        assert detail_response.json()["data"]["id"] == first_item["id"]
        assert "owner_user_id" not in detail_response.json()["data"]
        detail_payload = detail_response.json()["data"]
        assert isinstance(detail_payload["confidence"], float)
        assert detail_payload["asset_candidate"] in {True, False}


def test_list_motion_assets_accepts_library_limit_for_client_search(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200
        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 200
        current_user_id = me_response.json()["data"]["id"]

        upload_response = client.post(
            "/api/assets/upload",
            headers=_csrf_headers(client),
            files={
                "file": ("motion-library-source.mp4", BytesIO(b"fake-video-bytes"), "video/mp4"),
            },
        )
        assert upload_response.status_code == 200
        asset_id = upload_response.json()["data"]["id"]

        clips = [
            {
                "start_ms": index * 1000,
                "end_ms": index * 1000 + 800,
                "action_summary": f"动作资产库检索样本 {index}",
                "action_label": "library_search",
                "emotion_label": "neutral",
                "scene_label": "studio",
                "camera_motion": "static",
                "camera_shot": "medium",
                "review_status": "auto_tagged",
            }
            for index in range(120)
        ]
        AssetService().create_motion_assets_from_analysis(
            source_video_asset_id=asset_id,
            project_id=None,
            job_id=None,
            owner_user_id=current_user_id,
            clips=clips,
        )

        list_response = client.get("/api/assets/motions?limit=1000")

        assert list_response.status_code == 200
        assert len(list_response.json()["data"]["items"]) == 120


def test_motion_coarse_filter_matches_natural_language_variants() -> None:
    service = MotionService()

    is_candidate, matched_labels, signal_score, matched_sources = service._coarse_filter_candidate(
        start_ms=0,
        end_ms=9200,
        title_text="门口停顿镜头",
        transcript_text="男主推开房门迈步进屋，在门口顿了一下，扭头看向女主。",
        visual_summary="",
        storyboard_text="",
        ocr_text="",
    )

    assert is_candidate is True
    assert "push_door" in matched_labels
    assert "walk_in" in matched_labels
    assert "turn_back" in matched_labels
    assert "stare" in matched_labels
    assert signal_score >= 4
    assert "transcript_text" in matched_sources


def test_motion_coarse_filter_ignores_generic_storyboard_copy() -> None:
    service = MotionService()

    is_candidate, matched_labels, signal_score, matched_sources = service._coarse_filter_candidate(
        start_ms=0,
        end_ms=3200,
        title_text="开场引入镜头",
        transcript_text="",
        visual_summary="中段通过主体展示与动作推进承接卖点信息，节奏保持连续。",
        storyboard_text="",
        ocr_text="",
    )

    assert is_candidate is False
    assert matched_labels == []
    assert signal_score == 0
    assert matched_sources == []

    evaluation = service._evaluate_coarse_filter_candidate(
        start_ms=0,
        end_ms=3200,
        title_text="开场引入镜头",
        transcript_text="",
        visual_summary="中段通过主体展示与动作推进承接卖点信息，节奏保持连续。",
        storyboard_text="",
        ocr_text="",
    )
    assert evaluation["filter_reason"] == "no_motion_signal"


def test_motion_coarse_filter_hint_boosts_borderline_candidate() -> None:
    service = MotionService()

    evaluation = service._evaluate_coarse_filter_candidate(
        start_ms=0,
        end_ms=4200,
        title_text="控制面板",
        transcript_text="",
        visual_summary="",
        storyboard_text="",
        ocr_text="",
    )
    assert evaluation["is_candidate"] is False
    assert evaluation["matched_labels"] == ["operate_machine"]
    assert evaluation["signal_score"] == 2

    boosted = service._evaluate_coarse_filter_candidate(
        start_ms=0,
        end_ms=4200,
        title_text="控制面板",
        transcript_text="",
        visual_summary="",
        storyboard_text="",
        ocr_text="",
        hint_labels=service._extract_hint_labels("优先提取设备操作、控制面板展示这类动作"),
    )

    assert boosted["is_candidate"] is True
    assert boosted["signal_score"] >= 3
    assert "extraction_hint" in boosted["matched_sources"]


def test_motion_ai_tags_are_normalized_to_supported_schema() -> None:
    service = MotionService()
    candidate = {
        "matched_labels": ["wave", "smile"],
        "combined_text": "工厂团队站在门口微笑挥手欢迎来访者。",
        "scene_label": "factory",
        "camera_motion_code": "static",
        "shot_type_code": "wide",
        "title": "欢迎镜头",
        "visual_summary": "工厂团队挥手欢迎。",
    }
    fallback_tags = service._build_fallback_tags(candidate=candidate)

    normalized = service._normalize_ai_tags(
        candidate=candidate,
        tags={
            "action_label": "smile, wave",
            "entrance_style": "welcome entrance",
            "emotion_label": "friendly",
            "temperament_label": "warm",
            "scene_label": "factory entrance",
            "camera_motion": "tracking shot",
            "camera_shot": "wide shot",
            "action_summary": "工厂团队在门口微笑挥手欢迎来访者。",
            "confidence": 0.92,
            "is_high_value": True,
        },
        fallback_tags=fallback_tags,
    )

    assert normalized["action_label"] == "team_greeting"
    assert normalized["entrance_style"] == fallback_tags["entrance_style"]
    assert normalized["emotion_label"] == fallback_tags["emotion_label"]
    assert normalized["temperament_label"] == fallback_tags["temperament_label"]
    assert normalized["scene_label"] == "factory_entrance"
    assert normalized["camera_motion"] == "tracking"
    assert normalized["camera_shot"] == "wide"
    assert normalized["confidence"] == 0.92


def test_motion_coarse_filter_matches_factory_showcase_actions() -> None:
    service = MotionService()

    is_candidate, matched_labels, signal_score, matched_sources = service._coarse_filter_candidate(
        start_ms=0,
        end_ms=5600,
        title_text="工厂展示镜头",
        transcript_text="工人正在操作控制面板，团队在仓库搬运包装袋。",
        visual_summary="镜头特写展示塑料颗粒细节，传送带上的颗粒持续流动。",
        storyboard_text="工厂团队挥手欢迎来访者后，工人在设备前进行操作演示。",
        ocr_text="Plastic granules production line",
    )

    assert is_candidate is True
    assert "operate_machine" in matched_labels
    assert "carry_goods" in matched_labels
    assert "display_product" in matched_labels
    assert signal_score >= 4
    assert "transcript_text" in matched_sources


def test_extract_motion_assets_reports_filtered_items_when_no_candidates(tmp_path, monkeypatch) -> None:
    async def fake_transcribe_source_media(self, *, project, source_asset):
        return {
            "provider": "faster_whisper",
            "timeline_segments": [
                {
                    "id": 1,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 0,
                    "end_ms": 4100,
                    "content": "Hello Boss! Welcome to Chinese Factory!",
                }
            ],
        }

    async def fake_detect_shot_segments(self, *, project, source_asset, video_meta):
        return [
            {
                "id": "shot-generic-1",
                "segment_index": 1,
                "start_ms": 0,
                "end_ms": 4100,
                "duration_ms": 4100,
                "start_frame": 0,
                "end_frame": 123,
                "boundary_in_type": "cut",
                "boundary_out_type": "cut",
                "detector_name": "stub",
                "detector_version": None,
                "detector_config_json": {},
                "keyframe_asset_ids_json": [],
                "transcript_text": "Hello Boss! Welcome to Chinese Factory!",
                "ocr_text": "",
                "title": "开场引入镜头",
                "visual_summary": "视频开场快速建立主题，围绕“动作提取默认前置分析”进行主体引入。",
                "shot_type_code": "wide",
                "camera_angle_code": "eye_level",
                "camera_motion_code": "static",
                "scene_label": None,
                "confidence": 0.9,
                "metadata_json": {},
            }
        ]

    async def fake_generate_storyboard_reply(self, *, objective, source_name, video_meta, shot_segments):
        return {
            "storyboard": {
                "summary": "围绕工厂介绍整理出的基础分镜。",
                "items": [
                    {
                        "item_index": 1,
                        "title": "开场引入镜头",
                        "start_ms": 0,
                        "end_ms": 4100,
                        "shot_type_code": "wide",
                        "camera_angle_code": "eye_level",
                        "camera_motion_code": "static",
                        "visual_description": "视频开场快速建立主题，围绕“动作提取默认前置分析”进行主体引入。",
                        "source_segment_indexes": [1],
                        "confidence": 0.9,
                    }
                ],
            },
            "provider": "fallback",
            "model": "fallback",
            "used_remote": False,
        }

    monkeypatch.setattr(ProjectService, "_transcribe_source_media", fake_transcribe_source_media)
    monkeypatch.setattr(ProjectService, "_detect_shot_segments", fake_detect_shot_segments)
    monkeypatch.setattr(AnalysisAIService, "generate_storyboard_reply", fake_generate_storyboard_reply)

    with _build_test_client(tmp_path) as client:
        login_response = _login(client, login="admin", password="Admin12345!")
        assert login_response.status_code == 200

        project_response = client.post(
            "/api/projects/upload",
            headers=_csrf_headers(client),
            data={
                "objective": "先完成视频分析，再做动作提取",
                "workflow_type": "analysis",
            },
            files={
                "file": ("generic-motion-source.mp4", BytesIO(b"fake-video-bytes"), "video/mp4"),
            },
        )
        assert project_response.status_code == 200
        project_id = project_response.json()["data"]["id"]

        extract_response = client.post(
            "/api/assets/motions/extract",
            headers=_csrf_headers(client),
            json={"project_id": project_id},
        )
        assert extract_response.status_code == 200
        job_id = extract_response.json()["data"]["job_id"]

        job_response = client.get(f"/api/jobs/{job_id}")
        assert job_response.status_code == 200
        result_json = job_response.json()["data"]["result_json"]

        assert result_json["candidate_count"] == 0
        assert result_json["saved_count"] == 0
        assert result_json["filtered_summary"]["no_motion_signal"] >= 1
        assert result_json["filtered_items"]
        assert result_json["filtered_items"][0]["filter_reason"] == "no_motion_signal"
        assert result_json["filtered_items"][0]["filter_reason_label"] == "未识别到动作信号"


def test_extract_motion_assets_uses_auxiliary_hint_without_overriding_defaults(tmp_path, monkeypatch) -> None:
    async def fake_transcribe_source_media(self, *, project, source_asset):
        return {
            "provider": "faster_whisper",
            "timeline_segments": [],
        }

    async def fake_detect_shot_segments(self, *, project, source_asset, video_meta):
        return [
            {
                "id": "shot-hint-1",
                "segment_index": 1,
                "start_ms": 0,
                "end_ms": 4200,
                "duration_ms": 4200,
                "start_frame": 0,
                "end_frame": 126,
                "boundary_in_type": "cut",
                "boundary_out_type": "cut",
                "detector_name": "stub",
                "detector_version": None,
                "detector_config_json": {},
                "keyframe_asset_ids_json": [],
                "transcript_text": "",
                "ocr_text": "",
                "title": "控制面板",
                "visual_summary": "",
                "shot_type_code": "medium_close",
                "camera_angle_code": "eye_level",
                "camera_motion_code": "static",
                "scene_label": "product_closeup",
                "confidence": 0.9,
                "metadata_json": {},
            }
        ]

    async def fake_generate_storyboard_reply(self, *, objective, source_name, video_meta, shot_segments):
        return {
            "storyboard": {
                "summary": "仅保留中性分镜摘要，不额外增强动作信号。",
                "items": [
                    {
                        "item_index": 1,
                        "title": "中性镜头",
                        "start_ms": 0,
                        "end_ms": 4200,
                        "shot_type_code": "medium_close",
                        "camera_angle_code": "eye_level",
                        "camera_motion_code": "static",
                        "visual_description": "镜头以主体展示为主。",
                        "source_segment_indexes": [1],
                        "confidence": 0.8,
                    }
                ],
            },
            "provider": "fallback",
            "model": "fallback",
            "used_remote": False,
        }

    monkeypatch.setattr(ProjectService, "_transcribe_source_media", fake_transcribe_source_media)
    monkeypatch.setattr(ProjectService, "_detect_shot_segments", fake_detect_shot_segments)
    monkeypatch.setattr(AnalysisAIService, "generate_storyboard_reply", fake_generate_storyboard_reply)

    with _build_test_client(tmp_path) as client:
        login_response = _login(client, login="admin", password="Admin12345!")
        assert login_response.status_code == 200

        project_response = client.post(
            "/api/projects/upload",
            headers=_csrf_headers(client),
            data={
                "objective": "先完成视频分析，再做动作提取",
                "workflow_type": "analysis",
            },
            files={
                "file": ("motion-hint-source.mp4", BytesIO(b"fake-video-bytes"), "video/mp4"),
            },
        )
        assert project_response.status_code == 200
        project_id = project_response.json()["data"]["id"]

        without_hint = client.post(
            "/api/assets/motions/extract",
            headers=_csrf_headers(client),
            json={"project_id": project_id},
        )
        assert without_hint.status_code == 200
        without_hint_job_id = without_hint.json()["data"]["job_id"]

        without_hint_job = client.get(f"/api/jobs/{without_hint_job_id}")
        assert without_hint_job.status_code == 200
        without_hint_result = without_hint_job.json()["data"]["result_json"]
        assert without_hint_result["candidate_count"] == 0
        assert without_hint_result["saved_count"] == 0

        with_hint = client.post(
            "/api/assets/motions/extract",
            headers=_csrf_headers(client),
            json={
                "project_id": project_id,
                "extraction_hint": "优先关注设备操作、控制面板展示这类动作",
            },
        )
        assert with_hint.status_code == 200
        with_hint_job_id = with_hint.json()["data"]["job_id"]

        with_hint_job = client.get(f"/api/jobs/{with_hint_job_id}")
        assert with_hint_job.status_code == 200
        with_hint_result = with_hint_job.json()["data"]["result_json"]
        assert with_hint_result["candidate_count"] == 1
        assert with_hint_result["saved_count"] == 1
        assert with_hint_result["extraction_hint"] == "优先关注设备操作、控制面板展示这类动作"

        motion_id = with_hint_result["asset_ids"][0]
        detail_response = client.get(f"/api/assets/motions/{motion_id}")
        assert detail_response.status_code == 200
        assert detail_response.json()["data"]["review_status"] == "approved"


def test_extract_motion_assets_from_analyzed_project(tmp_path, monkeypatch) -> None:
    async def fake_transcribe_source_media(self, *, project, source_asset):
        return {
            "provider": "faster_whisper",
            "timeline_segments": [
                {
                    "id": 1,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 0,
                    "end_ms": 9200,
                    "content": "女主推开房门迈步进屋，在门口顿了一下，扭头看向对方。",
                }
            ],
        }

    async def fake_detect_shot_segments(self, *, project, source_asset, video_meta):
        return [
            {
                "id": "shot-motion-1",
                "segment_index": 1,
                "start_ms": 0,
                "end_ms": 9200,
                "duration_ms": 9200,
                "start_frame": 0,
                "end_frame": 276,
                "boundary_in_type": "cut",
                "boundary_out_type": "cut",
                "detector_name": "stub",
                "detector_version": None,
                "detector_config_json": {},
                "keyframe_asset_ids_json": [],
                "transcript_text": "推开房门迈步进屋，在门口顿了一下，扭头看向对方。",
                "ocr_text": "",
                "title": "门口停顿镜头",
                "visual_summary": "角色推开房门迈步进屋，在门口短暂停住后扭头看向对方。",
                "shot_type_code": "medium",
                "camera_angle_code": "eye_level",
                "camera_motion_code": "tracking",
                "scene_label": "office",
                "confidence": 0.95,
                "metadata_json": {},
            }
        ]

    monkeypatch.setattr(
        ProjectService,
        "_transcribe_source_media",
        fake_transcribe_source_media,
    )
    monkeypatch.setattr(
        ProjectService,
        "_detect_shot_segments",
        fake_detect_shot_segments,
    )

    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        project_response = client.post(
            "/api/projects/upload",
            headers=_csrf_headers(client),
            data={
                "objective": "先完成视频分析，再做动作提取",
                "workflow_type": "analysis",
            },
            files={
                "file": ("motion-source.mp4", BytesIO(b"fake-video-bytes"), "video/mp4"),
            },
        )
        assert project_response.status_code == 200
        project_id = project_response.json()["data"]["id"]
        service = ProjectService()
        project = service._get_project_for_execution(project_id=project_id)
        assert project is not None

        extract_response = client.post(
            "/api/assets/motions/extract",
            headers=_csrf_headers(client),
            json={
                "project_id": project_id,
                "extraction_hint": "优先关注推门进入、停顿回头这类动作",
            },
        )
        assert extract_response.status_code == 200
        job_id = extract_response.json()["data"]["job_id"]

        job_response = client.get(f"/api/jobs/{job_id}")
        assert job_response.status_code == 200
        job = job_response.json()["data"]
        assert job["job_type"] == "motion_extraction"
        assert job["status"] == "succeeded"
        assert job["result_json"]["candidate_count"] >= 1
        assert job["result_json"]["saved_count"] >= 1
        assert all(
            step["status"] == "completed"
            for step in job["result_json"]["steps"]
        )

        list_response = client.get("/api/assets/motions?review_status=approved")
        assert list_response.status_code == 200
        items = list_response.json()["data"]["items"]
        project_items = [item for item in items if item["metadata_json"]["project_id"] == project_id]
        assert project_items
        assert project_items[0]["metadata_json"]["signal_score"] >= 3
        assert "matched_sources" in project_items[0]["metadata_json"]
        assert project_items[0]["metadata_json"]["extraction_hint"] == "优先关注推门进入、停顿回头这类动作"
        assert project_items[0]["review_status"] == "approved"


def test_extract_motion_assets_persists_preview_assets(tmp_path, monkeypatch) -> None:
    async def fake_transcribe_source_media(self, *, project, source_asset):
        return {
            "provider": "faster_whisper",
            "timeline_segments": [
                {
                    "id": 1,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 0,
                    "end_ms": 4200,
                    "content": "工厂团队挥手欢迎，微笑示意。",
                }
            ],
        }

    async def fake_detect_shot_segments(self, *, project, source_asset, video_meta):
        return [
            {
                "id": "shot-preview-1",
                "segment_index": 1,
                "start_ms": 0,
                "end_ms": 4200,
                "duration_ms": 4200,
                "start_frame": 0,
                "end_frame": 126,
                "boundary_in_type": "cut",
                "boundary_out_type": "cut",
                "detector_name": "stub",
                "detector_version": None,
                "detector_config_json": {},
                "keyframe_asset_ids_json": [],
                "transcript_text": "工厂团队挥手欢迎，微笑示意。",
                "ocr_text": "",
                "title": "工厂欢迎镜头",
                "visual_summary": "工厂团队站在门口挥手欢迎，面带微笑。",
                "shot_type_code": "wide",
                "camera_angle_code": "eye_level",
                "camera_motion_code": "static",
                "scene_label": "factory",
                "confidence": 0.95,
                "metadata_json": {},
            }
        ]

    async def fake_generate_motion_tags_reply(
        self,
        *,
        source_name,
        candidate,
        fallback_payload,
        extraction_hint=None,
        provider_group=None,
    ):
        return {
            "payload": {
                "action_label": "wave",
                "entrance_style": "welcome_entrance",
                "emotion_label": "friendly",
                "temperament_label": "warm",
                "scene_label": "factory_gate",
                "camera_motion": "static",
                "camera_shot": "wide",
                "action_summary": "工厂团队在门口微笑挥手欢迎来访者。",
                "confidence": 0.88,
                "is_high_value": True,
            },
            "provider": "doubao",
            "model": "doubao-seed-test",
            "used_remote": True,
        }

    async def fake_extract_thumbnail(self, *, ffmpeg_bin, source_file, project_id, segment_id, timestamp_ms):
        output_path = tmp_path / f"{project_id}-{segment_id}.jpg"
        output_path.write_bytes(b"fake-thumbnail")
        return str(output_path)

    async def fake_extract_clip(
        self,
        *,
        ffmpeg_bin,
        source_file,
        project_id,
        segment_id,
        start_ms,
        end_ms,
    ):
        output_path = tmp_path / f"{project_id}-{segment_id}.mp4"
        output_path.write_bytes(b"fake-clip")
        return str(output_path)

    monkeypatch.setattr(ProjectService, "_transcribe_source_media", fake_transcribe_source_media)
    monkeypatch.setattr(ProjectService, "_detect_shot_segments", fake_detect_shot_segments)
    monkeypatch.setattr(AnalysisAIService, "generate_motion_tags_reply", fake_generate_motion_tags_reply)
    monkeypatch.setattr(MotionService, "_extract_thumbnail", fake_extract_thumbnail)
    monkeypatch.setattr(MotionService, "_extract_clip", fake_extract_clip)
    monkeypatch.setattr("app.services.motion_service.shutil.which", lambda _binary: "/usr/bin/ffmpeg")

    with _build_test_client(tmp_path) as client:
        login_response = _login(client, login="admin", password="Admin12345!")
        assert login_response.status_code == 200
        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 200
        current_user_id = me_response.json()["data"]["id"]

        project_response = client.post(
            "/api/projects/upload",
            headers=_csrf_headers(client),
            data={
                "objective": "先完成视频分析，再做动作提取",
                "workflow_type": "analysis",
            },
            files={
                "file": ("motion-preview-source.mp4", BytesIO(b"fake-video-bytes"), "video/mp4"),
            },
        )
        assert project_response.status_code == 200
        project_id = project_response.json()["data"]["id"]

        extract_response = client.post(
            "/api/assets/motions/extract",
            headers=_csrf_headers(client),
            json={"project_id": project_id},
        )
        assert extract_response.status_code == 200
        job_id = extract_response.json()["data"]["job_id"]

        job_response = client.get(f"/api/jobs/{job_id}")
        assert job_response.status_code == 200
        job = job_response.json()["data"]
        assert job["status"] == "succeeded"
        assert job["result_json"]["saved_count"] == 1

        motion_id = job["result_json"]["asset_ids"][0]
        detail_response = client.get(f"/api/assets/motions/{motion_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert detail["confidence"] == 0.88
        assert detail["asset_candidate"] is True
        assert detail["review_status"] == "approved"
        assert detail["clip_asset_id"]
        assert detail["clip_asset"]["asset_type"] == "video"
        assert detail["clip_asset"]["source_type"] == "derived"
        assert detail["clip_asset"]["thumbnail_path"]
        assert detail["metadata_json"]["thumbnail_asset_id"]
        assert detail["metadata_json"]["thumbnail_path"]
        assert detail["metadata_json"]["used_remote"] is True

        thumbnail_asset = AssetService().get_asset(
            asset_id=detail["metadata_json"]["thumbnail_asset_id"],
            owner_user_id=current_user_id,
        )
        assert thumbnail_asset is not None
        assert thumbnail_asset["asset_type"] == "image"
        assert thumbnail_asset["source_type"] == "derived"


def test_motion_ai_tags_normalize_factory_labels_to_new_schema() -> None:
    service = MotionService()
    candidate = {
        "matched_labels": ["wave", "display_product"],
        "combined_text": "工厂团队在门口微笑挥手欢迎，随后特写展示塑料颗粒产品细节。",
        "scene_label": "factory_entrance",
        "camera_motion_code": "static",
        "shot_type_code": "wide",
        "title": "工厂欢迎与产品展示",
        "visual_summary": "工厂团队欢迎来访者，并特写展示产品。",
    }
    fallback_tags = service._build_fallback_tags(candidate=candidate)

    normalized = service._normalize_ai_tags(
        candidate=candidate,
        tags={
            "action_label": "Factory team smiling and waving to welcome visitors",
            "entrance_style": "welcome entrance",
            "emotion_label": "friendly",
            "temperament_label": "professional",
            "scene_label": "factory entrance",
            "camera_motion": "static",
            "camera_shot": "wide shot",
            "action_summary": "工厂团队在入口处微笑挥手，欢迎来访者。",
            "confidence": 0.81,
            "is_high_value": True,
        },
        fallback_tags=fallback_tags,
    )

    assert normalized["action_label"] == "team_greeting"
    assert normalized["entrance_style"] == "welcome_entrance"
    assert normalized["emotion_label"] == "friendly_welcome"
    assert normalized["temperament_label"] == "skilled_professional"
    assert normalized["scene_label"] == "factory_entrance"
    assert normalized["camera_shot"] == "wide"


def test_review_and_batch_review_motion_assets(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200
        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 200
        current_user_id = me_response.json()["data"]["id"]

        asset_response = client.post(
            "/api/assets/upload",
            headers=_csrf_headers(client),
            files={
                "file": ("motion-review-source.mp4", BytesIO(b"fake-video-bytes"), "video/mp4"),
            },
        )
        assert asset_response.status_code == 200
        source_asset_id = asset_response.json()["data"]["id"]

        created_items = AssetService().create_motion_assets_from_analysis(
            source_video_asset_id=source_asset_id,
            project_id=None,
            job_id=None,
            owner_user_id=current_user_id,
            clips=[
                {
                    "start_ms": 0,
                    "end_ms": 2400,
                    "action_summary": "角色推门进入办公室。",
                    "action_label": "push_door_enter",
                    "emotion_label": "determination",
                    "scene_label": "office",
                    "camera_motion": "tracking",
                    "camera_shot": "medium",
                    "review_status": "auto_tagged",
                    "confidence": 0.91,
                    "asset_candidate": True,
                    "metadata_json": {"project_id": 1, "source_shot_segment_id": "shot-1"},
                },
                {
                    "start_ms": 3000,
                    "end_ms": 5200,
                    "action_summary": "角色停顿后回头凝视。",
                    "action_label": "pause_and_turn",
                    "emotion_label": "pressure",
                    "scene_label": "corridor",
                    "camera_motion": "static",
                    "camera_shot": "close_up",
                    "review_status": "auto_tagged",
                    "confidence": 0.84,
                    "asset_candidate": True,
                    "metadata_json": {"project_id": 1, "source_shot_segment_id": "shot-2"},
                },
            ],
        )
        assert created_items[0]["confidence"] == 0.91
        assert created_items[0]["asset_candidate"] is True

        review_response = client.patch(
            f"/api/assets/motions/{created_items[0]['id']}/review",
            headers=_csrf_headers(client),
            json={"action": "approve", "comment": "可以入库"},
        )
        assert review_response.status_code == 200
        reviewed_item = review_response.json()["data"]
        assert reviewed_item["review_status"] == "approved"
        assert reviewed_item["metadata_json"]["last_review_comment"] == "可以入库"

        batch_response = client.post(
            "/api/assets/motions/batch-review",
            headers=_csrf_headers(client),
            json={
                "ids": [created_items[1]["id"]],
                "action": "reject",
                "comment": "动作价值不足",
            },
        )
        assert batch_response.status_code == 200
        assert batch_response.json()["data"]["reviewed_count"] == 1

        detail_response = client.get(f"/api/assets/motions/{created_items[1]['id']}")
        assert detail_response.status_code == 200
        assert detail_response.json()["data"]["review_status"] == "rejected"
