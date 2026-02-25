"""
Integration tests for isnad API v1 — runs against real PostgreSQL.
"""

import os
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-integration")

import pytest
from fastapi.testclient import TestClient
from isnad.api_v1 import create_app

app = create_app(allowed_origins=["*"], use_lifespan=True)


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


def test_health(c):
    resp = c.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register_get_update_check(c):
    """Full lifecycle: register → get profile → update → check."""
    # Register
    resp = c.post("/api/v1/agents/register", json={
        "name": "Integration Test Agent",
        "description": "Created by test suite",
        "agent_type": "autonomous",
        "platforms": [{"name": "github", "url": "https://github.com/test"}],
        "capabilities": ["code-review", "testing"],
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    agent_id = data["agent_id"]
    api_key = data["api_key"]
    assert api_key.startswith("isnad_")

    # Get profile
    resp = c.get(f"/api/v1/agents/{agent_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Integration Test Agent"

    # Update
    resp = c.patch(
        f"/api/v1/agents/{agent_id}",
        json={"name": "Updated Agent Name"},
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Agent Name"

    # Check
    resp = c.get(f"/api/v1/check/{agent_id}")
    assert resp.status_code == 200
    assert "overall_score" in resp.json()

    # Trust report
    resp = c.get(f"/api/v1/agents/{agent_id}/trust-report")
    assert resp.status_code == 200
    assert "overall_score" in resp.json()


def test_explorer_pagination(c):
    resp = c.get("/api/v1/explorer", params={"page": 1, "limit": 5})
    assert resp.status_code == 200
    assert resp.json()["page"] == 1


def test_explorer_page_zero_rejected(c):
    resp = c.get("/api/v1/explorer", params={"page": 0})
    assert resp.status_code == 422


def test_explorer_limit_over_max(c):
    resp = c.get("/api/v1/explorer", params={"limit": 999})
    assert resp.status_code == 422


def test_agents_list(c):
    resp = c.get("/api/v1/agents", params={"page": 1, "limit": 10})
    assert resp.status_code == 200
    assert resp.json()["page"] == 1


def test_stats(c):
    resp = c.get("/api/v1/stats")
    assert resp.status_code == 200
    assert "uptime" in resp.json()
