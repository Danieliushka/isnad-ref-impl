"""Tests for TrustPolicy — declarative trust requirements."""

import json
import pytest

from isnad.policy import (
    TrustRequirement,
    EvaluationContext,
    PolicyRule,
    PolicyAction,
    PolicyDecision,
    TrustPolicy,
    strict_commerce_policy,
    open_discovery_policy,
    scoped_delegation_policy,
)


# --- TrustRequirement ---

class TestTrustRequirement:
    def test_empty_requirement_always_passes(self):
        req = TrustRequirement()
        ctx = EvaluationContext(agent_id="a1")
        assert req.evaluate(ctx) is True

    def test_min_trust_score_pass(self):
        req = TrustRequirement(min_trust_score=0.5)
        ctx = EvaluationContext(agent_id="a1", trust_score=0.7)
        assert req.evaluate(ctx) is True

    def test_min_trust_score_fail(self):
        req = TrustRequirement(min_trust_score=0.8)
        ctx = EvaluationContext(agent_id="a1", trust_score=0.5)
        assert req.evaluate(ctx) is False

    def test_min_endorsements_pass(self):
        req = TrustRequirement(min_endorsements=3)
        ctx = EvaluationContext(agent_id="a1", endorsement_count=5)
        assert req.evaluate(ctx) is True

    def test_min_endorsements_fail(self):
        req = TrustRequirement(min_endorsements=3)
        ctx = EvaluationContext(agent_id="a1", endorsement_count=1)
        assert req.evaluate(ctx) is False

    def test_max_chain_length_pass(self):
        req = TrustRequirement(max_chain_length=5)
        ctx = EvaluationContext(agent_id="a1", chain_length=3)
        assert req.evaluate(ctx) is True

    def test_max_chain_length_fail(self):
        req = TrustRequirement(max_chain_length=5)
        ctx = EvaluationContext(agent_id="a1", chain_length=7)
        assert req.evaluate(ctx) is False

    def test_required_scopes_pass(self):
        req = TrustRequirement(required_scopes=["read", "write"])
        ctx = EvaluationContext(agent_id="a1", scopes=["read", "write", "admin"])
        assert req.evaluate(ctx) is True

    def test_required_scopes_fail(self):
        req = TrustRequirement(required_scopes=["read", "write"])
        ctx = EvaluationContext(agent_id="a1", scopes=["read"])
        assert req.evaluate(ctx) is False

    def test_required_issuer_ids_pass(self):
        req = TrustRequirement(required_issuer_ids=["issuer-1", "issuer-2"])
        ctx = EvaluationContext(agent_id="a1", issuer_ids=["issuer-2", "issuer-3"])
        assert req.evaluate(ctx) is True

    def test_required_issuer_ids_fail(self):
        req = TrustRequirement(required_issuer_ids=["issuer-1"])
        ctx = EvaluationContext(agent_id="a1", issuer_ids=["issuer-2"])
        assert req.evaluate(ctx) is False

    def test_max_age_seconds_pass(self):
        req = TrustRequirement(max_age_seconds=3600)
        ctx = EvaluationContext(agent_id="a1", chain_age_seconds=1800)
        assert req.evaluate(ctx) is True

    def test_max_age_seconds_fail(self):
        req = TrustRequirement(max_age_seconds=3600)
        ctx = EvaluationContext(agent_id="a1", chain_age_seconds=7200)
        assert req.evaluate(ctx) is False

    def test_combined_requirements(self):
        req = TrustRequirement(min_trust_score=0.7, min_endorsements=2, max_chain_length=5)
        ctx = EvaluationContext(agent_id="a1", trust_score=0.8, endorsement_count=3, chain_length=3)
        assert req.evaluate(ctx) is True

    def test_combined_requirements_partial_fail(self):
        req = TrustRequirement(min_trust_score=0.7, min_endorsements=5)
        ctx = EvaluationContext(agent_id="a1", trust_score=0.8, endorsement_count=2)
        assert req.evaluate(ctx) is False


# --- PolicyDecision ---

class TestPolicyDecision:
    def test_allowed(self):
        d = PolicyDecision(PolicyAction.ALLOW, "r1", True, "ok", "a1")
        assert d.allowed() is True

    def test_denied(self):
        d = PolicyDecision(PolicyAction.DENY, "r1", False, "no", "a1")
        assert d.allowed() is False

    def test_to_dict(self):
        d = PolicyDecision(PolicyAction.DENY, "r1", False, "failed", "a1")
        data = d.to_dict()
        assert data["action"] == "deny"
        assert data["agent_id"] == "a1"


# --- TrustPolicy ---

