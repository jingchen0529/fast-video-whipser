from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ResponseModel(BaseModel):
    code: int = Field(default=200, description="HTTP status code | HTTP状态码")
    router: str = Field(
        default="",
        description="The endpoint that generated this response | 生成此响应的端点",
    )
    params: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="The parameters used in the request | 请求中使用的参数",
    )
    data: Optional[Any] = Field(default=None, description="The response data | 响应数据")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": 200,
                "router": "/example/endpoint",
                "params": {"query": "example"},
                "data": {"key": "value"},
            }
        }
    )


class ErrorResponseModel(BaseModel):
    code: int = Field(default=400, description="HTTP status code | HTTP状态码")
    message: str = Field(
        default="An error occurred. | 服务器发生错误。",
        description="Error message | 错误消息",
    )
    time: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        description="The time the error occurred | 发生错误的时间",
    )
    router: str = Field(
        default="",
        description="The endpoint that generated this response | 生成此响应的端点",
    )
    params: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="The parameters used in the request | 请求中使用的参数",
    )
    details: Optional[Any] = Field(
        default=None,
        description="Structured error details | 结构化错误详情",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": 400,
                "message": "Invalid request parameters. | 请求参数无效。",
                "time": "2026-03-31 16:19:00",
                "router": "/example/endpoint",
                "params": {"param1": "invalid"},
                "details": [{"loc": ["query", "param1"], "msg": "Field required"}],
            }
        }
    )
