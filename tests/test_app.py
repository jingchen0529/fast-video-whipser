from fastapi.testclient import TestClient

from app.api.routers import common as common_router_module
from app.core.application import create_app
from app.core.config import settings
from app.services import captcha_service
from main import app

client = TestClient(app)


def _build_authenticated_client(tmp_path) -> TestClient:
    settings.database_url = f"sqlite:///{tmp_path / 'app-test.db'}"
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


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["router"] == "/health"
    assert body["data"]["status"] == "ok"


def test_health_check_legacy_route() -> None:
    response = client.get("/health/check")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["router"] == "/health/check"
    assert body["data"]["status"] == "ok"


def test_health_check_api_prefix() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["router"] == "/api/health"
    assert body["data"]["status"] == "ok"


def test_upload_file(tmp_path) -> None:
    with _build_authenticated_client(tmp_path) as auth_client:
        _login_admin(auth_client)

        response = auth_client.post(
            "/common/upload",
            files={"file": ("sample.txt", b"hello world", "text/plain")},
            headers=_csrf_headers(auth_client),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 200
        assert body["router"] == "/common/upload"
        assert body["data"]["original_name"] == "sample.txt"
        assert body["data"]["file_url"].startswith("/uploads/common/")
        assert body["data"]["size_bytes"] == 11


def test_upload_file_validation_error_uses_error_envelope(tmp_path) -> None:
    with _build_authenticated_client(tmp_path) as auth_client:
        _login_admin(auth_client)

        response = auth_client.post(
            "/common/upload",
            headers=_csrf_headers(auth_client),
        )

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == 422
        assert body["router"] == "/common/upload"
        assert body["message"] == "Request validation failed."
        assert isinstance(body["details"], list)


def test_common_captcha_route_returns_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        common_router_module.captcha_service,
        "create_captcha",
        lambda: {
            "captcha_id": "captcha-1",
            "captcha_type": "svg",
            "captcha_image": "data:image/svg+xml;base64,ZmFrZQ==",
            "expires_in_seconds": 300,
        },
    )

    response = client.get("/common/captcha")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["router"] == "/common/captcha"
    assert body["data"]["captcha_id"] == "captcha-1"
    assert body["data"]["captcha_type"] == "svg"
    assert body["data"]["expires_in_seconds"] == 300


def test_common_captcha_api_prefix_route_returns_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        common_router_module.captcha_service,
        "create_captcha",
        lambda: {
            "captcha_id": "captcha-2",
            "captcha_type": "svg",
            "captcha_image": "data:image/svg+xml;base64,ZmFrZTI=",
            "expires_in_seconds": 300,
        },
    )

    response = client.get("/api/common/captcha")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["router"] == "/api/common/captcha"
    assert body["data"]["captcha_id"] == "captcha-2"
    assert body["data"]["captcha_type"] == "svg"
    assert body["data"]["expires_in_seconds"] == 300


def test_common_captcha_verify_route_returns_result(monkeypatch) -> None:
    def fake_verify(captcha_id: str, captcha_code: str) -> bool:
        assert captcha_id == "captcha-1"
        assert captcha_code == "ABCD"
        return True

    monkeypatch.setattr(common_router_module.captcha_service, "verify_captcha", fake_verify)

    response = client.post(
        "/common/captcha/verify",
        json={"captcha_id": "captcha-1", "captcha_code": "ABCD"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["router"] == "/common/captcha/verify"
    assert body["data"]["captcha_id"] == "captcha-1"
    assert body["data"]["verified"] is True


def test_common_captcha_verify_api_prefix_route_returns_result(monkeypatch) -> None:
    def fake_verify(captcha_id: str, captcha_code: str) -> bool:
        assert captcha_id == "captcha-2"
        assert captcha_code == "WXYZ"
        return True

    monkeypatch.setattr(common_router_module.captcha_service, "verify_captcha", fake_verify)

    response = client.post(
        "/api/common/captcha/verify",
        json={"captcha_id": "captcha-2", "captcha_code": "WXYZ"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["router"] == "/api/common/captcha/verify"
    assert body["data"]["captcha_id"] == "captcha-2"
    assert body["data"]["verified"] is True


def test_create_app_can_serve_static_frontend(tmp_path) -> None:
    index_path = tmp_path / "index.html"
    asset_path = tmp_path / "robots.txt"
    index_content = "<html><body>frontend</body></html>"
    asset_content = "User-agent: *"
    index_path.write_text(index_content, encoding="utf-8")
    asset_path.write_text(asset_content, encoding="utf-8")

    static_app = create_app(
        serve_frontend_static=True,
        frontend_static_dir=tmp_path,
    )
    static_client = TestClient(static_app)

    root_response = static_client.get("/")
    route_response = static_client.get("/dashboard")
    asset_response = static_client.get("/robots.txt")
    api_response = static_client.get("/api/health")
    missing_api_response = static_client.get("/api/missing")

    assert root_response.status_code == 200
    assert root_response.text == index_content
    assert route_response.status_code == 200
    assert route_response.text == index_content
    assert asset_response.status_code == 200
    assert asset_response.text == asset_content
    assert api_response.status_code == 200
    assert api_response.json()["router"] == "/api/health"
    assert missing_api_response.status_code == 404
