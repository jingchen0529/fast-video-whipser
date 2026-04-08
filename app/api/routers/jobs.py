from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.dependencies import get_current_user, require_permissions
from app.core.http import ResponseModel, build_response
from app.services.job_service import JobService

router = APIRouter()


@router.get("/{job_id}", response_model=ResponseModel, summary="获取任务详情")
async def get_job(
    job_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    _: dict = Depends(require_permissions("jobs.read")),
) -> ResponseModel:
    _ = current_user
    service = JobService()
    job = service.get_job(job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在。")

    return build_response(request, data=job)
