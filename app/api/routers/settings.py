from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import get_current_user, require_csrf_protection, require_permissions
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

    model_config = ConfigDict(extra="ignore")


class ProviderGroupSettingsPayload(BaseModel):
    default_provider: str = ""
    providers: list[ProviderSettingsPayload] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class SystemSettingsPayload(BaseModel):
    system: SystemSettingsInfoPayload = Field(default_factory=SystemSettingsInfoPayload)
    proxy: ProxySettingsPayload = Field(default_factory=ProxySettingsPayload)
    analysis: ProviderGroupSettingsPayload = Field(default_factory=ProviderGroupSettingsPayload)
    remake: ProviderGroupSettingsPayload = Field(default_factory=ProviderGroupSettingsPayload)

    model_config = ConfigDict(extra="ignore")


@router.get("", response_model=ResponseModel, summary="获取系统设置")
async def get_system_settings(
    request: Request,
    _: dict = Depends(get_current_user),
    __: dict = Depends(require_permissions("settings.view")),
) -> ResponseModel:
    data = SystemSettingsService().get_settings()
    return build_response(request, data=data)


@router.head("", include_in_schema=False, summary="检查系统设置接口")
async def head_system_settings(
    _: dict = Depends(get_current_user),
    __: dict = Depends(require_permissions("settings.view")),
) -> Response:
    SystemSettingsService().get_settings()
    return Response(status_code=status.HTTP_200_OK)


@router.patch("", response_model=ResponseModel, summary="更新系统设置")
async def update_system_settings(
    request: Request,
    payload: SystemSettingsPayload,
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(require_permissions("settings.update")),
    __: None = Depends(require_csrf_protection),
) -> ResponseModel:
    data = SystemSettingsService().update_settings(
        payload=payload.model_dump(),
        updated_by_user_id=current_user["id"],
    )
    return build_response(request, data=data)
