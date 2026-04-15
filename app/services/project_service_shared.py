import asyncio
import base64
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import shutil
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import quote, urlparse

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.orm import Session

from app.auth.security import utcnow, utcnow_ms
from app.core.config import settings
from app.crawlers.tiktok import TikTokAPPCrawler
from app.db.session import get_db_session
from app.http_client import AsyncHttpClient
from app.models.project import (
    Project,
    ProjectMessage,
    ProjectTaskStep,
    ShotSegment,
    Storyboard,
    StoryboardItem,
    StoryboardItemSegment,
)
from app.repositories import (
    ProjectMessageRepository,
    ProjectRepository,
    ProjectTaskStepRepository,
    ShotSegmentRepository,
    StoryboardRepository,
)
from app.services.analysis_ai_service import AnalysisAIService
from app.services.asset_service import AssetService
from app.services.system_settings_service import SystemSettingsService
from app.utils.file_utils import FileUtils
from app.workflows.engine import TaskStepDefinition, WorkflowRegistry


def _get_session() -> Session:
    gen = get_db_session()
    return next(gen)


logger = logging.getLogger(__name__)

# Re-export for backward compatibility with legacy step migration code
from app.workflows.engine import UNSUPPORTED_WORKFLOW_STEPS  # noqa: E402

DEFAULT_SCRIPT_OVERVIEW = {
    "full_text": "",
    "dialogue_text": "",
    "narration_text": "",
    "caption_text": "",
}

DEFAULT_ECOMMERCE_ANALYSIS = {
    "title": "分析结果",
    "content": None,
}

DEFAULT_SOURCE_ANALYSIS = {
    "reference_frames": [],
    "visual_features": None,
}

DEFAULT_STORYBOARD = {
    "id": None,
    "version_no": 0,
    "status": "idle",
    "summary": "",
    "items": [],
}

DEFAULT_VIDEO_GENERATION = {
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

REMAKE_INTENT_LABELS = {
    "video_remake": "视频复刻",
    "viral_remake": "爆款复刻",
}

DEFAULT_DOUBAO_VIDEO_BASE_URL = "https://operator.las.cn-beijing.volces.com"
DEFAULT_KLING_VIDEO_BASE_URL = "https://api-beijing.klingai.com"
DEFAULT_WANXIANG_VIDEO_BASE_URL = "https://dashscope.aliyuncs.com"
DOUBAO_VIDEO_TASK_PATHS = (
    "/api/v1/contents/generations/tasks",
    "/contents/generations/tasks",
)

VIDEO_PROVIDER_MODEL_ALIASES = {
    "kling": {
        "kling-v1": "kling-v3",
        "kling-master": "kling-v3-omni",
    },
    "veo": {
        "veo-2": "veo-2.0-generate-001",
        "veo-3": "veo-3.0-generate-001",
        "veo-3-fast": "veo-3.0-fast-generate-001",
        "veo-3.1": "veo-3.1-generate-001",
        "veo-3.1-fast": "veo-3.1-fast-generate-001",
    },
}

JSON_PROJECT_COLUMNS = {
    "script_overview": "script_overview_json",
    "ecommerce_analysis": "ecommerce_analysis_json",
    "source_analysis": "source_analysis_json",
    "timeline_segments": "timeline_segments_json",
    "video_generation": "video_generation_json",
}

__all__ = [name for name in globals() if not name.startswith("__")]
