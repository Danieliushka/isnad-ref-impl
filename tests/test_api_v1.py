"""Tests for isnad API v1 router."""

import pytest
from httpx import AsyncClient, ASGITransport
from isnad.api_v1 import create_app, configure, router, _trust_chain, _identities
from isnad.core import AgentIdentity, Attestation, TrustChain, RevocationRegistry


@pytest.fixture
def app():
    """Create a fresh v1 app with clean state."""
    from isnad import api_v1
    # Reset module state
    api_v1._identities = {}
    api_v1._trust_chain = TrustChain(revocation_registry=RevocationRegistry())
    api_v1._db = None
    api_v1._request_times = []

    app = create_app()
    return app


@pytest.fixture
def app_with_agents():
    """App pre-loaded with test agents and attestations."""
    from isnad import api_v1

    rev_reg = RevocationRegistry()
    chain = TrustChain(revocation_registry=rev_reg)
    identities = {}

    alice = AgentIdentity()
    bob = AgentIdentity()
    identities[alice.agent_id] = alice
    identities[bob.agent_id] = bob

    att = Attestation(
        subject=bob.agent_id,
        witness=alice.agent_id,
        task="code-review",
        evidence="https://example.com/pr/1",
    )
    att.sign(alice)
    chain.add(att)

    api_v1._identities = identities
    api_v1._trust_chain = chain
    api_v1._db = None
    api_v1._request_times = []

    app = create_app()
    app._test_alice = alice
    app._test_bob = bob
    return app


@pytest.mark.asyncio
async def test_health(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.3.0"
    assert data["modules"] == 36
    assert data["tests"] == 1029


@pytest.mark.asyncio
async def test_stats(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/stats")
    assert r.status_code == 200
    data = r.json()
    assert "agents_checked" in data
    assert "attestations_verified" in data
    assert "avg_response_ms" in data
    assert "uptime" in data
    assert data["uptime"] >= 0


@pytest.mark.asyncio
async def test_check_agent(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/check/agent:test123")
    assert r.status_code == 200
    data = r.json()
    assert data["agent_id"] == "agent:test123"
    assert 0 <= data["overall_score"] <= 100
    assert data["confidence"] in ("high", "medium", "low")
    assert isinstance(data["risk_flags"], list)
    assert isinstance(data["categories"], list)
    assert len(data["categories"]) == 6
    cat_names = {c["name"] for c in data["categories"]}
    assert cat_names == {"identity", "attestation", "behavioral", "platform", "transactions", "security"}
    assert data["last_checked"].endswith("Z")
    assert data["certification_id"] != ""


@pytest.mark.asyncio
async def test_check_agent_with_attestations(app_with_agents):
    app = app_with_agents
    bob_id = app._test_bob.agent_id
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/v1/check/{bob_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["attestation_count"] >= 1
    # attestation category should have non-zero score
    att_cat = [c for c in data["categories"] if c["name"] == "attestation"][0]
    assert att_cat["modules_passed"] >= 1


@pytest.mark.asyncio
async def test_explorer_empty(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/explorer")
    assert r.status_code == 200
    data = r.json()
    assert data["agents"] == []
    assert data["total"] == 0
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_explorer_with_agents(app_with_agents):
    app = app_with_agents
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/explorer")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert len(data["agents"]) == 2


@pytest.mark.asyncio
async def test_explorer_pagination(app_with_agents):
    app = app_with_agents
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/explorer?page=1&limit=1")
    data = r.json()
    assert len(data["agents"]) == 1
    assert data["limit"] == 1


@pytest.mark.asyncio
async def test_explorer_detail(app_with_agents):
    app = app_with_agents
    bob_id = app._test_bob.agent_id
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/v1/explorer/{bob_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["agent_id"] == bob_id
    assert data["public_key"] != ""
    assert data["attestation_count"] >= 1


@pytest.mark.asyncio
async def test_explorer_detail_not_found(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/explorer/nonexistent")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_security_headers(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "max-age" in r.headers.get("Strict-Transport-Security", "")
    assert r.headers.get("Content-Security-Policy") == "default-src 'self'"


@pytest.mark.asyncio
async def test_cors_headers(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.options("/api/v1/health", headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "GET",
        })
    assert r.status_code == 200
    assert "access-control-allow-origin" in r.headers


@pytest.mark.asyncio
async def test_check_records_response_time(app):
    from isnad import api_v1
    before = len(api_v1._request_times)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.get("/api/v1/check/agent:timing_test")
    assert len(api_v1._request_times) == before + 1


@pytest.mark.asyncio
async def test_configure():
    """configure() should inject shared state."""
    from isnad import api_v1
    chain = TrustChain()
    ids = {"test": AgentIdentity()}
    configure(identities=ids, trust_chain=chain)
    assert api_v1._trust_chain is chain
    assert api_v1._identities is ids
    # Reset
    api_v1._identities = {}
    api_v1._trust_chain = TrustChain()
