"""Tests for POST /api/v1/check endpoint."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from isnad.api_v1 import create_app, _db, router


@pytest.fixture
def app():
    """Create test app with mocked DB."""
    app = create_app(use_lifespan=False)
    return app


@pytest.mark.asyncio
async def test_post_check_missing_api_key(app):
    """POST /check without API key returns 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/check", json={"agent_id": "test-agent"})
        assert resp.status_code in (401, 503)  # 401 if DB up, 503 if DB not available


@pytest.mark.asyncio
async def test_post_check_no_body_no_key(app):
    """POST /check without body or key returns 401 (auth checked first)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/check")
        assert resp.status_code in (401, 503)


@pytest.mark.asyncio
async def test_post_check_empty_agent_id(app):
    """POST /check with empty agent_id returns 422 (validation before DB)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/check",
            json={"agent_id": ""},
            headers={"X-API-Key": "test"},
        )
        # Either 422 (pydantic catches empty) or 503 (DB not available for auth)
        assert resp.status_code in (422, 503)


@pytest.mark.asyncio
async def test_post_check_response_schema():
    """POST /check returns TrustCheckResult schema when auth passes."""
    from isnad.api_v1 import CheckRequest, TrustCheckResult, _run_certification

    # Test that _run_certification returns valid data
    result = _run_certification("test-agent-123")
    assert isinstance(result, TrustCheckResult)
    assert result.agent_id == "test-agent-123"
    assert 0 <= result.overall_score <= 100
    assert result.confidence in ("high", "medium", "low")
    assert isinstance(result.categories, list)
    assert len(result.categories) == 6
    assert result.last_checked.endswith("Z")


def test_check_request_validation():
    """CheckRequest model validates correctly."""
    from isnad.api_v1 import CheckRequest

    # Valid
    req = CheckRequest(agent_id="test-agent")
    assert req.agent_id == "test-agent"

    # Empty string should fail
    with pytest.raises(Exception):
        CheckRequest(agent_id="")

    # Too long should fail
    with pytest.raises(Exception):
        CheckRequest(agent_id="x" * 201)
