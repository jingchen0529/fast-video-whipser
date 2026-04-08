from fastapi import APIRouter, Request, status

from app.core.http import ResponseModel, build_response

router = APIRouter()


@router.get(
    "",
    summary="检查服务器是否正确响应请求 / Check if the server responds to requests correctly",
    response_model=ResponseModel,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "服务器响应成功 / Server responds successfully",
            "content": {
                "application/json": {
                    "example": {
                        "code": 200,
                        "router": "/health",
                        "params": {},
                        "data": {"status": "ok"},
                    }
                }
            }
        }
    }
)
async def health_check(request: Request):
    """
    # [中文]

    ### 用途说明:

    - 检查服务器是否正确响应请求。

    ### 参数说明:

    - 无参数。

    ### 返回结果:

    - `status`: 服务器状态，正常为 `ok`。

    # [English]

    ### Purpose:

    - Check if the server responds to requests correctly.

    ### Parameter Description:

    - No parameters.

    ### Return Result:

    - `status`: Server status, normal is `ok`.
    """
    return build_response(request, data={"status": "ok"})


@router.get(
    "/check",
    include_in_schema=False,
)
async def health_check_legacy(request: Request):
    return await health_check(request)
