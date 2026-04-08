import os

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from app.auth.dependencies import (
    get_current_user,
    require_csrf_protection,
    require_permissions,
)
from app.core.config import settings
from app.core.http import ResponseModel, build_response
from app.services.asset_service import AssetService
from app.utils.file_utils import FileUtils

router = APIRouter()


def _guess_asset_type(content_type: str) -> str:
    if content_type.startswith("video/"):
        return "video"
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("audio/"):
        return "audio"
    return "video"


@router.post("/upload", response_model=ResponseModel, summary="上传媒体资产")
async def upload_asset(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(require_permissions("assets.upload")),
    __: None = Depends(require_csrf_protection),
) -> ResponseModel:
    file_name = file.filename or "upload.bin"
    content_type = file.content_type or "application/octet-stream"

    try:
        async with FileUtils(
            temp_dir=settings.temp_dir,
            auto_delete=False,
            max_file_size=settings.max_file_size,
        ) as file_utils:
            saved_path = await file_utils.save_uploaded_file(file, file_name)
            size_bytes = os.path.getsize(saved_path)
    finally:
        await file.close()

    asset = AssetService().create_asset(
        owner_user_id=current_user["id"],
        asset_type=_guess_asset_type(content_type),
        source_type="upload",
        file_name=file_name,
        file_path=saved_path,
        mime_type=content_type,
        size_bytes=size_bytes,
        metadata={},
    )

    return build_response(request, data=asset)


@router.get("/motions", response_model=ResponseModel, summary="查询动作资产候选")
async def list_motion_assets(
    request: Request,
    action_label: str | None = None,
    scene_label: str | None = None,
    review_status: str | None = None,
    source_video_asset_id: str | None = None,
    keyword: str | None = Query(None, alias="q"),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(require_permissions("motion_assets.read")),
) -> ResponseModel:
    _ = current_user
    items = AssetService().list_motion_assets(
        source_video_asset_id=source_video_asset_id,
        action_label=action_label,
        scene_label=scene_label,
        review_status=review_status,
        keyword=keyword,
        limit=limit,
    )
    return build_response(
        request,
        data={
            "items": items,
        },
    )


@router.get("/motions/{motion_asset_id}", response_model=ResponseModel, summary="获取动作资产详情")
async def get_motion_asset(
    motion_asset_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(require_permissions("motion_assets.read")),
) -> ResponseModel:
    _ = current_user
    item = AssetService().get_motion_asset(
        motion_asset_id=motion_asset_id,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="动作资产不存在。")

    return build_response(request, data=item)
