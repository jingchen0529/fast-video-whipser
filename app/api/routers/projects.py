import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.auth.dependencies import get_current_user, require_csrf_protection
from app.core.http import ResponseModel, build_response
from app.schemas.projects import ProjectMessageRequest, UpdateProjectTitleRequest
from app.services.project_service import ProjectService
from app.workflows.task_queue import TaskQueue

router = APIRouter()


@router.get("", response_model=ResponseModel)
async def list_projects(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    items = ProjectService().list_projects(user_id=current_user["id"])
    return build_response(request, data=items)

@router.get("/{project_id}", response_model=ResponseModel)
async def get_project_detail(
    project_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    project = ProjectService().get_project_detail(
        project_id=project_id,
        user_id=current_user["id"],
    )
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在。")
    return build_response(request, data=project)

@router.post("/upload", response_model=ResponseModel)
async def upload_project(
    request: Request,
    file: Optional[UploadFile] = File(None),
    objective: str = Form(...),
    workflow_type: str = Form("analysis"),
    source_url: str = Form(""),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_csrf_protection),
):
    service = ProjectService()
    try:
        project = await service.create_project(
            user_id=current_user["id"],
            objective=objective,
            workflow_type=workflow_type,
            source_url=source_url,
            file=file,
        )
    finally:
        if file is not None:
            await file.close()

    if os.environ.get("PYTEST_CURRENT_TEST"):
        await service.run_project_workflow(project_id=project["id"])
    else:
        TaskQueue.instance().enqueue(
            task_type="workflow",
            payload={"project_id": project["id"]},
        )
    return build_response(request, data=project)

@router.post("/{project_id}/messages", response_model=ResponseModel)
async def add_project_message(
    project_id: int,
    request: ProjectMessageRequest,
    req: Request,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_csrf_protection),
):
    service = ProjectService()
    message = await service.add_followup_message(
        project_id=project_id,
        user_id=current_user["id"],
        content=request.content,
    )
    return build_response(req, data=message)

@router.patch("/{project_id}", response_model=ResponseModel)
async def update_project_title(
    project_id: int,
    request: UpdateProjectTitleRequest,
    req: Request,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_csrf_protection),
):
    service = ProjectService()
    success = service.update_project_title(
        project_id=project_id,
        user_id=current_user["id"],
        title=request.title,
    )
    if not success:
        raise HTTPException(status_code=404, detail="项目不存在。")
    return build_response(req, data={"success": True})

@router.delete("/{project_id}", response_model=ResponseModel)
async def delete_project(
    project_id: int,
    req: Request,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_csrf_protection),
):
    service = ProjectService()
    success = service.delete_project(
        project_id=project_id,
        user_id=current_user["id"],
    )
    if not success:
        raise HTTPException(status_code=404, detail="项目不存在。")
    return build_response(req, data={"success": True})
