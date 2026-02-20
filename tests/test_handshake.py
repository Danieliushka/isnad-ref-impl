"""Tests for isnad.handshake — Multi-Agent Trust Handshake Protocol."""

import time
import pytest
from isnad.core import AgentIdentity
from isnad.handshake import (
    HandshakeManager,
    HandshakeRequest,
    HandshakeResponse,
    HandshakeSession,
    HandshakeStatus,
    TrustPolicy,
)


@pytest.fixture
def alice():
    return AgentIdentity()


@pytest.fixture
def bob():
    return AgentIdentity()


@pytest.fixture
def alice_mgr(alice):
    return HandshakeManager(alice)


@pytest.fixture
def bob_mgr(bob):
    return HandshakeManager(bob)


class TestHandshakeRequest:
    def test_create_request(self, alice_mgr, alice, bob):
        req = alice_mgr.create_request(bob.agent_id, ["read", "write"])
        assert req.initiator_id == alice.agent_id
        assert req.responder_id == bob.agent_id
        assert req.capabilities_needed == ["read", "write"]
        assert req.signature != ""
        assert len(req.request_id) == 16

    def test_request_signed(self, alice_mgr, bob):
        req = alice_mgr.create_request(bob.agent_id, ["read"])
        assert req.signature
        assert len(req.signature) == 128  # ed25519 sig hex

    def test_request_to_dict(self, alice_mgr, alice, bob):
        req = alice_mgr.create_request(bob.agent_id, ["read"])
        d = req.to_dict()
        assert d["initiator_id"] == alice.agent_id
        assert d["responder_id"] == bob.agent_id


class TestHandshakeResponse:
    def test_accept_request(self, alice_mgr, bob_mgr, bob):
        req = alice_mgr.create_request(bob.agent_id, ["read"])
        resp = bob_mgr.receive_request(req, trust_score=0.8)
        assert resp.status == HandshakeStatus.ACCEPTED
        assert resp.granted_capabilities == ["read"]
        assert resp.trust_score == 0.8

    def test_reject_low_trust(self, alice_mgr, bob_mgr, bob):
        bob_mgr.policy = TrustPolicy(min_trust=0.5)
        req = alice_mgr.create_request(bob.agent_id, ["read"])
        resp = bob_mgr.receive_request(req, trust_score=0.2)
        assert resp.status == HandshakeStatus.REJECTED

    def test_reject_unknown_agent(self, alice_mgr, bob_mgr, bob):
        bob_mgr.policy = TrustPolicy(require_known_agent=True)
        req = alice_mgr.create_request(bob.agent_id, ["read"])
        resp = bob_mgr.receive_request(req, trust_score=0.9, is_known=False)
        assert resp.status == HandshakeStatus.REJECTED

    def test_wrong_responder(self, alice_mgr, bob_mgr):
        req = alice_mgr.create_request("agent:charlie", ["read"])
        resp = bob_mgr.receive_request(req, trust_score=0.9)
        assert resp.status == HandshakeStatus.REJECTED
        assert resp.metadata["reason"] == "wrong responder"

    def test_invalid_signature(self, bob_mgr, bob):
        req = HandshakeRequest(
            request_id="fake",
            initiator_id="alice",
            initiator_pubkey="00" * 32,
            responder_id=bob.agent_id,
            capabilities_needed=["read"],
            timestamp=time.time(),
            signature="00" * 64,
        )
        resp = bob_mgr.receive_request(req)
        assert resp.status == HandshakeStatus.REJECTED

    def test_capability_filtering(self, alice_mgr, bob_mgr, bob):
        bob_mgr.policy = TrustPolicy(allowed_capabilities=["read", "list"])
        req = alice_mgr.create_request(bob.agent_id, ["read", "write", "delete"])
        resp = bob_mgr.receive_request(req, trust_score=0.8)
        assert resp.status == HandshakeStatus.ACCEPTED
        assert sorted(resp.granted_capabilities) == ["read"]

    def test_duration_capped(self, alice_mgr, bob_mgr, bob):
        bob_mgr.policy = TrustPolicy(max_duration_s=1800)
        req = alice_mgr.create_request(bob.agent_id, ["read"], duration_s=7200)
        resp = bob_mgr.receive_request(req, trust_score=0.5)
        assert resp.session_duration_s == 1800


