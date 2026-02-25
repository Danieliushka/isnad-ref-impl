"""TrustScorer v2 — Real platform data scoring for AI agent trust.

Replaces vanity metrics (writing_fingerprint, activity_rhythm, topic_drift)
with real, verifiable signals from agent marketplaces.

Signal weights:
    platform_reputation      40%  — ratings, reviews, completion rates
    delivery_track_record    30%  — jobs completed vs cancelled/disputed
    identity_verification    15%  — profile completeness, cross-platform linking
    cross_platform_consistency 15% — consistency across multiple platforms

Also provides PlatformTrustCalculator for aggregated trust reports
based on worker-collected platform_data metrics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


# ═══════════════════════════════════════════════════════════════════
# PlatformTrustCalculator — aggregated trust from worker platform_data
# ═══════════════════════════════════════════════════════════════════

# Trust decay: half-life of 30 days — inactive agents lose trust
_DECAY_HALF_LIFE_DAYS = 30


def _decay_factor(days_since_fetch: float) -> float:
    """Exponential decay factor. At half-life, factor = 0.5."""
    if days_since_fetch <= 0:
        return 1.0
    return math.pow(0.5, days_since_fetch / _DECAY_HALF_LIFE_DAYS)


class PlatformTrustCalculator:
    """Compute aggregated trust report from worker-collected platform_data.

    ⚠️ HONEST scoring — no data = low score, not mid score.
    Evidence-based only. Trust decays over time.

    Scores:
        identity_score    (0-100) — platform count, profile completeness
        activity_score    (0-100) — average activity across platforms
        reputation_score  (0-100) — reviews, ratings, stars
        security_score    (0-100) — SSL, verification levels
        overall_score     (0-100) — weighted average with time decay

    Weights:
        reputation   35%
        activity     25%
        identity     20%
        security     20%
    """

    WEIGHTS = {
        "identity": 0.20,
        "activity": 0.25,
        "reputation": 0.35,
        "security": 0.20,
    }

    def __init__(self, platform_data: list[dict]):
        """
        Args:
            platform_data: list of platform_data rows from DB.
                Each must have: metrics (dict), last_fetched (str), platform_name.
        """
        self.platforms = platform_data

    def compute_report(self) -> dict:
        """Compute full trust report with breakdown."""
        identity = self._identity_score()
        activity = self._activity_score()
        reputation = self._reputation_score()
        security = self._security_score()

        # Weighted average with global decay
        overall_raw = (
            identity["score"] * self.WEIGHTS["identity"]
            + activity["score"] * self.WEIGHTS["activity"]
            + reputation["score"] * self.WEIGHTS["reputation"]
            + security["score"] * self.WEIGHTS["security"]
        )

        # Apply global decay based on most recent fetch
        global_decay = self._global_decay_factor()
        overall = int(overall_raw * global_decay)

        return {
            "overall_score": max(0, min(100, overall)),
            "decay_factor": round(global_decay, 4),
            "platform_count": len(self.platforms),
            "scores": {
                "identity": identity,
                "activity": activity,
                "reputation": reputation,
                "security": security,
            },
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _global_decay_factor(self) -> float:
        """Decay based on the most recent platform fetch."""
        if not self.platforms:
            return 0.0

        now = datetime.now(timezone.utc)
        most_recent = 999999.0
        for p in self.platforms:
            fetched = p.get("last_fetched")
            if not fetched:
                continue
            try:
                if isinstance(fetched, str):
                    dt = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
                else:
                    dt = fetched
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                days = (now - dt).total_seconds() / 86400
                most_recent = min(most_recent, days)
            except Exception:
                continue

        if most_recent > 999998:
            return 0.0
        return _decay_factor(most_recent)

    def _get_metrics(self) -> list[dict]:
        """Extract metrics dicts from platform data, parsing JSON if needed."""
        import json
        results = []
        for p in self.platforms:
            m = p.get("metrics", {})
            if isinstance(m, str):
                try:
                    m = json.loads(m)
                except Exception:
                    m = {}
            if isinstance(m, dict):
                results.append(m)
        return results

    def _identity_score(self) -> dict:
        """Identity score: platform count + verification levels.

        0 platforms = 0 score.
        1 platform = max 30 (low confidence).
        2 platforms = max 60.
        3+ platforms = up to 100.
        """
        metrics = self._get_metrics()
        n = len(metrics)
        evidence = {"platform_count": n}

        if n == 0:
            return {"score": 0, "evidence": evidence}

        # Platform count contribution (cap per count)
        count_score = min(n * 25, 75)

        # Verification bonus
        verified_count = sum(
            1 for m in metrics if m.get("verification_level") in ("basic", "verified")
        )
        full_verified = sum(
            1 for m in metrics if m.get("verification_level") == "verified"
        )
        verification_bonus = min(verified_count * 5 + full_verified * 10, 25)

        score = min(count_score + verification_bonus, 100)
        evidence["verified_platforms"] = verified_count
        evidence["fully_verified"] = full_verified

        return {"score": score, "evidence": evidence}

    def _activity_score(self) -> dict:
        """Activity score: average activity_score across platforms.

        No data = 0. Single inactive platform = whatever that platform reports.
        """
        metrics = self._get_metrics()
        evidence: dict = {}

        if not metrics:
            return {"score": 0, "evidence": {"reason": "no_platforms"}}

        activities = [m.get("activity_score", 0) for m in metrics]
        avg = sum(activities) / len(activities)
        evidence["per_platform"] = activities
        evidence["average"] = round(avg, 1)

        return {"score": int(avg), "evidence": evidence}

    def _reputation_score(self) -> dict:
        """Reputation score: evidence-based only.

        ⚠️ No reviews = 0, not 50.
        """
        metrics = self._get_metrics()
        evidence: dict = {}

        if not metrics:
            return {"score": 0, "evidence": {"reason": "no_platforms"}}

        reps = [m.get("reputation_score", 0) for m in metrics]
        evidence_counts = [m.get("evidence_count", 0) for m in metrics]
        total_evidence = sum(evidence_counts)

        if total_evidence == 0:
            # No evidence at all = 0 reputation
            return {"score": 0, "evidence": {"reason": "no_evidence", "per_platform": reps}}

        # Weighted average by evidence count (more evidence = more weight)
        weighted_sum = sum(r * e for r, e in zip(reps, evidence_counts))
        score = weighted_sum / total_evidence if total_evidence > 0 else 0

        evidence["per_platform"] = reps
        evidence["evidence_counts"] = evidence_counts
        evidence["total_evidence"] = total_evidence

        return {"score": int(score), "evidence": evidence}

    def _security_score(self) -> dict:
        """Security score: SSL, verification levels, attestation chain.

        Generic platforms with valid SSL get basic credit.
        No SSL or no data = 0.
        """
        import json
        evidence: dict = {}

        if not self.platforms:
            return {"score": 0, "evidence": {"reason": "no_platforms"}}

        ssl_valid = 0
        ssl_total = 0
        verification_scores = []

        for p in self.platforms:
            raw = p.get("raw_data", {})
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = {}

            # Check SSL from raw_data
            ssl_info = raw.get("ssl", {})
            if ssl_info:
                ssl_total += 1
                if ssl_info.get("valid"):
                    ssl_valid += 1

            # Verification level
            m = p.get("metrics", {})
            if isinstance(m, str):
                try:
                    m = json.loads(m)
                except Exception:
                    m = {}
            vl = m.get("verification_level", "none")
            if vl == "verified":
                verification_scores.append(40)
            elif vl == "basic":
                verification_scores.append(20)
            else:
                verification_scores.append(0)

        score = 0
        if ssl_total > 0:
            ssl_score = (ssl_valid / ssl_total) * 40
            score += ssl_score
            evidence["ssl_valid"] = ssl_valid
            evidence["ssl_total"] = ssl_total

        if verification_scores:
            avg_ver = sum(verification_scores) / len(verification_scores)
            score += avg_ver
            evidence["avg_verification"] = round(avg_ver, 1)

        return {"score": min(int(score), 100), "evidence": evidence}
