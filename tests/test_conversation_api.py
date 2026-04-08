from fastapi.testclient import TestClient

from tests.test_auth_api import _build_test_client, _csrf_headers, _login, _upload_video_asset


def test_create_conversation_requires_auth(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        response = client.post(
            "/api/conversations",
            json={
                "title": "测试会话",
                "conversation_type": "mixed",
            },
        )

        assert response.status_code == 401


def test_create_conversation_success(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        response = client.post(
            "/api/conversations",
            headers=_csrf_headers(client),
            json={
                "title": "短剧动作分析",
                "conversation_type": "mixed",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["id"]
        assert body["data"]["title"] == "短剧动作分析"
        assert body["data"]["conversation_type"] == "mixed"
        assert body["data"]["status"] == "active"


def test_list_conversations_success(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        create_response = client.post(
            "/api/conversations",
            headers=_csrf_headers(client),
            json={
                "title": "视频分析会话",
                "conversation_type": "mixed",
            },
        )
        assert create_response.status_code == 200

        response = client.get("/api/conversations")
        assert response.status_code == 200

        body = response.json()
        assert "items" in body["data"]
        assert len(body["data"]["items"]) >= 1


def test_create_plain_message_success(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        conversation_response = client.post(
            "/api/conversations",
            headers=_csrf_headers(client),
            json={
                "title": "消息测试会话",
                "conversation_type": "mixed",
            },
        )
        assert conversation_response.status_code == 200
        conversation_id = conversation_response.json()["data"]["id"]

        message_response = client.post(
            f"/api/conversations/{conversation_id}/messages",
            headers=_csrf_headers(client),
            json={
                "message_type": "text",
                "content": "你好，帮我分析视频",
                "asset_ids": [],
                "options": {},
            },
        )

        assert message_response.status_code == 200
        body = message_response.json()
        assert body["data"]["message_id"]
        assert body["data"]["job"] is None


def test_create_analysis_message_creates_job_and_results(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        conversation_response = client.post(
            "/api/conversations",
            headers=_csrf_headers(client),
            json={
                "title": "分析任务会话",
                "conversation_type": "mixed",
            },
        )
        assert conversation_response.status_code == 200
        conversation_id = conversation_response.json()["data"]["id"]
        asset_id = _upload_video_asset(client)

        message_response = client.post(
            f"/api/conversations/{conversation_id}/messages",
            headers=_csrf_headers(client),
            json={
                "message_type": "video_analysis_request",
                "content": "分析这个视频里的出场动作",
                "asset_ids": [asset_id],
                "options": {
                    "extract_motion_clips": True,
                    "generate_tags": True,
                },
            },
        )

        assert message_response.status_code == 200
        body = message_response.json()
        assert body["data"]["message_id"]
        assert body["data"]["job"] is not None
        assert body["data"]["job"]["job_type"] == "video_analysis"

        list_response = client.get(f"/api/conversations/{conversation_id}/messages")
        assert list_response.status_code == 200
        items = list_response.json()["data"]["items"]

        assert any(item["message_type"] == "video_analysis_request" for item in items)
        assert any(item["message_type"] == "job_status" for item in items)
        assert any(item["message_type"] == "video_analysis_result" for item in items)


def test_create_analysis_message_rejects_missing_asset(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        conversation_response = client.post(
            "/api/conversations",
            headers=_csrf_headers(client),
            json={
                "title": "缺失资产测试会话",
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
                "content": "分析这个视频里的出场动作",
                "asset_ids": ["asset_missing_001"],
                "options": {},
            },
        )

        assert message_response.status_code == 404
        assert "以下资产不存在或无权访问" in message_response.json()["message"]
