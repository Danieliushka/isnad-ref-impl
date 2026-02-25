"""Tests for the PostgreSQL database module."""

import os
import pytest
import pytest_asyncio

# Ensure DATABASE_URL is set for tests
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://isnad:isnad_secret@localhost:5432/isnad_db")
os.environ["DATABASE_URL"] = DATABASE_URL

from isnad.database import Database


@pytest_asyncio.fixture
async def db():
    """Fresh database for each test — truncates all tables."""
    d = Database()
    await d.connect()
    # Clean tables
    async with d._pool.acquire() as conn:
        await conn.execute("TRUNCATE agents, attestations, certifications, api_keys, trust_checks, platform_data CASCADE")
    yield d
    await d.close()


@pytest.mark.asyncio
async def test_create_and_get_agent(db):
    result = await db.create_agent("agent:abc", "pubkey123", name="TestBot")
    assert result["id"] == "agent:abc"

    fetched = await db.get_agent("agent:abc")
    assert fetched is not None
    assert fetched["name"] == "TestBot"
    assert fetched["public_key"] == "pubkey123"


@pytest.mark.asyncio
async def test_get_agent_by_pubkey(db):
    await db.create_agent("agent:x", "unique_pk")
    found = await db.get_agent_by_pubkey("unique_pk")
    assert found is not None
    assert found["id"] == "agent:x"


@pytest.mark.asyncio
async def test_list_agents(db):
    await db.create_agent("agent:1", "pk1")
    await db.create_agent("agent:2", "pk2")
    agents = await db.list_agents()
    assert len(agents) == 2


@pytest.mark.asyncio
async def test_update_agent(db):
    await db.create_agent("agent:u", "pku")
    ok = await db.update_agent("agent:u", name="Updated")
    assert ok
    a = await db.get_agent("agent:u")
    assert a["name"] == "Updated"


@pytest.mark.asyncio
async def test_delete_agent(db):
    await db.create_agent("agent:d", "pkd")
    ok = await db.delete_agent("agent:d")
    assert ok
    assert await db.get_agent("agent:d") is None


@pytest.mark.asyncio
async def test_attestation_crud(db):
    await db.create_agent("agent:s", "pks")
    await db.create_agent("agent:w", "pkw")

    att = await db.create_attestation("att:1", "agent:s", "agent:w", "code-review")
    assert att["id"] == "att:1"

    fetched = await db.get_attestation("att:1")
    assert fetched is not None

    atts = await db.get_attestations_for_subject("agent:s")
    assert len(atts) == 1

    atts_w = await db.get_attestations_by_witness("agent:w")
    assert len(atts_w) == 1

    count = await db.count_attestations()
    assert count == 1


@pytest.mark.asyncio
async def test_revoke_attestation(db):
    await db.create_attestation("att:r", "s", "w", "task")
    ok = await db.revoke_attestation("att:r")
    assert ok
    att = await db.get_attestation("att:r")
    assert att["is_revoked"] is True


@pytest.mark.asyncio
async def test_certification_crud(db):
    await db.create_agent("agent:c", "pkc")
    cert = await db.create_certification(
        "cert:1", "agent:c", 0.95, {"safety": 0.9}, "2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
    )
    assert cert["score"] == 0.95

    fetched = await db.get_certification("cert:1")
    assert fetched is not None
    assert isinstance(fetched["category_scores"], dict)

    certs = await db.get_certifications_for_agent("agent:c")
    assert len(certs) == 1


@pytest.mark.asyncio
async def test_api_key_crud(db):
    key = await db.create_api_key("secret-key-123", "test@example.com")
    assert key["is_active"] == 1

    validated = await db.validate_api_key("secret-key-123")
    assert validated is not None

    ok = await db.deactivate_api_key(key["key_hash"])
    assert ok

    validated = await db.validate_api_key("secret-key-123")
    assert validated is None


@pytest.mark.asyncio
async def test_trust_check_crud(db):
    tc = await db.create_trust_check("agent:t", 0.85, {"detail": "ok"}, "127.0.0.1")
    assert tc["score"] == 0.85

    checks = await db.get_trust_checks("agent:t")
    assert len(checks) == 1
    assert checks[0]["report"]["detail"] == "ok"


@pytest.mark.asyncio
async def test_platform_data_crud(db):
    await db.create_agent("agent:p", "pkp")
    pd = await db.create_platform_data(
        "agent:p", "github", "https://github.com/bot",
        raw_data={"repos": 5}, metrics={"stars": 100},
    )
    assert pd["platform_name"] == "github"

    data = await db.get_platform_data("agent:p")
    assert len(data) == 1


@pytest.mark.asyncio
async def test_nonexistent_agent(db):
    assert await db.get_agent("nope") is None


@pytest.mark.asyncio
async def test_transaction(db):
    async with db.transaction() as conn:
        await conn.execute(
            "INSERT INTO agents (id, name, public_key, created_at) VALUES ($1, $2, $3, $4)",
            "agent:tx", "TxBot", "pktx", "2025-01-01T00:00:00Z",
        )
    a = await db.get_agent("agent:tx")
    assert a is not None
