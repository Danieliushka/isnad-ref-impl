"""Tests for Atlas TrustScore integration."""

import pytest
from unittest.mock import patch, MagicMock
from isnad.core import TrustChain, Attestation, AgentIdentity
from isnad.trustscore.atlas import AtlasIntegration, AtlasScore, ATLAS_API_URL


@pytest.fixture
def chain_with_agents():
    """Create a chain with attestations for testing."""
    chain = TrustChain()
    alice = AgentIdentity()
    bob = AgentIdentity()

    att1 = Attestation(subject=alice.agent_id, witness=bob.agent_id,
                       task="code_review", evidence="Reviewed PR #42")
    att1.sign(bob)
    chain.add(att1)

    att2 = Attestation(subject=alice.agent_id, witness=bob.agent_id,
                       task="security_audit", evidence="Passed security audit")
    att2.sign(bob)
    chain.add(att2)

    att3 = Attestation(subject=bob.agent_id, witness=alice.agent_id,
                       task="deployment", evidence="Deployed v2.0")
    att3.sign(alice)
    chain.add(att3)

    return chain, alice, bob


@pytest.fixture
def mock_atlas_response():
    """Mock Atlas API response."""
    return {"score": 85, "classification": "trusted", "agent_id": "alice"}


class TestAtlasScore:
    def test_dataclass(self):
        score = AtlasScore(
            agent_id="test",
            atlas_score=0.85,
            atlas_classification="trusted",
            isnad_raw_score=0.9,
            isnad_weighted_score=0.88,
            combined_score=0.87,
            attestation_count=5,
            confidence="medium",
        )
        d = score.to_dict()
        assert d["agent_id"] == "test"
        assert d["combined_score"] == 0.87
        assert d["confidence"] == "medium"


class TestAtlasIntegration:
    @patch("isnad.trustscore.atlas.httpx")
    def test_score_agent(self, mock_httpx, chain_with_agents, mock_atlas_response):
        chain, alice, bob = chain_with_agents
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_atlas_response
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value = mock_client

        atlas = AtlasIntegration(chain)
        atlas._client = mock_client

        score = atlas.score_agent(alice.agent_id)
        assert score.agent_id == alice.agent_id
        assert score.atlas_score == 0.85
        assert score.atlas_classification == "trusted"
        assert score.isnad_raw_score > 0
        assert 0 <= score.combined_score <= 1
        assert score.attestation_count == 2
        assert score.confidence == "low"  # 2 attestations < 3

    @patch("isnad.trustscore.atlas.httpx")
    def test_trust_gate_allow(self, mock_httpx, chain_with_agents, mock_atlas_response):
        chain, alice, bob = chain_with_agents
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_atlas_response
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value = mock_client

        atlas = AtlasIntegration(chain)
        atlas._client = mock_client

        result = atlas.trust_gate(alice.agent_id, threshold=0.3)
        assert result["allowed"] is True
        assert result["score"] >= 0.3

    @patch("isnad.trustscore.atlas.httpx")
    def test_trust_gate_deny(self, mock_httpx, chain_with_agents):
        chain, alice, bob = chain_with_agents
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"score": 10, "classification": "suspicious"}
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value = mock_client

        atlas = AtlasIntegration(chain)
        atlas._client = mock_client

        result = atlas.trust_gate(alice.agent_id, threshold=0.9)
        assert result["allowed"] is False

    @patch("isnad.trustscore.atlas.httpx")
    def test_batch_score(self, mock_httpx, chain_with_agents, mock_atlas_response):
        chain, alice, bob = chain_with_agents
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_atlas_response
        mock_client.post.return_value = mock_resp
        mock_httpx.Client.return_value = mock_client

        atlas = AtlasIntegration(chain)
        atlas._client = mock_client

        scores = atlas.batch_score([alice.agent_id, bob.agent_id])
        assert len(scores) == 2

    @patch("isnad.trustscore.atlas.httpx")
    def test_context_manager(self, mock_httpx, chain_with_agents):
        chain, alice, bob = chain_with_agents
        mock_client = MagicMock()
        mock_httpx.Client.return_value = mock_client

        with AtlasIntegration(chain) as atlas:
            assert atlas is not None
        mock_client.close.assert_called_once()
