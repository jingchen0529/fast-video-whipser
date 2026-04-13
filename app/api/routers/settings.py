from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import require_admin_access, require_csrf_protection
from app.core.http import ResponseModel, build_response
from app.services.system_settings_service import SystemSettingsService

router = APIRouter()


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


class SystemSettingsPayload(BaseModel):
    system: SystemSettingsInfoPayload = Field(default_factory=SystemSettingsInfoPayload)
    proxy: ProxySettingsPayload = Field(default_factory=ProxySettingsPayload)
    analysis: ProviderGroupSettingsPayload = Field(default_factory=ProviderGroupSettingsPayload)
    transcription: ProviderGroupSettingsPayload = Field(default_factory=ProviderGroupSettingsPayload)
    remake: ProviderGroupSettingsPayload = Field(default_factory=ProviderGroupSettingsPayload)

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


@router.get("", response_model=ResponseModel, summary="获取系统设置")
async def get_system_settings(
    request: Request,
    _: dict = Depends(require_admin_access),

) -> ResponseModel:
    data = SystemSettingsService().get_settings()
    return build_response(request, data=data)


@router.head("", include_in_schema=False, summary="检查系统设置接口")
async def head_system_settings(
    _: dict = Depends(require_admin_access),

) -> Response:
    SystemSettingsService().get_settings()
    return Response(status_code=status.HTTP_200_OK)


@router.patch("", response_model=ResponseModel, summary="更新系统设置")
async def update_system_settings(
    request: Request,
    payload: SystemSettingsPayload,
    current_user: dict = Depends(require_admin_access),

    __: None = Depends(require_csrf_protection),
) -> ResponseModel:
    data = SystemSettingsService().update_settings(
        payload=payload.model_dump(),
        updated_by_user_id=current_user["id"],
    )
    return build_response(request, data=data)


@router.get(
    "/transcription/capabilities",
    response_model=ResponseModel,
    summary="获取转写引擎能力检测结果",
)
async def get_transcription_capabilities(
    request: Request,
    _: dict = Depends(require_admin_access),

) -> ResponseModel:
    data = SystemSettingsService().get_transcription_capabilities()
    return build_response(request, data=data)


@router.post(
    "/transcription/capabilities",
    response_model=ResponseModel,
    summary="基于当前配置预览转写引擎能力检测结果",
)
async def preview_transcription_capabilities(
    request: Request,
    payload: SystemSettingsPayload,
    _: dict = Depends(require_admin_access),

    ___: None = Depends(require_csrf_protection),
) -> ResponseModel:
    data = SystemSettingsService().get_transcription_capabilities(
        payload=payload.model_dump(),
    )
    return build_response(request, data=data)
