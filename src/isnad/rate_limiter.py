"""TrustRateLimiter — Dynamic rate limiting based on isnad trust scores.

Higher trust = more requests allowed. Unknown agents get baseline limits.
Integrates with TrustPolicy engine for consistent trust evaluation.

Usage:
    limiter = TrustRateLimiter(
        tiers=[
            RateTier(min_trust=0.8, requests_per_minute=100, burst=20),
            RateTier(min_trust=0.5, requests_per_minute=50, burst=10),
            RateTier(min_trust=0.0, requests_per_minute=10, burst=3),
        ]
    )

    # Check if agent can make a request
    result = limiter.check("agent_id", trust_score=0.75)
    if result.allowed:
        process_request()
    else:
        return 429, {"retry_after": result.retry_after}
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RateTier:
    """A rate limit tier based on trust score threshold."""
    min_trust: float
    requests_per_minute: int
    burst: int = 5
    label: str = ""

    def __post_init__(self):
        if not self.label:
            self.label = f"trust>={self.min_trust}"


@dataclass
class RateCheckResult:
    """Result of a rate limit check."""
    allowed: bool
    tier: RateTier
    remaining: int
    retry_after: float = 0.0
    agent_id: str = ""
    trust_score: float = 0.0


@dataclass
class _AgentBucket:
    """Token bucket for a single agent."""
    tokens: float
    max_tokens: int
    refill_rate: float  # tokens per second
    last_refill: float = 0.0

    def refill(self, now: float) -> None:
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def consume(self, now: float) -> bool:
        self.refill(now)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    def time_until_available(self, now: float) -> float:
        self.refill(now)
        if self.tokens >= 1.0:
            return 0.0
        deficit = 1.0 - self.tokens
        return deficit / self.refill_rate if self.refill_rate > 0 else float("inf")


class TrustRateLimiter:
    """Dynamic rate limiter that adjusts limits based on trust scores.

    Uses token bucket algorithm per agent. Tier is selected based on
    the agent's current trust score — trust can change between requests.
    """

    def __init__(self, tiers: list[RateTier] | None = None):
        if tiers is None:
            tiers = [
                RateTier(min_trust=0.8, requests_per_minute=100, burst=20, label="trusted"),
                RateTier(min_trust=0.5, requests_per_minute=50, burst=10, label="known"),
                RateTier(min_trust=0.0, requests_per_minute=10, burst=3, label="unknown"),
            ]
        # Sort descending by min_trust for matching
        self._tiers = sorted(tiers, key=lambda t: t.min_trust, reverse=True)
        self._buckets: dict[str, _AgentBucket] = {}
        self._agent_tiers: dict[str, str] = {}  # agent_id -> tier label

    @property
    def tiers(self) -> list[RateTier]:
        return list(self._tiers)

    def get_tier(self, trust_score: float) -> RateTier:
        """Find the appropriate tier for a trust score."""
        for tier in self._tiers:
            if trust_score >= tier.min_trust:
                return tier
        return self._tiers[-1]  # Fallback to lowest tier

    def _get_or_create_bucket(self, agent_id: str, tier: RateTier, now: float) -> _AgentBucket:
        """Get existing bucket or create new one. Recreate if tier changed."""
        current_tier_label = self._agent_tiers.get(agent_id)
        if agent_id in self._buckets and current_tier_label == tier.label:
            return self._buckets[agent_id]

        # New agent or tier changed — create fresh bucket
        refill_rate = tier.requests_per_minute / 60.0
        bucket = _AgentBucket(
            tokens=float(tier.burst),
            max_tokens=tier.burst,
            refill_rate=refill_rate,
            last_refill=now,
        )
        self._buckets[agent_id] = bucket
        self._agent_tiers[agent_id] = tier.label
        return bucket

    def check(self, agent_id: str, trust_score: float, now: float | None = None) -> RateCheckResult:
        """Check if an agent's request should be allowed.

        Args:
            agent_id: Unique agent identifier
            trust_score: Current trust score (0.0 - 1.0)
            now: Current timestamp (defaults to time.time())

        Returns:
            RateCheckResult with allowed status, remaining tokens, retry info
        """
        if now is None:
            now = time.time()

        tier = self.get_tier(trust_score)
        bucket = self._get_or_create_bucket(agent_id, tier, now)

        allowed = bucket.consume(now)
        remaining = int(bucket.tokens)
        retry_after = 0.0 if allowed else bucket.time_until_available(now)

        return RateCheckResult(
            allowed=allowed,
            tier=tier,
            remaining=remaining,
            retry_after=round(retry_after, 3),
            agent_id=agent_id,
            trust_score=trust_score,
        )

    def reset(self, agent_id: str) -> None:
        """Reset rate limit state for an agent."""
        self._buckets.pop(agent_id, None)
        self._agent_tiers.pop(agent_id, None)

    def reset_all(self) -> None:
        """Reset all rate limit state."""
        self._buckets.clear()
        self._agent_tiers.clear()

    def stats(self) -> dict:
        """Get current limiter statistics."""
        now = time.time()
        agents = {}
        for agent_id, bucket in self._buckets.items():
            bucket.refill(now)
            agents[agent_id] = {
                "tier": self._agent_tiers.get(agent_id, "unknown"),
                "remaining_tokens": round(bucket.tokens, 1),
                "max_tokens": bucket.max_tokens,
            }
        return {
            "total_agents": len(self._buckets),
            "tiers": [{"label": t.label, "min_trust": t.min_trust, "rpm": t.requests_per_minute, "burst": t.burst} for t in self._tiers],
            "agents": agents,
        }
