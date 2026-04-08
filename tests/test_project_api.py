from io import BytesIO
from pathlib import Path

from app.crawlers.tiktok import TikTokAPPCrawler
from app.services.analysis_ai_service import AnalysisAIService
from app.utils.file_utils import FileUtils
from tests.test_auth_api import _build_test_client, _csrf_headers, _login


def test_upload_project_with_file_completes_analysis_workflow(tmp_path) -> None:
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
            "analyze_video_content",
            "identify_audio_content",
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
        assert detail["summary"] == "视频分析工作流已完成，已输出脚本梳理、电商效果分析和优化建议。"
        assert "豆包已生成分析正文。" in detail["ecommerce_analysis"]["content"]
        assert any(
            item["message_type"] == "analysis_reply"
            and item["content"].startswith("## 爆点总结")
            for item in detail["conversation_messages"]
        )
        assert detail["task_steps"][1]["status"] == "completed"
        assert detail["task_steps"][-1]["step_key"] == "finish"


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
