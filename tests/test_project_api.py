from io import BytesIO
from pathlib import Path

from app.crawlers.tiktok import TikTokAPPCrawler
from app.db.sqlite import create_connection
from app.services.analysis_ai_service import AnalysisAIService
from app.services.project_service import ProjectService
from app.services.system_settings_service import SystemSettingsService
from app.utils.file_utils import FileUtils
from tests.test_auth_api import _build_test_client, _csrf_headers, _login


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
        assert detail["conversation_id"]
        assert detail["source_type"] == "upload"
        assert detail["media_url"].startswith("/uploads/project-sources/")
        assert detail["script_overview"]["full_text"]
        assert "优化建议" in detail["ecommerce_analysis"]["content"]
        assert len(detail["timeline_segments"]) == 4
        assert len(detail["shot_segments"]) >= 1
        assert detail["storyboard"]["items"]
        assert detail["storyboard"]["summary"]
        assert len(detail["conversation_messages"]) >= 6
        assert detail["conversation_messages"][0]["role"] == "user"
        assert detail["conversation_messages"][0]["message_type"] == "project_request"
        assert any(
            item["message_type"] == "analysis_reply"
            for item in detail["conversation_messages"]
        )
        assert any(
            item["message_type"] == "suggestion_reply"
            for item in detail["conversation_messages"]
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
            for item in detail["conversation_messages"]
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
                WHERE project_id = ?
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
                "DELETE FROM project_task_steps WHERE project_id = ?",
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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
