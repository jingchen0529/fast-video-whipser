import pytest
import httpx

from app.db import initialize_database
from app.core.http import APINotFoundError
from app.http_client import AsyncHttpClient
from app.services.system_settings_service import SystemSettingsService
from tests.test_auth_api import _test_database_scope

@pytest.mark.asyncio
async def test_fetch_data_maps_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=404, request=request, json={"detail": "missing"})

    client = AsyncHttpClient(transport=httpx.MockTransport(handler), retry_limit=1)

    with pytest.raises(APINotFoundError):
        await client.fetch_data("GET", "https://example.com/missing")

    await client.close()


@pytest.mark.asyncio
async def test_fetch_head_allows_empty_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, request=request, content=b"")

    client = AsyncHttpClient(transport=httpx.MockTransport(handler), retry_limit=1)
    response = await client.fetch_data_via_head("https://example.com/health")

    assert response.status_code == 200
    assert response.content == b""

    await client.close()


@pytest.mark.asyncio
async def test_http_client_loads_proxy_from_system_settings(tmp_path) -> None:
    with _test_database_scope(tmp_path, prefix="proxy"):
        initialize_database()
        SystemSettingsService().update_settings(
            payload={
                "proxy": {
                    "enabled": True,
                    "all_url": "http://127.0.0.1:7890",
                },
            }
        )

        client = AsyncHttpClient(retry_limit=1)
        try:
            assert client.proxy_settings == {
                "http://": "http://127.0.0.1:7890",
                "https://": "http://127.0.0.1:7890",
            }
        finally:
            await client.close()
