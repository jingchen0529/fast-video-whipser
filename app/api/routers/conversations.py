from typing import Any, Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, StringConstraints

from app.auth.dependencies import get_current_user
from app.core.http import ResponseModel, build_response
from app.services.conversation_service import ConversationService

router = APIRouter()


class CreateConversationRequest(BaseModel):
    title: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
    ]
    conversation_type: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
    ] = "mixed"
    source_video_id: str | None = None


class CreateConversationMessageRequest(BaseModel):
    message_type: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
    ] = "text"
    content: str = ""
    asset_ids: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    reply_to_message_id: str | None = None


@router.post("", response_model=ResponseModel, summary="创建会话")
async def create_conversation(
    request: Request,
    payload: CreateConversationRequest,
    current_user: dict = Depends(get_current_user),

) -> ResponseModel:
    service = ConversationService()
    conversation = service.create_conversation(
        user_id=current_user["id"],
        title=payload.title,
        conversation_type=payload.conversation_type,
        source_video_id=payload.source_video_id,
    )
    return build_response(request, data=conversation)


@router.get("", response_model=ResponseModel, summary="获取会话列表")
async def list_conversations(
    request: Request,
    current_user: dict = Depends(get_current_user),

) -> ResponseModel:
    service = ConversationService()
    items = service.list_conversations(user_id=current_user["id"])
    return build_response(request, data={"items": items})


@router.get(
    "/{conversation_id}/messages",
    response_model=ResponseModel,
    summary="获取会话消息",
)
async def list_conversation_messages(
    conversation_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),

) -> ResponseModel:
    service = ConversationService()
    try:
        items = service.list_messages(
            conversation_id=conversation_id,
            user_id=current_user["id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return build_response(
        request,
        data={
            "conversation_id": conversation_id,
            "items": items,
        },
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=ResponseModel,
    summary="发送会话消息",
)
async def create_conversation_message(
    conversation_id: str,
    request: Request,
    payload: CreateConversationMessageRequest,
    current_user: dict = Depends(get_current_user),

) -> ResponseModel:
    service = ConversationService()
    try:
        result = service.create_message_and_dispatch(
            conversation_id=conversation_id,
            user_id=current_user["id"],
            message_type=payload.message_type,
            content=payload.content,
            asset_ids=payload.asset_ids,
            options=payload.options,
            reply_to_message_id=payload.reply_to_message_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return build_response(request, data=result)
