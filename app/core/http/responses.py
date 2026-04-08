from typing import Any, Dict, Optional

from fastapi import Request

from app.core.http.schemas import ResponseModel


def build_response(
    request: Request,
    *,
    data: Any = None,
    code: int = 200,
    params: Optional[Dict[str, Any]] = None,
) -> ResponseModel:
    return ResponseModel(
        code=code,
        router=request.url.path,
        params=params or dict(request.query_params),
        data=data,
    )
