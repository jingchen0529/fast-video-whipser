from io import BytesIO

from app.services.asset_service import AssetService
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

        upload_response = client.post(
            "/api/assets/upload",
            headers=_csrf_headers(client),
            files={
                "file": ("analysis-source.mp4", BytesIO(b"fake-video-bytes"), "video/mp4"),
            },
        )
        assert upload_response.status_code == 200
        asset_id = upload_response.json()["data"]["id"]

        conversation_response = client.post(
            "/api/conversations",
            headers=_csrf_headers(client),
            json={
                "title": "动作资产生成测试",
                "conversation_type": "mixed",
            },
        )
        assert conversation_response.status_code == 200
        conversation_id = conversation_response.json()["data"]["id"]

        message_response = client.post(
            f"/api/conversations/{conversation_id}/messages",
            headers=_csrf_headers(client),
            json={
                "message_type": "video_analysis_request",
                "content": "分析这个视频里的动作资产候选",
                "asset_ids": [asset_id],
                "options": {
                    "extract_motion_clips": True,
                    "generate_tags": True,
                },
            },
        )
        assert message_response.status_code == 200

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
                    "end_ms": 3600,
                    "content": "女主推门进入办公室，停顿后回头凝视对方。",
                }
            ],
        }

    async def fake_detect_shot_segments(self, *, project, source_asset, video_meta):
        return [
            {
                "id": "shot-motion-1",
                "segment_index": 1,
                "start_ms": 0,
                "end_ms": 3600,
                "duration_ms": 3600,
                "start_frame": 0,
                "end_frame": 108,
                "boundary_in_type": "cut",
                "boundary_out_type": "cut",
                "detector_name": "stub",
                "detector_version": None,
                "detector_config_json": {},
                "keyframe_asset_ids_json": [],
                "transcript_text": "推门进入办公室，停顿后回头。",
                "ocr_text": "",
                "title": "推门进入镜头",
                "visual_summary": "角色推门进入办公室后短暂停顿并回头凝视。",
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
        source_asset = AssetService().get_asset(asset_id=project["source_asset_id"])
        assert source_asset is not None
        shot_segments = [
            {
                "id": "shot-motion-1",
                "segment_index": 1,
                "start_ms": 0,
                "end_ms": 3600,
                "duration_ms": 3600,
                "start_frame": 0,
                "end_frame": 108,
                "boundary_in_type": "cut",
                "boundary_out_type": "cut",
                "detector_name": "stub",
                "detector_version": None,
                "detector_config_json": {},
                "keyframe_asset_ids_json": [],
                "transcript_text": "推门进入办公室，停顿后回头。",
                "ocr_text": "",
                "title": "推门进入镜头",
                "visual_summary": "角色推门进入办公室后短暂停顿并回头凝视。",
                "shot_type_code": "medium",
                "camera_angle_code": "eye_level",
                "camera_motion_code": "tracking",
                "scene_label": "office",
                "confidence": 0.95,
                "metadata_json": {},
            }
        ]
        service._replace_shot_segments(
            project_id=project_id,
            project=project,
            source_asset=source_asset,
            shot_segments=shot_segments,
        )
        service._replace_storyboard(
            project_id=project_id,
            project=project,
            source_asset=source_asset,
            storyboard_payload={
                "summary": "角色推门进入后停顿回头，属于高价值动作片段。",
                "items": [
                    {
                        "item_index": 1,
                        "title": "推门进入镜头",
                        "start_ms": 0,
                        "end_ms": 3600,
                        "duration_ms": 3600,
                        "shot_type_code": "medium",
                        "camera_angle_code": "eye_level",
                        "camera_motion_code": "tracking",
                        "visual_description": "角色推门进入办公室后短暂停顿并回头凝视。",
                        "source_segment_indexes": [1],
                        "confidence": 0.95,
                    }
                ],
            },
            provider="fallback",
            model="fallback",
            used_remote=False,
        )

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
        assert job["job_type"] == "motion_extraction"
        assert job["status"] == "succeeded"
        assert job["result_json"]["candidate_count"] >= 1
        assert job["result_json"]["saved_count"] >= 1
        assert all(
            step["status"] == "completed"
            for step in job["result_json"]["steps"]
        )

        list_response = client.get("/api/assets/motions?review_status=auto_tagged")
        assert list_response.status_code == 200
        items = list_response.json()["data"]["items"]
        assert any(item["metadata_json"]["project_id"] == project_id for item in items)


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
            conversation_id=None,
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
                    "metadata_json": {"project_id": 1, "source_shot_segment_id": "shot-2"},
                },
            ],
        )

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
