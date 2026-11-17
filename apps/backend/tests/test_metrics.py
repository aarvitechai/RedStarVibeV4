import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.usefixtures("db")


async def test_metrics_exposes_route_templates_not_raw_paths(client: AsyncClient) -> None:
    await client.get("/health/live")
    await client.get("/api/v1/profiles/someone-who-does-not-exist")
    body = (await client.get("/metrics")).text
    assert 'rsv_http_requests_total{method="GET",route="/health/live",status="200"}' in body
    assert 'route="/api/v1/profiles/{username}"' in body  # bounded label cardinality
    assert "someone-who-does-not-exist" not in body
    assert "rsv_http_request_seconds_bucket" in body


async def test_unknown_urls_do_not_create_new_labels(client: AsyncClient) -> None:
    await client.get("/api/v1/zz-random-path-123")
    body = (await client.get("/metrics")).text
    assert "zz-random-path-123" not in body and 'route="unmatched"' in body
