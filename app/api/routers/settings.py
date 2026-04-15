from fastapi import APIRouter, Depends, Request, Response, status

from app.auth.dependencies import require_admin_access, require_csrf_protection
from app.core.http import ResponseModel, build_response
from app.schemas.settings import (
    FasterWhisperCapabilitiesPayload,
    OpenAIWhisperCapabilitiesPayload,
    ProviderGroupSettingsPayload,
    SystemSettingsPayload,
    TranscriptionCapabilitiesPayload,
)
from app.services.system_settings_service import SystemSettingsService

router = APIRouter()


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
