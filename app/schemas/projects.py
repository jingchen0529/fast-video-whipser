"""Pydantic request/response schemas for project-related endpoints."""
from typing import List, Optional

from pydantic import BaseModel


class ProjectMessageRequest(BaseModel):
    content: str


class UpdateProjectTitleRequest(BaseModel):
    title: str


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


class ProjectListItem(BaseModel):
    id: int
    title: str
    source_url: str = ""
    source_platform: str = "local"
    workflow_type: str = "analysis"
    source_type: str = "upload"
    source_name: str = ""
    status: str = "ready"
    media_url: Optional[str] = None
    generated_media_url: Optional[str] = None
    objective: str = ""
    summary: str = ""
    created_at: str = "2024-03-20T10:00:00Z"
    updated_at: str = "2024-03-20T10:00:00Z"


class ProjectDetail(ProjectListItem):
    script_overview: dict = {
        "full_text": "",
        "dialogue_text": "",
        "narration_text": "",
        "caption_text": "",
    }
    ecommerce_analysis: dict = {"title": "", "content": ""}
    source_analysis: dict = {"reference_frames": [], "visual_features": None}
    timeline_segments: List[dict] = []
    shot_segments: List[dict] = []
    storyboard: dict = {
        "id": None,
        "version_no": 0,
        "status": "idle",
        "summary": "",
        "items": [],
    }
    video_generation: dict = {
        "status": "idle",
        "provider": None,
        "model": None,
        "objective": None,
        "asset_type": None,
        "asset_name": None,
        "asset_url": None,
        "output_asset_id": None,
        "audio_name": None,
        "audio_url": None,
        "reference_frames": [],
        "script": None,
        "storyboard": None,
        "prompt": None,
        "provider_task_id": None,
        "result_video_url": None,
        "error_detail": None,
        "updated_at": None,
    }
    messages: List[ProjectConversationMessage] = []
    task_steps: List[ProjectTaskStep] = []
