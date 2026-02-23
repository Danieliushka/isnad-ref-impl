"""Tests for isnad.database — async SQLite persistence layer."""

import asyncio
import os
import tempfile
import pytest
import pytest_asyncio

from isnad.database import Database
from isnad.core import AgentIdentity, Attestation, TrustChain, RevocationRegistry


@pytest_asyncio.fixture
async def db(tmp_path):
    """Fresh in-memory database for each test."""
    database = Database(str(tmp_path / "test.db"))
    await database.connect()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_schema_version(db):
    row = await (await db._db.execute("SELECT MAX(version) FROM schema_version")).fetchone()
    assert row[0] == 1


# ─── Agents ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_get_agent(db):
    agent = await db.create_agent("agent:abc123", "deadbeef01", name="Alice")
    assert agent["id"] == "agent:abc123"

    fetched = await db.get_agent("agent:abc123")
    assert fetched["name"] == "Alice"
    assert fetched["public_key"] == "deadbeef01"


@pytest.mark.asyncio
async def test_get_agent_by_pubkey(db):
    await db.create_agent("agent:x", "pubkey_unique_1", name="Bob")
    fetched = await db.get_agent_by_pubkey("pubkey_unique_1")
    assert fetched["id"] == "agent:x"


@pytest.mark.asyncio
async def test_update_agent(db):
    await db.create_agent("agent:u1", "pk1")
    ok = await db.update_agent("agent:u1", trust_score=0.85, is_certified=1)
    assert ok
    fetched = await db.get_agent("agent:u1")
    assert fetched["trust_score"] == 0.85
    assert fetched["is_certified"] == 1


@pytest.mark.asyncio
async def test_delete_agent_cascades(db):
    await db.create_agent("agent:del", "pk_del")
    await db.create_attestation("att1", "agent:del", "agent:del", "task")
    await db.create_trust_check("agent:del", 0.5, {"ok": True})

    deleted = await db.delete_agent("agent:del")
    assert deleted

    assert await db.get_agent("agent:del") is None
    assert await db.get_attestation("att1") is None


@pytest.mark.asyncio
async def test_list_agents(db):
    for i in range(5):
        await db.create_agent(f"agent:{i}", f"pk_{i}")
    agents = await db.list_agents(limit=3)
    assert len(agents) == 3


# ─── Attestations ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_get_attestation(db):
    att = await db.create_attestation("att_x", "subj", "wit", "code-review",
                                       evidence_uri="https://example.com")
    assert att["id"] == "att_x"
    fetched = await db.get_attestation("att_x")
    assert fetched["task"] == "code-review"
    assert fetched["evidence_uri"] == "https://example.com"


@pytest.mark.asyncio
async def test_attestations_for_subject(db):
    await db.create_attestation("a1", "subj1", "w1", "task1")
    await db.create_attestation("a2", "subj1", "w2", "task2")
    await db.create_attestation("a3", "subj2", "w1", "task3")

    results = await db.get_attestations_for_subject("subj1")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_revoke_attestation(db):
    await db.create_attestation("rev1", "s", "w", "t")
    ok = await db.revoke_attestation("rev1")
    assert ok
    # Revoked attestation excluded from subject query
    results = await db.get_attestations_for_subject("s")
    assert len(results) == 0
    # But still fetchable directly
    att = await db.get_attestation("rev1")
    assert att["is_revoked"] == 1


@pytest.mark.asyncio
async def test_count_attestations(db):
    for i in range(4):
        await db.create_attestation(f"c{i}", "s", "w", "t")
    assert await db.count_attestations() == 4


# ─── Certifications ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_get_certification(db):
    cats = {"security": 0.9, "reliability": 0.8}
    cert = await db.create_certification("cert1", "agent:a", 0.85, cats,
                                          "2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z",
                                          badge_hash="abc")
    assert cert["score"] == 0.85

    fetched = await db.get_certification("cert1")
    assert fetched["category_scores"] == cats
    assert fetched["badge_hash"] == "abc"


@pytest.mark.asyncio
async def test_certifications_for_agent(db):
    await db.create_certification("c1", "agent:b", 0.7, {}, "2025-01-01", "2025-02-01")
    await db.create_certification("c2", "agent:b", 0.8, {}, "2025-02-01", "2025-03-01")
    results = await db.get_certifications_for_agent("agent:b")
    assert len(results) == 2


# ─── API Keys ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_key_lifecycle(db):
    key_data = await db.create_api_key("sk-test-12345", "user@example.com", rate_limit=50)
    assert key_data["rate_limit"] == 50

    valid = await db.validate_api_key("sk-test-12345")
    assert valid is not None
    assert valid["owner_email"] == "user@example.com"

    # Deactivate
    ok = await db.deactivate_api_key(key_data["key_hash"])
    assert ok

    # Now invalid
    assert await db.validate_api_key("sk-test-12345") is None


@pytest.mark.asyncio
async def test_invalid_api_key(db):
    assert await db.validate_api_key("nonexistent") is None


# ─── Trust Checks ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trust_check(db):
    report = {"modules_passed": 30, "total": 36}
    check = await db.create_trust_check("agent:tc", 0.83, report, "127.0.0.1")
    assert check["score"] == 0.83

    checks = await db.get_trust_checks("agent:tc")
    assert len(checks) == 1
    assert checks[0]["report"]["modules_passed"] == 30


# ─── Migration ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_migrate_from_memory(db):
    # Set up in-memory state like api.py
    alice = AgentIdentity()
    bob = AgentIdentity()
    identities = {alice.agent_id: alice, bob.agent_id: bob}

    rev_registry = RevocationRegistry()
    chain = TrustChain(revocation_registry=rev_registry)

    att = Attestation(
        subject=bob.agent_id, witness=alice.agent_id,
        task="code-review", evidence="https://example.com",
    ).sign(alice)
    chain.add(att)

    result = await db.migrate_from_memory(identities, chain, rev_registry)
    assert result["agents"] == 2
    assert result["attestations"] == 1

    # Verify data in DB
    agent = await db.get_agent(alice.agent_id)
    assert agent is not None
    assert agent["public_key"] == alice.public_key_hex

    db_att = await db.get_attestation(att.attestation_id)
    assert db_att is not None
    assert db_att["task"] == "code-review"
