"""Tests for /verify endpoint — ACN credit tier mapping."""

import pytest
from fastapi.testclient import TestClient
from src.isnad.api_v1 import create_app, router, _trust_chain, VerifyResponse


@pytest.fixture
def client():
    app = create_app(use_lifespan=False)
    return TestClient(app)


class TestVerifyEndpoint:
    def test_verify_returns_200(self, client):
        resp = client.get("/api/v1/verify/test-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "test-agent"
        assert "trust_score" in data
        assert "credit_tier" in data
        assert "breakdown" in data
        assert "verified_at" in data
        assert "certification_id" in data
        assert data["protocol_version"] == "0.3.0"

    def test_verify_credit_tier_structure(self, client):
        resp = client.get("/api/v1/verify/test-agent")
        tier = resp.json()["credit_tier"]
        assert "score" in tier
        assert "tier" in tier
        assert "description" in tier
        assert tier["tier"] in ("A", "B", "C", "D", "F")

    def test_verify_breakdown_structure(self, client):
        resp = client.get("/api/v1/verify/test-agent")
        bd = resp.json()["breakdown"]
        assert "attestation_count" in bd
        assert "witness_diversity" in bd
        assert "recency_score" in bd
        assert "categories" in bd
        assert isinstance(bd["categories"], list)

    def test_verify_trust_score_range(self, client):
        resp = client.get("/api/v1/verify/test-agent")
        ts = resp.json()["trust_score"]
        assert 0.0 <= ts <= 1.0

    def test_verify_credit_score_range(self, client):
        resp = client.get("/api/v1/verify/test-agent")
        cs = resp.json()["credit_tier"]["score"]
        assert 300.0 <= cs <= 850.0

    def test_verify_confidence_values(self, client):
        resp = client.get("/api/v1/verify/test-agent")
        assert resp.json()["confidence"] in ("high", "medium", "low")

    def test_verify_different_agents_get_unique_cert_ids(self, client):
        r1 = client.get("/api/v1/verify/agent-a")
        r2 = client.get("/api/v1/verify/agent-b")
        assert r1.json()["certification_id"] != r2.json()["certification_id"]


class TestCreditTierMapping:
    """Test that credit tiers map correctly based on ACNBridge output."""

    def test_tier_labels(self):
        """Verify tier boundaries match spec: A(750+), B(700-749), C(650-699), D(600-649), F(<600)."""
        from src.isnad.acn_bridge import ACNBridge
        bridge = ACNBridge()

        # A tier: trust=1.0 → credit=850
        assert bridge.trust_to_credit(1.0) >= 750

        # F tier: trust=0.0 → credit=300
        assert bridge.trust_to_credit(0.0) < 600

        # B tier: ~0.73 → ~700
        credit_mid_b = bridge.trust_to_credit(0.73)
        assert 700 <= credit_mid_b < 750
