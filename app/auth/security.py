import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Dict

import jwt


def utcnow() -> datetime:
    return datetime.now(UTC)


def utcnow_iso() -> str:
    return utcnow().replace(microsecond=0).isoformat()


def datetime_to_timestamp_ms(value: datetime) -> int:
    normalized = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return int(normalized.timestamp() * 1000)


def utcnow_ms() -> int:
    return datetime_to_timestamp_ms(utcnow())


def parse_datetime_value(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)

    if isinstance(value, (int, float)):
        numeric_value = float(value)
        if abs(numeric_value) >= 10_000_000_000:
            numeric_value /= 1000
        return datetime.fromtimestamp(numeric_value, tz=UTC)

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.lstrip("-").isdigit():
            return parse_datetime_value(int(normalized))
        parsed = datetime.fromisoformat(normalized)
        return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    raise TypeError(f"不支持的时间值类型: {type(value)!r}")


def normalize_timestamp_ms(value: Any) -> int | None:
    parsed = parse_datetime_value(value)
    if parsed is None:
        return None
    return datetime_to_timestamp_ms(parsed)


def hash_password(password: str, *, iterations: int = 390_000) -> str:
    normalized_password = password.strip()
    if len(normalized_password) < 8:
        raise ValueError("密码长度至少需要 8 位。")

    salt = secrets.token_hex(16)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        normalized_password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return (
        f"pbkdf2_sha256${iterations}${salt}$"
        f"{base64.urlsafe_b64encode(derived_key).decode('ascii')}"
    )


def verify_password(password: str, encoded_password: str) -> bool:
    try:
        algorithm, iteration_text, salt, encoded_hash = encoded_password.split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    try:
        iterations = int(iteration_text)
    except ValueError:
        return False

    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.strip().encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    expected_hash = base64.urlsafe_b64encode(derived_key).decode("ascii")
    return hmac.compare_digest(expected_hash, encoded_hash)


def create_jwt_token(
    *,
    subject: str,
    secret: str,
    issuer: str,
    token_type: str,
    expires_delta: timedelta,
    additional_claims: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not secret:
        raise ValueError("JWT 密钥不能为空。")

    issued_at = utcnow()
    expires_at = issued_at + expires_delta
    payload: Dict[str, Any] = {
        "sub": subject,
        "iss": issuer,
        "typ": token_type,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if additional_claims:
        payload.update(additional_claims)

    token = jwt.encode(payload, secret, algorithm="HS256")

    return {
        "token": token,
        "claims": payload,
    }


def decode_jwt_token(
    token: str,
    *,
    secret: str,
    issuer: str,
    expected_type: str | None = None,
) -> Dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=issuer,
            options={"require": ["sub", "iss", "exp", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("JWT 已过期。") from exc
    except jwt.InvalidIssuerError as exc:
        raise ValueError("JWT 签发方不匹配。") from exc
    except jwt.InvalidSignatureError as exc:
        raise ValueError("JWT 签名校验失败。") from exc
    except jwt.DecodeError as exc:
        raise ValueError("JWT 格式不正确。") from exc
    except jwt.InvalidTokenError as exc:
        raise ValueError(f"JWT 校验失败: {exc}") from exc

    if expected_type and payload.get("typ") != expected_type:
        raise ValueError("JWT 类型不匹配。")

    return payload
