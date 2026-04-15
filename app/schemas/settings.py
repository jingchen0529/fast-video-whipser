"""Pydantic request/response schemas for system settings endpoints."""
from pydantic import BaseModel, ConfigDict, Field


class SystemSettingsInfoPayload(BaseModel):
    name: str = "爆款杀手"
    description: str = "您的专属 AI 工作平台"
    logo_url: str = "/logo.png"

    model_config = ConfigDict(extra="ignore")


class ProxySettingsPayload(BaseModel):
    enabled: bool = False
    http_url: str = ""
    https_url: str = ""
    all_url: str = ""
    no_proxy: str = ""

    model_config = ConfigDict(extra="ignore")


class ProviderSettingsPayload(BaseModel):
    provider: str = ""
    label: str = ""
    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    default_model: str = ""
    model_options: list[str] = Field(default_factory=list)
    model_dir: str = ""
    device: str = "auto"
    compute_type: str = "auto"
    language: str = ""
    prompt: str = ""
    beam_size: int = 5
    vad_filter: bool = True

    model_config = ConfigDict(extra="ignore")


class ProviderGroupSettingsPayload(BaseModel):
    default_provider: str = ""
    providers: list[ProviderSettingsPayload] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class MotionExtractionSettingsPayload(BaseModel):
    coarse_filter_mode: str = "keyword"
    min_duration_ms: int = 800
    max_duration_ms: int = 15000
    signal_score_threshold: int = 3
    confidence_threshold: float = 0.6
    default_provider: str = ""
    providers: list[ProviderSettingsPayload] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class SystemSettingsPayload(BaseModel):
    system: SystemSettingsInfoPayload = Field(default_factory=SystemSettingsInfoPayload)
    proxy: ProxySettingsPayload = Field(default_factory=ProxySettingsPayload)
    analysis: ProviderGroupSettingsPayload = Field(default_factory=ProviderGroupSettingsPayload)
    transcription: ProviderGroupSettingsPayload = Field(default_factory=ProviderGroupSettingsPayload)
    remake: ProviderGroupSettingsPayload = Field(default_factory=ProviderGroupSettingsPayload)
    motion_extraction: MotionExtractionSettingsPayload = Field(default_factory=MotionExtractionSettingsPayload)

    model_config = ConfigDict(extra="ignore")


class DependencyStatusPayload(BaseModel):
    installed: bool = False
    version: str = ""

    model_config = ConfigDict(extra="ignore")


class FasterWhisperModelPayload(BaseModel):
    name: str = ""
    path: str = ""

    model_config = ConfigDict(extra="ignore")


class FasterWhisperCapabilitiesPayload(BaseModel):
    provider: str = "faster_whisper"
    available: bool = False
    issues: list[str] = Field(default_factory=list)
    dependency_status: dict[str, DependencyStatusPayload] = Field(default_factory=dict)
    binary_status: dict[str, bool] = Field(default_factory=dict)
    model_dir: str = ""
    local_models: list[FasterWhisperModelPayload] = Field(default_factory=list)
    available_devices: list[str] = Field(default_factory=list)
    available_compute_types: list[str] = Field(default_factory=list)
    recommended_device: str = "cpu"
    recommended_compute_type: str = "int8"
    cuda_device_count: int = 0

    model_config = ConfigDict(extra="ignore")


class OpenAIWhisperCapabilitiesPayload(BaseModel):
    provider: str = "openai_whisper_api"
    available: bool = True
    issues: list[str] = Field(default_factory=list)
    supported_models: list[str] = Field(default_factory=list)
    base_url: str = ""
    file_size_limit_mb: int = 25
    supported_formats: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class TranscriptionCapabilitiesPayload(BaseModel):
    default_provider: str = ""
    providers: dict[str, dict] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class CaptchaVerifyRequest(BaseModel):
    captcha_id: str = Field(..., description="Captcha ID returned by the captcha endpoint.")
    captcha_code: str = Field(..., description="Captcha code entered by the user.")
