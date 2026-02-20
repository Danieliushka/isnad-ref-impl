"""Tests for discovery API endpoints."""
import pytest
from fastapi.testclient import TestClient
from isnad.api import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def agent_id(client):
    resp = client.post("/identity", json={"name": "DiscoveryBot"})
    assert resp.status_code == 200
    return resp.json()["agent_id"]


class TestDiscoveryAPI:
    def test_register_agent(self, client, agent_id):
        resp = client.post("/discovery/register", json={
            "agent_id": agent_id,
            "name": "DiscoveryBot",
            "capabilities": ["search", "translate"],
            "endpoints": {"http": "http://localhost:9000"},
        })
        assert resp.status_code == 200
        assert resp.json()["registered"] == agent_id

    def test_register_unknown_agent(self, client):
        resp = client.post("/discovery/register", json={
            "agent_id": "nonexistent",
            "name": "Ghost",
        })
        assert resp.status_code == 404

    def test_list_agents(self, client, agent_id):
        client.post("/discovery/register", json={
            "agent_id": agent_id,
            "name": "ListBot",
            "capabilities": ["qa"],
        })
        resp = client.get("/discovery/agents")
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        assert any(a["agent_id"] == agent_id for a in agents)

    def test_list_by_capability(self, client, agent_id):
        client.post("/discovery/register", json={
            "agent_id": agent_id,
            "name": "CapBot",
            "capabilities": ["rare_skill"],
        })
        resp = client.get("/discovery/agents?capability=rare_skill")
        assert resp.status_code == 200
        assert len(resp.json()["agents"]) >= 1

        resp2 = client.get("/discovery/agents?capability=nonexistent_skill")
        assert resp2.json()["agents"] == []

    def test_get_agent_profile(self, client, agent_id):
        client.post("/discovery/register", json={
            "agent_id": agent_id,
            "name": "ProfileBot",
            "capabilities": ["verify"],
            "metadata": {"version": "1.0"},
        })
        resp = client.get(f"/discovery/agents/{agent_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["signature_valid"] is True
        assert data["name"] == "ProfileBot"
        assert "version" in data["metadata"]

    def test_get_unknown_agent(self, client):
        resp = client.get("/discovery/agents/nonexistent")
        assert resp.status_code == 404

    def test_unregister_agent(self, client, agent_id):
        client.post("/discovery/register", json={
            "agent_id": agent_id,
            "name": "ByeBot",
        })
        resp = client.delete(f"/discovery/agents/{agent_id}")
        assert resp.status_code == 200
        assert resp.json()["unregistered"] == agent_id

        resp2 = client.get(f"/discovery/agents/{agent_id}")
        assert resp2.status_code == 404

    def test_unregister_unknown(self, client):
        resp = client.delete("/discovery/agents/nonexistent")
        assert resp.status_code == 404
