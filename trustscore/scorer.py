"""TrustScorer — Behavioral trust scoring from interaction and endorsement batches."""

from __future__ import annotations

import math
from collections import Counter
from typing import Optional

from .bridge import InteractionRecord, EndorsementRecord


class TrustScorer:
    """
    Compute a TrustScore (0.0–1.0) from interaction + endorsement batches.

    Signal weights:
        relationship_graph   35%
        activity_rhythm      25%
        topic_drift          20%
        writing_fingerprint  20%
    """

    WEIGHTS = {
        "relationship_graph": 0.35,
        "activity_rhythm": 0.25,
        "topic_drift": 0.20,
        "writing_fingerprint": 0.20,
    }

    def __init__(self, interactions: Optional[list[InteractionRecord]] = None,
                 endorsements: Optional[list[EndorsementRecord]] = None):
        self.interactions = interactions or []
        self.endorsements = endorsements or []

    # ── Signal Extractors ──

    def _relationship_graph_score(self) -> float:
        """Score based on diversity and quality of endorsements."""
        if not self.endorsements:
            return 0.0
        unique_endorsers = len({e.endorser_id for e in self.endorsements})
        avg_confidence = sum(e.confidence for e in self.endorsements) / len(self.endorsements)
        # More unique endorsers → higher score, log-scaled, cap at 1.0
        diversity = min(math.log2(unique_endorsers + 1) / 4.0, 1.0)
        return diversity * avg_confidence

    def _activity_rhythm_score(self) -> float:
        """Score based on regularity of interactions."""
        if len(self.interactions) < 2:
            return 0.5 if self.interactions else 0.0
        # Parse timestamps and compute intervals
        from datetime import datetime
        timestamps = []
        for ir in self.interactions:
            try:
                timestamps.append(datetime.fromisoformat(ir.timestamp))
            except (ValueError, TypeError):
                pass
        if len(timestamps) < 2:
            return 0.5
        timestamps.sort()
        intervals = [(timestamps[i+1] - timestamps[i]).total_seconds()
                      for i in range(len(timestamps) - 1)]
        mean_interval = sum(intervals) / len(intervals)
        if mean_interval == 0:
            return 1.0
        # Coefficient of variation: lower = more regular = higher score
        variance = sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)
        std = math.sqrt(variance)
        cv = std / mean_interval
        # cv=0 → perfect regularity → score=1; cv≥2 → score≈0
        return max(0.0, min(1.0, 1.0 - cv / 2.0))

    def _topic_drift_score(self) -> float:
        """Score based on consistency of skill areas / interaction types."""
        types = [ir.interaction_type for ir in self.interactions]
        skills = [e.skill_area for e in self.endorsements]
        all_topics = types + skills
        if not all_topics:
            return 0.0
        counts = Counter(all_topics)
        total = sum(counts.values())
        # Entropy-based: low entropy = focused = higher score
        entropy = -sum((c / total) * math.log2(c / total) for c in counts.values() if c > 0)
        max_entropy = math.log2(len(counts)) if len(counts) > 1 else 1.0
        normalized = entropy / max_entropy if max_entropy > 0 else 0.0
        # Focused agent gets higher score (inverted entropy)
        return max(0.0, 1.0 - normalized * 0.5)

    def _writing_fingerprint_score(self) -> float:
        """Score based on evidence quality and consistency."""
        records_with_evidence = 0
        total = len(self.interactions) + len(self.endorsements)
        if total == 0:
            return 0.0
        for ir in self.interactions:
            if ir.context.get("evidence"):
                records_with_evidence += 1
        for e in self.endorsements:
            if e.evidence_hash:
                records_with_evidence += 1
        return records_with_evidence / total

    # ── Main Scorer ──

    def compute(self) -> float:
        """Compute the final TrustScore (0.0–1.0)."""
        signals = {
            "relationship_graph": self._relationship_graph_score(),
            "activity_rhythm": self._activity_rhythm_score(),
            "topic_drift": self._topic_drift_score(),
            "writing_fingerprint": self._writing_fingerprint_score(),
        }
        score = sum(self.WEIGHTS[k] * signals[k] for k in self.WEIGHTS)
        return max(0.0, min(1.0, score))

    def compute_detailed(self) -> dict:
        """Compute TrustScore with per-signal breakdown."""
        signals = {
            "relationship_graph": self._relationship_graph_score(),
            "activity_rhythm": self._activity_rhythm_score(),
            "topic_drift": self._topic_drift_score(),
            "writing_fingerprint": self._writing_fingerprint_score(),
        }
        score = sum(self.WEIGHTS[k] * signals[k] for k in self.WEIGHTS)
        return {
            "trust_score": max(0.0, min(1.0, score)),
            "signals": signals,
            "weights": dict(self.WEIGHTS),
            "interaction_count": len(self.interactions),
            "endorsement_count": len(self.endorsements),
        }
