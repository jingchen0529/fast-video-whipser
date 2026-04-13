import os
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, require_csrf_protection
from app.core.http import ResponseModel, build_response
from app.services.project_service import ProjectService
from app.workflows.task_queue import TaskQueue

class ProjectMessageRequest(BaseModel):
    content: str

router = APIRouter()

class ProjectListItem(BaseModel):
    id: int
    conversation_id: str | None = None
    title: str
    source_url: str = ""
    source_platform: str = "local"
    workflow_type: str = "analysis"
    source_type: str = "upload"
    source_name: str = ""
    status: str = "ready"
    media_url: Optional[str] = None
    objective: str = ""
    summary: str = ""
    created_at: str = "2024-03-20T10:00:00Z"
    updated_at: str = "2024-03-20T10:00:00Z"

class ProjectTaskStep(BaseModel):
    id: int
    step_key: str
    title: str
    detail: str
    status: str
    error_detail: Optional[str] = None
    display_order: int
    updated_at: str = "2024-03-20T10:00:00Z"


class ProjectConversationMessage(BaseModel):
    id: str
    role: str
    message_type: str
    content: str
    content_json: dict | None = None
    reply_to_message_id: str | None = None
    created_at: str

class ProjectDetail(ProjectListItem):
    script_overview: dict = {"full_text": "这是一个测试脚本内容", "dialogue_text": "", "narration_text": "", "caption_text": ""}
    ecommerce_analysis: dict = {"title": "分析结果", "content": "AI 分析内容占位符"}
    source_analysis: dict = {"reference_frames": [], "visual_features": None}
    timeline_segments: List[dict] = []
    shot_segments: List[dict] = []
    storyboard: dict = {"id": None, "version_no": 0, "status": "idle", "summary": "", "items": []}
    video_generation: dict = {"status": "idle", "provider": None, "model": None, "objective": None, "asset_type": None, "asset_name": None, "asset_url": None, "output_asset_id": None, "audio_name": None, "audio_url": None, "reference_frames": [], "script": None, "storyboard": None, "prompt": None, "provider_task_id": None, "result_video_url": None, "error_detail": None, "updated_at": None}
    conversation_messages: List[ProjectConversationMessage] = []
    task_steps: List[ProjectTaskStep] = []

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

class UpdateProjectTitleRequest(BaseModel):
    title: str

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
