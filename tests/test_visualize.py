"""Tests for isnad.visualize — trust chain visualization."""

import pytest
from isnad.core import AgentIdentity, Attestation, TrustChain
from isnad.visualize import (
    render_chain,
    render_graph,
    render_agent_summary,
    _bar,
    _truncate,
)


@pytest.fixture
def agents():
    """Create a set of test agents."""
    return {
        name: AgentIdentity()
        for name in ["alice", "bob", "charlie", "diana"]
    }


@pytest.fixture
def populated_chain(agents):
    """Create a chain with several attestations."""
    chain = TrustChain()
    attestations = [
        Attestation(
            subject=agents["bob"].agent_id,
            witness=agents["alice"].agent_id,
            task="code-review",
            evidence="https://github.com/pr/1",
        ).sign(agents["alice"]),
        Attestation(
            subject=agents["bob"].agent_id,
            witness=agents["alice"].agent_id,
            task="code-review",
            evidence="https://github.com/pr/2",
        ).sign(agents["alice"]),
        Attestation(
            subject=agents["charlie"].agent_id,
            witness=agents["bob"].agent_id,
            task="deploy",
            evidence="https://deploy.log/42",
        ).sign(agents["bob"]),
        Attestation(
            subject=agents["alice"].agent_id,
            witness=agents["diana"].agent_id,
            task="audit",
            evidence="https://audit.report/7",
        ).sign(agents["diana"]),
    ]
    for att in attestations:
        chain.add(att)
    return chain


class TestRenderChain:
    def test_empty_chain(self):
        chain = TrustChain()
        result = render_chain(chain)
        assert "empty" in result.lower()

    def test_basic_output(self, populated_chain):
        result = render_chain(populated_chain)
        assert "Trust Chain" in result
        assert "4 attestations" in result
        assert "4 agents" in result
        assert "▶" in result

    def test_contains_agent_ids(self, populated_chain, agents):
        result = render_chain(populated_chain)
        for name in ["alice", "bob", "charlie", "diana"]:
            assert agents[name].agent_id in result

    def test_shows_scores(self, populated_chain):
        result = render_chain(populated_chain)
        assert "Agent Scores:" in result
        assert "0." in result  # some score value

    def test_no_scores(self, populated_chain):
        result = render_chain(populated_chain, show_scores=False)
        assert "Agent Scores:" not in result

    def test_scope_filter(self, populated_chain):
        result = render_chain(populated_chain, scope="deploy")
        assert "1 attestations" in result

    def test_scope_filter_empty(self, populated_chain):
        result = render_chain(populated_chain, scope="nonexistent")
        assert "empty" in result.lower()

    def test_timestamps(self, populated_chain):
        result = render_chain(populated_chain, show_timestamps=True)
        # Should contain date-like patterns
        assert "[20" in result

    def test_verified_status(self, populated_chain):
        result = render_chain(populated_chain)
        assert "✅" in result

    def test_repeat_witness_noted(self, populated_chain):
        result = render_chain(populated_chain)
        assert "repeat witness" in result


class TestRenderGraph:
    def test_dot_format(self, populated_chain):
        result = render_graph(populated_chain)
        assert result.startswith("digraph isnad_trust {")
        assert result.strip().endswith("}")
        assert "->" in result

    def test_contains_agents(self, populated_chain, agents):
        result = render_graph(populated_chain)
        for name in ["alice", "bob", "charlie", "diana"]:
            assert agents[name].agent_id in result

    def test_scope_filter(self, populated_chain):
        result = render_graph(populated_chain, scope="audit")
        # Should only have audit edges
        assert "audit" in result

    def test_scores_in_labels(self, populated_chain):
        result = render_graph(populated_chain)
        assert "score:" in result


class TestRenderAgentSummary:
    def test_basic_summary(self, populated_chain, agents):
        result = render_agent_summary(populated_chain, agents["bob"].agent_id)
        assert "Agent:" in result
        assert "Trust Score:" in result
        assert "Attestations received: 2" in result
        assert "Unique witnesses:      1" in result

    def test_given_attestations(self, populated_chain, agents):
        result = render_agent_summary(populated_chain, agents["bob"].agent_id)
        assert "Attestations given:    1" in result

    def test_top_scope(self, populated_chain, agents):
        result = render_agent_summary(populated_chain, agents["bob"].agent_id)
        assert "code-review" in result

    def test_unknown_agent(self, populated_chain):
        result = render_agent_summary(populated_chain, "unknown-agent")
        assert "Trust Score:           0.00" in result
        assert "Attestations received: 0" in result

    def test_scope_filter(self, populated_chain, agents):
        result = render_agent_summary(
            populated_chain, agents["bob"].agent_id, scope="deploy"
        )
        assert "Attestations received: 0" in result


class TestHelpers:
    def test_bar_full(self):
        assert _bar(1.0, 10) == "██████████"

    def test_bar_empty(self):
        assert _bar(0.0, 10) == "░░░░░░░░░░"

    def test_bar_half(self):
        result = _bar(0.5, 10)
        assert result.count("█") == 5
        assert result.count("░") == 5

    def test_truncate_short(self):
        assert _truncate("hello", 10) == "hello"

    def test_truncate_long(self):
        assert _truncate("hello world!", 8) == "hello w…"
        assert len(_truncate("hello world!", 8)) == 8