class TestTrustPolicy:
    def test_no_rules_uses_default(self):
        p = TrustPolicy("empty")
        ctx = EvaluationContext(agent_id="a1", trust_score=0.9)
        decision = p.evaluate(ctx)
        assert decision.action == PolicyAction.DENY  # default

    def test_no_rules_allow_default(self):
        p = TrustPolicy("open", default_action=PolicyAction.ALLOW)
        ctx = EvaluationContext(agent_id="a1")
        assert p.evaluate(ctx).allowed() is True

    def test_single_rule_pass(self):
        p = TrustPolicy("test")
        p.add_rule(PolicyRule("min-trust", TrustRequirement(min_trust_score=0.5)))
        ctx = EvaluationContext(agent_id="a1", trust_score=0.8)
        assert p.evaluate(ctx).allowed() is True

    def test_single_rule_fail(self):
        p = TrustPolicy("test")
        p.add_rule(PolicyRule("min-trust", TrustRequirement(min_trust_score=0.8)))
        ctx = EvaluationContext(agent_id="a1", trust_score=0.3)
        decision = p.evaluate(ctx)
        assert decision.action == PolicyAction.DENY
        assert decision.rule_name == "min-trust"

    def test_priority_ordering(self):
        p = TrustPolicy("test")
        p.add_rule(PolicyRule("low", TrustRequirement(min_trust_score=0.5), priority=1))
        p.add_rule(PolicyRule("high", TrustRequirement(min_endorsements=10), priority=10))
        ctx = EvaluationContext(agent_id="a1", trust_score=0.8, endorsement_count=2)
        decision = p.evaluate(ctx)
        assert decision.rule_name == "high"  # higher priority checked first

    def test_custom_fail_action(self):
        p = TrustPolicy("test")
        p.add_rule(PolicyRule(
            "low-trust", TrustRequirement(min_trust_score=0.5),
            on_fail=PolicyAction.RATE_LIMIT,
        ))
        ctx = EvaluationContext(agent_id="a1", trust_score=0.2)
        assert p.evaluate(ctx).action == PolicyAction.RATE_LIMIT

    def test_batch_evaluation(self):
        p = TrustPolicy("test")
        p.add_rule(PolicyRule("min-trust", TrustRequirement(min_trust_score=0.5)))
        contexts = [
            EvaluationContext(agent_id="good", trust_score=0.8),
            EvaluationContext(agent_id="bad", trust_score=0.2),
            EvaluationContext(agent_id="ok", trust_score=0.5),
        ]
        decisions = p.evaluate_batch(contexts)
        assert len(decisions) == 3
        assert decisions[0].allowed() is True
        assert decisions[1].allowed() is False
        assert decisions[2].allowed() is True

    def test_serialization_roundtrip(self):
        p = TrustPolicy("test")
        p.add_rule(PolicyRule(
            "trust", TrustRequirement(min_trust_score=0.7, min_endorsements=2),
            description="Combined check", priority=5,
        ))
        json_str = p.to_json()
        p2 = TrustPolicy.from_json(json_str)
        assert p2.name == "test"
        assert len(p2.rules) == 1
        assert p2.rules[0].name == "trust"
        assert p2.rules[0].requirement.min_trust_score == 0.7
        assert p2.rules[0].priority == 5

    def test_from_dict(self):
        data = {
            "name": "loaded",
            "default_action": "allow",
            "rules": [{"name": "r1", "requirement": {"min_trust_score": 0.6}}],
        }
        p = TrustPolicy.from_dict(data)
        assert p.name == "loaded"
        assert p.default_action == PolicyAction.ALLOW


# --- Preset policies ---

class TestPresetPolicies:
    def test_strict_commerce_high_trust(self):
        p = strict_commerce_policy()
        ctx = EvaluationContext(
            agent_id="trusted",
            trust_score=0.9,
            endorsement_count=5,
            chain_length=2,
            chain_age_seconds=3600,
        )
        assert p.evaluate(ctx).allowed() is True

    def test_strict_commerce_low_trust(self):
        p = strict_commerce_policy()
        ctx = EvaluationContext(agent_id="untrusted", trust_score=0.3)
        decision = p.evaluate(ctx)
        assert decision.action == PolicyAction.DENY

    def test_open_discovery_basic(self):
        p = open_discovery_policy()
        ctx = EvaluationContext(agent_id="new", trust_score=0.5)
        assert p.evaluate(ctx).allowed() is True

    def test_open_discovery_very_low(self):
        p = open_discovery_policy()
        ctx = EvaluationContext(agent_id="sus", trust_score=0.1)
        assert p.evaluate(ctx).action == PolicyAction.RATE_LIMIT

    def test_scoped_delegation_pass(self):
        p = scoped_delegation_policy(["read", "write"])
        ctx = EvaluationContext(
            agent_id="delegated",
            trust_score=0.7,
            scopes=["read", "write", "admin"],
        )
        assert p.evaluate(ctx).allowed() is True

    def test_scoped_delegation_missing_scope(self):
        p = scoped_delegation_policy(["read", "write"])
        ctx = EvaluationContext(
            agent_id="limited",
            trust_score=0.7,
            scopes=["read"],
        )
        assert p.evaluate(ctx).action == PolicyAction.DENY
