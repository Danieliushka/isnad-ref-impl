"""
isnad.metrics — Quantitative security metrics for isnad deployments.

Provides three metric classes for analysing trust network health:

- NetworkHealthMetrics: coverage, chain depth, orphans, witness diversity
- SecurityPosture: identity strength, freshness, revocation coverage, anomaly rate
- TrustDistribution: statistical analysis of trust scores across the network

Usage:
    from isnad.core import TrustChain, AgentIdentity
    from isnad.metrics import NetworkHealthMetrics, SecurityPosture, TrustDistribution

    health = NetworkHealthMetrics(chain)
    print(health.coverage_ratio, health.orphan_ratio)

    posture = SecurityPosture(chain, revocations=registry, current_epoch_start=t)
    print(posture.freshness, posture.revocation_coverage)

    dist = TrustDistribution(chain, agent_ids)
    print(dist.mean_trust_score, dist.trust_histogram(bins=5))
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Sequence

from isnad.core import (
    AgentIdentity,
    Attestation,
    TrustChain,
    RevocationRegistry,
)


# ─── NetworkHealthMetrics ──────────────────────────────────────────

@dataclass
class NetworkHealthMetrics:
    """Computes health metrics for a trust network.

    Parameters:
        chain: The TrustChain to analyse.
        agent_ids: Explicit set of all known agents. If None, derived from
                   attestation subjects and witnesses.
    """

    chain: TrustChain
    agent_ids: Optional[set[str]] = field(default=None)

    def __post_init__(self):
        if self.agent_ids is None:
            self.agent_ids = self._discover_agents()

    def _discover_agents(self) -> set[str]:
        agents: set[str] = set()
        for att in self.chain.attestations:
            agents.add(att.subject)
            agents.add(att.witness)
        return agents

    @property
    def coverage_ratio(self) -> float:
        """Fraction of agents with at least 1 attestation (as subject)."""
        if not self.agent_ids:
            return 0.0
        covered = sum(
            1 for a in self.agent_ids if a in self.chain._by_subject
        )
        return covered / len(self.agent_ids)

    @property
    def avg_chain_length(self) -> float:
        """Average attestation chain depth across all agents.

        For each agent, chain depth = number of attestations where
        they are the subject.
        """
        if not self.agent_ids:
            return 0.0
        depths = [
            len(self.chain._by_subject.get(a, []))
            for a in self.agent_ids
        ]
        return sum(depths) / len(depths)

    @property
    def orphan_ratio(self) -> float:
        """Fraction of agents with no incoming attestations (not a subject)."""
        if not self.agent_ids:
            return 0.0
        orphans = sum(
            1 for a in self.agent_ids if a not in self.chain._by_subject
        )
        return orphans / len(self.agent_ids)

    @property
    def witness_diversity(self) -> float:
        """Average number of unique witnesses per agent (subjects only)."""
        if not self.agent_ids:
            return 0.0
        diversities: list[int] = []
        for a in self.agent_ids:
            atts = self.chain._by_subject.get(a, [])
            if atts:
                diversities.append(len({att.witness for att in atts}))
        if not diversities:
            return 0.0
        return sum(diversities) / len(diversities)

    def to_dict(self) -> dict:
        return {
            "coverage_ratio": self.coverage_ratio,
            "avg_chain_length": self.avg_chain_length,
            "orphan_ratio": self.orphan_ratio,
            "witness_diversity": self.witness_diversity,
            "total_agents": len(self.agent_ids) if self.agent_ids else 0,
            "total_attestations": len(self.chain.attestations),
        }


# ─── SecurityPosture ──────────────────────────────────────────────

@dataclass
class SecurityPosture:
    """Aggregate security score for an isnad deployment.

    Parameters:
        chain: The TrustChain to analyse.
        agent_ids: Known agents. Derived from chain if None.
        revocations: RevocationRegistry for revocation coverage checks.
        compromised_ids: Set of agent IDs known to be compromised.
        bootstrap_anchors: Dict mapping agent_id → number of bootstrap
                           anchor factors (e.g. 2 = multi-factor).
        current_epoch_start: ISO timestamp; attestations after this are "fresh".
        anomaly_scores: Dict mapping agent_id → anomaly score (0.0-1.0).
        anomaly_threshold: Agents above this score count as anomalous.
    """

    chain: TrustChain
    agent_ids: Optional[set[str]] = field(default=None)
    revocations: Optional[RevocationRegistry] = field(default=None)
    compromised_ids: set[str] = field(default_factory=set)
    bootstrap_anchors: dict[str, int] = field(default_factory=dict)
    current_epoch_start: Optional[str] = field(default=None)
    anomaly_scores: dict[str, float] = field(default_factory=dict)
    anomaly_threshold: float = field(default=0.5)

    def __post_init__(self):
        if self.agent_ids is None:
            self.agent_ids = set()
            for att in self.chain.attestations:
                self.agent_ids.add(att.subject)
                self.agent_ids.add(att.witness)

    @property
    def identity_strength(self) -> float:
        """Fraction of agents with multi-factor (>=2) bootstrap anchors."""
        if not self.agent_ids:
            return 0.0
        strong = sum(
            1 for a in self.agent_ids
            if self.bootstrap_anchors.get(a, 0) >= 2
        )
        return strong / len(self.agent_ids)

    @property
    def freshness(self) -> float:
        """Fraction of attestations within current epoch."""
        if not self.chain.attestations or not self.current_epoch_start:
            return 0.0
        fresh = sum(
            1 for att in self.chain.attestations
            if att.timestamp and att.timestamp >= self.current_epoch_start
        )
        return fresh / len(self.chain.attestations)

    @property
    def revocation_coverage(self) -> float:
        """Fraction of compromised identities that are properly revoked."""
        if not self.compromised_ids:
            return 1.0  # No compromised agents = perfect coverage
        if not self.revocations:
            return 0.0
        revoked = sum(
            1 for cid in self.compromised_ids
            if self.revocations.is_revoked(cid)
        )
        return revoked / len(self.compromised_ids)

    @property
    def anomaly_rate(self) -> float:
        """Fraction of agents with anomaly score above threshold."""
        if not self.agent_ids:
            return 0.0
        anomalous = sum(
            1 for a in self.agent_ids
            if self.anomaly_scores.get(a, 0.0) > self.anomaly_threshold
        )
        return anomalous / len(self.agent_ids)

    @property
    def overall_score(self) -> float:
        """Weighted aggregate security score (0.0–1.0, higher is better).

        Weights: identity_strength 0.3, freshness 0.25,
                 revocation_coverage 0.25, (1 - anomaly_rate) 0.2.
        """
        return (
            0.30 * self.identity_strength
            + 0.25 * self.freshness
            + 0.25 * self.revocation_coverage
            + 0.20 * (1.0 - self.anomaly_rate)
        )

    def to_dict(self) -> dict:
        return {
            "identity_strength": self.identity_strength,
            "freshness": self.freshness,
            "revocation_coverage": self.revocation_coverage,
            "anomaly_rate": self.anomaly_rate,
            "overall_score": self.overall_score,
        }


# ─── TrustDistribution ────────────────────────────────────────────

@dataclass
class TrustDistribution:
    """Statistical analysis of trust score distribution.

    Parameters:
        chain: The TrustChain used to compute trust scores.
        agent_ids: Agents to include. Derived from chain if None.
        scope: Optional scope filter for trust_score().
    """

    chain: TrustChain
    agent_ids: Optional[set[str]] = field(default=None)
    scope: Optional[str] = field(default=None)

    def __post_init__(self):
        if self.agent_ids is None:
            self.agent_ids = set()
            for att in self.chain.attestations:
                self.agent_ids.add(att.subject)
                self.agent_ids.add(att.witness)
        self._scores: Optional[list[float]] = None

    @property
    def scores(self) -> list[float]:
        """Cached list of trust scores for all agents."""
        if self._scores is None:
            self._scores = [
                self.chain.trust_score(a, scope=self.scope)
                for a in sorted(self.agent_ids) if self.agent_ids
            ]
        return self._scores

    @property
    def mean_trust_score(self) -> float:
        if not self.scores:
            return 0.0
        return statistics.mean(self.scores)

    @property
    def median_trust_score(self) -> float:
        if not self.scores:
            return 0.0
        return statistics.median(self.scores)

    @property
    def std_dev(self) -> float:
        if len(self.scores) < 2:
            return 0.0
        return statistics.stdev(self.scores)

    def trust_histogram(self, bins: int = 10) -> list[int]:
        """Distribution of trust scores into equal-width bins from 0.0 to 1.0.

        Returns a list of counts, one per bin. Bin edges:
        [0, 1/bins), [1/bins, 2/bins), ... [1-1/bins, 1.0].
        Scores exactly equal to 1.0 go into the last bin.
        """
        if bins <= 0:
            raise ValueError("bins must be positive")
        histogram = [0] * bins
        for s in self.scores:
            idx = int(s * bins)
            if idx >= bins:
                idx = bins - 1
            histogram[idx] += 1
        return histogram

    @property
    def scope_coverage(self) -> int:
        """Number of unique scopes (task types) attested in the chain."""
        scopes: set[str] = set()
        for att in self.chain.attestations:
            if att.task:
                scopes.add(att.task)
        return len(scopes)

    def to_dict(self) -> dict:
        return {
            "mean_trust_score": self.mean_trust_score,
            "median_trust_score": self.median_trust_score,
            "std_dev": self.std_dev,
            "scope_coverage": self.scope_coverage,
            "histogram": self.trust_histogram(),
            "agent_count": len(self.agent_ids) if self.agent_ids else 0,
        }
