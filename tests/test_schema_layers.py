"""Tests for L0-L3 intent-commit schema."""

import time
import pytest
from isnad.schema import (
    Intent, IntentStatus,
    Endorsement, EndorsementType,
    TrackRecord, TrackEntry,
    ProvenanceChain, ProvenanceNode,
)
from isnad.core import AgentIdentity


# ── L0 Intent ──────────────────────────────────────────────────

class TestIntent:
    def test_create_intent(self):
        i = Intent(agent_id="agent:abc123", action="deploy contract")
        assert i.intent_id.startswith("intent:")
        assert i.status == IntentStatus.DECLARED
        assert not i.is_expired()

    def test_deterministic_id(self):
        i = Intent(agent_id="agent:abc", action="do X", nonce="fixed")
        i2 = Intent(agent_id="agent:abc", action="do X", nonce="fixed")
        assert i.intent_id == i2.intent_id

    def test_sign_and_verify(self):
        alice = AgentIdentity()
        i = Intent(agent_id=alice.agent_id, action="test action")
        i.sign(alice)
        assert i.signature is not None
        assert i.verify(alice.verify_key)

    def test_verify_fails_with_wrong_key(self):
        alice = AgentIdentity()
        bob = AgentIdentity()
        i = Intent(agent_id=alice.agent_id, action="test").sign(alice)
        assert not i.verify(bob.verify_key)

    def test_commit(self):
        i = Intent(agent_id="agent:x", action="build")
        i.commit(evidence_hash="abc123")
        assert i.status == IntentStatus.COMMITTED
        assert i.metadata["evidence_hash"] == "abc123"

    def test_revoke(self):
        i = Intent(agent_id="agent:x", action="build")
        i.revoke("changed plans")
        assert i.status == IntentStatus.REVOKED

    def test_expired(self):
        i = Intent(agent_id="agent:x", action="old", deadline=int(time.time()) - 10)
        assert i.is_expired()


# ── L1 Endorsement ────────────────────────────────────────────

class TestEndorsement:
    def test_create_endorsement(self):
        e = Endorsement(intent_id="intent:abc", endorser_id="agent:bob")
        assert e.endorsement_id.startswith("endorse:")
        assert e.endorsement_type == EndorsementType.POST

    def test_sign_and_verify(self):
        bob = AgentIdentity()
        e = Endorsement(
            intent_id="intent:abc",
            endorser_id=bob.agent_id,
            endorsement_type=EndorsementType.PRE,
            confidence=0.9,
        )
        e.sign(bob)
        assert e.verify(bob.verify_key)

    def test_rejection(self):
        e = Endorsement(
            intent_id="intent:abc",
            endorser_id="agent:carol",
            endorsement_type=EndorsementType.REJECTION,
            comment="Evidence was fabricated",
        )
        assert e.endorsement_type == EndorsementType.REJECTION


# ── L2 Track Record ───────────────────────────────────────────

class TestTrackRecord:
    def test_empty_record(self):
        tr = TrackRecord(agent_id="agent:x")
        assert tr.total == 0
        assert tr.commitment_rate == 0.0

    def test_add_entries(self):
        tr = TrackRecord(agent_id="agent:x")
        tr.add_entry(TrackEntry(
            intent_id="intent:1", action_type="code", status="committed",
            endorsement_count=3, on_time=True
        ))
        tr.add_entry(TrackEntry(
            intent_id="intent:2", action_type="code", status="expired",
            on_time=False
        ))
        assert tr.total == 2
        assert tr.committed == 1
        assert tr.expired == 1
        assert tr.commitment_rate == 0.5
        assert tr.on_time_rate == 1.0  # only committed entries count

    def test_endorsement_ratio(self):
        tr = TrackRecord(agent_id="agent:x")
        tr.add_entry(TrackEntry(
            intent_id="i1", action_type="t", status="committed",
            endorsement_count=5, rejection_count=1
        ))
        assert tr.endorsement_ratio == 4.0

    def test_summary(self):
        tr = TrackRecord(agent_id="agent:x")
        s = tr.summary()
        assert s["agent_id"] == "agent:x"
        assert "commitment_rate" in s


# ── L3 Provenance ─────────────────────────────────────────────

class TestProvenance:
    def test_chain_from_intent(self):
        i = Intent(agent_id="agent:alice", action="deploy")
        chain = ProvenanceChain.from_intent(i)
        assert chain.chain_id == i.intent_id
        assert len(chain.nodes) == 1
        assert chain.nodes[0].node_type == "intent"
        assert chain.verify_integrity()

    def test_full_lifecycle(self):
        alice = AgentIdentity()
        bob = AgentIdentity()

        # L0: Intent
        intent = Intent(agent_id=alice.agent_id, action="audit contract")
        intent.sign(alice)

        # L3: Start chain
        chain = ProvenanceChain.from_intent(intent)

        # L1: Pre-endorsement
        pre = Endorsement(
            intent_id=intent.intent_id,
            endorser_id=bob.agent_id,
            endorsement_type=EndorsementType.PRE,
        ).sign(bob)
        chain.add_endorsement(pre)

        # L0: Commit
        intent.commit(evidence_hash="deadbeef")
        chain.add_commit(intent, evidence_hash="deadbeef")

        # L1: Post-endorsement
        post = Endorsement(
            intent_id=intent.intent_id,
            endorser_id=bob.agent_id,
            endorsement_type=EndorsementType.POST,
            confidence=0.95,
        ).sign(bob)
        chain.add_endorsement(post)

        assert len(chain.nodes) == 4
        assert chain.verify_integrity()
        assert chain.root_hash != ""

        s = chain.summary()
        assert s["integrity"] is True
        assert s["node_count"] == 4

    def test_tamper_detection(self):
        i = Intent(agent_id="agent:x", action="test")
        chain = ProvenanceChain.from_intent(i)
        assert chain.verify_integrity()

        # Tamper with a node
        chain.nodes[0].payload_hash = "tampered"
        assert not chain.verify_integrity()
