"""EpochPolicy — Multi-speed trust epochs with cross-domain bridging.

Different trust domains need different temporal rhythms. Payment trust
decays fast (30s epochs) because fraud is immediate. Reputation decays
slowly (weekly epochs). Identity is near-permanent (monthly epochs).

The EpochManager handles per-domain epoch tracking, decay computation,
and cross-domain trust transfer with conservative bridging.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EpochPolicy:
    """Defines epoch behavior for a trust domain."""

    domain: str
    epoch_duration_seconds: int
    decay_curve: str  # "linear", "exponential", "step"
    decay_rate: float  # 0.0–1.0, how fast trust decays per epoch
    min_observations: int  # minimum interactions before scoring
    boundary_condition: str = "time"  # "time", "event_count", "semantic"

    def __post_init__(self) -> None:
        if self.decay_curve not in ("linear", "exponential", "step"):
            raise ValueError(
                f"Invalid decay_curve '{self.decay_curve}'; "
                "must be 'linear', 'exponential', or 'step'"
            )
        if not (0.0 <= self.decay_rate <= 1.0):
            raise ValueError(
                f"decay_rate must be in [0.0, 1.0], got {self.decay_rate}"
            )
        if self.boundary_condition not in ("time", "event_count", "semantic"):
            raise ValueError(
                f"Invalid boundary_condition '{self.boundary_condition}'; "
                "must be 'time', 'event_count', or 'semantic'"
            )
        if self.epoch_duration_seconds <= 0:
            raise ValueError("epoch_duration_seconds must be positive")


# ── Default policies ─────────────────────────────────────────────────

PAYMENT_EPOCH = EpochPolicy(
    domain="payment",
    epoch_duration_seconds=30,
    decay_curve="exponential",
    decay_rate=0.3,
    min_observations=5,
    boundary_condition="time",
)

REPUTATION_EPOCH = EpochPolicy(
    domain="reputation",
    epoch_duration_seconds=7 * 24 * 3600,  # 7 days
    decay_curve="linear",
    decay_rate=0.1,
    min_observations=10,
    boundary_condition="time",
)

IDENTITY_EPOCH = EpochPolicy(
    domain="identity",
    epoch_duration_seconds=30 * 24 * 3600,  # 30 days
    decay_curve="step",
    decay_rate=0.05,
    min_observations=3,
    boundary_condition="time",
)


class EpochManager:
    """Manages multi-speed epochs across trust domains.

    Each domain runs on its own clock. The manager tracks registration
    time, computes current epoch numbers, decay multipliers, and
    conservative cross-domain trust bridging.
    """

    def __init__(self) -> None:
        self._policies: dict[str, EpochPolicy] = {}
        self._start_times: dict[str, float] = {}
        self._event_counts: dict[str, int] = {}

    def register_policy(self, policy: EpochPolicy) -> None:
        """Register a domain's epoch policy. Re-registering resets the clock."""
        self._policies[policy.domain] = policy
        self._start_times[policy.domain] = time.time()
        self._event_counts[policy.domain] = 0

    def _require_policy(self, domain: str) -> EpochPolicy:
        """Get policy or raise."""
        if domain not in self._policies:
            raise KeyError(f"No policy registered for domain '{domain}'")
        return self._policies[domain]

    def get_current_epoch(self, domain: str) -> int:
        """Current epoch number (0-indexed) based on elapsed time."""
        policy = self._require_policy(domain)
        elapsed = time.time() - self._start_times[domain]
        return int(elapsed // policy.epoch_duration_seconds)

    def record_event(self, domain: str) -> None:
        """Record an event for event_count boundary tracking."""
        self._require_policy(domain)
        self._event_counts[domain] = self._event_counts.get(domain, 0) + 1

    def compute_decay(self, domain: str, epochs_elapsed: int) -> float:
        """Compute decay multiplier for a given number of elapsed epochs.

        Returns a value in [0.0, 1.0] where 1.0 means no decay.
        """
        policy = self._require_policy(domain)

        if epochs_elapsed <= 0:
            return 1.0

        rate = policy.decay_rate

        if policy.decay_curve == "linear":
            return max(0.0, 1.0 - rate * epochs_elapsed)

        if policy.decay_curve == "exponential":
            return math.pow(1.0 - rate, epochs_elapsed)

        if policy.decay_curve == "step":
            # Step decay: full trust for a while, then drops by rate at
            # each epoch boundary. Implemented as floor-based steps.
            return max(0.0, 1.0 - rate * (epochs_elapsed))

        return 1.0  # unreachable due to validation

    def should_rotate(self, domain: str) -> bool:
        """Whether current epoch should end based on boundary condition.

        For time-based: checks if we've crossed an epoch boundary.
        For event_count: checks if events >= min_observations.
        For semantic: always returns False (requires external trigger).
        """
        policy = self._require_policy(domain)

        if policy.boundary_condition == "time":
            elapsed = time.time() - self._start_times[domain]
            # We should rotate if we're past the first epoch boundary
            return elapsed >= policy.epoch_duration_seconds

        if policy.boundary_condition == "event_count":
            return self._event_counts.get(domain, 0) >= policy.min_observations

        # semantic — external trigger needed
        return False

    def cross_domain_bridge(self, source: str, target: str) -> float:
        """Trust transfer multiplier from source domain to target domain.

        Conservative bridging: transferring trust from a fast-moving domain
        (short epochs) to a slow-moving domain (long epochs) is penalised,
        because fast-domain trust hasn't been tested over long time horizons.

        Same-domain transfer returns 1.0.
        The multiplier is: min(source_duration, target_duration) / max(...)
        This gives a ratio in (0.0, 1.0].
        """
        if source == target:
            return 1.0

        src_policy = self._require_policy(source)
        tgt_policy = self._require_policy(target)

        src_dur = src_policy.epoch_duration_seconds
        tgt_dur = tgt_policy.epoch_duration_seconds

        return min(src_dur, tgt_dur) / max(src_dur, tgt_dur)
