"""Tests for POST /api/v1/register — simple agent registration endpoint."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from isnad.api_v1 import create_app, configure, _db


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.get_agent_by_name = AsyncMock(return_value=None)
    db.create_agent = AsyncMock(return_value={
        "id": "test-id", "name": "Kit", "public_key": "abc",
        "created_at": "2026-02-26T00:00:00Z", "metadata": "{}",
        "is_certified": 0, "trust_score": 0.0, "last_checked": None,
    })
    db.update_agent = AsyncMock(return_value=True)
    db.connect = AsyncMock()
    db.close = AsyncMock()
    return db


@pytest.fixture
def app(mock_db):
    configure(db=mock_db)
    return create_app(use_lifespan=False)


@pytest.mark.asyncio
async def test_register_minimal(app, mock_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/register", json={
            "agent_name": "Kit the Fox",
            "description": "A friendly fox agent",
        })
    assert resp.status_code == 201
    data = resp.json()
    assert "agent_id" in data
    assert "api_key" in data
    assert data["api_key"].startswith("isnad_")
    mock_db.create_agent.assert_called_once()


@pytest.mark.asyncio
async def test_register_with_homepage(app, mock_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/register", json={
            "agent_name": "Kit the Fox",
            "homepage_url": "https://kit.example.com",
        })
    assert resp.status_code == 201
    data = resp.json()
    assert "agent_id" in data
    assert "api_key" in data


@pytest.mark.asyncio
async def test_register_duplicate_name(app, mock_db):
    mock_db.get_agent_by_name = AsyncMock(return_value={"id": "existing"})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/register", json={
            "agent_name": "Kit the Fox",
        })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_missing_name(app, mock_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/register", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_empty_name(app, mock_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/register", json={"agent_name": ""})
    assert resp.status_code == 422
