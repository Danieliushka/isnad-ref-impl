"""Tests for isnad.epochs — EpochPolicy engine."""

import time
import pytest
from isnad.epochs import (
    DecayCurve,
    RenewalCondition,
    EpochState,
    EpochPolicy,
    Epoch,
    EpochRegistry,
    CrossDomainBridge,
    BridgeResult,
    AdaptiveEpochCalculator,
)


NOW = 1_000_000.0


# ─── EpochPolicy decay ─────────────────────────────────────────────


class TestEpochPolicyDecay:
    def test_linear_decay_midpoint(self):
        p = EpochPolicy(domain="d", duration_seconds=100, decay_curve=DecayCurve.LINEAR)
        assert p.compute_decay(50) == pytest.approx(0.5)

    def test_linear_decay_full(self):
        p = EpochPolicy(domain="d", duration_seconds=100, decay_curve=DecayCurve.LINEAR)
        assert p.compute_decay(100) == pytest.approx(0.0)

    def test_exponential_decay_start(self):
        p = EpochPolicy(domain="d", duration_seconds=100, decay_curve=DecayCurve.EXPONENTIAL)
        assert p.compute_decay(0) == pytest.approx(1.0)

    def test_exponential_decay_decreases(self):
        p = EpochPolicy(domain="d", duration_seconds=100, decay_curve=DecayCurve.EXPONENTIAL)
        assert p.compute_decay(50) < 1.0

    def test_step_decay_before_end(self):
        p = EpochPolicy(domain="d", duration_seconds=100, decay_curve=DecayCurve.STEP)
        assert p.compute_decay(99) == 1.0

    def test_step_decay_at_end(self):
        p = EpochPolicy(domain="d", duration_seconds=100, decay_curve=DecayCurve.STEP)
        assert p.compute_decay(100) == 0.0

    def test_none_decay(self):
        p = EpochPolicy(domain="d", duration_seconds=100, decay_curve=DecayCurve.NONE)
        assert p.compute_decay(99) == 1.0


# ─── Epoch lifecycle ───────────────────────────────────────────────


class TestEpochLifecycle:
    def test_active_before_end(self):
        p = EpochPolicy(domain="d", duration_seconds=100)
        e = Epoch(agent_id="a1", policy=p, start_time=NOW)
        assert e.is_active(NOW + 50)

    def test_expired_after_end(self):
        p = EpochPolicy(domain="d", duration_seconds=100, grace_period_seconds=0)
        e = Epoch(agent_id="a1", policy=p, start_time=NOW)
        assert e.is_expired(NOW + 100)

    def test_grace_period(self):
        p = EpochPolicy(domain="d", duration_seconds=100, grace_period_seconds=20)
        e = Epoch(agent_id="a1", policy=p, start_time=NOW)
        assert e.is_in_grace(NOW + 110)
        assert not e.is_expired(NOW + 110)
        assert e.is_expired(NOW + 120)

    def test_trust_multiplier_zero_when_expired(self):
        p = EpochPolicy(domain="d", duration_seconds=100, grace_period_seconds=0)
        e = Epoch(agent_id="a1", policy=p, start_time=NOW)
        assert e.trust_multiplier(NOW + 200) == 0.0

    def test_record_interaction(self):
        p = EpochPolicy(domain="d", duration_seconds=100)
        e = Epoch(agent_id="a1", policy=p, start_time=NOW)
        e.record_interaction(trust_score=0.9, now=NOW + 10)
        assert e.state.interaction_count == 1
        assert e.state.current_trust_score == 0.9


# ─── Renewal ───────────────────────────────────────────────────────


class TestRenewal:
    def test_renew_success(self):
        p = EpochPolicy(domain="d", duration_seconds=100, max_renewals=2)
        e = Epoch(agent_id="a1", policy=p, start_time=NOW)
        assert e.try_renew(NOW + 100)
        assert e.renewal_count == 1
        assert e.start_time == NOW + 100

    def test_renew_exceeds_max(self):
        p = EpochPolicy(domain="d", duration_seconds=100, max_renewals=1)
        e = Epoch(agent_id="a1", policy=p, start_time=NOW)
        assert e.try_renew(NOW + 100)
        assert not e.try_renew(NOW + 200)

    def test_renewal_condition_fails(self):
        cond = RenewalCondition(min_interactions=5)
        p = EpochPolicy(domain="d", duration_seconds=100, renewal_conditions=[cond])
        e = Epoch(agent_id="a1", policy=p, start_time=NOW)
        e.record_interaction(now=NOW + 10)
        assert not e.try_renew(NOW + 100)

    def test_renewal_condition_passes(self):
        cond = RenewalCondition(min_interactions=1)
        p = EpochPolicy(domain="d", duration_seconds=100, renewal_conditions=[cond])
        e = Epoch(agent_id="a1", policy=p, start_time=NOW)
        e.record_interaction(now=NOW + 10)
        assert e.try_renew(NOW + 100)


