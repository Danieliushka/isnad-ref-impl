"""
isnad epochs — EpochPolicy engine for time-bounded trust relationships.

Trust doesn't last forever. Epochs define windows during which trust scores,
delegations, and attestations remain valid. Different domains can run at
different speeds, and cross-domain bridges negotiate shared epoch parameters.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable


class DecayCurve(str, Enum):
    """How trust decays over an epoch's lifetime."""
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    STEP = "step"
    NONE = "none"


@dataclass
class RenewalCondition:
    """A condition that must be met to renew an epoch."""
    min_interactions: int = 0
    min_trust_score: float = 0.0
    requires_attestation: bool = False
    custom_check: Optional[Callable[["EpochState"], bool]] = None

    def evaluate(self, state: "EpochState") -> bool:
        if state.interaction_count < self.min_interactions:
            return False
        if state.current_trust_score < self.min_trust_score:
            return False
        if self.requires_attestation and not state.has_fresh_attestation:
            return False
        if self.custom_check is not None:
            return self.custom_check(state)
        return True


@dataclass
class EpochState:
    """Runtime state of an active epoch."""
    interaction_count: int = 0
    current_trust_score: float = 1.0
    has_fresh_attestation: bool = False
    last_interaction_time: float = 0.0


@dataclass
class EpochPolicy:
    """Defines trust epoch parameters for a domain."""
    domain: str
    duration_seconds: float = 3600.0
    decay_curve: DecayCurve = DecayCurve.LINEAR
    renewal_conditions: list[RenewalCondition] = field(default_factory=list)
    max_renewals: int = -1  # -1 = unlimited
    grace_period_seconds: float = 0.0

    def compute_decay(self, elapsed: float) -> float:
        """Return trust multiplier [0.0, 1.0] based on elapsed time within epoch."""
        if self.duration_seconds <= 0:
            return 0.0
        ratio = min(elapsed / self.duration_seconds, 1.0)
        if self.decay_curve == DecayCurve.NONE:
            return 1.0
        if self.decay_curve == DecayCurve.LINEAR:
            return 1.0 - ratio
        if self.decay_curve == DecayCurve.EXPONENTIAL:
            return math.exp(-3.0 * ratio)
        if self.decay_curve == DecayCurve.STEP:
            return 0.0 if ratio >= 1.0 else 1.0
        return 1.0 - ratio

    def can_renew(self, state: EpochState, renewal_count: int) -> bool:
        """Check if epoch can be renewed given current state."""
        if self.max_renewals >= 0 and renewal_count >= self.max_renewals:
            return False
        if not self.renewal_conditions:
            return True
        return all(c.evaluate(state) for c in self.renewal_conditions)


