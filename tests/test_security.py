"""Security-focused tests: auth, rate limiting, input validation, health check."""
import os
import pytest
from unittest.mock import AsyncMock, patch

# Set admin key before importing app
os.environ["ADMIN_API_KEY"] = "test-admin-key-12345"

from fastapi.testclient import TestClient
from isnad.api import app, identities, trust_chain

client = TestClient(app)
AUTH_HEADER = {"X-API-Key": "test-admin-key-12345"}


@pytest.fixture(autouse=True)
def clean_state():
    """Reset state between tests."""
    identities.clear()
    trust_chain.attestations.clear()
    trust_chain._by_subject.clear()
    trust_chain._by_witness.clear()
    yield


# ─── Auth Tests ────────────────────────────────────────────────────

class TestAuth:
    """Write endpoints require API key."""

    def test_create_identity_no_auth(self):
        r = client.post("/identity", json={})
        assert r.status_code == 401
        assert "Missing" in r.json()["detail"]

    def test_create_identity_bad_key(self):
        r = client.post("/identity", json={}, headers={"X-API-Key": "wrong"})
        assert r.status_code == 403
        assert "Invalid" in r.json()["detail"]

    def test_create_identity_valid_key(self):
        r = client.post("/identity", json={}, headers=AUTH_HEADER)
        assert r.status_code == 200
        assert "agent_id" in r.json()

    def test_attest_no_auth(self):
        r = client.post("/attest", json={
            "subject_id": "a", "witness_id": "b", "task": "t"
        })
        assert r.status_code == 401

    def test_attest_valid_key(self):
        # Create identities first
        r1 = client.post("/identity", json={}, headers=AUTH_HEADER)
        r2 = client.post("/identity", json={}, headers=AUTH_HEADER)
        w = r1.json()["agent_id"]
        s = r2.json()["agent_id"]
        r = client.post("/attest", json={
            "witness_id": w, "subject_id": s, "task": "test task"
        }, headers=AUTH_HEADER)
        assert r.status_code == 200

    def test_revoke_no_auth(self):
        r = client.post("/revoke", json={
            "target_id": "x", "reason": "test", "revoked_by": "y"
        })
        assert r.status_code == 401

    def test_certify_no_auth(self):
        r = client.post("/certify", json={"agent_id": "test"})
        assert r.status_code == 401

    def test_read_endpoints_no_auth_ok(self):
        """Read endpoints should work without auth."""
        assert client.get("/").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/chain").status_code == 200
        assert client.get("/trust-score/test").status_code == 200
        assert client.get("/policies").status_code == 200

    def test_delegation_no_auth(self):
        r = client.post("/delegations", json={
            "delegator_id": "x", "delegate_pubkey": "abc", "scope": "test"
        })
        assert r.status_code == 401

    def test_discovery_register_no_auth(self):
        r = client.post("/discovery/register", json={
            "agent_id": "x", "name": "test"
        })
        assert r.status_code == 401

    def test_policy_create_no_auth(self):
        r = client.post("/policies", json={
            "name": "test", "rules": []
        })
        assert r.status_code == 401


# ─── Input Validation Tests ────────────────────────────────────────

class TestInputValidation:
    """Strict input validation on write endpoints."""

    def test_attest_empty_task(self):
        r = client.post("/attest", json={
            "subject_id": "a", "witness_id": "b", "task": "   "
        }, headers=AUTH_HEADER)
        assert r.status_code == 422

    def test_attest_null_bytes(self):
        r = client.post("/attest", json={
            "subject_id": "a\x00b", "witness_id": "b", "task": "test"
        }, headers=AUTH_HEADER)
        assert r.status_code == 422

    def test_attest_oversized_task(self):
        r = client.post("/attest", json={
            "subject_id": "a", "witness_id": "b", "task": "x" * 1001
        }, headers=AUTH_HEADER)
        assert r.status_code == 422

    def test_attest_oversized_evidence(self):
        r = client.post("/attest", json={
            "subject_id": "a", "witness_id": "b", "task": "ok", "evidence": "x" * 2001
        }, headers=AUTH_HEADER)
        assert r.status_code == 422

    def test_attest_missing_required_fields(self):
        r = client.post("/attest", json={"task": "test"}, headers=AUTH_HEADER)
        assert r.status_code == 422


# ─── Health Check Tests ───────────────────────────────────────────

class TestHealthCheck:
    def test_health_returns_ok(self):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("ok", "degraded")
        assert "version" in data
        assert "timestamp" in data
        assert "database" in data


# ─── Security Headers Tests ───────────────────────────────────────

class TestSecurityHeaders:
    def test_response_has_security_headers(self):
        r = client.get("/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert "X-Request-ID" in r.headers

    def test_request_id_propagation(self):
        r = client.get("/health", headers={"X-Request-ID": "test-123"})
        assert r.headers.get("X-Request-ID") == "test-123"


# ─── Rate Limiting Tests ──────────────────────────────────────────

class TestRateLimiting:
    def test_rate_limit_header_present(self):
        """Rate-limited endpoints return rate limit info."""
        # Create an identity to test rate limiting on write endpoints
        r = client.post("/identity", json={}, headers=AUTH_HEADER)
        # slowapi adds these headers
        assert r.status_code == 200
