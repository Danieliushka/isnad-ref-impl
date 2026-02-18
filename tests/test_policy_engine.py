"""Tests for PolicyEngine, DefaultPolicies, and policy composition."""

import pytest

from isnad.policy import (
    TrustRequirement,
    EvaluationContext,
    PolicyRule,
    PolicyAction,
    PolicyDecision,
    TrustPolicy,
    PolicyEngine,
    DefaultPolicies,
)


# --- Helpers ---

def _ctx(score=0.5, age=0, endorsements=0, chain_len=1, agent_id="test-agent", **kw):
    return EvaluationContext(
        agent_id=agent_id,
        trust_score=score,
        chain_age_seconds=age,
        endorsement_count=endorsements,
        chain_length=chain_len,
        **kw,
    )


# --- DefaultPolicies ---

class TestDefaultPolicies:
    def test_strict_allows_high_trust_fresh(self):
        d = DefaultPolicies.STRICT.evaluate(_ctx(score=0.9, age=3600))
        assert d.allowed()

    def test_strict_denies_low_trust(self):
        d = DefaultPolicies.STRICT.evaluate(_ctx(score=0.5, age=100))
        assert d.action == PolicyAction.DENY

    def test_strict_denies_stale_attestation(self):
        d = DefaultPolicies.STRICT.evaluate(_ctx(score=0.9, age=100_000))
        assert d.action == PolicyAction.DENY

    def test_strict_boundary_score_exact(self):
        # Exactly 0.8 passes (>= threshold)
        d = DefaultPolicies.STRICT.evaluate(_ctx(score=0.8, age=100))
        assert d.allowed()

    def test_strict_boundary_score_just_below(self):
        d = DefaultPolicies.STRICT.evaluate(_ctx(score=0.79, age=100))
        assert d.action == PolicyAction.DENY

    def test_strict_boundary_age_exact(self):
        # Exactly 86400 passes (<= max)
        d = DefaultPolicies.STRICT.evaluate(_ctx(score=0.9, age=86400))
        assert d.allowed()

    def test_strict_boundary_age_over(self):
        d = DefaultPolicies.STRICT.evaluate(_ctx(score=0.9, age=86401))
        assert d.action == PolicyAction.DENY

    def test_moderate_allows_medium_trust(self):
        d = DefaultPolicies.MODERATE.evaluate(_ctx(score=0.6, age=300_000))
        assert d.allowed()

    def test_moderate_denies_low_trust(self):
        d = DefaultPolicies.MODERATE.evaluate(_ctx(score=0.3, age=100))
        assert d.action == PolicyAction.DENY

    def test_moderate_denies_old_attestation(self):
        d = DefaultPolicies.MODERATE.evaluate(_ctx(score=0.7, age=700_000))
        assert d.action == PolicyAction.DENY

    def test_permissive_allows_low_trust(self):
        d = DefaultPolicies.PERMISSIVE.evaluate(_ctx(score=0.3))
        assert d.allowed()

    def test_permissive_denies_very_low(self):
        d = DefaultPolicies.PERMISSIVE.evaluate(_ctx(score=0.1))
        assert d.action == PolicyAction.DENY

    def test_permissive_no_age_limit(self):
        d = DefaultPolicies.PERMISSIVE.evaluate(_ctx(score=0.5, age=999_999_999))
        assert d.allowed()


# --- PolicyEngine ---

