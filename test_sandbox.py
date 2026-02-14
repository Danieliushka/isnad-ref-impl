#!/usr/bin/env python3
"""End-to-end test for the sandbox API — simulates Kit_Fox pilot flow."""

from fastapi.testclient import TestClient
from sandbox_api import app

client = TestClient(app)


def test_full_pilot_flow():
    """Simulate: Kit_Fox signs attestation, Gendolf verifies, chain trust computed."""
    
    # 1. Health check
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["protocol"] == "isnad"
    print("✅ Health OK")
    
    # 2. Create two identities (Kit_Fox + Gendolf)
    r1 = client.post("/identity/create", json={"label": "Kit_Fox"})
    assert r1.status_code == 200
    kit = r1.json()
    print(f"✅ Kit_Fox: {kit['agent_id']}")
    
    r2 = client.post("/identity/create", json={"label": "Gendolf"})
    gendolf = r2.json()
    print(f"✅ Gendolf: {gendolf['agent_id']}")
    
    # 3. Kit_Fox attests Gendolf (code-review task)
    r3 = client.post("/attestation/create", json={
        "witness_private_key": kit["private_key"],
        "subject_agent_id": gendolf["agent_id"],
        "task": "code-review",
        "evidence": "https://github.com/isnad/ref-impl/pull/1",
    })
    assert r3.status_code == 200
    att = r3.json()
    assert att["valid"] is True
    print(f"✅ Attestation created: valid={att['valid']}")
    
    # 4. Verify attestation independently
    r4 = client.post("/attestation/verify", json={"attestation": att["attestation"]})
    assert r4.json()["valid"] is True
    print(f"✅ Verification: valid={r4.json()['valid']}")
    
    # 5. Add to chain
    r5 = client.post("/chain/add", json={"attestation": att["attestation"]})
    assert r5.status_code == 200
    assert r5.json()["added"] is True
    print(f"✅ Chain add: total={r5.json()['total_attestations']}")
    
    # 6. Query trust score
    r6 = client.get(f"/chain/score/{gendolf['agent_id']}")
    score = r6.json()
    assert score["trust_score"] > 0
    print(f"✅ Trust score: {score['trust_score']} ({score['attestation_count']} attestations)")
    
    # 7. Gendolf attests Kit_Fox back (mutual trust)
    r7 = client.post("/attestation/create", json={
        "witness_private_key": gendolf["private_key"],
        "subject_agent_id": kit["agent_id"],
        "task": "pilot-collaboration",
        "evidence": "https://clawk.ai/thread/isnad-pilot",
    })
    att2 = r7.json()
    client.post("/chain/add", json={"attestation": att2["attestation"]})
    
    # 8. Transitive trust
    r8 = client.post("/chain/transitive", json={
        "source_agent_id": kit["agent_id"],
        "target_agent_id": gendolf["agent_id"],
    })
    trans = r8.json()
    print(f"✅ Transitive trust Kit→Gendolf: {trans['trust']}")
    
    # 9. Dump chain
    r9 = client.get("/chain/dump")
    assert r9.json()["total"] == 2
    print(f"✅ Chain dump: {r9.json()['total']} attestations")
    
    print("\n🎉 Full pilot flow passed!")


def test_batch_verify():
    """Test batch verification of multiple attestations."""
    # Create identities
    r1 = client.post("/identity/create", json={"label": "alice"})
    alice = r1.json()
    r2 = client.post("/identity/create", json={"label": "bob"})
    bob = r2.json()
    
    # Create two valid attestations
    att1 = client.post("/attestation/create", json={
        "witness_private_key": alice["private_key"],
        "subject_agent_id": bob["agent_id"],
        "task": "review", "evidence": "https://example.com/1",
    }).json()["attestation"]
    
    att2 = client.post("/attestation/create", json={
        "witness_private_key": bob["private_key"],
        "subject_agent_id": alice["agent_id"],
        "task": "collab", "evidence": "https://example.com/2",
    }).json()["attestation"]
    
    # One tampered attestation
    bad = dict(att1)
    bad["subject"] = "tampered-agent-id"
    
    r = client.post("/attestation/batch-verify", json={"attestations": [att1, att2, bad]})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["valid_count"] == 2
    assert data["results"][0]["valid"] is True
    assert data["results"][1]["valid"] is True
    assert data["results"][2]["valid"] is False
    print("✅ Batch verify: 2 valid, 1 invalid")


def test_agent_reputation():
    """Test agent reputation summary endpoint."""
    r1 = client.post("/identity/create", json={"label": "rep-witness"})
    w = r1.json()
    r2 = client.post("/identity/create", json={"label": "rep-subject"})
    s = r2.json()
    
    # Create and add attestation
    att = client.post("/attestation/create", json={
        "witness_private_key": w["private_key"],
        "subject_agent_id": s["agent_id"],
        "task": "security-audit", "evidence": "https://example.com/audit",
    }).json()["attestation"]
    client.post("/chain/add", json={"attestation": att})
    
    # Check reputation
    r = client.get(f"/agent/{s['agent_id']}/reputation")
    assert r.status_code == 200
    rep = r.json()
    assert rep["attestations_received"] >= 1
    assert rep["trust_score"] > 0
    assert "security-audit" in rep["tasks_received"]
    assert rep["registered"] is True
    print(f"✅ Reputation: score={rep['trust_score']}, received={rep['attestations_received']}")


if __name__ == "__main__":
    test_full_pilot_flow()
