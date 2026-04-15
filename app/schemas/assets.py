"""Pydantic request/response schemas for asset-related endpoints."""
from pydantic import BaseModel


class BatchDeleteBody(BaseModel):
    ids: list[str]


class MotionExtractRequest(BaseModel):
    project_id: int
    extraction_hint: str | None = None


class MotionReviewRequest(BaseModel):
    action: str
    comment: str | None = None


class MotionBatchReviewRequest(BaseModel):
    ids: list[str]
    action: str
    comment: str | None = None
