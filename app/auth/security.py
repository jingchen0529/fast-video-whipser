import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Dict


def utcnow() -> datetime:
    return datetime.now(UTC)


def utcnow_iso() -> str:
    return utcnow().replace(microsecond=0).isoformat()


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


def _b64url_encode(raw_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


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

    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = hmac.new(
        secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()

    return {
        "token": f"{signing_input}.{_b64url_encode(signature)}",
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
        encoded_header, encoded_payload, encoded_signature = token.split(".", 2)
    except ValueError as exc:
        raise ValueError("JWT 格式不正确。") from exc

    signing_input = f"{encoded_header}.{encoded_payload}"
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        actual_signature = _b64url_decode(encoded_signature)
    except (TypeError, ValueError) as exc:
        raise ValueError("JWT 签名解析失败。") from exc

    if not hmac.compare_digest(expected_signature, actual_signature):
        raise ValueError("JWT 签名校验失败。")

    try:
        payload = json.loads(_b64url_decode(encoded_payload))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("JWT 载荷解析失败。") from exc

    if payload.get("iss") != issuer:
        raise ValueError("JWT 签发方不匹配。")

    if expected_type and payload.get("typ") != expected_type:
        raise ValueError("JWT 类型不匹配。")

    try:
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("JWT 缺少有效过期时间。") from exc

    if expires_at <= int(utcnow().timestamp()):
        raise ValueError("JWT 已过期。")

    return payload
