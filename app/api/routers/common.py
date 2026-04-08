import os
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field, StringConstraints

from app.auth.dependencies import require_csrf_protection, require_permissions
from app.core.config import settings
from app.core.http import ResponseModel, build_response
from app.services import captcha_service
from app.utils.file_utils import FileUtils

router = APIRouter()


class CaptchaVerifyRequest(BaseModel):
    # 验证码唯一 ID，由获取验证码接口返回。
    captcha_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
    ] = Field(..., description="Captcha ID returned by the captcha endpoint.")

    # 用户输入的验证码内容。
    captcha_code: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=16),
    ] = Field(..., description="Captcha code entered by the user.")


@router.get(
    "/captcha",
    response_model=ResponseModel,
    summary="获取人机验证码 / Get captcha challenge",
)
async def get_captcha(request: Request) -> ResponseModel:
    # 返回验证码图片和对应的 captcha_id，前端后续用 captcha_id 发起校验。
    return build_response(request, data=captcha_service.create_captcha())


@router.post(
    "/captcha/verify",
    response_model=ResponseModel,
    summary="校验人机验证码 / Verify captcha challenge",
)
async def verify_captcha(
    request: Request,
    payload: CaptchaVerifyRequest,
) -> ResponseModel:
    # 仅返回校验结果，不在这里耦合具体业务。
    verified = captcha_service.verify_captcha(
        payload.captcha_id,
        payload.captcha_code,
    )
    return build_response(
        request,
        data={
            "captcha_id": payload.captcha_id,
            "verified": verified,
        },
    )


@router.post(
    "/upload",
    response_model=ResponseModel,
    summary="上传文件 / Upload file",
)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    _: dict = Depends(require_permissions("files.upload")),
    __: None = Depends(require_csrf_protection),
) -> ResponseModel:
    # 公共上传接口，后续其他业务可以直接复用这个入口。
    file_name = file.filename or "upload.bin"

    try:
        async with FileUtils(
            temp_dir=settings.temp_dir,
            auto_delete=True,
            max_file_size=settings.max_file_size,
        ) as file_utils:
            saved_path = await file_utils.save_uploaded_file(file, file_name)
            size_bytes = os.path.getsize(saved_path)
            stored_name = os.path.basename(saved_path)
    finally:
        await file.close()

    return build_response(
        request,
        data={
            "original_name": file_name,
            "stored_name": stored_name,
            "content_type": file.content_type or "application/octet-stream",
            "size_bytes": size_bytes,
        },
    )
