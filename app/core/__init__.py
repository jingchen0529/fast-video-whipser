from app.core.config import Settings, get_settings, settings

__all__ = [
    "APIConnectionError",
    "APIError",
    "APIFileDownloadError",
    "APINotFoundError",
    "APIRateLimitError",
    "APIResponseError",
    "APIRetryExhaustedError",
    "APITimeoutError",
    "APIUnauthorizedError",
    "APIUnavailableError",
    "ErrorResponseModel",
    "ResponseModel",
    "Settings",
    "build_response",
    "configure_logging",
    "get_settings",
    "register_exception_handlers",
    "settings",
]


def __getattr__(name: str):
    if name == "configure_logging":
        from app.core.logging import configure_logging

        return configure_logging

    if name in {
        "APIConnectionError",
        "APIError",
        "APIFileDownloadError",
        "APINotFoundError",
        "APIRateLimitError",
        "APIResponseError",
        "APIRetryExhaustedError",
        "APITimeoutError",
        "APIUnauthorizedError",
        "APIUnavailableError",
        "ErrorResponseModel",
        "ResponseModel",
        "build_response",
        "register_exception_handlers",
    }:
        from app.core import http as http_module

        return getattr(http_module, name)

    raise AttributeError(f"module 'app.core' has no attribute {name!r}")
