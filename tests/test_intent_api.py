"""Tests for intent-commit API endpoints."""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.intent.api import router, _commitments, _cusum_states
from src.intent.models import compute_commitment_hash, generate_nonce

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_stores():
    """Clear in-memory stores between tests."""
    _commitments.clear()
    _cusum_states.clear()
    yield
    _commitments.clear()
    _cusum_states.clear()


class TestCommitEndpoint:
    def test_l0_commit(self):
        resp = client.post("/api/v1/intent/commit", json={
            "agent_id": "test-agent",
            "level": 0,
            "intent_plaintext": "review PR #42",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == 0
        assert data["status"] == "committed"

    def test_l1_commit(self):
        nonce = generate_nonce()
        ts = "2026-03-07T15:00:00Z"
        h = compute_commitment_hash("review PR", nonce, ts)
        resp = client.post("/api/v1/intent/commit", json={
            "agent_id": "test-agent",
            "level": 1,
            "commitment_hash": h,
        })
        assert resp.status_code == 200

    def test_l2_requires_scope_and_sig(self):
        resp = client.post("/api/v1/intent/commit", json={
            "agent_id": "test-agent",
            "level": 2,
            "commitment_hash": "abc",
        })
        assert resp.status_code == 422

    def test_l0_missing_plaintext(self):
        resp = client.post("/api/v1/intent/commit", json={
            "agent_id": "test-agent",
            "level": 0,
        })
        assert resp.status_code == 422


class TestRevealEndpoint:
    def test_l1_reveal_success(self):
        nonce = generate_nonce()
        ts = "2026-03-07T15:00:00Z"
        intent = "deploy contract"
        h = compute_commitment_hash(intent, nonce, ts)

        # Commit
        resp = client.post("/api/v1/intent/commit", json={
            "agent_id": "a", "level": 1, "commitment_hash": h,
        })
        cid = resp.json()["id"]

        # Reveal
        resp = client.post("/api/v1/intent/reveal", json={
            "commitment_id": cid,
            "intent_plaintext": intent,
            "nonce": nonce,
            "timestamp": ts,
        })
        assert resp.status_code == 200
        assert resp.json()["verified"] is True
        assert resp.json()["status"] == "revealed"

    def test_reveal_wrong_intent(self):
        nonce = generate_nonce()
        ts = "2026-03-07T15:00:00Z"
        h = compute_commitment_hash("real intent", nonce, ts)

        resp = client.post("/api/v1/intent/commit", json={
            "agent_id": "a", "level": 1, "commitment_hash": h,
        })
        cid = resp.json()["id"]

        resp = client.post("/api/v1/intent/reveal", json={
            "commitment_id": cid,
            "intent_plaintext": "fake intent",
            "nonce": nonce,
            "timestamp": ts,
        })
        assert resp.status_code == 422

    def test_reveal_not_found(self):
        resp = client.post("/api/v1/intent/reveal", json={
            "commitment_id": "00000000-0000-0000-0000-000000000000",
            "intent_plaintext": "x", "nonce": "n", "timestamp": "t",
        })
        assert resp.status_code == 404


class TestWitnessEndpoint:
    def test_add_witness_to_l3(self):
        resp = client.post("/api/v1/intent/commit", json={
            "agent_id": "a", "level": 3, "commitment_hash": "abc",
            "scope": {"tools": ["git"]}, "signature": "sig",
        })
        cid = resp.json()["id"]

        resp = client.post(f"/api/v1/intent/{cid}/witness", json={
            "agent_id": "witness-1", "pubkey": "ed25519:xxx", "ack_signature": "sig1",
        })
        assert resp.status_code == 200
        assert resp.json()["witness_count"] == 1

    def test_witness_rejected_for_l1(self):
        resp = client.post("/api/v1/intent/commit", json={
            "agent_id": "a", "level": 1, "commitment_hash": "abc",
        })
        cid = resp.json()["id"]

        resp = client.post(f"/api/v1/intent/{cid}/witness", json={
            "agent_id": "w", "pubkey": "k", "ack_signature": "s",
        })
        assert resp.status_code == 422


class TestL25Assessment:
    def test_assess_l2_commitment(self):
        resp = client.post("/api/v1/intent/commit", json={
            "agent_id": "a", "level": 2, "commitment_hash": "abc",
            "scope": {"tools": ["git"], "max_actions": 10}, "signature": "sig",
        })
        cid = resp.json()["id"]

        resp = client.post(f"/api/v1/intent/{cid}/assess-l25", json={
            "tools_used": ["git"], "action_count": 5,
        })
        assert resp.status_code == 200
        assert resp.json()["passed"] is True
        assert resp.json()["deviation_score"] == 0.0

    def test_assess_rejected_for_l1(self):
        resp = client.post("/api/v1/intent/commit", json={
            "agent_id": "a", "level": 1, "commitment_hash": "abc",
        })
        cid = resp.json()["id"]

        resp = client.post(f"/api/v1/intent/{cid}/assess-l25", json={
            "tools_used": ["git"],
        })
        assert resp.status_code == 422
