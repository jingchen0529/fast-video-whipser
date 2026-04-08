from io import BytesIO

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
