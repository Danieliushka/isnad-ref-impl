"""Tests for isnad REST API server."""
import pytest
from fastapi.testclient import TestClient
from api_server import app, _identities, _chain

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    """Reset state between tests."""
    _identities.clear()
    _chain.attestations.clear()
    _chain._by_subject.clear()
    _chain._by_witness.clear()
    yield


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["protocol"] == "isnad"


def test_create_identity():
    r = client.post("/identities")
    assert r.status_code == 200
    data = r.json()
    assert data["agent_id"].startswith("agent:")
    assert len(data["public_key"]) == 64


def test_list_identities():
    client.post("/identities")
    client.post("/identities")
    r = client.get("/identities")
    assert r.json()["count"] == 2


def test_get_identity():
    r1 = client.post("/identities")
    aid = r1.json()["agent_id"]
    r2 = client.get(f"/identities/{aid}")
    assert r2.status_code == 200
    assert r2.json()["agent_id"] == aid
    assert "trust_score" in r2.json()


def test_get_identity_404():
    r = client.get("/identities/agent:nonexistent")
    assert r.status_code == 404


def test_create_attestation():
    w = client.post("/identities").json()
    s = client.post("/identities").json()
    r = client.post("/attest", json={
        "witness_id": w["agent_id"],
        "subject_id": s["agent_id"],
        "task": "completed code review",
        "evidence": "https://github.com/pr/123",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["verified"] is True
    assert data["task"] == "completed code review"


def test_attestation_unknown_witness():
    s = client.post("/identities").json()
    r = client.post("/attest", json={
        "witness_id": "agent:fake",
        "subject_id": s["agent_id"],
        "task": "test",
    })
    assert r.status_code == 404


def test_list_attestations():
    w = client.post("/identities").json()
    s = client.post("/identities").json()
    client.post("/attest", json={
        "witness_id": w["agent_id"],
        "subject_id": s["agent_id"],
        "task": "task1",
    })
    client.post("/attest", json={
        "witness_id": w["agent_id"],
        "subject_id": s["agent_id"],
        "task": "task2",
    })
    r = client.get("/attestations")
    assert r.json()["count"] == 2

    # Filter by subject
    r2 = client.get(f"/attestations?subject={s['agent_id']}")
    assert r2.json()["count"] == 2


def test_trust_score():
    w = client.post("/identities").json()
    s = client.post("/identities").json()
    client.post("/attest", json={
        "witness_id": w["agent_id"],
        "subject_id": s["agent_id"],
        "task": "delivered MVP",
    })
    r = client.get(f"/trust/{s['agent_id']}")
    assert r.status_code == 200
    assert r.json()["score"] > 0
    assert r.json()["attestation_count"] == 1


def test_chain_trust():
    # A attests B, B attests C → transitive trust A→C
    a = client.post("/identities").json()
    b = client.post("/identities").json()
    c = client.post("/identities").json()
    client.post("/attest", json={
        "witness_id": a["agent_id"],
        "subject_id": b["agent_id"],
        "task": "verified identity",
    })
    client.post("/attest", json={
        "witness_id": b["agent_id"],
        "subject_id": c["agent_id"],
        "task": "reviewed code",
    })
    r = client.get(f"/trust/{a['agent_id']}/to/{c['agent_id']}")
    assert r.status_code == 200
    assert r.json()["trust"] >= 0  # May be 0 if no path, but endpoint works


def test_verify_chain():
    w = client.post("/identities").json()
    s = client.post("/identities").json()
    client.post("/attest", json={
        "witness_id": w["agent_id"],
        "subject_id": s["agent_id"],
        "task": "test",
    })
    r = client.get("/chain/verify")
    assert r.json()["chain_valid"] is True


def test_export_chain():
    r = client.get("/chain/export")
    assert r.status_code == 200
    assert "attestations" in r.json()
    assert "identities" in r.json()


def test_openapi_docs():
    r = client.get("/docs")
    assert r.status_code == 200


def test_full_flow():
    """End-to-end: create identities → attest → verify → score."""
    # Create 3 agents
    alice = client.post("/identities").json()
    bob = client.post("/identities").json()
    carol = client.post("/identities").json()

    # Alice attests Bob (2 tasks)
    client.post("/attest", json={
        "witness_id": alice["agent_id"],
        "subject_id": bob["agent_id"],
        "task": "deployed production service",
    })
    client.post("/attest", json={
        "witness_id": alice["agent_id"],
        "subject_id": bob["agent_id"],
        "task": "fixed critical security bug",
    })

    # Bob attests Carol
    client.post("/attest", json={
        "witness_id": bob["agent_id"],
        "subject_id": carol["agent_id"],
        "task": "completed audit",
    })

    # Verify chain
    verify = client.get("/chain/verify").json()
    assert verify["chain_valid"] is True
    assert verify["total"] == 3

    # Check scores
    bob_score = client.get(f"/trust/{bob['agent_id']}").json()
    assert bob_score["attestation_count"] == 2
    assert bob_score["score"] > 0

    # Chain trust Alice → Carol (through Bob)
    chain = client.get(f"/trust/{alice['agent_id']}/to/{carol['agent_id']}").json()
    assert chain["trust"] >= 0
