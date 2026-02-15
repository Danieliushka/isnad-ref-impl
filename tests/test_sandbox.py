#!/usr/bin/env python3
"""End-to-end test for the sandbox API — simulates Kit_Fox pilot flow."""

from fastapi.testclient import TestClient
from isnad.sandbox_api import app

client = TestClient(app)


def test_full_pilot_flow():
    """Simulate: Kit_Fox signs attestation, Gendolf verifies, chain trust computed."""

    # 1. Health check
    r = client.get("/sandbox/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    # 2. Generate keypairs
    r1 = client.post("/sandbox/keys/generate")
    assert r1.status_code == 200
    kit = r1.json()

    r2 = client.post("/sandbox/keys/generate")
    gendolf = r2.json()

    # 3. Kit_Fox attests Gendolf
    r3 = client.post("/sandbox/attestations/create", json={
        "witness_id": kit["agent_id"],
        "subject_id": gendolf["agent_id"],
        "task": "code-review",
        "evidence": "https://github.com/isnad/ref-impl/pull/1",
    })
    assert r3.status_code == 200
    att = r3.json()
    assert att["added_to_chain"] is True

    # 4. Verify attestation
    r4 = client.post("/sandbox/attestations/verify", json=att["attestation"])
    assert r4.json()["valid"] is True

    # 5. Trust score
    r5 = client.post("/sandbox/trust/score", json={"agent_id": gendolf["agent_id"]})
    score = r5.json()
    assert score["trust_score"] > 0
    assert score["attestation_count"] == 1

    # 6. Mutual attestation
    r6 = client.post("/sandbox/attestations/create", json={
        "witness_id": gendolf["agent_id"],
        "subject_id": kit["agent_id"],
        "task": "pilot-collaboration",
        "evidence": "https://clawk.ai/thread/isnad-pilot",
    })
    assert r6.status_code == 200

    # 7. Chain check
    r7 = client.get(f"/sandbox/chain/{gendolf['agent_id']}")
    chain = r7.json()
    assert chain["received_count"] >= 1


def test_batch_verify():
    """Test batch verification of multiple attestations."""
    a = client.post("/sandbox/keys/generate").json()
    b = client.post("/sandbox/keys/generate").json()

    att1 = client.post("/sandbox/attestations/create", json={
        "witness_id": a["agent_id"], "subject_id": b["agent_id"],
        "task": "review", "evidence": "https://example.com/1",
    }).json()["attestation"]

    att2 = client.post("/sandbox/attestations/create", json={
        "witness_id": b["agent_id"], "subject_id": a["agent_id"],
        "task": "collab", "evidence": "https://example.com/2",
    }).json()["attestation"]

    # One tampered attestation
    bad = dict(att1)
    bad["subject"] = "tampered-agent-id"

    r = client.post("/sandbox/attestations/batch-verify", json={"attestations": [att1, att2, bad]})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["valid_count"] == 2
    assert data["results"][2]["valid"] is False


def test_agent_reputation():
    """Test agent reputation summary endpoint."""
    w = client.post("/sandbox/keys/generate").json()
    s = client.post("/sandbox/keys/generate").json()

    client.post("/sandbox/attestations/create", json={
        "witness_id": w["agent_id"], "subject_id": s["agent_id"],
        "task": "security-audit", "evidence": "https://example.com/audit",
    })

    r = client.get(f"/sandbox/agent/{s['agent_id']}/reputation")
    assert r.status_code == 200
    rep = r.json()
    assert rep["attestations_received"] >= 1
    assert rep["trust_score"] > 0
    assert "security-audit" in rep["task_distribution"]


if __name__ == "__main__":
    test_full_pilot_flow()
    print("🎉 All sandbox tests passed!")
