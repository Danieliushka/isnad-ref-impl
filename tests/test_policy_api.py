"""Tests for Policy REST API endpoints."""
import pytest
from fastapi.testclient import TestClient
from isnad.api import app
from tests.conftest import AUTH_HEADERS as H

client = TestClient(app)


def test_list_policies():
    r = client.get("/policies")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()["policies"]]
    assert "strict-commerce" in names
    assert "open-discovery" in names


def test_get_policy():
    r = client.get("/policies/strict-commerce")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "strict-commerce"
    assert len(data["rules"]) > 0


def test_get_policy_not_found():
    r = client.get("/policies/nonexistent")
    assert r.status_code == 404


def test_create_and_delete_policy():
    r = client.post("/policies", headers=H, json={
        "name": "test_custom",
        "rules": [{
            "name": "high_trust",
            "requirement": {"min_trust_score": 0.9},
            "on_fail": "deny",
            "priority": 1,
        }],
        "default_action": "allow",
    })
    assert r.status_code == 201
    assert r.json()["created"] == "test_custom"
    # Verify it exists
    r = client.get("/policies/test_custom")
    assert r.status_code == 200
    # Delete
    r = client.delete("/policies/test_custom", headers=H)
    assert r.status_code == 200
    # Verify gone
    r = client.get("/policies/test_custom")
    assert r.status_code == 404


def test_create_policy_conflict():
    client.post("/policies", headers=H, json={"name": "dup_test", "rules": [], "default_action": "allow"})
    r = client.post("/policies", headers=H, json={"name": "dup_test", "rules": [], "default_action": "allow"})
    assert r.status_code == 409
    client.delete("/policies/dup_test", headers=H)


def test_evaluate_allowed():
    r = client.post("/policies/open-discovery/evaluate", json={
        "agent_id": "agent_good",
        "trust_score": 0.5,
        "endorsement_count": 1,
        "chain_length": 1,
    })
    assert r.status_code == 200
    assert r.json()["allowed"] is True


def test_evaluate_denied():
    r = client.post("/policies/strict-commerce/evaluate", json={
        "agent_id": "agent_bad",
        "trust_score": 0.1,
        "endorsement_count": 0,
        "chain_length": 10,
    })
    assert r.status_code == 200
    assert r.json()["allowed"] is False


def test_evaluate_batch():
    r = client.post("/policies/open-discovery/evaluate/batch", json=[
        {"agent_id": "good", "trust_score": 0.9, "endorsement_count": 5, "chain_length": 1},
        {"agent_id": "bad", "trust_score": 0.0, "endorsement_count": 0, "chain_length": 10},
    ])
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 2
    assert results[0]["agent_id"] == "good"


def test_evaluate_not_found():
    r = client.post("/policies/nonexistent/evaluate", json={"agent_id": "x"})
    assert r.status_code == 404
