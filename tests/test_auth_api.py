from pathlib import Path
from io import BytesIO

from fastapi.testclient import TestClient

from app.core.application import create_app
from app.core.config import settings
from app.services import captcha_service


def _build_test_client(tmp_path: Path) -> TestClient:
    settings.database_url = f"sqlite:///{tmp_path / 'auth-test.db'}"
    settings.environment = "development"
    settings.auth_jwt_secret = "unit-test-secret-value-which-is-long-enough"
    settings.auth_jwt_issuer = "unit-test-suite"
    settings.auth_initial_admin_username = "admin"
    settings.auth_initial_admin_email = "admin@example.com"
    settings.auth_initial_admin_password = "Admin12345!"
    settings.auth_initial_admin_display_name = "Admin User"
    settings.auth_allow_public_register = False
    settings.auth_require_captcha_for_login = True
    settings.auth_rate_limit_max_attempts = 5
    settings.auth_rate_limit_block_seconds = 60
    settings.auth_cookie_secure = False
    settings.auth_cookie_samesite = "lax"

    return TestClient(create_app(serve_frontend_static=False))


def _captcha_pair(client: TestClient) -> tuple[str, str]:
    captcha_response = client.get("/api/common/captcha")
    assert captcha_response.status_code == 200
    captcha_id = captcha_response.json()["data"]["captcha_id"]
    captcha_code = captcha_service._records[captcha_id].code
    return captcha_id, captcha_code


def _login(
    client: TestClient,
    *,
    login: str,
    password: str,
    remember: bool = False,
    captcha_code: str | None = None,
) -> TestClient:
    captcha_id, actual_captcha_code = _captcha_pair(client)
    response = client.post(
        "/api/auth/login",
        json={
            "login": login,
            "password": password,
            "captcha_id": captcha_id,
            "captcha_code": captcha_code or actual_captcha_code,
            "remember": remember,
        },
    )
    return response


def _csrf_headers(client: TestClient) -> dict[str, str]:
    csrf_token = client.cookies.get(settings.auth_cookie_csrf_name)
    assert csrf_token
    return {"X-CSRF-Token": csrf_token}


def _upload_video_asset(client: TestClient, *, file_name: str = "test.mp4") -> str:
    response = client.post(
        "/api/assets/upload",
        headers=_csrf_headers(client),
        files={
            "file": (file_name, BytesIO(b"fake-video-bytes"), "video/mp4"),
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


def test_auth_admin_login_cookie_me_and_refresh(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
            remember=True,
        )

        assert login_response.status_code == 200
        login_body = login_response.json()
        assert login_body["router"] == "/api/auth/login"
        assert login_body["data"]["token_type"] == "Cookie"
        assert login_body["data"]["user"]["username"] == "admin"
        assert client.cookies.get(settings.auth_cookie_access_name)
        assert client.cookies.get(settings.auth_cookie_refresh_name)
        assert client.cookies.get(settings.auth_cookie_csrf_name)

        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 200
        me_body = me_response.json()
        assert me_body["router"] == "/api/auth/me"
        assert me_body["data"]["username"] == "admin"
        assert any(role["code"] == "super_admin" for role in me_body["data"]["roles"])

        refresh_response = client.post(
            "/api/auth/refresh",
            headers=_csrf_headers(client),
        )
        assert refresh_response.status_code == 200
        refreshed_body = refresh_response.json()
        assert refreshed_body["data"]["user"]["username"] == "admin"
        assert refreshed_body["data"]["csrf_token"] == client.cookies.get(settings.auth_cookie_csrf_name)


def test_public_register_disabled_by_default(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        register_response = client.post(
            "/api/auth/register",
            json={
                "username": "member01",
                "email": "member01@example.com",
                "password": "Member12345!",
                "display_name": "Member 01",
            },
        )

        assert register_response.status_code == 403
        assert register_response.json()["message"] == "当前环境已关闭公开注册。"


def test_auth_role_permission_assignment_and_business_guards(tmp_path) -> None:
    with _build_test_client(tmp_path) as admin_client:
        admin_login = _login(
            admin_client,
            login="admin@example.com",
            password="Admin12345!",
        )
        assert admin_login.status_code == 200
        admin_headers = _csrf_headers(admin_client)

        permission_response = admin_client.post(
            "/api/auth/permissions",
            json={
                "code": "reports.view",
                "name": "查看报表",
                "group_name": "reports",
                "description": "允许查看报表页面。",
            },
            headers=admin_headers,
        )
        assert permission_response.status_code == 200
        permission_code = permission_response.json()["data"]["code"]
        assert permission_code == "reports.view"

        role_response = admin_client.post(
            "/api/auth/roles",
            json={
                "code": "report_viewer",
                "name": "报表查看者",
                "description": "只允许查看报表。",
                "permission_codes": ["reports.view", "profile.read"],
            },
            headers=admin_headers,
        )
        assert role_response.status_code == 200
        role_permissions = role_response.json()["data"]["permissions"]
        assert {item["code"] for item in role_permissions} == {"reports.view", "profile.read"}

        user_response = admin_client.post(
            "/api/auth/users",
            json={
                "username": "analyst01",
                "email": "analyst01@example.com",
                "password": "Analyst12345!",
                "display_name": "Analyst 01",
                "role_codes": ["report_viewer"],
                "is_active": True,
                "is_superuser": False,
            },
            headers=admin_headers,
        )
        assert user_response.status_code == 200
        user_id = user_response.json()["data"]["id"]

        assign_response = admin_client.post(
            f"/api/auth/users/{user_id}/roles",
            json={"role_codes": ["report_viewer"]},
            headers=admin_headers,
        )
        assert assign_response.status_code == 200
        assert any(
            role["code"] == "report_viewer"
            for role in assign_response.json()["data"]["roles"]
        )

    with _build_test_client(tmp_path) as user_client:
        user_login = _login(
            user_client,
            login="analyst01",
            password="Analyst12345!",
        )
        assert user_login.status_code == 200

        me_response = user_client.get("/api/auth/me")
        assert me_response.status_code == 200
        permission_codes = {
            item["code"]
            for item in me_response.json()["data"]["permissions"]
        }
        assert "reports.view" in permission_codes

        denied_users_response = user_client.get("/api/auth/users")
        assert denied_users_response.status_code == 403

        denied_tiktok_response = user_client.post(
            "/api/tiktok/info",
            json={"value": "7339393672959757570"},
            headers=_csrf_headers(user_client),
        )
        assert denied_tiktok_response.status_code == 403

    with _build_test_client(tmp_path) as anonymous_client:
        anonymous_response = anonymous_client.post(
            "/api/tiktok/info",
            json={"value": "7339393672959757570"},
        )
        assert anonymous_response.status_code == 401


def test_change_password_logout_and_old_access_token_revoked(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200
        old_access_token = client.cookies.get(settings.auth_cookie_access_name)
        assert old_access_token

        no_csrf_change = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "Admin12345!",
                "new_password": "Admin54321!",
            },
        )
        assert no_csrf_change.status_code == 403

        change_password_response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "Admin12345!",
                "new_password": "Admin54321!",
            },
            headers=_csrf_headers(client),
        )
        assert change_password_response.status_code == 200
        assert change_password_response.json()["data"]["changed"] is True

        old_access_me = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {old_access_token}"},
        )
        assert old_access_me.status_code == 401

        relogin_response = _login(
            client,
            login="admin",
            password="Admin54321!",
        )
        assert relogin_response.status_code == 200
        relogin_access_token = client.cookies.get(settings.auth_cookie_access_name)
        assert relogin_access_token

        no_csrf_logout = client.post("/api/auth/logout")
        assert no_csrf_logout.status_code == 403

        logout_response = client.post(
            "/api/auth/logout",
            headers=_csrf_headers(client),
        )
        assert logout_response.status_code == 200
        assert logout_response.json()["data"]["revoked"] is True

        old_logout_token_response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {relogin_access_token}"},
        )
        assert old_logout_token_response.status_code == 401


