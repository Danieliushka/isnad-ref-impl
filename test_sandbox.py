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


if __name__ == "__main__":
    test_full_pilot_flow()
