"""Tests for GET /api/v1/stats endpoint."""
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


def test_stats_empty():
    """Stats on empty platform returns zeros."""
    r = client.get("/api/v1/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_agents"] == 0
    assert data["total_attestations"] == 0
    assert data["attestations_verified"] == 0
    assert "trust_scores" in data
    assert data["trust_scores"]["average"] == 0.0
    assert "uptime" in data
    assert "avg_response_ms" in data


def test_stats_with_agents():
    """Stats reflects created agents."""
    # Create some agents
    client.post("/identities")
    client.post("/identities")
    client.post("/identities")

    r = client.get("/api/v1/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_agents"] == 3


def test_stats_with_attestations():
    """Stats reflects attestations after creation."""
    # Create two agents
    r1 = client.post("/identities").json()
    r2 = client.post("/identities").json()

    # Create an attestation
    client.post("/attest", json={
        "witness_id": r1["agent_id"],
        "subject_id": r2["agent_id"],
        "task": "test-task",
        "evidence": "http://example.com",
    })

    r = client.get("/api/v1/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_agents"] == 2
    assert data["total_attestations"] == 1
    assert data["attestations_verified"] == 1


def test_stats_trust_scores_in_memory():
    """Trust scores computed from in-memory chain when no DB."""
    r1 = client.post("/identities").json()
    r2 = client.post("/identities").json()

    # Create attestation so subject gets a trust score > 0
    client.post("/attest", json={
        "witness_id": r1["agent_id"],
        "subject_id": r2["agent_id"],
        "task": "proved-capability",
        "evidence": "",
    })

    r = client.get("/api/v1/stats")
    data = r.json()
    ts = data["trust_scores"]
    # At least one agent has score > 0, so average should be > 0
    assert ts["max"] > 0
    assert ts["average"] > 0


def test_stats_response_model():
    """All expected fields present in response."""
    r = client.get("/api/v1/stats")
    data = r.json()
    expected_fields = {"total_agents", "total_attestations", "agents_checked",
                       "attestations_verified", "trust_scores", "avg_response_ms", "uptime"}
    assert expected_fields.issubset(set(data.keys()))
    ts_fields = {"average", "min", "max"}
    assert ts_fields.issubset(set(data["trust_scores"].keys()))
