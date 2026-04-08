import asyncio
import json
import os
import re
from typing import Any, Dict, Optional

import aiofiles
import httpx
from httpx import AsyncBaseTransport, Response

from app.core.http import (
    APIConnectionError,
    APIFileDownloadError,
    APINotFoundError,
    APIRateLimitError,
    APIResponseError,
    APITimeoutError,
    APIUnauthorizedError,
    APIUnavailableError,
)
from app.core.logging import configure_logging
from app.services.system_settings_service import SystemSettingsService

logger = configure_logging(__name__)


class AsyncHttpClient:
    """
    异步 HTTP 客户端 (Asynchronous HTTP client)
    """

    def __init__(
        self,
        proxy_settings: Optional[Dict[str, str]] = None,
        retry_limit: int = 3,
        max_connections: int = 50,
        request_timeout: int = 10,
        max_concurrent_tasks: int = 50,
        headers: Optional[Dict[str, str]] = None,
        base_backoff: float = 1.0,
        follow_redirects: bool = False,
        transport: Optional[AsyncBaseTransport] = None,
    ) -> None:
        resolved_proxy_settings = proxy_settings
        if resolved_proxy_settings is None and transport is None:
            resolved_proxy_settings = SystemSettingsService().get_proxy_mounts()
        self.proxy_settings = (
            resolved_proxy_settings
            if isinstance(resolved_proxy_settings, dict)
            else None
        )
        self.headers = headers or {
            "User-Agent": "fast-video-whisper/http-client",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        }
        self.retry_limit = max(1, retry_limit)
        self.request_timeout = request_timeout
        self.base_backoff = base_backoff
        self.semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self.aclient = self._build_client(
            max_connections=max_connections,
            follow_redirects=follow_redirects,
            transport=transport,
        )

    def _build_client(
        self,
        *,
        max_connections: int,
        follow_redirects: bool,
        transport: Optional[AsyncBaseTransport],
    ) -> httpx.AsyncClient:
        default_transport = transport or httpx.AsyncHTTPTransport(retries=0)
        mounts = None

        if self.proxy_settings and transport is None:
            mounts = {
                key: httpx.AsyncHTTPTransport(proxy=value, retries=0)
                for key, value in self.proxy_settings.items()
            }

        return httpx.AsyncClient(
            headers=self.headers,
            timeout=httpx.Timeout(self.request_timeout),
            limits=httpx.Limits(max_connections=max_connections),
            transport=default_transport,
            mounts=mounts,
            follow_redirects=follow_redirects,
        )

    async def fetch_response(self, url: str, **kwargs: Any) -> Response:
        return await self.fetch_data("GET", url, **kwargs)

    async def fetch_get_json(self, url: str, **kwargs: Any) -> Dict[str, Any]:
        response = await self.fetch_data("GET", url, **kwargs)
        return self.parse_json(response)

    async def fetch_post_json(self, url: str, **kwargs: Any) -> Dict[str, Any]:
        response = await self.fetch_data("POST", url, **kwargs)
        return self.parse_json(response)

    async def fetch_data(self, method: str, url: str, **kwargs: Any) -> Response:
        backoff = self.base_backoff
        method = method.upper()

        for attempt in range(1, self.retry_limit + 1):
            try:
                request_kwargs = dict(kwargs)
                async with self.semaphore:
                    response = await self.aclient.request(
                        method=method,
                        url=url,
                        headers=request_kwargs.pop("headers", None),
                        **request_kwargs,
                    )

                response.raise_for_status()
                return response

            except httpx.TimeoutException as exc:
                logger.warning(
                    "Timeout while requesting %s %s on attempt %s/%s",
                    method,
                    url,
                    attempt,
                    self.retry_limit,
                )
                if attempt == self.retry_limit:
                    raise APITimeoutError() from exc

            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                logger.warning(
                    "HTTP %s returned status %s on attempt %s/%s",
                    url,
                    status_code,
                    attempt,
                    self.retry_limit,
                )
                if self._should_retry_status(status_code) and attempt < self.retry_limit:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                self.handle_http_status_error(exc, url, attempt)

            except httpx.RequestError as exc:
                logger.warning(
                    "Connection error while requesting %s %s on attempt %s/%s: %s",
                    method,
                    url,
                    attempt,
                    self.retry_limit,
                    str(exc),
                )
                if attempt == self.retry_limit:
                    raise APIConnectionError() from exc

            await asyncio.sleep(backoff)
            backoff *= 2

        raise APIConnectionError()

    async def fetch_data_via_head(self, url: str, **kwargs: Any) -> Response:
        return await self.fetch_data("HEAD", url, **kwargs)

    async def download_file(
        self,
        url: str,
        save_path: str,
        chunk_size: int = 1024 * 1024,
        **kwargs: Any,
    ) -> None:
        backoff = self.base_backoff
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

        for attempt in range(1, self.retry_limit + 1):
            try:
                request_kwargs = dict(kwargs)
                request_headers = {**self.headers, **request_kwargs.pop("headers", {})}
                request_headers["Referer"] = url

                async with self.semaphore:
                    async with self.aclient.stream(
                        "GET",
                        url,
                        headers=request_headers,
                        **request_kwargs,
                    ) as response:
                        response.raise_for_status()
                        async with aiofiles.open(save_path, "wb") as output_file:
                            async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                                await output_file.write(chunk)

                logger.info("File downloaded successfully: %s", save_path)
                return

            except httpx.TimeoutException as exc:
                logger.warning(
                    "Timeout while downloading %s on attempt %s/%s",
                    url,
                    attempt,
                    self.retry_limit,
                )
                if attempt == self.retry_limit:
                    raise APIFileDownloadError(f"Timed out while downloading {url}") from exc

            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                logger.warning(
                    "Download failed with status %s for %s on attempt %s/%s",
                    status_code,
                    url,
                    attempt,
                    self.retry_limit,
                )
                if self._should_retry_status(status_code) and attempt < self.retry_limit:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise APIFileDownloadError(f"Failed to download file from {url}") from exc

            except httpx.RequestError as exc:
                logger.warning(
                    "Connection error while downloading %s on attempt %s/%s: %s",
                    url,
                    attempt,
                    self.retry_limit,
                    str(exc),
                )
                if attempt == self.retry_limit:
                    raise APIFileDownloadError(f"Failed to download file from {url}") from exc

            await asyncio.sleep(backoff)
            backoff *= 2

        raise APIFileDownloadError(f"Failed to download file from {url}")

    @staticmethod
    def _should_retry_status(status_code: int) -> bool:
        return status_code in {408, 425, 429, 500, 502, 503, 504}

    @staticmethod
    def handle_http_status_error(http_error: httpx.HTTPStatusError, url: str, attempt: int) -> None:
        response = getattr(http_error, "response", None)
        status_code = getattr(response, "status_code", None)

        if not response or status_code is None:
            logger.error(
                "Unexpected HTTP error: %s, URL: %s, Attempt: %s",
                str(http_error),
                url,
                attempt,
            )
            raise APIResponseError() from http_error

        error_mapping = {
            401: APIUnauthorizedError(),
            404: APINotFoundError(),
            408: APITimeoutError(),
            429: APIRateLimitError(),
            503: APIUnavailableError(),
        }

        error = error_mapping.get(status_code, APIResponseError(status_code=status_code))
        logger.error("HTTP status error %s on attempt %s, URL: %s", status_code, attempt, url)
        raise error from http_error

    @staticmethod
    def parse_json(response: Response) -> Dict[str, Any]:
        if len(response.content) == 0:
            logger.error("Empty response content.")
            raise APIResponseError("Empty response content.")

        try:
            return response.json()
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", response.text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError as exc:
                    logger.error("Failed to parse JSON from %s: %s", response.url, str(exc))
                    raise APIResponseError(
                        "Failed to parse JSON data.",
                        status_code=response.status_code,
                    ) from exc

            logger.error("No valid JSON structure found in response.")
            raise APIResponseError("No JSON data found.", status_code=response.status_code)

    async def close(self) -> None:
        await self.aclient.aclose()

    async def __aenter__(self) -> "AsyncHttpClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
