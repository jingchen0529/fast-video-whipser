from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Fast Video Whisper"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False

    log_level: str = "INFO"
    log_dir: str = "./log_files"
    log_file_prefix: str = "app"
    log_backup_count: int = 7
    log_encoding: str = "utf-8"

    database_url: str = "mysql+pymysql://root@127.0.0.1/fast-video-whipser"
    temp_dir: str = "./temp_files"
    max_file_size: int = 2 * 1024 * 1024 * 1024
    frontend_static_dir: str = "./static"
    serve_frontend_static: bool = False
    frontend_dev_port: int = 3000
    auth_jwt_secret: str = "change-me-to-a-random-32-plus-char-secret"
    auth_jwt_issuer: str = "fast-video-whisper"
    auth_access_token_expire_minutes: int = 1440
    auth_refresh_token_expire_days: int = 30
    auth_allow_public_register: bool = False
    auth_require_captcha_for_login: bool = True
    auth_rate_limit_max_attempts: int = 5
    auth_rate_limit_block_seconds: int = 900
    auth_cookie_access_name: str = "auth_access_token"
    auth_cookie_refresh_name: str = "auth_refresh_token"
    auth_cookie_csrf_name: str = "auth_csrf_token"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    auth_cookie_domain: str | None = None
    auth_cookie_path: str = "/"
    auth_initial_admin_username: str = "admin"
    auth_initial_admin_email: str = "admin@example.com"
    auth_initial_admin_password: str = "ChangeMe123!"
    auth_initial_admin_display_name: str = "Super Admin"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("auth_cookie_samesite")
    @classmethod
    def validate_cookie_samesite(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("AUTH_COOKIE_SAMESITE 仅支持 lax、strict、none。")
        return normalized

    @field_validator("auth_jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("AUTH_JWT_SECRET 不能为空。")
        return normalized

    @field_validator("auth_cookie_domain")
    @classmethod
    def normalize_cookie_domain(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


def validate_runtime_settings() -> None:
    environment = settings.environment.strip().lower()
    failures: list[str] = []

    if settings.auth_cookie_samesite == "none" and not settings.auth_cookie_secure:
        failures.append("AUTH_COOKIE_SAMESITE=none 时必须同时开启 AUTH_COOKIE_SECURE=true。")

    if environment == "production":
        if settings.auth_jwt_secret == "change-me-to-a-random-32-plus-char-secret":
            failures.append("生产环境禁止使用默认 AUTH_JWT_SECRET。")
        if len(settings.auth_jwt_secret) < 32:
            failures.append("生产环境 AUTH_JWT_SECRET 长度至少需要 32 位。")
        if settings.auth_initial_admin_password == "ChangeMe123!":
            failures.append("生产环境禁止使用默认 AUTH_INITIAL_ADMIN_PASSWORD。")
        if not settings.auth_cookie_secure:
            failures.append("生产环境必须开启 AUTH_COOKIE_SECURE=true。")

    if failures:
        raise RuntimeError("认证配置校验失败: " + " ".join(failures))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


__all__ = ["Settings", "get_settings", "settings", "validate_runtime_settings"]