def test_admin_disable_user_revokes_active_session(tmp_path) -> None:
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
                "username": "member02",
                "email": "member02@example.com",
                "password": "Member12345!",
                "display_name": "Member 02",
                "role_codes": ["user"],
                "is_active": True,
                "is_superuser": False,
            },
            headers=_csrf_headers(admin_client),
        )
        assert create_user_response.status_code == 200
        user_id = create_user_response.json()["data"]["id"]

    with _build_test_client(tmp_path) as member_client:
        member_login = _login(
            member_client,
            login="member02",
            password="Member12345!",
        )
        assert member_login.status_code == 200
        member_access_token = member_client.cookies.get(settings.auth_cookie_access_name)
        assert member_access_token

        me_response = member_client.get("/api/auth/me")
        assert me_response.status_code == 200

        with _build_test_client(tmp_path) as admin_client:
            admin_relogin = _login(
                admin_client,
                login="admin",
                password="Admin12345!",
            )
            assert admin_relogin.status_code == 200
            disable_response = admin_client.patch(
                f"/api/auth/users/{user_id}",
                json={"is_active": False},
                headers=_csrf_headers(admin_client),
            )
            assert disable_response.status_code == 200
            assert disable_response.json()["data"]["is_active"] is False

        disabled_cookie_response = member_client.get("/api/auth/me")
        assert disabled_cookie_response.status_code == 401

        disabled_bearer_response = member_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {member_access_token}"},
        )
        assert disabled_bearer_response.status_code == 401


def test_login_rate_limit_and_captcha_enforced(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        missing_captcha_response = client.post(
            "/api/auth/login",
            json={
                "login": "admin",
                "password": "Admin12345!",
            },
        )
        assert missing_captcha_response.status_code == 422

        wrong_captcha_response = _login(
            client,
            login="admin",
            password="Admin12345!",
            captcha_code="WRONG1",
        )
        assert wrong_captcha_response.status_code == 400

        for _ in range(settings.auth_rate_limit_max_attempts - 1):
            failed_response = _login(
                client,
                login="admin",
                password="WrongPassword123!",
            )
            assert failed_response.status_code == 401

        blocked_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert blocked_response.status_code == 429
        assert blocked_response.json()["message"] == "登录尝试过于频繁，请稍后再试。"
