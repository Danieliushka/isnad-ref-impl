"""Bridge: convert Isnad attestation chains into TrustScore-compatible records."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from isnad import Attestation, TrustChain


# ─── Records ───────────────────────────────────────────────────────

@dataclass
class InteractionRecord:
    agent_id: str
    interaction_type: str
    outcome: str
    timestamp: str
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EndorsementRecord:
    endorser_id: str
    endorsed_id: str
    skill_area: str
    confidence: float
    evidence_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Bridge ────────────────────────────────────────────────────────

class IsnadBridge:
    """Converts Isnad attestation chains into TrustScore-compatible records."""

    HALF_LIFE_DAYS = 30.0

    def __init__(self, chain: TrustChain):
        self.chain = chain

    # ── Conversion ──

    def attestation_to_interaction(self, att: Attestation) -> InteractionRecord:
        return InteractionRecord(
            agent_id=att.subject,
            interaction_type=att.task,
            outcome="verified" if att.verify() else "unverified",
            timestamp=att.timestamp,
            context={"witness": att.witness, "evidence": att.evidence,
                      "attestation_id": att.attestation_id},
        )

    def attestation_to_endorsement(self, att: Attestation) -> EndorsementRecord:
        confidence = 1.0 if att.verify() else 0.0
        evidence_hash = hashlib.sha256(att.evidence.encode()).hexdigest()[:16] if att.evidence else ""
        return EndorsementRecord(
            endorser_id=att.witness,
            endorsed_id=att.subject,
            skill_area=att.task,
            confidence=confidence,
            evidence_hash=evidence_hash,
        )

    def to_interactions(self) -> list[InteractionRecord]:
        return [self.attestation_to_interaction(a) for a in self.chain.attestations]

    def to_endorsements(self) -> list[EndorsementRecord]:
        return [self.attestation_to_endorsement(a) for a in self.chain.attestations]

    # ── Trust Decay ──

    @staticmethod
    def trust_decay(base_score: float, days_since_last: float,
                    half_life: float = 30.0) -> float:
        """trust_weight = base_score * (0.5 ^ (days_since_last / half_life))"""
        return base_score * math.pow(0.5, days_since_last / half_life)

    # ── Reinforcement Multiplier ──

    @staticmethod
    def reinforcement_multiplier(consecutive_attestations: int) -> float:
        """1 + (0.1 * consecutive_attestations), capped at 2.0"""
        return min(1.0 + 0.1 * consecutive_attestations, 2.0)

    # ── Agent Trust Profile ──

    def agent_trust_profile(self, agent_id: str, reference_time: Optional[datetime] = None) -> dict:
        """Build a trust profile for an agent with decay and reinforcement."""
        ref = reference_time or datetime.now(timezone.utc)
        attestations = self.chain._by_subject.get(agent_id, [])
        if not attestations:
            return {"agent_id": agent_id, "raw_score": 0.0, "weighted_score": 0.0,
                    "attestation_count": 0, "unique_witnesses": 0, "skills": {}}

        # Sort by timestamp
        sorted_atts = sorted(attestations, key=lambda a: a.timestamp)

        # Count consecutive attestations (whole chain length)
        consecutive = len(sorted_atts)
        multiplier = self.reinforcement_multiplier(consecutive)

        # Compute per-attestation weighted scores
        raw_score = self.chain.trust_score(agent_id)
        skills: dict[str, int] = {}
        witnesses: set[str] = set()

        latest_ts = None
        for att in sorted_atts:
            skills[att.task] = skills.get(att.task, 0) + 1
            witnesses.add(att.witness)
            try:
                ts = datetime.fromisoformat(att.timestamp)
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts
            except (ValueError, TypeError):
                pass

        days_since = 0.0
        if latest_ts:
            delta = ref - latest_ts
            days_since = max(delta.total_seconds() / 86400.0, 0.0)

        decayed = self.trust_decay(raw_score, days_since, self.HALF_LIFE_DAYS)
        weighted = decayed * multiplier

        return {
            "agent_id": agent_id,
            "raw_score": raw_score,
            "weighted_score": min(weighted, 1.0),
            "attestation_count": len(sorted_atts),
            "unique_witnesses": len(witnesses),
            "skills": skills,
            "days_since_last": round(days_since, 2),
            "reinforcement_multiplier": multiplier,
        }

    # ── Agent Comparison ──

    def compare_agents(self, agent_a: str, agent_b: str,
                       reference_time: Optional[datetime] = None) -> dict:
        pa = self.agent_trust_profile(agent_a, reference_time)
        pb = self.agent_trust_profile(agent_b, reference_time)
        diff = pa["weighted_score"] - pb["weighted_score"]
        return {
            "agent_a": pa,
            "agent_b": pb,
            "score_difference": round(diff, 6),
            "higher_trust": agent_a if diff > 0 else (agent_b if diff < 0 else "equal"),
        }
