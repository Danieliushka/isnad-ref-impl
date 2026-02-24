#!/usr/bin/env python3
"""Tests for ACN Bridge — credit ↔ trust score mapping."""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from isnad.acn_bridge import (
    ACNBridge, TrustScore, MappingCurve, ChainlinkAdapter, acn_map_handler,
)


@pytest.fixture
def bridge():
    return ACNBridge()


@pytest.fixture
def convex_bridge():
    return ACNBridge(curve=MappingCurve(exponent=2.0))


# ─── credit_to_trust ──────────────────────────────────────────────

class TestCreditToTrust:
    def test_linear_min(self, bridge):
        t = bridge.credit_to_trust(300)
        assert t.score == 0.0

    def test_linear_max(self, bridge):
        t = bridge.credit_to_trust(850)
        assert t.score == 1.0

    def test_linear_midpoint(self, bridge):
        t = bridge.credit_to_trust(575)  # exact midpoint
        assert abs(t.score - 0.5) < 0.001

    def test_clamps_below_min(self, bridge):
        t = bridge.credit_to_trust(100)
        assert t.score == 0.0
        assert t.confidence == 0.5  # out of range → low confidence

    def test_clamps_above_max(self, bridge):
        t = bridge.credit_to_trust(900)
        assert t.score == 1.0
        assert t.confidence == 0.5

    def test_convex_curve(self, convex_bridge):
        t = convex_bridge.credit_to_trust(575)
        assert t.score == 0.25  # (0.5)^2 = 0.25

    def test_in_range_confidence(self, bridge):
        t = bridge.credit_to_trust(700)
        assert t.confidence == 0.95


# ─── trust_to_credit ──────────────────────────────────────────────

class TestTrustToCredit:
    def test_roundtrip_linear(self, bridge):
        for credit in [300, 500, 650, 750, 850]:
            trust = bridge.credit_to_trust(credit)
            back = bridge.trust_to_credit(trust.score)
            assert abs(back - credit) < 0.1

    def test_roundtrip_convex(self, convex_bridge):
        for credit in [300, 575, 850]:
            trust = convex_bridge.credit_to_trust(credit)
            back = convex_bridge.trust_to_credit(trust.score)
            assert abs(back - credit) < 0.5

    def test_boundaries(self, bridge):
        assert bridge.trust_to_credit(0.0) == 300.0
        assert bridge.trust_to_credit(1.0) == 850.0


# ─── Attestation ──────────────────────────────────────────────────

class TestAttestation:
    def test_create_and_verify(self, bridge):
        att = bridge.create_attestation("agent:test", 700, 0.73)
        assert att["type"] == "acn_credit_trust_mapping"
        assert att["subject"] == "agent:test"
        assert bridge.verify_attestation(att)

    def test_tampered_attestation_fails(self, bridge):
        att = bridge.create_attestation("agent:test", 700, 0.73)
        att["credit_score"] = 800  # tamper
        assert not bridge.verify_attestation(att)

    def test_missing_hash_fails(self, bridge):
        att = bridge.create_attestation("agent:test", 700, 0.73)
        del att["integrity_hash"]
        assert not bridge.verify_attestation(att)


# ─── ChainlinkAdapter ────────────────────────────────────────────

class TestChainlinkAdapter:
    def test_push_and_read(self):
        adapter = ChainlinkAdapter()
        tx = adapter.push_score("agent:abc", 0.85)
        assert tx.startswith("0x")
        assert adapter.read_score("agent:abc") == 0.85

    def test_read_missing(self):
        adapter = ChainlinkAdapter()
        assert adapter.read_score("agent:unknown") == 0.0


# ─── API Handler ──────────────────────────────────────────────────

class TestAPIHandler:
    def test_credit_to_trust_request(self):
        resp = acn_map_handler({"agent_id": "agent:x", "credit_score": 700})
        assert resp["direction"] == "credit_to_trust"
        assert "attestation" in resp

    def test_trust_to_credit_request(self):
        resp = acn_map_handler({"agent_id": "agent:x", "trust_score": 0.5})
        assert resp["direction"] == "trust_to_credit"
        assert resp["credit_score"] == 575.0

    def test_missing_both_returns_error(self):
        resp = acn_map_handler({"agent_id": "agent:x"})
        assert "error" in resp
