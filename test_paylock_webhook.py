"""Tests for POST /api/v1/webhook/paylock endpoint."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with mocked DB."""
    # Patch DB before importing
    from isnad import api_v1
    
    mock_db = AsyncMock()
    mock_db.get_agent = AsyncMock(return_value={"id": "agent-123", "name": "test-agent", "trust_score": 50})
    mock_db.get_agent_by_name = AsyncMock(return_value=None)
    mock_db.create_behavioral_signal = AsyncMock(return_value={
        "id": 1, "agent_id": "agent-123", "source": "paylock",
        "event_type": "escrow_released", "contract_id": "contract-abc",
        "amount_sol": 0.5, "metadata": {}, "created_at": "2026-03-02T12:00:00Z",
        "received_at": "2026-03-02T12:00:01Z",
    })
    mock_db.count_behavioral_signals = AsyncMock(return_value=0)
    
    old_db = api_v1._db
    api_v1._db = mock_db
    
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(api_v1.router)
    
    yield TestClient(app), mock_db
    
    api_v1._db = old_db


class TestPayLockWebhook:
    """Test PayLock webhook endpoint."""

    def test_escrow_released(self, client):
        c, mock_db = client
        resp = c.post("/api/v1/webhook/paylock", json={
            "event": "escrow_released",
            "agent_id": "agent-123",
            "contract_id": "contract-abc",
            "amount_sol": 0.5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["signal_id"] == 1
        assert data["event"] == "escrow_released"
        assert "positive" in data["behavioral_impact"]
        mock_db.create_behavioral_signal.assert_called_once()

    def test_escrow_created(self, client):
        c, mock_db = client
        resp = c.post("/api/v1/webhook/paylock", json={
            "event": "escrow_created",
            "agent_id": "agent-123",
            "contract_id": "contract-xyz",
            "amount_sol": 1.0,
        })
        assert resp.status_code == 200
        assert resp.json()["event"] == "escrow_created"
        assert "neutral" in resp.json()["behavioral_impact"]

    def test_escrow_disputed(self, client):
        c, mock_db = client
        resp = c.post("/api/v1/webhook/paylock", json={
            "event": "escrow_disputed",
            "agent_id": "agent-123",
            "contract_id": "contract-xyz",
            "amount_sol": 0.5,
        })
        assert resp.status_code == 200
        assert "negative" in resp.json()["behavioral_impact"]

    def test_invalid_event(self, client):
        c, _ = client
        resp = c.post("/api/v1/webhook/paylock", json={
            "event": "invalid_event",
            "agent_id": "agent-123",
            "contract_id": "contract-abc",
        })
        assert resp.status_code == 422

    def test_agent_not_found(self, client):
        c, mock_db = client
        mock_db.get_agent = AsyncMock(return_value=None)
        mock_db.get_agent_by_name = AsyncMock(return_value=None)
        resp = c.post("/api/v1/webhook/paylock", json={
            "event": "escrow_released",
            "agent_id": "nonexistent-agent",
            "contract_id": "contract-abc",
        })
        assert resp.status_code == 404

    def test_missing_required_fields(self, client):
        c, _ = client
        resp = c.post("/api/v1/webhook/paylock", json={
            "event": "escrow_released",
        })
        assert resp.status_code == 422

    def test_with_metadata(self, client):
        c, mock_db = client
        resp = c.post("/api/v1/webhook/paylock", json={
            "event": "escrow_released",
            "agent_id": "agent-123",
            "contract_id": "contract-abc",
            "amount_sol": 0.5,
            "timestamp": "2026-03-02T12:00:00Z",
            "metadata": {"bro_agent": True, "task": "code_review"},
        })
        assert resp.status_code == 200
        call_kwargs = mock_db.create_behavioral_signal.call_args
        assert call_kwargs[1].get("metadata") == {"bro_agent": True, "task": "code_review"} or \
               call_kwargs.kwargs.get("metadata") == {"bro_agent": True, "task": "code_review"}
