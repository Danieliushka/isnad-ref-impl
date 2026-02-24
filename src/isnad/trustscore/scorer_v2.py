"""TrustScorer v2 — Real platform data scoring for AI agent trust.

Replaces vanity metrics (writing_fingerprint, activity_rhythm, topic_drift)
with real, verifiable signals from agent marketplaces.

Signal weights:
    platform_reputation      40%  — ratings, reviews, completion rates
    delivery_track_record    30%  — jobs completed vs cancelled/disputed
    identity_verification    15%  — profile completeness, cross-platform linking
    cross_platform_consistency 15% — consistency across multiple platforms
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .platform_connectors import PlatformReputation, get_connector, CONNECTORS


@dataclass
class TrustSignal:
    """Individual trust signal with score and evidence."""
    name: str
    score: float  # 0.0-1.0
    weight: float
    evidence: dict = field(default_factory=dict)
    confidence: float = 1.0  # How confident we are in this signal


class TrustScorerV2:
    """
    Compute TrustScore from real platform reputation data.

    Signal weights:
        platform_reputation         40%
        delivery_track_record       30%
        identity_verification       15%
        cross_platform_consistency  15%
    """

    WEIGHTS = {
        "platform_reputation": 0.40,
        "delivery_track_record": 0.30,
        "identity_verification": 0.15,
        "cross_platform_consistency": 0.15,
    }

    def __init__(self, reputations: Optional[list[PlatformReputation]] = None):
        self.reputations = reputations or []

    @classmethod
    def from_platforms(cls, platforms: dict[str, str]) -> "TrustScorerV2":
        """
        Fetch reputation from multiple platforms and create scorer.

        Args:
            platforms: dict of {platform_name: username}
                e.g. {"ugig": "gendolf", "github": "gendolf-agent"}
        """
        reputations = []
        for platform, username in platforms.items():
            try:
                connector = get_connector(platform)
                rep = connector.fetch_profile(username)
                if rep:
                    reputations.append(rep)
            except Exception:
                pass  # Skip failed connectors
        return cls(reputations)

    # ── Signal Extractors ──

    def _platform_reputation_score(self) -> TrustSignal:
        """
        Score based on ratings and reviews across platforms.
        Weighted by review count (more reviews = more reliable).
        """
        if not self.reputations:
            return TrustSignal("platform_reputation", 0.0, self.WEIGHTS["platform_reputation"],
                             evidence={"reason": "no_platforms"}, confidence=0.0)

        total_weight = 0
        weighted_score = 0
        evidence = {}

        for rep in self.reputations:
            # Platform-specific scoring
            if rep.average_rating > 0 and rep.total_reviews > 0:
                # Normalize rating to 0-1 (assuming 5-star scale)
                normalized_rating = min(rep.average_rating / 5.0, 1.0)
                # Weight by number of reviews (log-scaled)
                review_weight = math.log2(rep.total_reviews + 1)
                weighted_score += normalized_rating * review_weight
                total_weight += review_weight
                evidence[rep.platform] = {
                    "rating": rep.average_rating,
                    "reviews": rep.total_reviews,
                    "weight": round(review_weight, 2),
                }
            elif rep.platform == "github" and rep.raw.get("total_stars", 0) > 0:
                # GitHub: use stars as proxy for quality
                stars = rep.raw["total_stars"]
                star_score = min(math.log2(stars + 1) / 10.0, 1.0)
                star_weight = 0.5  # Lower weight for indirect signal
                weighted_score += star_score * star_weight
                total_weight += star_weight
                evidence["github"] = {"stars": stars, "score": round(star_score, 2)}

        score = weighted_score / total_weight if total_weight > 0 else 0.0
        confidence = min(total_weight / 3.0, 1.0)  # Full confidence at ~8 reviews

        return TrustSignal("platform_reputation", min(score, 1.0),
                         self.WEIGHTS["platform_reputation"],
                         evidence=evidence, confidence=confidence)

    def _delivery_track_record_score(self) -> TrustSignal:
        """
        Score based on job completion rate.
        completed / (completed + cancelled + disputed)
        """
        total_completed = sum(r.completed_jobs for r in self.reputations)
        total_cancelled = sum(r.cancelled_jobs for r in self.reputations)
        total_disputed = sum(r.disputed_jobs for r in self.reputations)
        total_jobs = sum(r.total_jobs for r in self.reputations)

        evidence = {
            "completed": total_completed,
            "cancelled": total_cancelled,
            "disputed": total_disputed,
            "total_jobs": total_jobs,
        }

        if total_completed + total_cancelled + total_disputed == 0:
            # No track record — neutral score with low confidence
            return TrustSignal("delivery_track_record", 0.5,
                             self.WEIGHTS["delivery_track_record"],
                             evidence=evidence, confidence=0.1)

        denominator = total_completed + total_cancelled + total_disputed
        completion_rate = total_completed / denominator

        # Penalty for disputes (worse than cancellations)
        dispute_penalty = total_disputed * 0.1  # Each dispute = -0.1
        score = max(0.0, min(1.0, completion_rate - dispute_penalty))

        # Confidence based on sample size
        confidence = min(denominator / 10.0, 1.0)  # Full confidence at 10 jobs

        return TrustSignal("delivery_track_record", score,
                         self.WEIGHTS["delivery_track_record"],
                         evidence=evidence, confidence=confidence)

    def _identity_verification_score(self) -> TrustSignal:
        """
        Score based on profile completeness and identity signals.
        """
        if not self.reputations:
            return TrustSignal("identity_verification", 0.0,
                             self.WEIGHTS["identity_verification"],
                             confidence=0.0)

        scores = []
        evidence = {}

        for rep in self.reputations:
            platform_score = 0.0
            checks = {}

            # Profile completeness (0.3)
            if rep.profile_completed:
                platform_score += 0.3
                checks["profile_complete"] = True

            # Has avatar (0.1)
            if rep.has_avatar:
                platform_score += 0.1
                checks["has_avatar"] = True

            # Has portfolio (0.1)
            if rep.has_portfolio:
                platform_score += 0.1
                checks["has_portfolio"] = True

            # Skills declared (0.2)
            if rep.skills_count >= 3:
                platform_score += 0.2
                checks["skills"] = rep.skills_count
            elif rep.skills_count > 0:
                platform_score += 0.1
                checks["skills"] = rep.skills_count

            # Account age — older = more trustworthy (0.3)
            if rep.member_since:
                from datetime import datetime, timezone
                try:
                    created = datetime.fromisoformat(rep.member_since.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    age_days = (now - created).days
                    age_score = min(age_days / 180, 1.0) * 0.3  # Full at 6 months
                    platform_score += age_score
                    checks["age_days"] = age_days
                except (ValueError, TypeError):
                    pass

            scores.append(platform_score)
            evidence[rep.platform] = checks

        score = sum(scores) / len(scores) if scores else 0.0

        return TrustSignal("identity_verification", min(score, 1.0),
                         self.WEIGHTS["identity_verification"],
                         evidence=evidence, confidence=0.9)

    def _cross_platform_consistency_score(self) -> TrustSignal:
        """
        Score based on presence and consistency across multiple platforms.
        More platforms = more trust (harder to fake identity on many platforms).
        """
        num_platforms = len(self.reputations)
        evidence = {
            "platforms": [r.platform for r in self.reputations],
            "count": num_platforms,
        }

        if num_platforms == 0:
            return TrustSignal("cross_platform_consistency", 0.0,
                             self.WEIGHTS["cross_platform_consistency"],
                             evidence=evidence, confidence=0.0)

        # Base score from number of platforms
        # 1 platform = 0.3, 2 = 0.6, 3 = 0.8, 4+ = 1.0
        platform_score = min(num_platforms * 0.25, 1.0)

        # Consistency bonus: same username across platforms
        usernames = [r.username.lower() for r in self.reputations]
        unique_usernames = len(set(usernames))
        if unique_usernames == 1 and num_platforms > 1:
            consistency_bonus = 0.2
            evidence["consistent_username"] = True
        else:
            consistency_bonus = 0.0
            evidence["consistent_username"] = False

        # Activity consistency: active on multiple platforms
        active_platforms = sum(1 for r in self.reputations
                              if r.total_jobs > 0 or r.total_reviews > 0)
        if active_platforms > 1:
            evidence["active_platforms"] = active_platforms
            activity_bonus = 0.1
        else:
            activity_bonus = 0.0

        score = min(platform_score + consistency_bonus + activity_bonus, 1.0)

        return TrustSignal("cross_platform_consistency", score,
                         self.WEIGHTS["cross_platform_consistency"],
                         evidence=evidence, confidence=0.8)

    # ── Main Scorer ──

    def compute(self) -> float:
        """Compute the final TrustScore (0.0–1.0)."""
        signals = self._compute_signals()
        # Weighted sum with confidence adjustment
        score = sum(s.score * s.weight * s.confidence for s in signals)
        total_weight = sum(s.weight * s.confidence for s in signals)
        if total_weight == 0:
            return 0.0
        return max(0.0, min(1.0, score / total_weight))

    def compute_detailed(self) -> dict:
        """Compute TrustScore with per-signal breakdown."""
        signals = self._compute_signals()
        total_weight = sum(s.weight * s.confidence for s in signals)
        raw_score = sum(s.score * s.weight * s.confidence for s in signals)
        final_score = raw_score / total_weight if total_weight > 0 else 0.0

        return {
            "trust_score": max(0.0, min(1.0, final_score)),
            "version": "2.0",
            "signals": {
                s.name: {
                    "score": round(s.score, 4),
                    "weight": s.weight,
                    "confidence": round(s.confidence, 4),
                    "effective_weight": round(s.weight * s.confidence, 4),
                    "evidence": s.evidence,
                }
                for s in signals
            },
            "platforms": [r.platform for r in self.reputations],
            "platform_count": len(self.reputations),
            "data_quality": round(total_weight, 4),
        }

    def _compute_signals(self) -> list[TrustSignal]:
        """Compute all trust signals."""
        return [
            self._platform_reputation_score(),
            self._delivery_track_record_score(),
            self._identity_verification_score(),
            self._cross_platform_consistency_score(),
        ]
