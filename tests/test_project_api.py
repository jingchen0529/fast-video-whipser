import base64
from io import BytesIO
from pathlib import Path

import pytest

from app.crawlers.tiktok import TikTokAPPCrawler
from app.db import create_connection
from app.services.analysis_ai_service import AnalysisAIService
from app.services.project_service import ProjectService
from app.services.system_settings_service import SystemSettingsService
from app.utils.file_utils import FileUtils
from tests.test_auth_api import _build_test_client, _csrf_headers, _login


@pytest.mark.asyncio
async def test_submit_kling_video_generation_task_uses_official_endpoint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncHttpClient:
        def __init__(self, **kwargs):
            captured["headers"] = kwargs.get("headers") or {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def fetch_post_json(self, url: str, json: dict[str, object]):
            captured["url"] = url
            captured["json"] = json
            return {
                "task_id": "kling-task-001",
                "task_status": "submitted",
            }

    monkeypatch.setattr("app.services.project_service.AsyncHttpClient", FakeAsyncHttpClient)

    service = ProjectService()
    result = await service._submit_kling_video_generation_task(
        provider={
            "provider": "kling",
            "label": "可灵",
            "base_url": "",
            "api_key": "access-key:secret-key",
            "request_model": "kling-v3",
            "display_model": "kling-v3",
        },
        request_payload={
            "prompt": "一个人拿着折叠水杯在通勤路上快速展示使用动作",
            "negative_prompt": "模糊，低清",
            "duration_seconds": 5,
            "aspect_ratio": "9:16",
        },
    )

    assert captured["url"] == "https://api-beijing.klingai.com/v1/videos/text2video"
    assert captured["json"] == {
        "model_name": "kling-v3",
        "prompt": "一个人拿着折叠水杯在通勤路上快速展示使用动作",
        "negative_prompt": "模糊，低清",
        "mode": "pro",
        "aspect_ratio": "9:16",
        "duration": "5",
    }
    authorization = str((captured["headers"] or {}).get("Authorization") or "")
    assert authorization.startswith("Bearer ")
    assert authorization.count(".") == 2
    assert result["provider_task_id"] == "kling-task-001"
    assert result["status"] == "running"


def test_resolve_faster_whisper_compute_type_uses_recommended_value_for_auto(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        SystemSettingsService,
        "get_transcription_capabilities",
        lambda self: {
            "providers": {
                "faster_whisper": {
                    "recommended_device": "cpu",
                    "recommended_compute_type": "int8",
                }
            }
        },
    )

    service = ProjectService()

    assert service._resolve_faster_whisper_compute_type({"compute_type": "auto"}) == "int8"
    assert service._resolve_faster_whisper_compute_type({"compute_type": "default"}) == "int8"
    assert service._resolve_faster_whisper_compute_type({"compute_type": "float32"}) == "float32"


@pytest.mark.asyncio
async def test_poll_kling_video_generation_task_extracts_task_result(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncHttpClient:
        def __init__(self, **kwargs):
            captured["headers"] = kwargs.get("headers") or {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def fetch_get_json(self, url: str):
            captured["url"] = url
            return {
                "task_status": "succeed",
                "task_result": {
                    "videos": [
                        {
                            "url": "https://example.com/generated-kling.mp4",
                            "cover_url": "https://example.com/generated-kling.jpg",
                        }
                    ]
                },
            }

    monkeypatch.setattr("app.services.project_service.AsyncHttpClient", FakeAsyncHttpClient)

    service = ProjectService()
    result = await service._poll_kling_video_generation_task(
        provider={
            "provider": "kling",
            "label": "可灵",
            "base_url": "",
            "api_key": "kling-bearer-token",
            "request_model": "kling-v3",
            "display_model": "kling-v3",
        },
        provider_task_id="kling-task-001",
    )

    assert captured["url"] == "https://api-beijing.klingai.com/v1/videos/text2video/kling-task-001"
    assert result["status"] == "succeeded"
    assert result["result_video_url"] == "https://example.com/generated-kling.mp4"
    assert result["cover_url"] == "https://example.com/generated-kling.jpg"


@pytest.mark.asyncio
async def test_submit_doubao_video_generation_task_supports_ark_base_url(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncHttpClient:
        def __init__(self, **kwargs):
            captured["headers"] = kwargs.get("headers") or {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def fetch_post_json(self, url: str, json: dict[str, object]):
            captured["url"] = url
            captured["json"] = json
            return {
                "id": "doubao-task-001",
                "status": "submitted",
            }

    monkeypatch.setattr("app.services.project_service.AsyncHttpClient", FakeAsyncHttpClient)

    service = ProjectService()
    result = await service._submit_doubao_video_generation_task(
        provider={
            "provider": "doubao",
            "label": "豆包",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks",
            "api_key": "doubao-key",
            "request_model": "doubao-seedance-1-5-pro-251215",
            "display_model": "doubao-seedance-1-5-pro-251215",
        },
        request_payload={
            "prompt": "参考原视频节奏生成一条新的电动滑板车带货视频",
            "duration_seconds": 5,
            "aspect_ratio": "9:16",
        },
    )

    assert captured["url"] == "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
    assert captured["json"] == {
        "model": "doubao-seedance-1-5-pro-251215",
        "content": [
            {
                "type": "text",
                "text": "参考原视频节奏生成一条新的电动滑板车带货视频",
            }
        ],
        "duration": 5,
        "ratio": "9:16",
    }
    authorization = str((captured["headers"] or {}).get("Authorization") or "")
    assert authorization == "Bearer doubao-key"
    assert result["provider_task_id"] == "doubao-task-001"
    assert result["status"] == "running"


@pytest.mark.asyncio
async def test_poll_doubao_video_generation_task_supports_ark_base_url(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncHttpClient:
        def __init__(self, **kwargs):
            captured["headers"] = kwargs.get("headers") or {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def fetch_get_json(self, url: str):
            captured["url"] = url
            return {
                "status": "succeeded",
                "data": {
                    "video_url": "https://example.com/generated-doubao.mp4",
                },
            }

    monkeypatch.setattr("app.services.project_service.AsyncHttpClient", FakeAsyncHttpClient)

    service = ProjectService()
    result = await service._poll_doubao_video_generation_task(
        provider={
            "provider": "doubao",
            "label": "豆包",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_key": "doubao-key",
            "request_model": "doubao-seedance-1-5-pro-251215",
            "display_model": "doubao-seedance-1-5-pro-251215",
        },
        provider_task_id="doubao-task-001",
    )

    assert (
        captured["url"]
        == "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/doubao-task-001"
    )
    assert result["status"] == "succeeded"
    assert result["result_video_url"] == "https://example.com/generated-doubao.mp4"


@pytest.mark.asyncio
async def test_submit_veo_video_generation_task_uses_predict_long_running(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncHttpClient:
        def __init__(self, **kwargs):
            captured["headers"] = kwargs.get("headers") or {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def fetch_post_json(self, url: str, json: dict[str, object]):
            captured["url"] = url
            captured["json"] = json
            return {
                "name": "projects/demo/locations/us-central1/publishers/google/models/veo-3.0-generate-001/operations/op-123",
                "done": False,
            }

    monkeypatch.setattr("app.services.project_service.AsyncHttpClient", FakeAsyncHttpClient)

    service = ProjectService()
    result = await service._submit_veo_video_generation_task(
        provider={
            "provider": "veo",
            "label": "Veo",
            "base_url": "https://us-central1-aiplatform.googleapis.com/v1/projects/demo/locations/us-central1/publishers/google/models/veo-3.0-generate-001",
            "api_key": "veo-token",
            "request_model": "veo-3.0-generate-001",
            "display_model": "veo-3.0-generate-001",
        },
        request_payload={
            "prompt": "A commuter takes a foldable cup from a backpack and drinks coffee on a train platform",
            "negative_prompt": "blurry, low quality",
            "duration_seconds": 6,
            "aspect_ratio": "9:16",
            "resolution": "720P",
        },
    )

    assert captured["url"] == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/demo/locations/us-central1/"
        "publishers/google/models/veo-3.0-generate-001:predictLongRunning"
    )
    assert captured["json"] == {
        "instances": [
            {
                "prompt": "A commuter takes a foldable cup from a backpack and drinks coffee on a train platform",
            }
        ],
        "parameters": {
            "sampleCount": 1,
            "durationSeconds": 6,
            "aspectRatio": "9:16",
            "negativePrompt": "blurry, low quality",
            "resolution": "720p",
        },
    }
    assert (captured["headers"] or {}).get("Authorization") == "Bearer veo-token"
    assert result["provider_task_id"].endswith("/operations/op-123")
    assert result["status"] == "running"


@pytest.mark.asyncio
async def test_poll_veo_video_generation_task_extracts_inline_video_bytes(monkeypatch) -> None:
    captured: dict[str, object] = {}
    encoded_video = base64.b64encode(b"fake-veo-video").decode("ascii")

    class FakeAsyncHttpClient:
        def __init__(self, **kwargs):
            captured["headers"] = kwargs.get("headers") or {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def fetch_post_json(self, url: str, json: dict[str, object]):
            captured["url"] = url
            captured["json"] = json
            return {
                "done": True,
                "response": {
                    "videos": [
                        {
                            "bytesBase64Encoded": encoded_video,
                        }
                    ]
                },
            }

    monkeypatch.setattr("app.services.project_service.AsyncHttpClient", FakeAsyncHttpClient)

    service = ProjectService()
    result = await service._poll_veo_video_generation_task(
        provider={
            "provider": "veo",
            "label": "Veo",
            "base_url": "https://us-central1-aiplatform.googleapis.com/v1/projects/demo/locations/us-central1/publishers/google/models/veo-3.0-generate-001",
            "api_key": "veo-token",
            "request_model": "veo-3.0-generate-001",
            "display_model": "veo-3.0-generate-001",
        },
        provider_task_id="projects/demo/locations/us-central1/publishers/google/models/veo-3.0-generate-001/operations/op-123",
    )

    assert captured["url"] == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/demo/locations/us-central1/"
        "publishers/google/models/veo-3.0-generate-001:fetchPredictOperation"
    )
    assert captured["json"] == {
        "operationName": "projects/demo/locations/us-central1/publishers/google/models/veo-3.0-generate-001/operations/op-123",
    }
    assert result["status"] == "succeeded"
    assert result["inline_video_bytes"] == encoded_video
    assert result["result_video_url"] == ""


@pytest.mark.asyncio
async def test_materialize_generated_video_file_accepts_inline_video_bytes(monkeypatch, tmp_path) -> None:
    output_dir = tmp_path / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ProjectService, "_generated_upload_dir", lambda self: output_dir)

    service = ProjectService()
    encoded_video = base64.b64encode(b"inline-video-binary").decode("ascii")

    target_path = await service._materialize_generated_video_file(
        provider={
            "provider": "veo",
            "api_key": "veo-token",
        },
        generation_result={
            "inline_video_bytes": encoded_video,
            "result_video_url": "",
        },
    )

    assert Path(target_path).exists()
    assert Path(target_path).read_bytes() == b"inline-video-binary"


def test_analysis_ai_service_prefers_default_provider_over_enabled_doubao(monkeypatch) -> None:
    monkeypatch.setattr(
        SystemSettingsService,
        "get_settings",
        lambda self: {
            "analysis": {
                "default_provider": "openai",
                "providers": [
                    {
                        "provider": "openai",
                        "enabled": True,
                        "api_key": "openai-key",
                        "base_url": "https://api.openai.com/v1",
                        "default_model": "gpt-4.1",
                    },
                    {
                        "provider": "doubao",
                        "enabled": True,
                        "api_key": "doubao-key",
                        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                        "default_model": "doubao-seed-1-6-250615",
                    },
                ],
            },
        },
    )

    provider = AnalysisAIService()._resolve_provider()

    assert provider["provider"] == "openai"
    assert provider["api_key"] == "openai-key"
    assert provider["base_url"] == "https://api.openai.com/v1"
    assert provider["request_model"] == "gpt-4.1"
    assert provider["display_model"] == "gpt-4.1"


def test_upload_project_with_file_completes_analysis_workflow(monkeypatch, tmp_path) -> None:
    async def fake_transcribe_source_media(self, *, project, source_asset):
        return {
            "provider": "faster_whisper",
            "timeline_segments": [
                {
                    "id": 1,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 0,
                    "end_ms": 3000,
                    "content": "这是第一段真实转写内容。",
                },
                {
                    "id": 2,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 3000,
                    "end_ms": 9000,
                    "content": "这是第二段真实转写内容。",
                },
                {
                    "id": 3,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 9000,
                    "end_ms": 15000,
                    "content": "这是第三段真实转写内容。",
                },
                {
                    "id": 4,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 15000,
                    "end_ms": 21000,
                    "content": "这是第四段真实转写内容。",
                },
            ],
        }

    monkeypatch.setattr(
        ProjectService,
        "_transcribe_source_media",
        fake_transcribe_source_media,
    )

    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        response = client.post(
            "/api/projects/upload",
            headers=_csrf_headers(client),
            data={
                "objective": "请分析这个视频的脚本结构和电商转化节奏",
                "workflow_type": "analysis",
            },
            files={
                "file": ("demo.mp4", BytesIO(b"fake-video-bytes"), "video/mp4"),
            },
        )

        assert response.status_code == 200
        body = response.json()
        project_id = body["data"]["id"]

        detail_response = client.get(f"/api/projects/{project_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert detail["status"] == "succeeded"
        assert "messages" in detail
        assert detail["source_type"] == "upload"
        assert detail["media_url"].startswith("/uploads/project-sources/")
        assert detail["script_overview"]["full_text"]
        assert "优化建议" in detail["ecommerce_analysis"]["content"]
        assert len(detail["timeline_segments"]) == 4
        assert len(detail["shot_segments"]) >= 1
        assert detail["storyboard"]["items"]
        assert detail["storyboard"]["summary"]
        assert len(detail["messages"]) >= 6
        assert detail["messages"][0]["role"] == "user"
        assert detail["messages"][0]["message_type"] == "project_request"
        assert any(
            item["message_type"] == "analysis_reply"
            for item in detail["messages"]
        )
        assert any(
            item["message_type"] == "suggestion_reply"
            for item in detail["messages"]
        )
        assert [step["step_key"] for step in detail["task_steps"]] == [
            "extract_video_link",
            "validate_video_link",
            "segment_video_shots",
            "analyze_video_content",
            "identify_audio_content",
            "generate_storyboard",
            "generate_response",
            "generate_suggestions",
            "finish",
        ]
        assert all(step["status"] == "completed" for step in detail["task_steps"])


def test_upload_project_accepts_source_url_and_runs_workflow(monkeypatch, tmp_path) -> None:
    async def fake_fetch_video_info(self, value: str):
        assert value == "https://www.tiktok.com/@demo/video/1234567890"
        return {
            "aweme_id": "1234567890",
            "download_url": "https://example.com/video.mp4",
            "video_info": {
                "aweme_id": "1234567890",
                "desc": "夏季爆款短视频脚本分析案例",
                "duration_ms": 16890,
                "width": 720,
                "height": 1280,
            },
            "tiktok_basic_info": {
                "author": "demo_author",
                "statistics": {
                    "play_count": 12345,
                },
            },
        }

    async def fake_download_file_from_url(self, file_url: str) -> str:
        assert file_url == "https://example.com/video.mp4"
        target = Path(self.TEMP_DIR) / "downloaded.mp4"
        target.write_bytes(b"fake-downloaded-video")
        return str(target)

    monkeypatch.setattr(TikTokAPPCrawler, "fetch_video_info", fake_fetch_video_info)
    monkeypatch.setattr(FileUtils, "download_file_from_url", fake_download_file_from_url)

    async def fake_generate_analysis_reply(self, **kwargs):
        return {
            "content": "## 爆点总结\n豆包已生成分析正文。",
            "provider": "doubao",
            "model": "doubao-seed-1-6-250615",
            "used_remote": True,
        }

    async def fake_generate_suggestions_reply(self, **kwargs):
        return {
            "content": "1. 先强化前三秒钩子。\n2. 增加卖点证明镜头。",
            "provider": "doubao",
            "model": "doubao-seed-1-6-250615",
            "used_remote": True,
        }

    monkeypatch.setattr(
        AnalysisAIService,
        "generate_analysis_reply",
        fake_generate_analysis_reply,
    )
    monkeypatch.setattr(
        AnalysisAIService,
        "generate_suggestions_reply",
        fake_generate_suggestions_reply,
    )

    async def fake_openai_transcribe(self, *, source_asset, provider):
        assert provider["default_model"] == "whisper-1"
        assert provider["api_key"] == "whisper-key"
        return {
            "timeline_segments": [
                {
                    "id": 1,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 0,
                    "end_ms": 6000,
                    "content": "OpenAI Whisper 识别到的第一段文本。",
                },
                {
                    "id": 2,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 6000,
                    "end_ms": 12000,
                    "content": "OpenAI Whisper 识别到的第二段文本。",
                },
            ],
            "language": "zh",
        }

    monkeypatch.setattr(
        ProjectService,
        "_transcribe_with_openai_api",
        fake_openai_transcribe,
    )

    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        settings_payload = SystemSettingsService().get_settings()
        settings_payload["transcription"]["default_provider"] = "openai_whisper_api"
        for provider in settings_payload["transcription"]["providers"]:
            if provider["provider"] == "openai_whisper_api":
                provider["enabled"] = True
                provider["api_key"] = "whisper-key"
                provider["default_model"] = "whisper-1"
        SystemSettingsService().update_settings(payload=settings_payload)

        response = client.post(
            "/api/projects/upload",
            headers=_csrf_headers(client),
            data={
                "objective": "请分析这个视频的脚本结构",
                "workflow_type": "analysis",
                "source_url": "https://www.tiktok.com/@demo/video/1234567890",
            },
        )

        assert response.status_code == 200
        body = response.json()
        project_id = body["data"]["id"]
        assert body["data"]["source_url"] == "https://www.tiktok.com/@demo/video/1234567890"
        assert body["data"]["source_type"] == "url"

        detail_response = client.get(f"/api/projects/{project_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert detail["status"] == "succeeded"
        assert detail["title"] == "夏季爆款短视频脚本分析案例"
        assert detail["source_platform"] == "tiktok"
        assert detail["media_url"].startswith("/uploads/project-sources/")
        assert detail["summary"] == "视频分析工作流已完成，已输出结构化分镜、脚本梳理、电商效果分析和优化建议。"
        assert "豆包已生成分析正文。" in detail["ecommerce_analysis"]["content"]
        assert "OpenAI Whisper 识别到的第一段文本。" in detail["script_overview"]["full_text"]
        assert len(detail["shot_segments"]) >= 1
        assert detail["storyboard"]["items"]
        assert any(
            item["message_type"] == "analysis_reply"
            and item["content"].startswith("## 爆点总结")
            for item in detail["messages"]
        )
        assert detail["task_steps"][1]["status"] == "completed"
        assert detail["task_steps"][-1]["step_key"] == "finish"


def test_project_detail_rebuilds_legacy_analysis_task_steps(monkeypatch, tmp_path) -> None:
    async def fake_transcribe_source_media(self, *, project, source_asset):
        return {
            "provider": "faster_whisper",
            "timeline_segments": [
                {
                    "id": 1,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 0,
                    "end_ms": 3200,
                    "content": "这是旧项目的第一段转写内容。",
                },
                {
                    "id": 2,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 3200,
                    "end_ms": 8600,
                    "content": "这是旧项目的第二段转写内容。",
                },
            ],
        }

    monkeypatch.setattr(
        ProjectService,
        "_transcribe_source_media",
        fake_transcribe_source_media,
    )

    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        response = client.post(
            "/api/projects/upload",
            headers=_csrf_headers(client),
            data={
                "objective": "请分析这个历史项目的步骤兼容性",
                "workflow_type": "analysis",
            },
            files={
                "file": ("legacy.mp4", BytesIO(b"legacy-video-bytes"), "video/mp4"),
            },
        )

        assert response.status_code == 200
        project_id = response.json()["data"]["id"]

        connection = create_connection()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM project_task_steps
                WHERE project_id = %s
                ORDER BY display_order ASC, id ASC
                """,
                (project_id,),
            ).fetchall()
            rows_by_key = {row["step_key"]: dict(row) for row in rows}
            legacy_step_keys = [
                "extract_video_link",
                "validate_video_link",
                "analyze_video_content",
                "identify_audio_content",
                "generate_response",
                "generate_suggestions",
                "finish",
            ]

            connection.execute(
                "DELETE FROM project_task_steps WHERE project_id = %s",
                (project_id,),
            )
            for index, step_key in enumerate(legacy_step_keys, start=1):
                row = rows_by_key[step_key]
                detail = row["detail"]
                if step_key == "analyze_video_content":
                    detail = "已完成视频画面、节奏和结构分析，识别出 4 个高价值脚本片段。"
                connection.execute(
                    """
                    INSERT INTO project_task_steps (
                        project_id, step_key, title, detail, status,
                        error_detail, output_json, display_order, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        project_id,
                        step_key,
                        row["title"],
                        detail,
                        row["status"],
                        row["error_detail"],
                        row["output_json"],
                        index,
                        row["created_at"],
                        row["updated_at"],
                    ),
                )
            connection.commit()
        finally:
            connection.close()

        detail_response = client.get(f"/api/projects/{project_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert [step["step_key"] for step in detail["task_steps"]] == [
            "extract_video_link",
            "validate_video_link",
            "segment_video_shots",
            "analyze_video_content",
            "identify_audio_content",
            "generate_storyboard",
            "generate_response",
            "generate_suggestions",
            "finish",
        ]
        rebuilt_steps = {
            step["step_key"]: step
            for step in detail["task_steps"]
        }
        assert rebuilt_steps["segment_video_shots"]["status"] == "completed"
        assert rebuilt_steps["generate_storyboard"]["status"] == "completed"
        assert rebuilt_steps["segment_video_shots"]["detail"].startswith("旧版任务兼容补齐")
        assert rebuilt_steps["generate_storyboard"]["detail"].startswith("旧版任务兼容补齐")
        assert rebuilt_steps["analyze_video_content"]["detail"] == (
            "已完成视频画面、节奏和结构分析，识别出 4 个高价值脚本片段。"
        )


def test_upload_project_extracts_url_from_objective(monkeypatch, tmp_path) -> None:
    async def fake_fetch_video_info(self, value: str):
        assert value == "https://www.tiktok.com/@demo/video/8888888888"
        return {
            "aweme_id": "8888888888",
            "download_url": "https://example.com/extracted.mp4",
            "video_info": {
                "aweme_id": "8888888888",
                "desc": "从输入文本提取链接后的分析案例",
                "duration_ms": 24000,
                "width": 1080,
                "height": 1920,
            },
            "tiktok_basic_info": {},
        }

    async def fake_download_file_from_url(self, file_url: str) -> str:
        assert file_url == "https://example.com/extracted.mp4"
        target = Path(self.TEMP_DIR) / "extracted.mp4"
        target.write_bytes(b"fake-extracted-video")
        return str(target)

    monkeypatch.setattr(TikTokAPPCrawler, "fetch_video_info", fake_fetch_video_info)
    monkeypatch.setattr(FileUtils, "download_file_from_url", fake_download_file_from_url)

    async def fake_transcribe_source_media(self, *, project, source_asset):
        return {
            "provider": "faster_whisper",
            "timeline_segments": [
                {
                    "id": 1,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 0,
                    "end_ms": 5000,
                    "content": "从输入文本提取链接后，已完成第一段转写。",
                }
            ],
        }

    monkeypatch.setattr(
        ProjectService,
        "_transcribe_source_media",
        fake_transcribe_source_media,
    )

    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        response = client.post(
            "/api/projects/upload",
            headers=_csrf_headers(client),
            data={
                "objective": "帮我分析这个视频脚本 https://www.tiktok.com/@demo/video/8888888888",
                "workflow_type": "analysis",
            },
        )

        assert response.status_code == 200
        project_id = response.json()["data"]["id"]

        detail_response = client.get(f"/api/projects/{project_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert detail["status"] == "succeeded"
        assert detail["source_url"] == "https://www.tiktok.com/@demo/video/8888888888"
        assert detail["source_type"] == "url"
        assert detail["title"] == "从输入文本提取链接后的分析案例"
        assert "第一段转写" in detail["script_overview"]["full_text"]
        assert len(detail["shot_segments"]) >= 1
        assert detail["storyboard"]["items"]


def test_upload_project_create_workflow_generates_video_asset(monkeypatch, tmp_path) -> None:
    async def fake_submit_generic(self, *, provider, request_payload):
        assert provider["provider"] == "custom"
        assert request_payload["mode"] == "create"
        assert request_payload["prompt"]
        return {
            "provider_task_id": "create-task-001",
            "status": "running",
            "result_video_url": "",
            "raw_response": {"task_id": "create-task-001"},
        }

    async def fake_poll_generic(self, *, provider, provider_task_id):
        assert provider["provider"] == "custom"
        assert provider_task_id == "create-task-001"
        return {
            "status": "succeeded",
            "provider_task_id": provider_task_id,
            "result_video_url": "https://example.com/generated-create.mp4",
            "cover_url": "",
            "error_detail": "",
            "raw_response": {"status": "succeeded"},
        }

    async def fake_download_file_from_url(self, file_url: str) -> str:
        assert file_url == "https://example.com/generated-create.mp4"
        target = Path(self.TEMP_DIR) / "generated-create.mp4"
        target.write_bytes(b"fake-generated-create-video")
        return str(target)

    monkeypatch.setattr(
        ProjectService,
        "_submit_generic_video_generation_task",
        fake_submit_generic,
    )
    monkeypatch.setattr(
        ProjectService,
        "_poll_generic_video_generation_task",
        fake_poll_generic,
    )
    monkeypatch.setattr(
        FileUtils,
        "download_file_from_url",
        fake_download_file_from_url,
    )

    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        settings_payload = SystemSettingsService().get_settings()
        settings_payload["remake"]["default_provider"] = "custom"
        for provider in settings_payload["remake"]["providers"]:
            provider["enabled"] = provider["provider"] == "custom"
            if provider["provider"] == "custom":
                provider["base_url"] = "https://video.example.com/tasks"
                provider["api_key"] = "custom-video-key"
                provider["default_model"] = "custom-video-model"
                provider["model_options"] = ["custom-video-model"]
        SystemSettingsService().update_settings(payload=settings_payload)

        response = client.post(
            "/api/projects/upload",
            headers=_csrf_headers(client),
            data={
                "objective": (
                    "我希望创作的视频类型：产品演示\n"
                    "我的目标客群：北美通勤人群\n"
                    "我的商品名称：折叠水杯\n"
                    "我的商品卖点：便携、防漏、轻量\n"
                    "我倾向的视频风格：真实口播 + 生活化场景"
                ),
                "workflow_type": "create",
            },
        )

        assert response.status_code == 200
        project_id = response.json()["data"]["id"]

        detail_response = client.get(f"/api/projects/{project_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert detail["workflow_type"] == "create"
        assert detail["status"] == "succeeded"
        assert detail["video_generation"]["status"] == "succeeded"
        assert detail["video_generation"]["provider"] == "custom"
        assert detail["video_generation"]["model"] == "custom-video-model"
        assert detail["video_generation"]["provider_task_id"] == "create-task-001"
        assert detail["video_generation"]["output_asset_id"]
        assert detail["video_generation"]["asset_url"].startswith("/uploads/generated/")
        assert detail["generated_media_url"] == detail["video_generation"]["asset_url"]
        assert detail["video_generation"]["prompt"]
        assert detail["script_overview"]["full_text"]
        assert detail["storyboard"]["items"]
        assert [step["step_key"] for step in detail["task_steps"]] == [
            "define_objective",
            "generate_script",
            "select_style_reference",
            "generate_video",
            "post_production",
            "finish",
        ]
        assert all(step["status"] == "completed" for step in detail["task_steps"])
        assert any(
            message["message_type"] == "video_generation_result"
            for message in detail["messages"]
        )


def test_upload_project_remake_workflow_generates_video_asset(monkeypatch, tmp_path) -> None:
    async def fake_submit_generic(self, *, provider, request_payload):
        assert provider["provider"] == "custom"
        assert request_payload["mode"] == "remake"
        assert request_payload["prompt"]
        return {
            "provider_task_id": "remake-task-001",
            "status": "running",
            "result_video_url": "",
            "raw_response": {"task_id": "remake-task-001"},
        }

    async def fake_poll_generic(self, *, provider, provider_task_id):
        assert provider["provider"] == "custom"
        assert provider_task_id == "remake-task-001"
        return {
            "status": "succeeded",
            "provider_task_id": provider_task_id,
            "result_video_url": "https://example.com/generated-remake.mp4",
            "cover_url": "",
            "error_detail": "",
            "raw_response": {"status": "succeeded"},
        }

    async def fake_download_file_from_url(self, file_url: str) -> str:
        assert file_url == "https://example.com/generated-remake.mp4"
        target = Path(self.TEMP_DIR) / "generated-remake.mp4"
        target.write_bytes(b"fake-generated-remake-video")
        return str(target)

    async def fake_transcribe_source_media(self, *, project, source_asset):
        return {
            "provider": "faster_whisper",
            "timeline_segments": [
                {
                    "id": 1,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 0,
                    "end_ms": 4000,
                    "content": "参考视频开场先抛出卖点，再快速展示使用动作。",
                }
            ],
        }

    monkeypatch.setattr(
        ProjectService,
        "_submit_generic_video_generation_task",
        fake_submit_generic,
    )
    monkeypatch.setattr(
        ProjectService,
        "_poll_generic_video_generation_task",
        fake_poll_generic,
    )
    monkeypatch.setattr(
        ProjectService,
        "_transcribe_source_media",
        fake_transcribe_source_media,
    )
    monkeypatch.setattr(
        FileUtils,
        "download_file_from_url",
        fake_download_file_from_url,
    )

    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        settings_payload = SystemSettingsService().get_settings()
        settings_payload["remake"]["default_provider"] = "custom"
        for provider in settings_payload["remake"]["providers"]:
            provider["enabled"] = provider["provider"] == "custom"
            if provider["provider"] == "custom":
                provider["base_url"] = "https://video.example.com/tasks"
                provider["api_key"] = "custom-video-key"
                provider["default_model"] = "custom-video-model"
                provider["model_options"] = ["custom-video-model"]
        SystemSettingsService().update_settings(payload=settings_payload)

        response = client.post(
            "/api/projects/upload",
            headers=_csrf_headers(client),
            data={
                "objective": (
                    "任务类型：爆款复刻\n"
                    "保留项：节奏、镜头切换、卖点结构\n"
                    "改写项：人物、场景、产品文案\n"
                    "目标平台：TikTok\n"
                    "目标人群：北美女性 25-35 岁\n"
                    "商品卖点：防水、轻便、便携\n"
                    "风格偏好：真实口播 + 生活化场景"
                ),
                "workflow_type": "remake",
            },
            files={
                "file": ("reference.mp4", BytesIO(b"fake-remake-source-video"), "video/mp4"),
            },
        )

        assert response.status_code == 200
        project_id = response.json()["data"]["id"]

        detail_response = client.get(f"/api/projects/{project_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert detail["workflow_type"] == "remake"
        assert detail["status"] == "succeeded"
        assert detail["video_generation"]["status"] == "succeeded"
        assert detail["video_generation"]["provider"] == "custom"
        assert detail["video_generation"]["model"] == "custom-video-model"
        assert detail["video_generation"]["provider_task_id"] == "remake-task-001"
        assert detail["video_generation"]["output_asset_id"]
        assert detail["video_generation"]["asset_url"].startswith("/uploads/generated/")
        assert detail["generated_media_url"] == detail["video_generation"]["asset_url"]
        assert detail["media_url"].startswith("/uploads/project-sources/")
        assert detail["video_generation"]["prompt"]
        assert detail["source_analysis"]["visual_features"]
        assert "参考视频开场先抛出卖点" in detail["script_overview"]["full_text"]
        assert detail["storyboard"]["items"]
        assert [step["step_key"] for step in detail["task_steps"]] == [
            "extract_video_link",
            "validate_video_link",
            "analyze_reference_video",
            "define_remake_intent",
            "build_remake_prompt",
            "generate_video",
            "poll_generation_result",
            "finish",
        ]
        assert all(step["status"] == "completed" for step in detail["task_steps"])
        assert any(
            message["message_type"] == "video_generation_result"
            for message in detail["messages"]
        )


def test_upload_project_remake_workflow_falls_back_to_visual_script_when_transcription_fails(
    monkeypatch,
    tmp_path,
) -> None:
    async def fake_submit_generic(self, *, provider, request_payload):
        assert provider["provider"] == "custom"
        assert request_payload["mode"] == "remake"
        return {
            "provider_task_id": "remake-fallback-task-001",
            "status": "running",
            "result_video_url": "",
            "raw_response": {"task_id": "remake-fallback-task-001"},
        }

    async def fake_poll_generic(self, *, provider, provider_task_id):
        assert provider["provider"] == "custom"
        assert provider_task_id == "remake-fallback-task-001"
        return {
            "status": "succeeded",
            "provider_task_id": provider_task_id,
            "result_video_url": "https://example.com/generated-remake-fallback.mp4",
            "cover_url": "",
            "error_detail": "",
            "raw_response": {"status": "succeeded"},
        }

    async def fake_download_file_from_url(self, file_url: str) -> str:
        assert file_url == "https://example.com/generated-remake-fallback.mp4"
        target = Path(self.TEMP_DIR) / "generated-remake-fallback.mp4"
        target.write_bytes(b"fake-generated-remake-video")
        return str(target)

    async def fake_transcribe_source_media(self, *, project, source_asset):
        raise ValueError("faster-whisper 未识别到有效文本，请检查视频音轨或切换模型。")

    monkeypatch.setattr(
        ProjectService,
        "_submit_generic_video_generation_task",
        fake_submit_generic,
    )
    monkeypatch.setattr(
        ProjectService,
        "_poll_generic_video_generation_task",
        fake_poll_generic,
    )
    monkeypatch.setattr(
        ProjectService,
        "_transcribe_source_media",
        fake_transcribe_source_media,
    )
    monkeypatch.setattr(
        FileUtils,
        "download_file_from_url",
        fake_download_file_from_url,
    )

    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        settings_payload = SystemSettingsService().get_settings()
        settings_payload["remake"]["default_provider"] = "custom"
        for provider in settings_payload["remake"]["providers"]:
            provider["enabled"] = provider["provider"] == "custom"
            if provider["provider"] == "custom":
                provider["base_url"] = "https://video.example.com/tasks"
                provider["api_key"] = "custom-video-key"
                provider["default_model"] = "custom-video-model"
                provider["model_options"] = ["custom-video-model"]
        SystemSettingsService().update_settings(payload=settings_payload)

        response = client.post(
            "/api/projects/upload",
            headers=_csrf_headers(client),
            data={
                "objective": (
                    "任务类型：爆款复刻\n"
                    "保留项：节奏、镜头切换、卖点结构\n"
                    "改写项：人物、场景、产品文案\n"
                    "目标平台：TikTok\n"
                    "风格偏好：真实口播 + 生活化场景"
                ),
                "workflow_type": "remake",
            },
            files={
                "file": ("reference.mp4", BytesIO(b"fake-remake-source-video"), "video/mp4"),
            },
        )

        assert response.status_code == 200
        project_id = response.json()["data"]["id"]

        detail_response = client.get(f"/api/projects/{project_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert detail["status"] == "succeeded"
        assert detail["timeline_segments"]
        assert detail["script_overview"]["full_text"]
        assert "主体" in detail["script_overview"]["full_text"]
        assert detail["storyboard"]["items"]
        assert detail["storyboard"]["summary"]
        analyze_step = next(
            item for item in detail["task_steps"] if item["step_key"] == "analyze_reference_video"
        )
        assert "已根据镜头描述回填参考脚本" in analyze_step["detail"]


def test_upload_project_remake_accepts_source_url(monkeypatch, tmp_path) -> None:
    async def fake_fetch_video_info(self, value: str):
        assert value == "https://www.tiktok.com/@demo/video/1234567890"
        return {
            "aweme_id": "1234567890",
            "download_url": "https://example.com/remake-source.mp4",
            "video_info": {
                "aweme_id": "1234567890",
                "desc": "复刻参考视频案例",
                "duration_ms": 16890,
                "width": 720,
                "height": 1280,
            },
            "tiktok_basic_info": {
                "author": "demo_author",
                "statistics": {
                    "play_count": 12345,
                },
            },
        }

    async def fake_download_file_from_url(self, file_url: str) -> str:
        if file_url == "https://example.com/remake-source.mp4":
            target = Path(self.TEMP_DIR) / "remake-reference.mp4"
            target.write_bytes(b"fake-remake-reference-video")
            return str(target)

        assert file_url == "https://example.com/generated-remake-link.mp4"
        target = Path(self.TEMP_DIR) / "generated-remake-link.mp4"
        target.write_bytes(b"fake-remake-reference-video")
        return str(target)

    async def fake_submit_generic(self, *, provider, request_payload):
        assert provider["provider"] == "custom"
        assert request_payload["mode"] == "remake"
        assert request_payload["source_url"] == "https://example.com/remake-source.mp4"
        return {
            "provider_task_id": "remake-link-task-001",
            "status": "running",
            "result_video_url": "",
            "raw_response": {"task_id": "remake-link-task-001"},
        }

    async def fake_poll_generic(self, *, provider, provider_task_id):
        assert provider["provider"] == "custom"
        assert provider_task_id == "remake-link-task-001"
        return {
            "status": "succeeded",
            "provider_task_id": provider_task_id,
            "result_video_url": "https://example.com/generated-remake-link.mp4",
            "cover_url": "",
            "error_detail": "",
            "raw_response": {"status": "succeeded"},
        }

    async def fake_transcribe_source_media(self, *, project, source_asset):
        return {
            "provider": "faster_whisper",
            "timeline_segments": [
                {
                    "id": 1,
                    "segment_type": "speech",
                    "speaker": "口播",
                    "start_ms": 0,
                    "end_ms": 3200,
                    "content": "参考链接视频先展示产品动作，再补卖点字幕。",
                }
            ],
        }

    async def fake_detect_shot_segments(self, *, project, source_asset, video_meta):
        return [
            {
                "id": "shot-1",
                "segment_index": 1,
                "start_ms": 0,
                "end_ms": 3200,
                "duration_ms": 3200,
                "start_frame": 0,
                "end_frame": 96,
                "boundary_in_type": "cut",
                "boundary_out_type": "cut",
                "detector_name": "stub",
                "detector_version": None,
                "detector_config_json": {},
                "keyframe_asset_ids_json": [],
                "transcript_text": "",
                "ocr_text": "",
                "title": "参考开场镜头",
                "visual_summary": "开场突出产品主体动作",
                "shot_type_code": "wide",
                "camera_angle_code": "eye_level",
                "camera_motion_code": "static",
                "scene_label": "demo",
                "confidence": 0.9,
                "metadata_json": {},
            }
        ]

    monkeypatch.setattr(TikTokAPPCrawler, "fetch_video_info", fake_fetch_video_info)
    monkeypatch.setattr(FileUtils, "download_file_from_url", fake_download_file_from_url)
    monkeypatch.setattr(
        ProjectService,
        "_submit_generic_video_generation_task",
        fake_submit_generic,
    )
    monkeypatch.setattr(
        ProjectService,
        "_poll_generic_video_generation_task",
        fake_poll_generic,
    )
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

        settings_payload = SystemSettingsService().get_settings()
        settings_payload["remake"]["default_provider"] = "custom"
        for provider in settings_payload["remake"]["providers"]:
            provider["enabled"] = provider["provider"] == "custom"
            if provider["provider"] == "custom":
                provider["base_url"] = "https://video.example.com/tasks"
                provider["api_key"] = "custom-video-key"
                provider["default_model"] = "custom-video-model"
                provider["model_options"] = ["custom-video-model"]
        SystemSettingsService().update_settings(payload=settings_payload)

        response = client.post(
            "/api/projects/upload",
            headers=_csrf_headers(client),
            data={
                "objective": (
                    "任务类型：爆款复刻\n"
                    "保留项：节奏、镜头切换、卖点结构\n"
                    "改写项：人物、场景、产品文案\n"
                    "目标平台：TikTok"
                ),
                "workflow_type": "remake",
                "source_url": "https://www.tiktok.com/@demo/video/1234567890",
            },
        )

        assert response.status_code == 200
        project_id = response.json()["data"]["id"]

        detail_response = client.get(f"/api/projects/{project_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]

        assert detail["workflow_type"] == "remake"
        assert detail["source_type"] == "url"
        assert detail["status"] == "succeeded"
        assert detail["source_name"] == "复刻参考视频案例"
        assert detail["video_generation"]["status"] == "succeeded"
        assert detail["video_generation"]["provider"] == "custom"
        assert detail["video_generation"]["provider_task_id"] == "remake-link-task-001"
        assert detail["script_overview"]["full_text"]
        assert [step["step_key"] for step in detail["task_steps"]] == [
            "extract_video_link",
            "validate_video_link",
            "analyze_reference_video",
            "define_remake_intent",
            "build_remake_prompt",
            "generate_video",
            "poll_generation_result",
            "finish",
        ]
        assert all(step["status"] == "completed" for step in detail["task_steps"])
