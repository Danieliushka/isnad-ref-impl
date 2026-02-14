"""Tests for new sandbox endpoints: batch-verify, reputation, webhooks."""
from fastapi.testclient import TestClient
from sandbox import app

client = TestClient(app)


def _create_pair():
    """Create two agents and an attestation between them."""
    w = client.post("/sandbox/keys/generate").json()
    s = client.post("/sandbox/keys/generate").json()
    att = client.post("/sandbox/attestations/create", json={
        "witness_id": w["agent_id"],
        "subject_id": s["agent_id"],
        "task": "code-review",
        "evidence": "PR #42",
    }).json()
    return w, s, att


def test_batch_verify():
    w, s, att = _create_pair()
    a = att["attestation"]
    resp = client.post("/sandbox/attestations/batch-verify", json={
        "attestations": [
            {
                "subject": a["subject"],
                "witness": a["witness"],
                "task": a["task"],
                "evidence": a.get("evidence", ""),
                "timestamp": a["timestamp"],
                "signature": a["signature"],
                "witness_pubkey": a["witness_pubkey"],
            },
            {
                "subject": "fake",
                "witness": "fake",
                "task": "nope",
                "evidence": "",
                "timestamp": a["timestamp"],
                "signature": "bad",
                "witness_pubkey": "bad",
            },
        ]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["valid_count"] == 1
    assert data["results"][0]["valid"] is True
    assert data["results"][1]["valid"] is False


def test_agent_reputation():
    w, s, att = _create_pair()
    resp = client.get(f"/sandbox/agent/{s['agent_id']}/reputation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == s["agent_id"]
    assert data["trust_score"] > 0
    assert data["attestations_received"] >= 1
    assert "code-review" in data["task_distribution"]
    assert w["agent_id"] in data["peers"]["witnesses"]


def test_agent_reputation_unknown():
    resp = client.get("/sandbox/agent/nonexistent/reputation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trust_score"] == 0
    assert data["attestations_received"] == 0


def test_webhook_subscribe():
    resp = client.post("/sandbox/webhooks/subscribe", json={
        "url": "https://example.com/hook",
        "events": ["attestation.created"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["subscription"]["url"] == "https://example.com/hook"
    assert "attestation.created" in data["subscription"]["events"]


def test_webhook_invalid_event():
    resp = client.post("/sandbox/webhooks/subscribe", json={
        "url": "https://example.com/hook",
        "events": ["invalid.event"],
    })
    assert resp.status_code == 400


def test_webhook_list():
    resp = client.get("/sandbox/webhooks")
    assert resp.status_code == 200
    assert "webhooks" in resp.json()


def test_webhook_filtered():
    resp = client.post("/sandbox/webhooks/subscribe", json={
        "url": "https://example.com/filtered",
        "events": ["attestation.created"],
        "filter_issuer": "agent-123",
    })
    assert resp.status_code == 200
    assert resp.json()["subscription"]["filter_issuer"] == "agent-123"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
