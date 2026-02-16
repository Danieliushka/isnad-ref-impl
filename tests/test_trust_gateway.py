"""Tests for trust gateway example."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'examples'))
from trust_gateway import TrustGateway, TrustPolicy
from isnad.core import TrustChain, AgentIdentity, Attestation


@pytest.fixture
def trusted_setup():
    """Create a chain where alice is trusted by bob and charlie."""
    alice = AgentIdentity()
    bob = AgentIdentity()
    charlie = AgentIdentity()
    chain = TrustChain()

    for task, witness in [("code_review", bob), ("security_audit", charlie)]:
        att = Attestation(subject=alice.agent_id, witness=witness.agent_id,
                         task=task, evidence=f"Verified {task}")
        att.sign(witness)
        chain.add(att)

    return chain, alice, bob, charlie


class TestTrustGateway:

    def test_allow_trusted_agent(self, trusted_setup):
        chain, alice, _, _ = trusted_setup
        gw = TrustGateway(TrustPolicy(min_attestations=2))
        result = gw.evaluate(chain, alice.agent_id)
        assert result["decision"] == "ALLOW"
        assert result["trust_score"] == 1.0

    def test_deny_unknown_agent(self, trusted_setup):
        chain, _, _, _ = trusted_setup
        unknown = AgentIdentity()
        gw = TrustGateway()
        result = gw.evaluate(chain, unknown.agent_id)
        assert result["decision"] == "DENY"

    def test_deny_insufficient_attestations(self, trusted_setup):
        chain, alice, _, _ = trusted_setup
        gw = TrustGateway(TrustPolicy(min_attestations=5))
        result = gw.evaluate(chain, alice.agent_id)
        assert result["decision"] == "DENY"

    def test_deny_missing_required_task(self, trusted_setup):
        chain, alice, _, _ = trusted_setup
        gw = TrustGateway(TrustPolicy(required_tasks=["financial_audit"]))
        result = gw.evaluate(chain, alice.agent_id)
        assert result["decision"] == "DENY"
        assert "financial_audit" in result["reason"]

    def test_deny_low_trust_score(self):
        """Single witness = score 0.5, require > 0.5 → deny."""
        alice = AgentIdentity()
        bob = AgentIdentity()
        chain = TrustChain()

        for task in ["review", "audit"]:
            att = Attestation(subject=alice.agent_id, witness=bob.agent_id,
                             task=task, evidence="ok")
            att.sign(bob)
            chain.add(att)

        gw = TrustGateway(TrustPolicy(min_attestations=2, min_trust_score=0.8))
        result = gw.evaluate(chain, alice.agent_id)
        assert result["decision"] == "DENY"

    def test_audit_log(self, trusted_setup):
        chain, alice, _, _ = trusted_setup
        gw = TrustGateway()
        gw.evaluate(chain, alice.agent_id)
        gw.evaluate(chain, AgentIdentity().agent_id)
        assert len(gw.audit_log) == 2
        assert gw.audit_log[0]["decision"] == "ALLOW"
        assert gw.audit_log[1]["decision"] == "DENY"
