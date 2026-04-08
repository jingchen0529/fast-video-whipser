from tests.test_auth_api import _build_test_client, _csrf_headers, _login, _upload_video_asset


def test_get_job_returns_404_when_missing(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        response = client.get("/api/jobs/not_exists")
        assert response.status_code == 404


def test_get_job_success(tmp_path) -> None:
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
                "title": "任务详情测试",
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
                "content": "分析这个视频",
                "asset_ids": [asset_id],
                "options": {},
            },
        )
        assert message_response.status_code == 200
        job_id = message_response.json()["data"]["job"]["id"]

        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()

        assert body["data"]["id"] == job_id
        assert body["data"]["job_type"] == "video_analysis"
        assert body["data"]["status"] in {"queued", "running", "succeeded"}
