"""Tests for ACN Bridge — credit ↔ trust score mapping."""

import pytest
from src.isnad.acn_bridge import ACNBridge, MappingCurve, ChainlinkAdapter, acn_map_handler


class TestCreditToTrust:
    def test_midrange_credit(self):
        bridge = ACNBridge()
        result = bridge.credit_to_trust(575)  # midpoint of 300-850
        assert 0.49 <= result.score <= 0.51
        assert result.confidence == 0.95

    def test_min_credit(self):
        bridge = ACNBridge()
        result = bridge.credit_to_trust(300)
        assert result.score == 0.0

    def test_max_credit(self):
        bridge = ACNBridge()
        result = bridge.credit_to_trust(850)
        assert result.score == 1.0

    def test_below_min_clamped(self):
        bridge = ACNBridge()
        result = bridge.credit_to_trust(100)
        assert result.score == 0.0
        assert result.confidence == 0.5  # out of range

    def test_above_max_clamped(self):
        bridge = ACNBridge()
        result = bridge.credit_to_trust(900)
        assert result.score == 1.0
        assert result.confidence == 0.5

    def test_custom_curve(self):
        curve = MappingCurve(exponent=2.0)
        bridge = ACNBridge(curve=curve)
        result = bridge.credit_to_trust(575)
        # With exponent 2, midpoint 0.5^2 = 0.25
        assert 0.24 <= result.score <= 0.26


class TestTrustToCredit:
    def test_roundtrip(self):
        bridge = ACNBridge()
        for credit in [300, 450, 575, 720, 850]:
            trust = bridge.credit_to_trust(credit)
            back = bridge.trust_to_credit(trust.score)
            assert abs(back - credit) < 1.0

    def test_zero_trust(self):
        bridge = ACNBridge()
        assert bridge.trust_to_credit(0.0) == 300.0

    def test_full_trust(self):
        bridge = ACNBridge()
        assert bridge.trust_to_credit(1.0) == 850.0


class TestAttestation:
    def test_create_and_verify(self):
        bridge = ACNBridge()
        att = bridge.create_attestation("agent:test", 720, 0.76)
        assert att["subject"] == "agent:test"
        assert att["credit_score"] == 720
        assert att["trust_score"] == 0.76
        assert bridge.verify_attestation(att)

    def test_tampered_attestation_fails(self):
        bridge = ACNBridge()
        att = bridge.create_attestation("agent:test", 720, 0.76)
        att["credit_score"] = 800  # tamper
        assert not bridge.verify_attestation(att)

    def test_missing_hash_fails(self):
        bridge = ACNBridge()
        att = bridge.create_attestation("agent:test", 720, 0.76)
        del att["integrity_hash"]
        assert not bridge.verify_attestation(att)


class TestChainlinkAdapter:
    def test_push_and_read(self):
        adapter = ChainlinkAdapter()
        tx = adapter.push_score("agent:abc", 0.76)
        assert tx.startswith("0x")
        assert adapter.read_score("agent:abc") == 0.76

    def test_read_missing(self):
        adapter = ChainlinkAdapter()
        assert adapter.read_score("nonexistent") == 0.0


class TestAPIHandler:
    def test_credit_to_trust_handler(self):
        result = acn_map_handler({"agent_id": "test", "credit_score": 720})
        assert result["direction"] == "credit_to_trust"
        assert "trust_score" in result
        assert "attestation" in result

    def test_trust_to_credit_handler(self):
        result = acn_map_handler({"agent_id": "test", "trust_score": 0.76})
        assert result["direction"] == "trust_to_credit"
        assert "credit_score" in result

    def test_missing_scores_error(self):
        result = acn_map_handler({"agent_id": "test"})
        assert "error" in result
