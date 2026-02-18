"""Tests for TrustRateLimiter."""

import pytest
from isnad.rate_limiter import TrustRateLimiter, RateTier, RateCheckResult


class TestRateTier:
    def test_default_label(self):
        tier = RateTier(min_trust=0.5, requests_per_minute=50)
        assert tier.label == "trust>=0.5"

    def test_custom_label(self):
        tier = RateTier(min_trust=0.8, requests_per_minute=100, label="premium")
        assert tier.label == "premium"


class TestTrustRateLimiter:
    def test_default_tiers(self):
        limiter = TrustRateLimiter()
        assert len(limiter.tiers) == 3

    def test_get_tier_high_trust(self):
        limiter = TrustRateLimiter()
        tier = limiter.get_tier(0.9)
        assert tier.label == "trusted"
        assert tier.requests_per_minute == 100

    def test_get_tier_medium_trust(self):
        limiter = TrustRateLimiter()
        tier = limiter.get_tier(0.6)
        assert tier.label == "known"
        assert tier.requests_per_minute == 50

    def test_get_tier_low_trust(self):
        limiter = TrustRateLimiter()
        tier = limiter.get_tier(0.2)
        assert tier.label == "unknown"
        assert tier.requests_per_minute == 10

    def test_allow_within_burst(self):
        limiter = TrustRateLimiter()
        now = 1000.0
        # Trusted agent gets burst=20
        for i in range(20):
            result = limiter.check("agent_a", trust_score=0.9, now=now)
            assert result.allowed, f"Request {i} should be allowed within burst"

    def test_deny_after_burst(self):
        limiter = TrustRateLimiter()
        now = 1000.0
        # Unknown agent gets burst=3
        for _ in range(3):
            limiter.check("agent_b", trust_score=0.1, now=now)
        result = limiter.check("agent_b", trust_score=0.1, now=now)
        assert not result.allowed
        assert result.retry_after > 0

    def test_refill_over_time(self):
        limiter = TrustRateLimiter()
        now = 1000.0
        # Exhaust burst
        for _ in range(3):
            limiter.check("agent_c", trust_score=0.1, now=now)
        # Wait 60 seconds (10 rpm = 1 token every 6 seconds)
        result = limiter.check("agent_c", trust_score=0.1, now=now + 60)
        assert result.allowed

    def test_tier_upgrade_on_trust_change(self):
        limiter = TrustRateLimiter()
        now = 1000.0
        # Start as unknown
        result = limiter.check("agent_d", trust_score=0.2, now=now)
        assert result.tier.label == "unknown"
        # Trust increases — new tier
        result = limiter.check("agent_d", trust_score=0.9, now=now + 1)
        assert result.tier.label == "trusted"
        assert result.remaining == 19  # fresh burst of 20, minus 1

    def test_reset_agent(self):
        limiter = TrustRateLimiter()
        now = 1000.0
        limiter.check("agent_e", trust_score=0.5, now=now)
        limiter.reset("agent_e")
        assert limiter.stats()["total_agents"] == 0

    def test_reset_all(self):
        limiter = TrustRateLimiter()
        now = 1000.0
        limiter.check("a1", trust_score=0.5, now=now)
        limiter.check("a2", trust_score=0.9, now=now)
        limiter.reset_all()
        assert limiter.stats()["total_agents"] == 0

    def test_stats(self):
        limiter = TrustRateLimiter()
        now = 1000.0
        limiter.check("agent_f", trust_score=0.9, now=now)
        stats = limiter.stats()
        assert stats["total_agents"] == 1
        assert "agent_f" in stats["agents"]
        assert stats["agents"]["agent_f"]["tier"] == "trusted"

    def test_custom_tiers(self):
        tiers = [
            RateTier(min_trust=0.9, requests_per_minute=200, burst=50, label="vip"),
            RateTier(min_trust=0.0, requests_per_minute=5, burst=1, label="default"),
        ]
        limiter = TrustRateLimiter(tiers=tiers)
        assert limiter.get_tier(0.95).label == "vip"
        assert limiter.get_tier(0.5).label == "default"

    def test_result_fields(self):
        limiter = TrustRateLimiter()
        result = limiter.check("agent_g", trust_score=0.75, now=1000.0)
        assert isinstance(result, RateCheckResult)
        assert result.agent_id == "agent_g"
        assert result.trust_score == 0.75
        assert result.allowed
        assert result.remaining >= 0


class TestEdgeCases:
    def test_zero_trust(self):
        limiter = TrustRateLimiter()
        result = limiter.check("zero", trust_score=0.0, now=1000.0)
        assert result.allowed  # Still gets baseline
        assert result.tier.label == "unknown"

    def test_perfect_trust(self):
        limiter = TrustRateLimiter()
        result = limiter.check("perfect", trust_score=1.0, now=1000.0)
        assert result.tier.label == "trusted"

    def test_rapid_fire(self):
        """Simulate rapid requests from untrusted agent."""
        limiter = TrustRateLimiter()
        now = 1000.0
        allowed = sum(
            1 for _ in range(20)
            if limiter.check("spammer", trust_score=0.1, now=now).allowed
        )
        assert allowed == 3  # Only burst amount

    def test_concurrent_agents(self):
        """Multiple agents don't interfere with each other."""
        limiter = TrustRateLimiter()
        now = 1000.0
        # Exhaust agent_1
        for _ in range(3):
            limiter.check("agent_1", trust_score=0.1, now=now)
        # agent_2 should still work
        result = limiter.check("agent_2", trust_score=0.1, now=now)
        assert result.allowed
