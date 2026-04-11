"""Tests for POST /api/v1/evidence endpoint (DAN-105)."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nacl.signing import SigningKey

from fastapi.testclient import TestClient
from fastapi import FastAPI

from isnad.api_v1 import router, configure, _verify_ed25519_signature


# ─── Signature verification unit tests ─────────────────────────────

class TestEd25519Verification:
    """Unit tests for Ed25519 signature verification."""

    def setup_method(self):
        self.signing_key = SigningKey.generate()
        self.public_key_hex = self.signing_key.verify_key.encode().hex()

    def _sign(self, payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signed = self.signing_key.sign(canonical.encode("utf-8"))
        return signed.signature.hex()

    def test_valid_signature(self):
        payload = {"finding": "XSS", "severity": "high", "line": 42}
        sig = self._sign(payload)
        valid, err = _verify_ed25519_signature(payload, sig, self.public_key_hex)
        assert valid is True
        assert err == ""

    def test_invalid_signature_tampered_payload(self):
        payload = {"finding": "XSS", "severity": "high"}
        sig = self._sign(payload)
        tampered = {"finding": "XSS", "severity": "low"}
        valid, err = _verify_ed25519_signature(tampered, sig, self.public_key_hex)
        assert valid is False
        assert "Invalid signature" in err

    def test_invalid_signature_wrong_key(self):
        payload = {"test": True}
        sig = self._sign(payload)
        other_key = SigningKey.generate().verify_key.encode().hex()
        valid, err = _verify_ed25519_signature(payload, sig, other_key)
        assert valid is False

    def test_invalid_hex_key(self):
        valid, err = _verify_ed25519_signature({}, "aabb", "not_hex!")
        assert valid is False
        assert "Invalid key or signature" in err or "failed" in err

    def test_empty_payload(self):
        payload = {}
        sig = self._sign(payload)
        valid, err = _verify_ed25519_signature(payload, sig, self.public_key_hex)
        assert valid is True

    def test_nested_payload(self):
        payload = {"results": [{"id": 1, "sev": "high"}, {"id": 2, "sev": "low"}], "scan_id": "abc"}
        sig = self._sign(payload)
        valid, err = _verify_ed25519_signature(payload, sig, self.public_key_hex)
        assert valid is True


# ─── API endpoint integration tests ────────────────────────────────

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.get_agent = AsyncMock(return_value=None)
    db.get_agent_by_pubkey = AsyncMock(return_value=None)
    db.get_evidence_for_audit = AsyncMock(return_value=[])
    db.create_evidence = AsyncMock(return_value={"id": 1, "evidence_id": "test123"})
    db.create_behavioral_signal = AsyncMock(return_value={"id": 1})
    db.get_evidence_for_agent = AsyncMock(return_value=[])
    db.get_agent_by_api_key = AsyncMock(return_value=None)
    db.get_api_usage = AsyncMock(return_value=0)
    db.increment_api_usage = AsyncMock()
    return db


@pytest.fixture
def app(mock_db):
    from isnad import api_v1
    api_v1._db = mock_db
    test_app = FastAPI()
    test_app.include_router(router)

    # Disable rate limiting for tests
    from isnad.security import limiter
    from slowapi import _rate_limit_exceeded_handler
    test_app.state.limiter = limiter

    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def agent_keypair():
    sk = SigningKey.generate()
    pk_hex = sk.verify_key.encode().hex()
    return sk, pk_hex


def _sign_payload(signing_key: SigningKey, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signed = signing_key.sign(canonical.encode("utf-8"))
    return signed.signature.hex()


class TestEvidenceEndpoint:
    """Integration tests for POST /api/v1/evidence."""

    def test_submit_valid_evidence(self, client, mock_db, agent_keypair):
        sk, pk_hex = agent_keypair
        agent_id = "agent-hash-001"

        mock_db.get_agent.return_value = {
            "id": agent_id, "name": "Hash Agent",
            "public_key": pk_hex, "api_key_hash": "",
        }

        payload = {
            "scan_type": "skillfence",
            "findings": [{"id": "F1", "severity": "high", "description": "SQL injection"}],
            "score": 85,
        }
        signature = _sign_payload(sk, payload)

        resp = client.post("/api/v1/evidence", json={
            "agent_id": agent_id,
            "audit_id": "audit-2026-001",
            "evidence_type": "security_scan",
            "payload": payload,
            "signature": signature,
            "public_key": pk_hex,
        })

        assert resp.status_code == 201
        data = resp.json()
        assert data["verified"] is True
        assert data["agent_id"] == agent_id
        assert data["score_impact"] == 2.0
        assert "Evidence received and verified" in data["message"]

        # Verify DB was called
        mock_db.create_evidence.assert_called_once()
        mock_db.create_behavioral_signal.assert_called_once()

    def test_submit_invalid_signature(self, client, mock_db, agent_keypair):
        sk, pk_hex = agent_keypair
        agent_id = "agent-hash-002"

        mock_db.get_agent.return_value = {
            "id": agent_id, "name": "Hash Agent",
            "public_key": pk_hex, "api_key_hash": "",
        }

        payload = {"scan_type": "test", "score": 50}
        bad_sig = "aa" * 64  # Invalid signature

        resp = client.post("/api/v1/evidence", json={
            "agent_id": agent_id,
            "audit_id": "audit-bad-sig",
            "evidence_type": "security_scan",
            "payload": payload,
            "signature": bad_sig,
            "public_key": pk_hex,
        })

        assert resp.status_code == 201
        data = resp.json()
        assert data["verified"] is False
        assert data["score_impact"] == 0.0
        assert "invalid" in data["message"].lower()

    def test_unregistered_agent(self, client, mock_db, agent_keypair):
        sk, pk_hex = agent_keypair

        mock_db.get_agent.return_value = None
        mock_db.get_agent_by_pubkey.return_value = None

        payload = {"test": True}
        sig = _sign_payload(sk, payload)

        resp = client.post("/api/v1/evidence", json={
            "agent_id": "unknown-agent",
            "audit_id": "audit-999",
            "evidence_type": "security_scan",
            "payload": payload,
            "signature": sig,
            "public_key": pk_hex,
        })

        assert resp.status_code == 404
        assert "not registered" in resp.json()["detail"].lower()

    def test_wrong_public_key(self, client, mock_db, agent_keypair):
        sk, pk_hex = agent_keypair
        other_pk = SigningKey.generate().verify_key.encode().hex()

        mock_db.get_agent.return_value = {
            "id": "agent-001", "name": "Agent",
            "public_key": other_pk,  # Different key
        }

        payload = {"test": True}
        sig = _sign_payload(sk, payload)

        resp = client.post("/api/v1/evidence", json={
            "agent_id": "agent-001",
            "audit_id": "audit-pk-mismatch",
            "evidence_type": "security_scan",
            "payload": payload,
            "signature": sig,
            "public_key": pk_hex,
        })

        assert resp.status_code == 403
        assert "does not match" in resp.json()["detail"]

    def test_duplicate_audit_id(self, client, mock_db, agent_keypair):
        sk, pk_hex = agent_keypair
        agent_id = "agent-dup"

        mock_db.get_agent.return_value = {
            "id": agent_id, "public_key": pk_hex,
        }
        mock_db.get_evidence_for_audit.return_value = [
            {"agent_id": agent_id, "audit_id": "audit-dup"}
        ]

        payload = {"test": True}
        sig = _sign_payload(sk, payload)

        resp = client.post("/api/v1/evidence", json={
            "agent_id": agent_id,
            "audit_id": "audit-dup",
            "evidence_type": "security_scan",
            "payload": payload,
            "signature": sig,
            "public_key": pk_hex,
        })

        assert resp.status_code == 409
        assert "already submitted" in resp.json()["detail"]

    def test_invalid_evidence_type(self, client, mock_db, agent_keypair):
        sk, pk_hex = agent_keypair

        resp = client.post("/api/v1/evidence", json={
            "agent_id": "agent-001",
            "audit_id": "audit-001",
            "evidence_type": "hacking",
            "payload": {"test": True},
            "signature": "aa" * 64,
            "public_key": pk_hex,
        })

        assert resp.status_code == 400
        assert "Invalid evidence_type" in resp.json()["detail"]

    def test_code_review_evidence_type(self, client, mock_db, agent_keypair):
        sk, pk_hex = agent_keypair
        agent_id = "agent-cr"

        mock_db.get_agent.return_value = {
            "id": agent_id, "public_key": pk_hex,
        }

        payload = {"review": "LGTM", "files_reviewed": 5}
        sig = _sign_payload(sk, payload)

        resp = client.post("/api/v1/evidence", json={
            "agent_id": agent_id,
            "audit_id": "audit-cr-001",
            "evidence_type": "code_review",
            "payload": payload,
            "signature": sig,
            "public_key": pk_hex,
        })

        assert resp.status_code == 201
        assert resp.json()["score_impact"] == 1.5
