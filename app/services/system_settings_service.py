import json
from copy import deepcopy
from typing import Any

from app.auth.security import utcnow_iso
from app.db.sqlite import create_connection


DEFAULT_SYSTEM_SETTINGS: dict[str, Any] = {
    "system": {
        "name": "爆款杀手",
        "description": "您的专属 AI 工作平台",
        "logo_url": "/logo.png",
    },
    "proxy": {
        "enabled": False,
        "http_url": "",
        "https_url": "",
        "all_url": "",
        "no_proxy": "",
    },
    "analysis": {
        "default_provider": "openai",
        "providers": [
            {
                "provider": "openai",
                "label": "OpenAI",
                "enabled": True,
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "default_model": "gpt-4.1",
                "model_options": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
            },
            {
                "provider": "gemini",
                "label": "Gemini",
                "enabled": False,
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "api_key": "",
                "default_model": "gemini-2.5-flash",
                "model_options": [
                    "gemini-2.5-pro",
                    "gemini-2.5-flash",
                    "gemini-2.5-flash-lite",
                ],
            },
            {
                "provider": "doubao",
                "label": "豆包",
                "enabled": True,
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "api_key": "",
                "default_model": "doubao-seed-1-6-250615",
                "model_options": [
                    "doubao-seed-1-6-250615",
                    "doubao-pro",
                    "doubao-lite",
                    "doubao-thinking",
                ],
            },
            {
                "provider": "kimi",
                "label": "Kimi",
                "enabled": False,
                "base_url": "https://api.moonshot.cn/v1",
                "api_key": "",
                "default_model": "kimi-k2",
                "model_options": ["kimi-k2", "kimi-thinking", "moonshot-v1-128k"],
            },
            {
                "provider": "qwen",
                "label": "千问",
                "enabled": False,
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "",
                "default_model": "qwen-plus",
                "model_options": ["qwen-max", "qwen-plus", "qwen-turbo"],
            },
            {
                "provider": "deepseek",
                "label": "DeepSeek",
                "enabled": False,
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "",
                "default_model": "deepseek-chat",
                "model_options": ["deepseek-chat", "deepseek-reasoner"],
            },
            {
                "provider": "custom",
                "label": "自定义兼容服务",
                "enabled": False,
                "base_url": "",
                "api_key": "",
                "default_model": "custom-model",
                "model_options": ["custom-model"],
            },
        ],
    },
    "remake": {
        "default_provider": "doubao",
        "providers": [
            {
                "provider": "doubao",
                "label": "豆包",
                "enabled": True,
                "base_url": "",
                "api_key": "",
                "default_model": "seedance-pro",
                "model_options": ["seedance-pro", "seedance-lite"],
            },
            {
                "provider": "kling",
                "label": "可灵",
                "enabled": False,
                "base_url": "",
                "api_key": "",
                "default_model": "kling-v1",
                "model_options": ["kling-v1", "kling-master"],
            },
            {
                "provider": "veo",
                "label": "Veo",
                "enabled": False,
                "base_url": "",
                "api_key": "",
                "default_model": "veo-3",
                "model_options": ["veo-3", "veo-2"],
            },
            {
                "provider": "wanxiang",
                "label": "万相",
                "enabled": False,
                "base_url": "",
                "api_key": "",
                "default_model": "wanx-video",
                "model_options": ["wanx-video", "wanx-image-to-video"],
            },
            {
                "provider": "custom",
                "label": "自定义视频模型",
                "enabled": False,
                "base_url": "",
                "api_key": "",
                "default_model": "custom-video-model",
                "model_options": ["custom-video-model"],
            },
        ],
    },
}


