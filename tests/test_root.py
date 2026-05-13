from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_returns_service_metadata(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "transport-delay-predictor"
    assert body["docs"] == "/docs"


@pytest.mark.asyncio
async def test_openapi_schema_is_served(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Transport Delay Predictor"
    paths = schema["paths"]
    assert "/health" in paths
    assert "/api/v1/stops" in paths
    assert "/api/v1/predictions" in paths
