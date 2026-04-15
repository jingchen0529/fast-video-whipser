import hashlib
from contextlib import contextmanager
from pathlib import Path
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit

import pymysql
from fastapi.testclient import TestClient

from app.core.application import create_app
from app.core.config import settings
from app.services import captcha_service


def _build_test_database_url(tmp_path: Path, *, prefix: str = "auth") -> str:
    parsed = urlsplit(settings.database_url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise RuntimeError(f"当前测试仅支持 MySQL DATABASE_URL，实际为: {settings.database_url}")

    database_hash = hashlib.md5(str(tmp_path).encode("utf-8")).hexdigest()[:12]
    database_name = f"fvw_test_{prefix}_{database_hash}"
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{database_name}", parsed.query, parsed.fragment))


def _quote_identifier(identifier: str) -> str:
    return f"`{identifier.replace('`', '``')}`"


def _drop_database(database_url: str) -> None:
    parsed = urlsplit(database_url)
    database_name = parsed.path.lstrip("/")
    if not database_name.startswith("fvw_test_"):
        raise RuntimeError(f"拒绝删除非测试数据库: {database_name}")

    admin_url = urlunsplit((parsed.scheme, parsed.netloc, "", parsed.query, parsed.fragment))
    admin_parsed = urlsplit(admin_url)
    connection = pymysql.connect(
        host=admin_parsed.hostname or "127.0.0.1",
        port=admin_parsed.port or 3306,
        user=admin_parsed.username or "root",
        password=admin_parsed.password or "",
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS {_quote_identifier(database_name)}")
    finally:
        connection.close()


@contextmanager
def _test_database_scope(tmp_path: Path, *, prefix: str = "auth"):
    original_settings = {
        "database_url": settings.database_url,
        "environment": settings.environment,
        "auth_jwt_secret": settings.auth_jwt_secret,
        "auth_jwt_issuer": settings.auth_jwt_issuer,
        "auth_initial_admin_username": settings.auth_initial_admin_username,
        "auth_initial_admin_email": settings.auth_initial_admin_email,
        "auth_initial_admin_password": settings.auth_initial_admin_password,
        "auth_initial_admin_display_name": settings.auth_initial_admin_display_name,
        "auth_allow_public_register": settings.auth_allow_public_register,
        "auth_require_captcha_for_login": settings.auth_require_captcha_for_login,
        "auth_rate_limit_max_attempts": settings.auth_rate_limit_max_attempts,
        "auth_rate_limit_block_seconds": settings.auth_rate_limit_block_seconds,
        "auth_cookie_secure": settings.auth_cookie_secure,
        "auth_cookie_samesite": settings.auth_cookie_samesite,
    }
    test_database_url = _build_test_database_url(tmp_path, prefix=prefix)
    settings.database_url = test_database_url
    try:
        yield test_database_url
    finally:
        try:
            _drop_database(test_database_url)
        except pymysql.MySQLError:
            # 测试失败时不要让清库错误覆盖原始异常；在真实 MySQL 环境下会继续尽力删除。
            pass
        finally:
            for key, value in original_settings.items():
                setattr(settings, key, value)


@contextmanager
def _build_test_client(tmp_path: Path):
    with _test_database_scope(tmp_path, prefix="auth"):
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
        with TestClient(create_app(serve_frontend_static=False)) as client:
            yield client


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


def _replace_cookie(client: TestClient, *, name: str, value: str) -> None:
    current_cookie = next(
        (cookie for cookie in client.cookies.jar if cookie.name == name),
        None,
    )
    assert current_cookie is not None
    client.cookies.set(
        name,
        value,
        domain=current_cookie.domain,
        path=current_cookie.path,
    )


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


def test_me_401_only_clears_access_cookie_and_still_allows_refresh(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
            remember=True,
        )
        assert login_response.status_code == 200

        original_refresh_token = client.cookies.get(settings.auth_cookie_refresh_name)
        original_csrf_token = client.cookies.get(settings.auth_cookie_csrf_name)
        assert original_refresh_token
        assert original_csrf_token

        _replace_cookie(
            client,
            name=settings.auth_cookie_access_name,
            value="broken.access.token",
        )

        me_response = client.get("/api/auth/me")
        assert me_response.status_code == 401
        assert client.cookies.get(settings.auth_cookie_access_name) is None
        assert client.cookies.get(settings.auth_cookie_refresh_name) == original_refresh_token
        assert client.cookies.get(settings.auth_cookie_csrf_name) == original_csrf_token

        refresh_response = client.post(
            "/api/auth/refresh",
            headers=_csrf_headers(client),
        )
        assert refresh_response.status_code == 200
        assert client.cookies.get(settings.auth_cookie_access_name)
        assert client.cookies.get(settings.auth_cookie_refresh_name)
        assert client.cookies.get(settings.auth_cookie_csrf_name)


def test_refresh_401_clears_all_auth_cookies(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
            remember=True,
        )
        assert login_response.status_code == 200

        _replace_cookie(
            client,
            name=settings.auth_cookie_refresh_name,
            value="broken.refresh.token",
        )

        refresh_response = client.post(
            "/api/auth/refresh",
            headers=_csrf_headers(client),
        )
        assert refresh_response.status_code == 401
        assert client.cookies.get(settings.auth_cookie_access_name) is None
        assert client.cookies.get(settings.auth_cookie_refresh_name) is None
        assert client.cookies.get(settings.auth_cookie_csrf_name) is None


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


def test_menu_tree_and_navigation_are_available_for_admin(tmp_path) -> None:
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200

        menu_tree_response = client.get("/api/menus/tree")
        assert menu_tree_response.status_code == 200
        menu_tree = menu_tree_response.json()["data"]
        root_codes = {item["code"] for item in menu_tree}
        assert {"dashboard.root", "system.root", "creation.root", "space.root"} <= root_codes

        system_root = next(item for item in menu_tree if item["code"] == "system.root")
        system_child_codes = {item["code"] for item in system_root["children"]}
        assert {"system.users", "system.roles", "system.menus"} <= system_child_codes

        navigation_response = client.get("/api/auth/me/navigation")
        assert navigation_response.status_code == 200
        navigation = navigation_response.json()["data"]
        navigation_root_codes = {item["code"] for item in navigation}
        assert {"dashboard.root", "system.root", "creation.root", "space.root"} <= navigation_root_codes


def test_menu_crud_and_role_menu_assignment(tmp_path) -> None:
    removed_menu_field = "_".join(("per", "mission_code"))
    with _build_test_client(tmp_path) as client:
        login_response = _login(
            client,
            login="admin",
            password="Admin12345!",
        )
        assert login_response.status_code == 200
        headers = _csrf_headers(client)

        menu_tree_response = client.get("/api/menus/tree")
        assert menu_tree_response.status_code == 200
        system_root = next(
            item
            for item in menu_tree_response.json()["data"]
            if item["code"] == "system.root"
        )

        create_menu_response = client.post(
            "/api/menus",
            json={
                "code": "system.audit_logs",
                "title": "审计日志",
                "menu_type": "menu",
                "route_path": "/audit-logs",
                "icon": "FolderTree",
                "parent_id": system_root["id"],
                "sort_order": 60,
                "remark": "审计日志入口",
                "meta_json": {"section": "system"},
            },
            headers=headers,
        )
        assert create_menu_response.status_code == 200
        created_menu = create_menu_response.json()["data"]
        assert created_menu["code"] == "system.audit_logs"
        assert created_menu["parent_id"] == system_root["id"]
        assert removed_menu_field not in created_menu

        update_menu_response = client.patch(
            f"/api/menus/{created_menu['id']}",
            json={
                "title": "审计日志中心",
                "parent_id": None,
                "icon": None,
            },
            headers=headers,
        )
        assert update_menu_response.status_code == 200
        updated_menu = update_menu_response.json()["data"]
        assert updated_menu["title"] == "审计日志中心"
        assert updated_menu["parent_id"] is None
        assert updated_menu["icon"] is None
        assert removed_menu_field not in updated_menu

        roles_response = client.get("/api/auth/roles")
        assert roles_response.status_code == 200
        user_role = next(
            item
            for item in roles_response.json()["data"]
            if item["code"] == "user"
        )

        assign_response = client.put(
            f"/api/auth/roles/{user_role['id']}/menus",
            json={"menu_ids": [created_menu["id"]]},
            headers=headers,
        )
        assert assign_response.status_code == 200
        assigned_menu_codes = {
            item["code"]
            for item in assign_response.json()["data"]["menus"]
        }
        assert "system.audit_logs" in assigned_menu_codes

        role_menus_response = client.get(f"/api/auth/roles/{user_role['id']}/menus")
        assert role_menus_response.status_code == 200
        role_menu_codes = {item["code"] for item in role_menus_response.json()["data"]}
        assert "system.audit_logs" in role_menu_codes

        delete_response = client.delete(
            f"/api/menus/{created_menu['id']}",
            headers=headers,
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["data"]["deleted"] is True


def test_regular_user_cannot_access_management_routes(tmp_path) -> None:
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
                "username": "member04",
                "email": "member04@example.com",
                "password": "Member12345!",
                "display_name": "Member 04",
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
            login="member04",
            password="Member12345!",
        )
        assert member_login.status_code == 200

        assert member_client.get("/api/auth/users").status_code == 403
        assert member_client.get("/api/auth/roles").status_code == 403
        assert member_client.get("/api/menus/tree").status_code == 403
