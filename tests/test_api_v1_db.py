"""Tests for api_v1 database integration (DAN-54)."""

import pytest
import tempfile
import os
from httpx import AsyncClient, ASGITransport

from isnad.api_v1 import create_app, configure
from isnad.core import AgentIdentity, TrustChain, RevocationRegistry
from isnad.database import Database


@pytest.fixture
async def db(tmp_path):
    """Create a temporary database."""
    db_path = str(tmp_path / "test.db")
    database = Database(db_path)
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def app_with_db(db):
    """App configured with a real database."""
    from isnad import api_v1
    api_v1._identities = {}
    api_v1._trust_chain = TrustChain(revocation_registry=RevocationRegistry())
    api_v1._request_times = []
    api_v1._db = db

    app = create_app(use_lifespan=False)
    yield app
    api_v1._db = None


# ── /check stores in DB ──────────────────────────────────────────

@pytest.mark.anyio
async def test_check_stores_in_db(app_with_db, db):
    """GET /check/{agent_id} should persist the result to trust_checks table."""
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/check/agent:test123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "agent:test123"

    # Verify it's in DB
    checks = await db.get_trust_checks("agent:test123")
    assert len(checks) >= 1
    assert checks[0]["agent_id"] == "agent:test123"
    assert checks[0]["score"] == data["overall_score"] / 100.0


@pytest.mark.anyio
async def test_check_multiple_stores_all(app_with_db, db):
    """Multiple checks for the same agent should all be stored."""
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/api/v1/check/agent:multi")
        await client.get("/api/v1/check/agent:multi")

    checks = await db.get_trust_checks("agent:multi")
    assert len(checks) == 2


# ── /explorer reads from DB ──────────────────────────────────────

@pytest.mark.anyio
async def test_explorer_reads_from_db(app_with_db, db):
    """GET /explorer should return agents from the database."""
    # Seed an agent in DB
    await db.create_agent("agent:dbagent", "deadbeef" * 8, name="DB Agent")

    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/explorer")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        ids = [a["agent_id"] for a in data["agents"]]
        assert "agent:dbagent" in ids


@pytest.mark.anyio
async def test_explorer_fallback_in_memory(db):
    """When DB is empty/None, explorer falls back to in-memory identities."""
    from isnad import api_v1
    api_v1._identities = {}
    api_v1._trust_chain = TrustChain(revocation_registry=RevocationRegistry())
    api_v1._request_times = []
    api_v1._db = None

    alice = AgentIdentity()
    api_v1._identities[alice.agent_id] = alice

    app = create_app(use_lifespan=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/explorer")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        ids = [a["agent_id"] for a in data["agents"]]
        assert alice.agent_id in ids


# ── API key generation + auth ────────────────────────────────────

@pytest.mark.anyio
async def test_create_api_key(app_with_db, db):
    """POST /keys should return a new API key and store its hash."""
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/keys", json={
            "owner_email": "test@example.com",
            "rate_limit": 50,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["api_key"].startswith("isnad_")
        assert data["owner_email"] == "test@example.com"
        assert data["rate_limit"] == 50

    # Verify key validates
    record = await db.validate_api_key(data["api_key"])
    assert record is not None
    assert record["owner_email"] == "test@example.com"


@pytest.mark.anyio
async def test_api_key_auth_valid(app_with_db, db):
    """A valid API key should authenticate successfully."""
    # Create a key
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/keys", json={"owner_email": "auth@test.com"})
        api_key = resp.json()["api_key"]

    # Validate it in DB
    record = await db.validate_api_key(api_key)
    assert record is not None


@pytest.mark.anyio
async def test_api_key_auth_invalid(app_with_db):
    """An invalid API key should be rejected."""
    from isnad.api_v1 import require_api_key
    with pytest.raises(Exception):
        await require_api_key("bad_key_12345")


@pytest.mark.anyio
async def test_keys_endpoint_without_db():
    """POST /keys should return 503 when no database is configured."""
    from isnad import api_v1
    api_v1._identities = {}
    api_v1._trust_chain = TrustChain(revocation_registry=RevocationRegistry())
    api_v1._request_times = []
    api_v1._db = None

    app = create_app(use_lifespan=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/keys", json={"owner_email": "x@y.com"})
        assert resp.status_code == 503
