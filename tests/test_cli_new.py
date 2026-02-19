"""Tests for new CLI commands: health, revoke, compare."""
import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from isnad.cli import cmd_health, cmd_revoke, cmd_compare


class TestCmdHealth:
    def test_healthy_server(self, capsys):
        client = MagicMock()
        client.health.return_value = {"status": "ok", "version": "0.4.0", "attestations": 42}
        result = cmd_health(client, SimpleNamespace())
        assert result["status"] == "ok"
        out = capsys.readouterr().out
        assert "healthy" in out
        assert "42" in out

    def test_unreachable_server(self, capsys):
        client = MagicMock()
        client.health.side_effect = ConnectionError("refused")
        client.base_url = "http://localhost:8420"
        with pytest.raises(SystemExit):
            cmd_health(client, SimpleNamespace())
        out = capsys.readouterr().out
        assert "Cannot reach" in out


class TestCmdRevoke:
    def test_revoke_valid_reason(self, capsys):
        client = MagicMock()
        args = SimpleNamespace(
            attestation_id="att-123",
            reason="key_compromise",
            revoked_by="agent-admin"
        )
        result = cmd_revoke(client, args)
        assert result.attestation_id == "att-123"
        out = capsys.readouterr().out
        assert "revoked" in out.lower()
        assert "key_compromise" in out

    def test_revoke_invalid_reason(self, capsys):
        client = MagicMock()
        args = SimpleNamespace(
            attestation_id="att-123",
            reason="banana",
            revoked_by=""
        )
        with pytest.raises(SystemExit):
            cmd_revoke(client, args)

    def test_revoke_default_by(self, capsys):
        client = MagicMock()
        args = SimpleNamespace(
            attestation_id="att-456",
            reason="superseded",
            revoked_by=""
        )
        result = cmd_revoke(client, args)
        assert result.revoked_by == "cli-user"


class TestCmdCompare:
    def test_compare_agents(self, capsys):
        client = MagicMock()
        client.trust_score.side_effect = [
            {"trust_score": 0.85},
            {"trust_score": 0.62},
        ]
        args = SimpleNamespace(agent_a="agent-alice-123456", agent_b="agent-bob-789012")
        result = cmd_compare(client, args)
        assert result["agent_a"]["trust_score"] == 0.85
        assert result["agent_b"]["trust_score"] == 0.62
        out = capsys.readouterr().out
        assert "Agent A leads" in out
        assert "0.23" in out

    def test_compare_equal(self, capsys):
        client = MagicMock()
        client.trust_score.side_effect = [
            {"trust_score": 0.5},
            {"trust_score": 0.5},
        ]
        args = SimpleNamespace(agent_a="a" * 20, agent_b="b" * 20)
        result = cmd_compare(client, args)
        out = capsys.readouterr().out
        assert "Equal" in out

    def test_compare_b_leads(self, capsys):
        client = MagicMock()
        client.trust_score.side_effect = [
            {"trust_score": 0.3},
            {"trust_score": 0.9},
        ]
        args = SimpleNamespace(agent_a="a" * 20, agent_b="b" * 20)
        cmd_compare(client, args)
        out = capsys.readouterr().out
        assert "Agent B leads" in out
