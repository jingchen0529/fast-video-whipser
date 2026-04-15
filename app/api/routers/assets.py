import os

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app.auth.dependencies import (
    get_current_user,
    require_csrf_protection,

)
from app.core.config import settings
from app.core.http import ResponseModel, build_response
from app.schemas.assets import BatchDeleteBody, MotionBatchReviewRequest, MotionExtractRequest, MotionReviewRequest
from app.services.asset_service import AssetService, MAX_MOTION_ASSET_LIST_LIMIT
from app.services.job_service import JobService
from app.services.motion_service import MotionService
from app.utils.file_utils import FileUtils
from app.workflows.task_queue import TaskQueue

router = APIRouter()


def _guess_asset_type(content_type: str) -> str:
    if content_type.startswith("video/"):
        return "video"
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("audio/"):
        return "audio"
    return "video"


@router.get("", response_model=ResponseModel, summary="查询媒体资产列表")
async def list_assets(
    request: Request,
    asset_type: str | None = Query(None, description="资产类型: video/image/audio"),
    source_type: str | None = Query(None, description="来源类型: upload/generated/derived"),
    keyword: str | None = Query(None, alias="q"),
    sort: str = Query("newest", description="排序: newest/oldest"),
    page: int = Query(1, ge=1),
    page_size: int = Query(40, ge=1, le=100),
    current_user: dict = Depends(get_current_user),

) -> ResponseModel:
    result = AssetService().list_media_assets(
        asset_type=asset_type,
        source_type=source_type,
        owner_user_id=current_user["id"],
        keyword=keyword,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return build_response(request, data=result)


@router.get("/storage", response_model=ResponseModel, summary="查询存储用量")
async def get_storage(
    request: Request,
    current_user: dict = Depends(get_current_user),

) -> ResponseModel:
    usage = AssetService().get_storage_usage(owner_user_id=current_user["id"])
    return build_response(request, data=usage)


@router.delete("/{asset_id}", response_model=ResponseModel, summary="删除媒体资产")
async def delete_asset(
    asset_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),

    __: None = Depends(require_csrf_protection),
) -> ResponseModel:
    deleted = AssetService().delete_asset(
        asset_id=asset_id,
        owner_user_id=current_user["id"],
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="资产不存在。")
    return build_response(request, data={"deleted": True})


@router.post("/batch-delete", response_model=ResponseModel, summary="批量删除媒体资产")
async def batch_delete_assets(
    body: BatchDeleteBody,
    request: Request,
    current_user: dict = Depends(get_current_user),

    __: None = Depends(require_csrf_protection),
) -> ResponseModel:
    count = AssetService().delete_assets_batch(
        asset_ids=body.ids,
        owner_user_id=current_user["id"],
    )
    return build_response(request, data={"deleted_count": count})


@router.post("/upload", response_model=ResponseModel, summary="上传媒体资产")
async def upload_asset(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),

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


@router.get("/file/{asset_id}", summary="读取资产文件", include_in_schema=False)
async def get_asset_file(
    asset_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),

):
    asset = AssetService().get_asset(
        asset_id=asset_id,
        owner_user_id=current_user["id"],
    )
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在。")
    file_path = asset.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件在磁盘上丢失。")
    return FileResponse(file_path, filename=asset.get("file_name"))


@router.get("/motions", response_model=ResponseModel, summary="查询动作资产候选")
async def list_motion_assets(
    request: Request,
    action_label: str | None = None,
    scene_label: str | None = None,
    review_status: str | None = None,
    origin: str | None = Query(None, description="来源类型: upload 或 ai_generated"),
    source_video_asset_id: str | None = None,
    keyword: str | None = Query(None, alias="q"),
    limit: int = Query(20, ge=1, le=MAX_MOTION_ASSET_LIST_LIMIT),
    current_user: dict = Depends(get_current_user),

) -> ResponseModel:
    _ = current_user
    items = AssetService().list_motion_assets(
        source_video_asset_id=source_video_asset_id,
        action_label=action_label,
        scene_label=scene_label,
        review_status=review_status,
        origin=origin,
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

) -> ResponseModel:
    _ = current_user
    item = AssetService().get_motion_asset(
        motion_asset_id=motion_asset_id,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="动作资产不存在。")

    return build_response(request, data=item)


@router.post("/motions/extract", response_model=ResponseModel, summary="触发动作资产提取")
async def extract_motion_assets(
    body: MotionExtractRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    __: None = Depends(require_csrf_protection),
) -> ResponseModel:
    extraction_hint = (body.extraction_hint or "").strip()
    project = MotionService()._project_service._get_project_for_execution(
        project_id=body.project_id,
    )
    if project is None or project.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=404, detail="项目不存在。")

    job = JobService().create_job(
        job_type="motion_extraction",
        project_id=body.project_id,
        input_asset_id=project.get("source_asset_id"),
        result={
            "project_id": body.project_id,
            "steps": [],
            "candidate_count": 0,
            "tagged_count": 0,
            "saved_count": 0,
            "asset_ids": [],
            "items": [],
            "extraction_hint": extraction_hint,
        },
    )

    if os.environ.get("PYTEST_CURRENT_TEST"):
        await MotionService().run_job(
            job_id=job["id"],
            project_id=body.project_id,
            owner_user_id=current_user["id"],
            extraction_hint=extraction_hint,
        )
    else:
        TaskQueue.instance().enqueue(
            task_type="motion_extraction",
            payload={
                "job_id": job["id"],
                "project_id": body.project_id,
                "owner_user_id": current_user["id"],
                "extraction_hint": extraction_hint,
            },
        )

    return build_response(request, data={"job_id": job["id"]})


@router.patch("/motions/{motion_asset_id}/review", response_model=ResponseModel, summary="审核动作资产")
async def review_motion_asset(
    motion_asset_id: str,
    body: MotionReviewRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    __: None = Depends(require_csrf_protection),
) -> ResponseModel:
    try:
        item = AssetService().review_motion_asset(
            motion_asset_id=motion_asset_id,
            action=body.action,
            comment=body.comment,
            reviewer_id=current_user["id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="动作资产不存在。")
    return build_response(request, data=item)


@router.post("/motions/batch-review", response_model=ResponseModel, summary="批量审核动作资产")
async def batch_review_motion_assets(
    body: MotionBatchReviewRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    __: None = Depends(require_csrf_protection),
) -> ResponseModel:
    try:
        reviewed_count = AssetService().batch_review_motion_assets(
            asset_ids=body.ids,
            action=body.action,
            reviewer_id=current_user["id"],
            comment=body.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return build_response(request, data={"reviewed_count": reviewed_count})