class TestHandshakeSession:
    def test_full_handshake(self, alice_mgr, alice, bob_mgr, bob):
        req = alice_mgr.create_request(bob.agent_id, ["read", "write"])
        resp = bob_mgr.receive_request(req, trust_score=0.85)
        session = alice_mgr.complete_handshake(req, resp)
        assert session is not None
        assert session.initiator_id == alice.agent_id
        assert session.responder_id == bob.agent_id
        assert session.capabilities == ["read", "write"]
        assert not session.is_expired

    def test_session_on_both_sides(self, alice_mgr, bob_mgr, bob):
        req = alice_mgr.create_request(bob.agent_id, ["read"])
        resp = bob_mgr.receive_request(req, trust_score=0.9)
        alice_session = alice_mgr.complete_handshake(req, resp)
        bob_session = bob_mgr.get_session(req.request_id)
        assert alice_session is not None
        assert bob_session is not None
        assert alice_session.session_id == bob_session.session_id

    def test_rejected_no_session(self, alice_mgr, bob_mgr, bob):
        bob_mgr.policy = TrustPolicy(min_trust=0.99)
        req = alice_mgr.create_request(bob.agent_id, ["read"])
        resp = bob_mgr.receive_request(req, trust_score=0.1)
        session = alice_mgr.complete_handshake(req, resp)
        assert session is None

    def test_session_expiry(self, alice_mgr, bob_mgr, bob):
        req = alice_mgr.create_request(bob.agent_id, ["read"], duration_s=0.001)
        resp = bob_mgr.receive_request(req, trust_score=0.8)
        session = alice_mgr.complete_handshake(req, resp)
        assert session is not None
        time.sleep(0.01)
        assert session.is_expired
        assert session.remaining_s == 0

    def test_active_sessions(self, alice_mgr, bob_mgr, bob):
        for i in range(3):
            req = alice_mgr.create_request(bob.agent_id, [f"cap{i}"])
            resp = bob_mgr.receive_request(req, trust_score=0.7)
            alice_mgr.complete_handshake(req, resp)
        assert len(alice_mgr.active_sessions()) == 3

    def test_revoke_session(self, alice_mgr, bob_mgr, bob):
        req = alice_mgr.create_request(bob.agent_id, ["read"])
        resp = bob_mgr.receive_request(req, trust_score=0.8)
        session = alice_mgr.complete_handshake(req, resp)
        assert alice_mgr.revoke_session(session.session_id)
        assert alice_mgr.get_session(session.session_id) is None

    def test_revoke_nonexistent(self, alice_mgr):
        assert not alice_mgr.revoke_session("nonexistent")

    def test_session_to_dict(self, alice_mgr, alice, bob_mgr, bob):
        req = alice_mgr.create_request(bob.agent_id, ["read"])
        resp = bob_mgr.receive_request(req, trust_score=0.7)
        session = alice_mgr.complete_handshake(req, resp)
        d = session.to_dict()
        assert d["initiator_id"] == alice.agent_id
        assert d["responder_id"] == bob.agent_id


class TestTrustPolicy:
    def test_default_accepts_all(self):
        policy = TrustPolicy()
        req = HandshakeRequest(
            request_id="test",
            initiator_id="a",
            initiator_pubkey="",
            responder_id="b",
            capabilities_needed=["x"],
            proposed_duration_s=3600,
            timestamp=time.time(),
        )
        status, caps, reason = policy.evaluate(req, trust_score=0.0, is_known=True)
        assert status == HandshakeStatus.ACCEPTED

    def test_min_trust_threshold(self):
        policy = TrustPolicy(min_trust=0.5)
        req = HandshakeRequest(
            request_id="t", initiator_id="a", initiator_pubkey="",
            responder_id="b", capabilities_needed=["x"],
            proposed_duration_s=3600, timestamp=time.time(),
        )
        status, _, reason = policy.evaluate(req, 0.3, True)
        assert status == HandshakeStatus.REJECTED
        assert "below minimum" in reason

    def test_require_known(self):
        policy = TrustPolicy(require_known_agent=True)
        req = HandshakeRequest(
            request_id="t", initiator_id="a", initiator_pubkey="",
            responder_id="b", capabilities_needed=["x"],
            proposed_duration_s=3600, timestamp=time.time(),
        )
        status, _, reason = policy.evaluate(req, 0.9, is_known=False)
        assert status == HandshakeStatus.REJECTED
        assert "unknown" in reason