# ─── EpochRegistry ────────────────────────────────────────────────


class TestEpochRegistry:
    def test_register_and_start(self):
        reg = EpochRegistry()
        reg.register_policy(EpochPolicy(domain="finance", duration_seconds=60))
        e = reg.start_epoch("a1", "finance", now=NOW)
        assert e.agent_id == "a1"
        assert reg.active_count == 1

    def test_get_agent_epochs(self):
        reg = EpochRegistry()
        reg.register_policy(EpochPolicy(domain="d1", duration_seconds=60))
        reg.register_policy(EpochPolicy(domain="d2", duration_seconds=120))
        reg.start_epoch("a1", "d1", now=NOW)
        reg.start_epoch("a1", "d2", now=NOW)
        assert len(reg.get_agent_epochs("a1")) == 2

    def test_remove_expired(self):
        reg = EpochRegistry()
        reg.register_policy(EpochPolicy(domain="d", duration_seconds=10, grace_period_seconds=0))
        reg.start_epoch("a1", "d", now=NOW)
        removed = reg.remove_expired(NOW + 20)
        assert len(removed) == 1
        assert reg.active_count == 0

    def test_no_policy_raises(self):
        reg = EpochRegistry()
        with pytest.raises(ValueError):
            reg.start_epoch("a1", "unknown", now=NOW)


# ─── CrossDomainBridge ────────────────────────────────────────────


class TestCrossDomainBridge:
    def test_negotiate_takes_shorter_duration(self):
        bridge = CrossDomainBridge()
        s = EpochPolicy(domain="fast", duration_seconds=60)
        t = EpochPolicy(domain="slow", duration_seconds=3600)
        result = bridge.negotiate(s, t)
        assert result.negotiated_duration == 60

    def test_negotiate_takes_stricter_decay(self):
        bridge = CrossDomainBridge()
        s = EpochPolicy(domain="a", decay_curve=DecayCurve.EXPONENTIAL)
        t = EpochPolicy(domain="b", decay_curve=DecayCurve.LINEAR)
        result = bridge.negotiate(s, t)
        assert result.negotiated_decay == DecayCurve.EXPONENTIAL

    def test_transfer_trust_reduces_score(self):
        bridge = CrossDomainBridge(trust_transfer_ratio=0.5)
        src_policy = EpochPolicy(domain="src", duration_seconds=100)
        tgt_policy = EpochPolicy(domain="tgt", duration_seconds=200)
        src = Epoch(agent_id="a1", policy=src_policy, start_time=NOW,
                    state=EpochState(current_trust_score=0.8))
        new = bridge.transfer_trust(src, tgt_policy, now=NOW)
        assert new.state.current_trust_score == pytest.approx(0.4)
        assert new.policy.domain == "tgt"


# ─── AdaptiveEpochCalculator ──────────────────────────────────────


class TestAdaptiveCalculator:
    def test_few_interactions_returns_base(self):
        calc = AdaptiveEpochCalculator(base_duration=3600)
        assert calc.calculate_duration([NOW]) == 3600

    def test_frequent_interactions_increase_duration(self):
        calc = AdaptiveEpochCalculator(base_duration=3600)
        # interactions every 60 seconds
        ts = [NOW + i * 60 for i in range(20)]
        duration = calc.calculate_duration(ts)
        assert duration > 3600

    def test_infrequent_interactions_stay_near_base(self):
        calc = AdaptiveEpochCalculator(base_duration=3600)
        # interactions every 2 hours
        ts = [NOW + i * 7200 for i in range(5)]
        duration = calc.calculate_duration(ts)
        assert duration < 3600 * 3  # not wildly inflated

    def test_respects_max_duration(self):
        calc = AdaptiveEpochCalculator(base_duration=3600, max_duration=7200)
        ts = [NOW + i for i in range(100)]  # very frequent
        assert calc.calculate_duration(ts) <= 7200

    def test_recommend_policy(self):
        calc = AdaptiveEpochCalculator(base_duration=3600)
        ts = [NOW + i * 60 for i in range(20)]
        policy = calc.recommend_policy("chat", ts)
        assert policy.domain == "chat"
        assert policy.duration_seconds > 0
        assert policy.grace_period_seconds > 0
