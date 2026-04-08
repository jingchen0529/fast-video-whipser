from fastapi.testclient import TestClient

from app.core.application import create_app
from app.core.config import settings
from app.crawlers.tiktok import TikTokAPPCrawler
from app.services import captcha_service


def _build_authenticated_client(tmp_path) -> TestClient:
    settings.database_url = f"sqlite:///{tmp_path / 'tiktok-test.db'}"
    settings.environment = "development"
    settings.auth_jwt_secret = "unit-test-secret-value-which-is-long-enough"
    settings.auth_jwt_issuer = "unit-test-suite"
    settings.auth_initial_admin_username = "admin"
    settings.auth_initial_admin_email = "admin@example.com"
    settings.auth_initial_admin_password = "Admin12345!"
    settings.auth_initial_admin_display_name = "Admin User"
    settings.auth_allow_public_register = False
    settings.auth_require_captcha_for_login = True
    settings.auth_cookie_secure = False
    settings.auth_cookie_samesite = "lax"

    return TestClient(create_app(serve_frontend_static=False))


def _login_admin(client: TestClient) -> None:
    captcha_response = client.get("/api/common/captcha")
    captcha_id = captcha_response.json()["data"]["captcha_id"]
    captcha_code = captcha_service._records[captcha_id].code
    login_response = client.post(
        "/api/auth/login",
        json={
            "login": "admin",
            "password": "Admin12345!",
            "captcha_id": captcha_id,
            "captcha_code": captcha_code,
            "remember": False,
        },
    )
    assert login_response.status_code == 200


def _csrf_headers(client: TestClient) -> dict[str, str]:
    csrf_token = client.cookies.get(settings.auth_cookie_csrf_name)
    assert csrf_token
    return {"X-CSRF-Token": csrf_token}


def test_tiktok_info_route_returns_structured_video_detail(monkeypatch, tmp_path) -> None:
    async def fake_fetch_video_info(self, value: str):
        assert value == "7339393672959757570"
        return {
            "aweme_id": "7339393672959757570",
            "download_url": "https://example.com/video.mp4",
            "video_info": {
                "aweme_id": "7339393672959757570",
                "desc": "demo video",
                "create_time": 1711888888,
                "duration_ms": 12345,
                "width": 720,
                "height": 1280,
                "ratio": "720p",
                "cover_url": "https://example.com/cover.jpeg",
                "download_url": "https://example.com/video.mp4",
            },
            "tiktok_basic_info": {
                "author": "angelinazhq",
                "author_nickname": "Angelina",
                "author_uid": "user-1",
                "music_title": "demo music",
                "music_author": "demo artist",
                "statistics": {
                    "play_count": 10,
                    "digg_count": 2,
                    "comment_count": 1,
                    "share_count": 3,
                    "collect_count": 4,
                },
            },
        }

    monkeypatch.setattr(TikTokAPPCrawler, "fetch_video_info", fake_fetch_video_info)

    with _build_authenticated_client(tmp_path) as client:
        _login_admin(client)

        response = client.post(
            "/tiktok/info",
            json={"value": "7339393672959757570"},
            headers=_csrf_headers(client),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 200
        assert body["router"] == "/tiktok/info"
        assert body["data"]["input"] == "7339393672959757570"
        assert body["data"]["aweme_id"] == "7339393672959757570"
        assert body["data"]["download_url"] == "https://example.com/video.mp4"
        assert body["data"]["video_info"]["duration_ms"] == 12345
        assert body["data"]["tiktok_basic_info"]["statistics"]["play_count"] == 10


def test_tiktok_info_route_validation_uses_error_envelope(tmp_path) -> None:
    with _build_authenticated_client(tmp_path) as client:
        _login_admin(client)

        response = client.post(
            "/tiktok/info",
            json={"value": "   "},
            headers=_csrf_headers(client),
        )

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == 422
        assert body["router"] == "/tiktok/info"
        assert body["message"] == "Request validation failed."
        assert isinstance(body["details"], list)
