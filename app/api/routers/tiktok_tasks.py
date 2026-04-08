from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StringConstraints

from app.auth.dependencies import require_permissions
from app.core.http import ResponseModel, build_response
from app.crawlers.tiktok import TikTokAPPCrawler

router = APIRouter()


class TikTokValueRequest(BaseModel):
    # 统一接收作品 ID 或 TikTok 分享链接。
    value: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
    ] = Field(
        ...,
        description="TikTok aweme_id or TikTok video/share URL.",
        examples=["7339393672959757570"],
    )


@router.post(
    "/info",
    response_model=ResponseModel,
    summary="获取 TikTok 视频信息 / Fetch TikTok video info by aweme_id or URL",
)
async def get_tiktok_video_info(
    request: Request,
    payload: TikTokValueRequest,
    _: dict = Depends(require_permissions("tiktok.fetch")),
) -> ResponseModel:
    # 统一返回视频信息、下载链接，以及作品在 TikTok 上的基础信息。
    crawler = TikTokAPPCrawler()
    result = await crawler.fetch_video_info(payload.value)

    return build_response(
        request,
        data={
            "input": payload.value,
            **result,
        },
    )