class SystemSettingsService:
    SETTINGS_KEY = "runtime_ai_settings"

    def get_settings(self) -> dict[str, Any]:
        connection = create_connection()
        try:
            return self._read_settings(connection)
        finally:
            connection.close()

    def update_settings(
        self,
        *,
        payload: dict[str, Any],
        updated_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_settings_payload(payload)

        connection = create_connection()
        try:
            self._persist_settings(
                connection,
                payload=normalized,
                updated_by_user_id=updated_by_user_id,
            )
            return normalized
        finally:
            connection.close()

    def get_proxy_mounts(self) -> dict[str, str] | None:
        proxy_settings = self.get_settings()["proxy"]
        if not proxy_settings["enabled"]:
            return None

        mounts: dict[str, str] = {}
        http_url = proxy_settings["http_url"]
        https_url = proxy_settings["https_url"]
        all_url = proxy_settings["all_url"]

        if http_url:
            mounts["http://"] = http_url
        if https_url:
            mounts["https://"] = https_url
        if all_url:
            mounts.setdefault("http://", all_url)
            mounts.setdefault("https://", all_url)

        return mounts or None

    def _read_settings(self, connection) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT value_json
            FROM system_settings
            WHERE key = ?
            LIMIT 1
            """,
            (self.SETTINGS_KEY,),
        ).fetchone()

        if row is None:
            normalized = deepcopy(DEFAULT_SYSTEM_SETTINGS)
            self._persist_settings(connection, payload=normalized)
            return normalized

        try:
            payload = json.loads(row["value_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}

        normalized = self._normalize_settings_payload(payload)
        if normalized != payload:
            self._persist_settings(connection, payload=normalized)
        return normalized

    def _persist_settings(
        self,
        connection,
        *,
        payload: dict[str, Any],
        updated_by_user_id: str | None = None,
    ) -> None:
        now = utcnow_iso()
        connection.execute(
            """
            INSERT INTO system_settings (
                key, value_json, updated_at, updated_by_user_id
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at,
                updated_by_user_id = excluded.updated_by_user_id
            """,
            (
                self.SETTINGS_KEY,
                json.dumps(payload, ensure_ascii=False),
                now,
                updated_by_user_id,
            ),
        )
        connection.commit()

    def _normalize_settings_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        normalized_payload = payload if isinstance(payload, dict) else {}
        return {
            "system": self._normalize_system_settings(normalized_payload.get("system")),
            "proxy": self._normalize_proxy_settings(normalized_payload.get("proxy")),
            "analysis": self._normalize_provider_group(
                normalized_payload.get("analysis"),
                DEFAULT_SYSTEM_SETTINGS["analysis"],
            ),
            "remake": self._normalize_provider_group(
                normalized_payload.get("remake"),
                DEFAULT_SYSTEM_SETTINGS["remake"],
            ),
        }

    def _normalize_system_settings(self, payload: Any) -> dict[str, Any]:
        raw = payload if isinstance(payload, dict) else {}
        default = DEFAULT_SYSTEM_SETTINGS["system"]
        return {
            "name": self._normalize_string(raw.get("name")) or default["name"],
            "description": self._normalize_string(raw.get("description")) or default["description"],
            "logo_url": self._normalize_string(raw.get("logo_url")) or default["logo_url"],
        }

    def _normalize_proxy_settings(self, payload: Any) -> dict[str, Any]:
        raw = payload if isinstance(payload, dict) else {}
        return {
            "enabled": bool(raw.get("enabled", False)),
            "http_url": self._normalize_string(raw.get("http_url")),
            "https_url": self._normalize_string(raw.get("https_url")),
            "all_url": self._normalize_string(raw.get("all_url")),
            "no_proxy": self._normalize_string(raw.get("no_proxy")),
        }

    def _normalize_provider_group(
        self,
        payload: Any,
        default_group: dict[str, Any],
    ) -> dict[str, Any]:
        raw_group = payload if isinstance(payload, dict) else {}
        raw_providers = raw_group.get("providers")
        provider_overrides: dict[str, dict[str, Any]] = {}

        if isinstance(raw_providers, list):
            for item in raw_providers:
                if not isinstance(item, dict):
                    continue
                provider_key = self._normalize_string(item.get("provider")).lower()
                if not provider_key:
                    continue
                provider_overrides[provider_key] = {
                    **item,
                    "provider": provider_key,
                }

        providers: list[dict[str, Any]] = []
        seen_keys: set[str] = set()

        for default_provider in default_group["providers"]:
            provider_key = default_provider["provider"]
            merged_payload = deepcopy(default_provider)
            if provider_key in provider_overrides:
                merged_payload.update(provider_overrides[provider_key])
            providers.append(self._normalize_provider(merged_payload))
            seen_keys.add(provider_key)

        for provider_key, override_payload in provider_overrides.items():
            if provider_key in seen_keys:
                continue
            providers.append(self._normalize_provider(override_payload))

        provider_keys = [item["provider"] for item in providers]
        default_provider = self._normalize_string(raw_group.get("default_provider")).lower()
        if default_provider not in provider_keys:
            default_provider = next(
                (item["provider"] for item in providers if item["enabled"]),
                provider_keys[0] if provider_keys else "",
            )

        return {
            "default_provider": default_provider,
            "providers": providers,
        }

    def _normalize_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider_key = self._normalize_string(payload.get("provider")).lower()
        label = self._normalize_string(payload.get("label")) or provider_key.replace("_", " ").title()
        default_model = self._normalize_string(payload.get("default_model"))
        model_options = self._normalize_string_list(payload.get("model_options"))

        if default_model and default_model not in model_options:
            model_options.insert(0, default_model)
        if not default_model and model_options:
            default_model = model_options[0]

        return {
            "provider": provider_key,
            "label": label,
            "enabled": bool(payload.get("enabled", False)),
            "base_url": self._normalize_string(payload.get("base_url")),
            "api_key": self._normalize_string(payload.get("api_key")),
            "default_model": default_model,
            "model_options": model_options,
        }

    @staticmethod
    def _normalize_string(value: Any) -> str:
        return str(value or "").strip()

    def _normalize_string_list(self, value: Any) -> list[str]:
        if isinstance(value, str):
            items = value.replace(",", "\n").splitlines()
        elif isinstance(value, list):
            items = value
        else:
            items = []

        normalized: list[str] = []
        seen: set[str] = set()
        for item in items:
            candidate = self._normalize_string(item)
            if not candidate or candidate in seen:
                continue
            normalized.append(candidate)
            seen.add(candidate)
        return normalized


__all__ = ["DEFAULT_SYSTEM_SETTINGS", "SystemSettingsService"]