@dataclass
class Epoch:
    """A concrete epoch instance for an agent in a domain."""
    agent_id: str
    policy: EpochPolicy
    start_time: float = field(default_factory=time.time)
    renewal_count: int = 0
    state: EpochState = field(default_factory=EpochState)

    @property
    def end_time(self) -> float:
        return self.start_time + self.policy.duration_seconds

    @property
    def grace_end_time(self) -> float:
        return self.end_time + self.policy.grace_period_seconds

    def is_active(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        return now < self.end_time

    def is_in_grace(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        return self.end_time <= now < self.grace_end_time

    def is_expired(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        return now >= self.grace_end_time

    def elapsed(self, now: Optional[float] = None) -> float:
        now = now or time.time()
        return max(0.0, now - self.start_time)

    def trust_multiplier(self, now: Optional[float] = None) -> float:
        now = now or time.time()
        if self.is_expired(now):
            return 0.0
        if self.is_in_grace(now):
            return self.policy.compute_decay(self.policy.duration_seconds) * 0.5
        return self.policy.compute_decay(self.elapsed(now))

    def record_interaction(self, trust_score: Optional[float] = None, now: Optional[float] = None) -> None:
        now = now or time.time()
        self.state.interaction_count += 1
        self.state.last_interaction_time = now
        if trust_score is not None:
            self.state.current_trust_score = trust_score

    def try_renew(self, now: Optional[float] = None) -> bool:
        """Attempt to renew. Returns True if renewed."""
        now = now or time.time()
        if not self.policy.can_renew(self.state, self.renewal_count):
            return False
        self.start_time = now
        self.renewal_count += 1
        self.state = EpochState(
            current_trust_score=self.state.current_trust_score,
        )
        return True


# ─── Multi-speed Epochs ────────────────────────────────────────────


class EpochRegistry:
    """Track active epochs per agent across domains."""

    def __init__(self) -> None:
        self._epochs: dict[tuple[str, str], Epoch] = {}  # (agent_id, domain) -> Epoch
        self._policies: dict[str, EpochPolicy] = {}

    def register_policy(self, policy: EpochPolicy) -> None:
        self._policies[policy.domain] = policy

    def get_policy(self, domain: str) -> Optional[EpochPolicy]:
        return self._policies.get(domain)

    def start_epoch(self, agent_id: str, domain: str, now: Optional[float] = None) -> Epoch:
        policy = self._policies.get(domain)
        if policy is None:
            raise ValueError(f"No policy registered for domain '{domain}'")
        epoch = Epoch(agent_id=agent_id, policy=policy, start_time=now or time.time())
        self._epochs[(agent_id, domain)] = epoch
        return epoch

    def get_epoch(self, agent_id: str, domain: str) -> Optional[Epoch]:
        return self._epochs.get((agent_id, domain))

    def get_agent_epochs(self, agent_id: str) -> list[Epoch]:
        return [e for (aid, _), e in self._epochs.items() if aid == agent_id]

    def get_domain_epochs(self, domain: str) -> list[Epoch]:
        return [e for (_, d), e in self._epochs.items() if d == domain]

    def remove_expired(self, now: Optional[float] = None) -> list[tuple[str, str]]:
        now = now or time.time()
        expired = [(k, e) for k, e in self._epochs.items() if e.is_expired(now)]
        for k, _ in expired:
            del self._epochs[k]
        return [k for k, _ in expired]

    @property
    def active_count(self) -> int:
        return len(self._epochs)


# ─── Cross-Domain Bridge ──────────────────────────────────────────


@dataclass
class BridgeResult:
    """Result of cross-domain epoch negotiation."""
    negotiated_duration: float
    negotiated_decay: DecayCurve
    source_domain: str
    target_domain: str
    trust_transfer_ratio: float = 1.0


class CrossDomainBridge:
    """Composable epoch negotiation between domains."""

    def __init__(self, trust_transfer_ratio: float = 0.8) -> None:
        self.trust_transfer_ratio = max(0.0, min(1.0, trust_transfer_ratio))

    def negotiate(self, source: EpochPolicy, target: EpochPolicy) -> BridgeResult:
        """Negotiate epoch parameters between two domains.

        Takes the more conservative (shorter) duration and stricter decay.
        """
        negotiated_duration = min(source.duration_seconds, target.duration_seconds)

        decay_strictness = {
            DecayCurve.EXPONENTIAL: 3,
            DecayCurve.LINEAR: 2,
            DecayCurve.STEP: 1,
            DecayCurve.NONE: 0,
        }
        negotiated_decay = (
            source.decay_curve
            if decay_strictness[source.decay_curve] >= decay_strictness[target.decay_curve]
            else target.decay_curve
        )

        return BridgeResult(
            negotiated_duration=negotiated_duration,
            negotiated_decay=negotiated_decay,
            source_domain=source.domain,
            target_domain=target.domain,
            trust_transfer_ratio=self.trust_transfer_ratio,
        )

    def transfer_trust(self, epoch: Epoch, target_policy: EpochPolicy, now: Optional[float] = None) -> Epoch:
        """Create a new epoch in the target domain based on source epoch trust."""
        now = now or time.time()
        result = self.negotiate(epoch.policy, target_policy)
        new_epoch = Epoch(
            agent_id=epoch.agent_id,
            policy=EpochPolicy(
                domain=target_policy.domain,
                duration_seconds=result.negotiated_duration,
                decay_curve=result.negotiated_decay,
                renewal_conditions=target_policy.renewal_conditions,
                max_renewals=target_policy.max_renewals,
                grace_period_seconds=min(
                    epoch.policy.grace_period_seconds,
                    target_policy.grace_period_seconds,
                ),
            ),
            start_time=now,
            state=EpochState(
                current_trust_score=epoch.state.current_trust_score * result.trust_transfer_ratio,
            ),
        )
        return new_epoch


# ─── Adaptive Epoch Calculator ─────────────────────────────────────


class AdaptiveEpochCalculator:
    """Dynamic epoch duration based on interaction frequency.

    More frequent interactions → longer epochs (higher trust).
    Infrequent interactions → shorter epochs (trust erodes faster).
    """

    def __init__(
        self,
        base_duration: float = 3600.0,
        min_duration: float = 300.0,
        max_duration: float = 86400.0,
        frequency_weight: float = 1.0,
    ) -> None:
        self.base_duration = base_duration
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.frequency_weight = frequency_weight

    def calculate_duration(self, interactions: list[float]) -> float:
        """Calculate epoch duration from a list of interaction timestamps.

        Args:
            interactions: Sorted list of unix timestamps of past interactions.
        """
        if len(interactions) < 2:
            return self.base_duration

        intervals = [
            interactions[i + 1] - interactions[i]
            for i in range(len(interactions) - 1)
        ]
        avg_interval = sum(intervals) / len(intervals)

        if avg_interval <= 0:
            return self.max_duration

        # frequency = interactions per hour
        frequency = 3600.0 / avg_interval
        # Scale: more frequent → longer duration
        multiplier = 1.0 + math.log1p(frequency) * self.frequency_weight
        duration = self.base_duration * multiplier

        return max(self.min_duration, min(self.max_duration, duration))

    def recommend_policy(self, domain: str, interactions: list[float]) -> EpochPolicy:
        """Generate an EpochPolicy with adaptive duration."""
        duration = self.calculate_duration(interactions)

        # High frequency → gentle decay; low frequency → aggressive decay
        if duration >= self.base_duration * 1.5:
            decay = DecayCurve.LINEAR
        elif duration <= self.base_duration * 0.5:
            decay = DecayCurve.EXPONENTIAL
        else:
            decay = DecayCurve.LINEAR

        return EpochPolicy(
            domain=domain,
            duration_seconds=duration,
            decay_curve=decay,
            grace_period_seconds=duration * 0.1,
        )
