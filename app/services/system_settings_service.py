import importlib.metadata
import importlib.util
import json
import shutil
from copy import deepcopy
from pathlib import Path
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
    "transcription": {
        "default_provider": "faster_whisper",
        "providers": [
            {
                "provider": "faster_whisper",
                "label": "本地 faster-whisper",
                "enabled": True,
                "base_url": "",
                "api_key": "",
                "default_model": "small",
                "model_options": [
                    "tiny",
                    "base",
                    "small",
                    "medium",
                    "large-v3",
                    "large-v3-turbo",
                ],
                "model_dir": "./models/faster-whisper",
                "device": "auto",
                "compute_type": "auto",
                "language": "",
                "prompt": "",
                "beam_size": 5,
                "vad_filter": True,
            },
            {
                "provider": "openai_whisper_api",
                "label": "OpenAI Whisper API",
                "enabled": False,
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "default_model": "whisper-1",
                "model_options": [
                    "whisper-1",
                    "gpt-4o-mini-transcribe",
                    "gpt-4o-transcribe",
                ],
                "model_dir": "",
                "device": "server",
                "compute_type": "server",
                "language": "",
                "prompt": "",
                "beam_size": 5,
                "vad_filter": True,
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
                "base_url": "https://api-beijing.klingai.com",
                "api_key": "",
                "default_model": "kling-v3",
                "model_options": ["kling-v3", "kling-v3-omni", "kling-video-o1", "kling-v2-6"],
            },
            {
                "provider": "veo",
                "label": "Veo",
                "enabled": False,
                "base_url": "",
                "api_key": "",
                "default_model": "veo-3.0-generate-001",
                "model_options": [
                    "veo-3.0-generate-001",
                    "veo-3.0-fast-generate-001",
                    "veo-3.1-generate-001",
                    "veo-3.1-fast-generate-001",
                    "veo-2.0-generate-001",
                ],
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
        normalized = self._normalize_settings_payload(payload, validate_base_urls=True)

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

    def get_transcription_capabilities(
        self,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_settings_payload(payload or self.get_settings())
        transcription_group = normalized["transcription"]
        faster_provider = next(
            (
                item
                for item in transcription_group["providers"]
                if item["provider"] == "faster_whisper"
            ),
            None,
        )
        openai_provider = next(
            (
                item
                for item in transcription_group["providers"]
                if item["provider"] == "openai_whisper_api"
            ),
            None,
        )

        return {
            "default_provider": transcription_group["default_provider"],
            "providers": {
                "faster_whisper": self._collect_faster_whisper_capabilities(
                    faster_provider or {},
                ),
                "openai_whisper_api": self._collect_openai_whisper_capabilities(
                    openai_provider or {},
                ),
            },
        }

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

    def _normalize_settings_payload(
        self,
        payload: dict[str, Any] | None,
        *,
        validate_base_urls: bool = False,
    ) -> dict[str, Any]:
        normalized_payload = payload if isinstance(payload, dict) else {}
        return {
            "system": self._normalize_system_settings(normalized_payload.get("system")),
            "proxy": self._normalize_proxy_settings(normalized_payload.get("proxy")),
            "analysis": self._normalize_provider_group(
                "analysis",
                normalized_payload.get("analysis"),
                DEFAULT_SYSTEM_SETTINGS["analysis"],
                validate_base_urls=validate_base_urls,
            ),
            "transcription": self._normalize_provider_group(
                "transcription",
                normalized_payload.get("transcription"),
                DEFAULT_SYSTEM_SETTINGS["transcription"],
                validate_base_urls=validate_base_urls,
            ),
            "remake": self._normalize_provider_group(
                "remake",
                normalized_payload.get("remake"),
                DEFAULT_SYSTEM_SETTINGS["remake"],
                validate_base_urls=validate_base_urls,
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
        group_key: str,
        payload: Any,
        default_group: dict[str, Any],
        *,
        validate_base_urls: bool = False,
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
            providers.append(
                self._normalize_provider(
                    merged_payload,
                    group_key=group_key,
                    validate_base_urls=validate_base_urls,
                )
            )
            seen_keys.add(provider_key)

        for provider_key, override_payload in provider_overrides.items():
            if provider_key in seen_keys:
                continue
            providers.append(
                self._normalize_provider(
                    override_payload,
                    group_key=group_key,
                    validate_base_urls=validate_base_urls,
                )
            )

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

    def _normalize_provider(
        self,
        payload: dict[str, Any],
        *,
        group_key: str,
        validate_base_urls: bool = False,
    ) -> dict[str, Any]:
        provider_key = self._normalize_string(payload.get("provider")).lower()
        label = self._normalize_string(payload.get("label")) or provider_key.replace("_", " ").title()
        default_model = self._normalize_string(payload.get("default_model"))
        model_options = self._normalize_string_list(payload.get("model_options"))
        base_url = self._normalize_provider_base_url(
            group_key=group_key,
            provider_key=provider_key,
            raw_value=payload.get("base_url"),
        )

        if default_model and default_model not in model_options:
            model_options.insert(0, default_model)
        if not default_model and model_options:
            default_model = model_options[0]
        if validate_base_urls and base_url and not self._is_http_base_url(base_url):
            raise ValueError(
                f"{label} 的 API Base Endpoint 必须以 http:// 或 https:// 开头。"
            )

        return {
            "provider": provider_key,
            "label": label,
            "enabled": bool(payload.get("enabled", False)),
            "base_url": base_url,
            "api_key": self._normalize_string(payload.get("api_key")),
            "default_model": default_model,
            "model_options": model_options,
            "model_dir": self._normalize_string(payload.get("model_dir")),
            "device": self._normalize_string(payload.get("device")) or "auto",
            "compute_type": self._normalize_string(payload.get("compute_type")) or "auto",
            "language": self._normalize_string(payload.get("language")),
            "prompt": self._normalize_string(payload.get("prompt")),
            "beam_size": self._normalize_int(payload.get("beam_size"), default=5, minimum=1),
            "vad_filter": self._normalize_bool(payload.get("vad_filter"), default=True),
        }

    def _normalize_provider_base_url(
        self,
        *,
        group_key: str,
        provider_key: str,
        raw_value: Any,
    ) -> str:
        normalized = self._normalize_string(raw_value)
        if not normalized:
            return ""

        lowered = normalized.lower().rstrip("/")
        suffixes: list[str] = []

        if group_key == "analysis":
            suffixes.append("/chat/completions")
        if group_key == "remake" and provider_key == "doubao":
            suffixes.extend(
                [
                    "/api/v1/contents/generations/tasks",
                    "/contents/generations/tasks",
                ]
            )
        if group_key == "transcription" and provider_key == "openai_whisper_api":
            suffixes.append("/audio/transcriptions")

        for suffix in suffixes:
            if lowered.endswith(suffix):
                return normalized[: -len(suffix)]

        return normalized

    @staticmethod
    def _is_http_base_url(value: str) -> bool:
        normalized = SystemSettingsService._normalize_string(value)
        return normalized.lower().startswith(("http://", "https://"))

    def _collect_faster_whisper_capabilities(self, provider: dict[str, Any]) -> dict[str, Any]:
        dependency_names = ("faster_whisper", "ctranslate2", "av")
        dependencies = {
            name: self._inspect_python_dependency(name)
            for name in dependency_names
        }
        ffmpeg_available = bool(shutil.which("ffmpeg"))
        ffprobe_available = bool(shutil.which("ffprobe"))
        cuda_info = self._inspect_ctranslate2_cuda()
        recommended_runtime = self._recommend_faster_whisper_runtime(cuda_info)
        model_dir = self._resolve_directory(provider.get("model_dir"))
        local_models = self._scan_faster_whisper_models(model_dir)
        issues: list[str] = []

        if not dependencies["faster_whisper"]["installed"]:
            issues.append("未检测到 faster-whisper Python 依赖。")
        if not dependencies["ctranslate2"]["installed"]:
            issues.append("未检测到 ctranslate2 依赖，本地推理不可用。")
        if not dependencies["av"]["installed"]:
            issues.append("未检测到 av 依赖，媒体解码可能失败。")
        if not local_models:
            issues.append("未在本地模型目录中检测到现成模型，首次运行时将尝试按模型名自动下载。")
        if not cuda_info["cuda_available"]:
            issues.append("当前环境未检测到 CUDA，推荐使用 cpu + int8 以获得更稳定的本地转写性能。")

        available_devices = ["auto", "cpu"]
        if cuda_info["cuda_available"]:
            available_devices.append("cuda")
        available_compute_types = ["auto", "default", "int8", "float32"]
        if cuda_info["cuda_available"]:
            available_compute_types.extend(["float16", "int8_float16"])

        return {
            "provider": "faster_whisper",
            "available": dependencies["faster_whisper"]["installed"]
            and dependencies["ctranslate2"]["installed"]
            and dependencies["av"]["installed"],
            "issues": issues,
            "dependency_status": dependencies,
            "binary_status": {
                "ffmpeg": ffmpeg_available,
                "ffprobe": ffprobe_available,
            },
            "model_dir": str(model_dir) if model_dir else "",
            "local_models": local_models,
            "available_devices": available_devices,
            "available_compute_types": available_compute_types,
            "recommended_device": recommended_runtime["device"],
            "recommended_compute_type": recommended_runtime["compute_type"],
            "cuda_device_count": cuda_info["cuda_device_count"],
        }

    def _collect_openai_whisper_capabilities(self, provider: dict[str, Any]) -> dict[str, Any]:
        model_options = self._normalize_string_list(provider.get("model_options"))
        default_model = self._normalize_string(provider.get("default_model"))
        if default_model and default_model not in model_options:
            model_options.insert(0, default_model)

        issues: list[str] = []
        if not self._normalize_string(provider.get("api_key")):
            issues.append("尚未配置 OpenAI API Key。")
        if not self._normalize_string(provider.get("base_url")):
            issues.append("尚未配置 OpenAI Base URL。")

        return {
            "provider": "openai_whisper_api",
            "available": True,
            "issues": issues,
            "supported_models": model_options,
            "base_url": self._normalize_string(provider.get("base_url")),
            "file_size_limit_mb": 25,
            "supported_formats": ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"],
        }

    @staticmethod
    def _inspect_python_dependency(module_name: str) -> dict[str, Any]:
        installed = False
        version = ""
        try:
            installed = importlib.util.find_spec(module_name) is not None
        except (ModuleNotFoundError, ValueError):
            installed = False

        if installed:
            try:
                version = importlib.metadata.version(module_name.replace("_", "-"))
            except importlib.metadata.PackageNotFoundError:
                version = ""

        return {
            "installed": installed,
            "version": version,
        }

    @staticmethod
    def _inspect_ctranslate2_cuda() -> dict[str, Any]:
        try:
            import ctranslate2  # type: ignore
        except Exception:
            return {
                "cuda_available": False,
                "cuda_device_count": 0,
            }

        get_count = getattr(ctranslate2, "get_cuda_device_count", None)
        if not callable(get_count):
            return {
                "cuda_available": False,
                "cuda_device_count": 0,
            }

        try:
            cuda_device_count = int(get_count())
        except Exception:
            cuda_device_count = 0

        return {
            "cuda_available": cuda_device_count > 0,
            "cuda_device_count": max(0, cuda_device_count),
        }

    @staticmethod
    def _recommend_faster_whisper_runtime(cuda_info: dict[str, Any]) -> dict[str, str]:
        cuda_available = bool(cuda_info.get("cuda_available"))
        if cuda_available:
            return {
                "device": "cuda",
                "compute_type": "float16",
            }

        return {
            "device": "cpu",
            "compute_type": "int8",
        }

    def _scan_faster_whisper_models(self, model_dir: Path | None) -> list[dict[str, str]]:
        if model_dir is None or not model_dir.exists() or not model_dir.is_dir():
            return []

        candidates: list[Path] = []
        if self._looks_like_faster_whisper_model_dir(model_dir):
            candidates.append(model_dir)

        for child in sorted(model_dir.iterdir(), key=lambda item: item.name.lower()):
            if child.is_dir() and self._looks_like_faster_whisper_model_dir(child):
                candidates.append(child)

        return [
            {
                "name": item.name,
                "path": str(item),
            }
            for item in candidates
        ]

    @staticmethod
    def _looks_like_faster_whisper_model_dir(directory: Path) -> bool:
        markers = (
            "model.bin",
            "model.safetensors",
            "config.json",
            "tokenizer.json",
            "vocabulary.json",
        )
        return any((directory / marker).exists() for marker in markers)

    def _resolve_directory(self, value: Any) -> Path | None:
        normalized = self._normalize_string(value)
        if not normalized:
            return None

        path = Path(normalized)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    @staticmethod
    def _normalize_string(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _normalize_bool(value: Any, *, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return bool(value)

    @staticmethod
    def _normalize_int(value: Any, *, default: int, minimum: int | None = None) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = default
        if minimum is not None:
            normalized = max(minimum, normalized)
        return normalized

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