class TestPolicyEngine:
    def test_no_policies_denies(self):
        engine = PolicyEngine()
        d = engine.evaluate(_ctx())
        assert d.action == PolicyAction.DENY
        assert "no policies" in d.reason.lower() or "No policies" in d.reason

    def test_single_policy_pass(self):
        engine = PolicyEngine()
        engine.add_policy(DefaultPolicies.PERMISSIVE)
        d = engine.evaluate(_ctx(score=0.5))
        assert d.allowed()

    def test_single_policy_fail(self):
        engine = PolicyEngine()
        engine.add_policy(DefaultPolicies.STRICT)
        d = engine.evaluate(_ctx(score=0.3))
        assert d.action == PolicyAction.DENY

    def test_strictest_wins_deny_over_allow(self):
        engine = PolicyEngine()
        engine.add_policy(DefaultPolicies.PERMISSIVE)  # would allow
        engine.add_policy(DefaultPolicies.STRICT)       # would deny (score too low)
        d = engine.evaluate(_ctx(score=0.5, age=100))
        assert d.action == PolicyAction.DENY

    def test_strictest_wins_all_allow(self):
        engine = PolicyEngine()
        engine.add_policy(DefaultPolicies.PERMISSIVE)
        engine.add_policy(DefaultPolicies.MODERATE)
        engine.add_policy(DefaultPolicies.STRICT)
        d = engine.evaluate(_ctx(score=0.9, age=100))
        assert d.allowed()

    def test_review_over_allow(self):
        review_policy = TrustPolicy("review-test")
        review_policy.add_rule(PolicyRule(
            name="review-low",
            requirement=TrustRequirement(min_endorsements=5),
            on_fail=PolicyAction.REQUIRE_REVIEW,
        ))
        engine = PolicyEngine()
        engine.add_policy(DefaultPolicies.PERMISSIVE)  # allow
        engine.add_policy(review_policy)                 # require_review
        d = engine.evaluate(_ctx(score=0.5, endorsements=2))
        assert d.action == PolicyAction.REQUIRE_REVIEW

    def test_deny_over_review(self):
        review_policy = TrustPolicy("review-test")
        review_policy.add_rule(PolicyRule(
            name="review-low",
            requirement=TrustRequirement(min_endorsements=5),
            on_fail=PolicyAction.REQUIRE_REVIEW,
        ))
        engine = PolicyEngine()
        engine.add_policy(review_policy)
        engine.add_policy(DefaultPolicies.STRICT)  # will deny
        d = engine.evaluate(_ctx(score=0.3, endorsements=2))
        assert d.action == PolicyAction.DENY

    def test_chaining_add_policy(self):
        engine = PolicyEngine()
        result = engine.add_policy(DefaultPolicies.PERMISSIVE)
        assert result is engine  # fluent API

    def test_batch_evaluation(self):
        engine = PolicyEngine()
        engine.add_policy(DefaultPolicies.MODERATE)
        contexts = [_ctx(score=0.7, age=100), _ctx(score=0.3, age=100)]
        decisions = engine.evaluate_batch(contexts)
        assert len(decisions) == 2
        assert decisions[0].allowed()
        assert decisions[1].action == PolicyAction.DENY

    def test_reason_mentions_policy_count(self):
        engine = PolicyEngine()
        engine.add_policy(DefaultPolicies.PERMISSIVE)
        engine.add_policy(DefaultPolicies.MODERATE)
        d = engine.evaluate(_ctx(score=0.6, age=100))
        assert "2 policies" in d.reason

    def test_three_policies_strictest_wins(self):
        rate_limit_policy = TrustPolicy("rl")
        rate_limit_policy.add_rule(PolicyRule(
            name="rl-check",
            requirement=TrustRequirement(min_endorsements=10),
            on_fail=PolicyAction.RATE_LIMIT,
        ))
        engine = PolicyEngine()
        engine.add_policy(DefaultPolicies.PERMISSIVE)  # allow
        engine.add_policy(rate_limit_policy)             # rate_limit
        # score=0.5 passes permissive, endorsements=0 fails rl → RATE_LIMIT
        d = engine.evaluate(_ctx(score=0.5, endorsements=0))
        assert d.action == PolicyAction.RATE_LIMIT

    def test_context_agent_id_preserved(self):
        engine = PolicyEngine()
        engine.add_policy(DefaultPolicies.PERMISSIVE)
        d = engine.evaluate(_ctx(score=0.5, agent_id="my-agent-42"))
        assert d.context_agent_id == "my-agent-42"


# --- Edge Cases ---

class TestEdgeCases:
    def test_zero_score(self):
        d = DefaultPolicies.STRICT.evaluate(_ctx(score=0.0))
        assert d.action == PolicyAction.DENY

    def test_perfect_score(self):
        d = DefaultPolicies.STRICT.evaluate(_ctx(score=1.0, age=0))
        assert d.allowed()

    def test_negative_age(self):
        # Shouldn't happen but shouldn't crash
        d = DefaultPolicies.STRICT.evaluate(_ctx(score=0.9, age=-1))
        assert d.allowed()

    def test_engine_duplicate_policies(self):
        engine = PolicyEngine()
        engine.add_policy(DefaultPolicies.STRICT)
        engine.add_policy(DefaultPolicies.STRICT)
        d = engine.evaluate(_ctx(score=0.9, age=100))
        assert d.allowed()
