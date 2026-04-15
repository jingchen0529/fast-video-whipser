from app.db import create_connection
from app.services.system_settings_service import SystemSettingsService
from tests.test_auth_api import _build_test_client, _csrf_headers, _login


def test_get_settings_returns_default_payload(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        response = client.get("/api/settings")

        assert response.status_code == 200
        body = response.json()
        assert body["router"] == "/api/settings"
        assert body["data"]["system"]["name"] == "爆款杀手"
        assert body["data"]["system"]["logo_url"] == "/logo.png"
        assert body["data"]["proxy"]["enabled"] is False
        assert body["data"]["analysis"]["default_provider"] == "openai"
        assert body["data"]["transcription"]["default_provider"] == "faster_whisper"
        assert {
            item["provider"]
            for item in body["data"]["analysis"]["providers"]
        } >= {"openai", "gemini", "doubao", "kimi", "qwen", "deepseek", "custom"}
        assert {
            item["provider"]
            for item in body["data"]["transcription"]["providers"]
        } >= {"faster_whisper", "openai_whisper_api"}
        assert {
            item["provider"]
            for item in body["data"]["remake"]["providers"]
        } >= {"doubao", "kling", "veo", "wanxiang", "custom"}

        head_response = client.head("/api/settings")
        assert head_response.status_code == 200

        capability_response = client.get("/api/settings/transcription/capabilities")
        assert capability_response.status_code == 200
        capability_payload = capability_response.json()["data"]
        assert capability_payload["default_provider"] == "faster_whisper"
        assert set(capability_payload["providers"].keys()) == {
            "faster_whisper",
            "openai_whisper_api",
        }

    connection = create_connection()
    try:
        row = connection.execute(
            "SELECT value_json FROM system_settings WHERE `key` = %s",
            ("runtime_ai_settings",),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None


def test_get_settings_backfills_legacy_payload(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        connection = create_connection()
        try:
            connection.execute(
                """
                INSERT INTO system_settings (`key`, value_json, updated_at, updated_by_user_id)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    "runtime_ai_settings",
                    '{"proxy":{"enabled":true,"http_url":"http://127.0.0.1:7890"}}',
                    1767225600000,
                    None,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        response = client.get("/api/settings")

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["system"]["name"] == "爆款杀手"
        assert payload["proxy"]["enabled"] is True
        assert payload["analysis"]["default_provider"] == "openai"
        assert payload["transcription"]["default_provider"] == "faster_whisper"

        connection = create_connection()
        try:
            row = connection.execute(
                "SELECT value_json FROM system_settings WHERE `key` = %s",
                ("runtime_ai_settings",),
            ).fetchone()
        finally:
            connection.close()
        assert row is not None
        assert '"system"' in row["value_json"]
        assert '"analysis"' in row["value_json"]
        assert '"transcription"' in row["value_json"]
        assert '"remake"' in row["value_json"]


def test_update_settings_persists_configuration(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        initial_response = client.get("/api/settings")
        assert initial_response.status_code == 200
        payload = initial_response.json()["data"]

        payload["proxy"]["enabled"] = True
        payload["proxy"]["http_url"] = "http://127.0.0.1:7890"
        payload["proxy"]["https_url"] = "http://127.0.0.1:7890"
        payload["proxy"]["no_proxy"] = "localhost,127.0.0.1"
        payload["analysis"]["default_provider"] = "deepseek"
        payload["transcription"]["default_provider"] = "openai_whisper_api"
        payload["remake"]["default_provider"] = "veo"

        for provider in payload["analysis"]["providers"]:
            if provider["provider"] == "deepseek":
                provider["enabled"] = True
                provider["api_key"] = "deepseek-key"
                provider["default_model"] = "deepseek-reasoner"
                provider["model_options"] = ["deepseek-reasoner", "deepseek-chat"]
        for provider in payload["remake"]["providers"]:
            if provider["provider"] == "veo":
                provider["enabled"] = True
                provider["base_url"] = "https://example.com/veo"
                provider["api_key"] = "veo-key"
                provider["default_model"] = "veo-3"
                provider["model_options"] = ["veo-3", "veo-2"]
        for provider in payload["transcription"]["providers"]:
            if provider["provider"] == "openai_whisper_api":
                provider["enabled"] = True
                provider["api_key"] = "whisper-key"
                provider["default_model"] = "whisper-1"
            if provider["provider"] == "faster_whisper":
                provider["model_dir"] = "./models/faster-whisper"
                provider["device"] = "cpu"
                provider["compute_type"] = "int8"
                provider["beam_size"] = 3

        update_response = client.patch(
            "/api/settings",
            headers=_csrf_headers(client),
            json=payload,
        )

        assert update_response.status_code == 200
        updated = update_response.json()["data"]
        assert updated["proxy"]["enabled"] is True
        assert updated["proxy"]["http_url"] == "http://127.0.0.1:7890"
        assert updated["analysis"]["default_provider"] == "deepseek"
        assert updated["transcription"]["default_provider"] == "openai_whisper_api"
        assert updated["remake"]["default_provider"] == "veo"
        deepseek_provider = next(
            item
            for item in updated["analysis"]["providers"]
            if item["provider"] == "deepseek"
        )
        assert deepseek_provider["enabled"] is True
        assert deepseek_provider["default_model"] == "deepseek-reasoner"
        veo_provider = next(
            item
            for item in updated["remake"]["providers"]
            if item["provider"] == "veo"
        )
        assert veo_provider["base_url"] == "https://example.com/veo"
        assert veo_provider["api_key"] == "veo-key"
        openai_whisper_provider = next(
            item
            for item in updated["transcription"]["providers"]
            if item["provider"] == "openai_whisper_api"
        )
        assert openai_whisper_provider["enabled"] is True
        assert openai_whisper_provider["api_key"] == "whisper-key"
        faster_provider = next(
            item
            for item in updated["transcription"]["providers"]
            if item["provider"] == "faster_whisper"
        )
        assert faster_provider["device"] == "cpu"
        assert faster_provider["compute_type"] == "int8"
        assert faster_provider["beam_size"] == 3

        get_response = client.get("/api/settings")
        assert get_response.status_code == 200
        persisted = get_response.json()["data"]
        assert persisted["proxy"]["https_url"] == "http://127.0.0.1:7890"
        assert persisted["proxy"]["no_proxy"] == "localhost,127.0.0.1"
        assert persisted["analysis"]["default_provider"] == "deepseek"
        assert persisted["transcription"]["default_provider"] == "openai_whisper_api"
        assert persisted["remake"]["default_provider"] == "veo"

        preview_response = client.post(
            "/api/settings/transcription/capabilities",
            headers=_csrf_headers(client),
            json=persisted,
        )
        assert preview_response.status_code == 200
        preview_payload = preview_response.json()["data"]
        assert preview_payload["default_provider"] == "openai_whisper_api"


def test_transcription_capabilities_recommend_cpu_int8_when_cuda_unavailable(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        SystemSettingsService,
        "_inspect_ctranslate2_cuda",
        staticmethod(lambda: {"cuda_available": False, "cuda_device_count": 0}),
    )

    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        capability_response = client.get("/api/settings/transcription/capabilities")

        assert capability_response.status_code == 200
        faster_whisper = capability_response.json()["data"]["providers"]["faster_whisper"]
        assert faster_whisper["recommended_device"] == "cpu"
        assert faster_whisper["recommended_compute_type"] == "int8"
        assert faster_whisper["available_compute_types"] == [
            "auto",
            "default",
            "int8",
            "float32",
        ]
        assert any("cpu + int8" in issue for issue in faster_whisper["issues"])


def test_update_settings_rejects_invalid_provider_base_url(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        initial_response = client.get("/api/settings")
        assert initial_response.status_code == 200
        payload = initial_response.json()["data"]

        for provider in payload["remake"]["providers"]:
            if provider["provider"] == "doubao":
                provider["enabled"] = True
                provider["base_url"] = "doubao-seedance-1-5-pro-251215"

        update_response = client.patch(
            "/api/settings",
            headers=_csrf_headers(client),
            json=payload,
        )

        assert update_response.status_code == 400
        assert (
            update_response.json()["message"]
            == "豆包 的 API Base Endpoint 必须以 http:// 或 https:// 开头。"
        )


def test_update_settings_normalizes_doubao_remake_task_endpoint(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        initial_response = client.get("/api/settings")
        assert initial_response.status_code == 200
        payload = initial_response.json()["data"]

        for provider in payload["remake"]["providers"]:
            if provider["provider"] == "doubao":
                provider["enabled"] = True
                provider["base_url"] = (
                    "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
                )
                provider["default_model"] = "doubao-seedance-1-5-pro-251215"

        update_response = client.patch(
            "/api/settings",
            headers=_csrf_headers(client),
            json=payload,
        )

        assert update_response.status_code == 200
        updated = update_response.json()["data"]
        doubao_provider = next(
            item
            for item in updated["remake"]["providers"]
            if item["provider"] == "doubao"
        )
        assert doubao_provider["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"


def test_regular_user_cannot_access_settings(tmp_path) -> None:
    with _build_test_client(tmp_path) as admin_client:
        admin_login = _login(
            admin_client,
            login="admin",
            password="Admin12345!",
        )
        assert admin_login.status_code == 200

        create_user_response = admin_client.post(
            "/api/auth/users",
            json={
                "username": "member03",
                "email": "member03@example.com",
                "password": "Member12345!",
                "display_name": "Member 03",
                "role_codes": ["user"],
                "is_active": True,
                "is_superuser": False,
            },
            headers=_csrf_headers(admin_client),
        )
        assert create_user_response.status_code == 200

    with _build_test_client(tmp_path) as member_client:
        member_login = _login(
            member_client,
            login="member03",
            password="Member12345!",
        )
        assert member_login.status_code == 200

        response = member_client.get("/api/settings")

        assert response.status_code == 403
