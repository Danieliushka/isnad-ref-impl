"""Atlas TrustScore integration — live scoring via Atlas DCA API.

Connects isnad attestation chains to Atlas's TrustScore service,
enabling real-time trust evaluation with external validation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Optional

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

from isnad.core import TrustChain
from isnad.trustscore.bridge import IsnadBridge


ATLAS_API_URL = "https://dca-api.bot-named-atlas.workers.dev"


@dataclass
class AtlasScore:
    """Result from Atlas TrustScore API."""
    agent_id: str
    atlas_score: float
    atlas_classification: str
    isnad_raw_score: float
    isnad_weighted_score: float
    combined_score: float
    attestation_count: int
    confidence: str  # "high", "medium", "low"

    def to_dict(self) -> dict:
        return asdict(self)


class AtlasIntegration:
    """Bridge between isnad chains and Atlas TrustScore API."""

    def __init__(self, chain: TrustChain, api_url: str = ATLAS_API_URL):
        if not HAS_HTTPX:
            raise ImportError("httpx required for Atlas integration: pip install httpx")
        self.chain = chain
        self.bridge = IsnadBridge(chain)
        self.api_url = api_url.rstrip("/")
        self._client = httpx.Client(timeout=10.0)

    def _query_atlas(self, agent_id: str, evidence: Optional[dict] = None) -> dict:
        """Query Atlas TrustScore API for an agent."""
        payload = {
            "agent_id": agent_id,
            "protocol": "isnad",
            "attestation_count": len(self.chain._by_subject.get(agent_id, [])),
        }
        if evidence:
            payload["evidence"] = evidence

        resp = self._client.post(f"{self.api_url}/v1/score", json=payload)
        resp.raise_for_status()
        return resp.json()

    def score_agent(self, agent_id: str) -> AtlasScore:
        """Get combined isnad + Atlas trust score for an agent.

        Combines local attestation chain analysis with Atlas's
        external trust evaluation for a comprehensive score.
        """
        # Local isnad analysis
        profile = self.bridge.agent_trust_profile(agent_id)

        # Prepare evidence from chain
        interactions = self.bridge.to_interactions()
        agent_interactions = [i.to_dict() for i in interactions
                             if i.agent_id == agent_id]

        # Query Atlas
        atlas_data = self._query_atlas(agent_id, evidence={
            "interactions": agent_interactions[:10],  # Last 10
            "isnad_score": profile["raw_score"],
            "attestation_count": profile["attestation_count"],
        })

        atlas_score = atlas_data.get("score", 0) / 100.0  # Normalize to 0-1
        atlas_class = atlas_data.get("classification", "unknown")

        # Combined score: weighted average (isnad 60%, Atlas 40%)
        isnad_weight = 0.6
        atlas_weight = 0.4
        combined = (profile["weighted_score"] * isnad_weight +
                    atlas_score * atlas_weight)

        # Confidence based on attestation count
        att_count = profile["attestation_count"]
        if att_count >= 10:
            confidence = "high"
        elif att_count >= 3:
            confidence = "medium"
        else:
            confidence = "low"

        return AtlasScore(
            agent_id=agent_id,
            atlas_score=round(atlas_score, 4),
            atlas_classification=atlas_class,
            isnad_raw_score=round(profile["raw_score"], 4),
            isnad_weighted_score=round(profile["weighted_score"], 4),
            combined_score=round(combined, 4),
            attestation_count=att_count,
            confidence=confidence,
        )

    def batch_score(self, agent_ids: list[str]) -> list[AtlasScore]:
        """Score multiple agents."""
        return [self.score_agent(aid) for aid in agent_ids]

    def trust_gate(self, agent_id: str, threshold: float = 0.5) -> dict:
        """Binary trust decision: allow/deny based on combined score.

        Use as middleware for agent-to-agent interactions.
        """
        score = self.score_agent(agent_id)
        allowed = score.combined_score >= threshold

        return {
            "agent_id": agent_id,
            "allowed": allowed,
            "score": score.combined_score,
            "threshold": threshold,
            "reason": (f"Combined score {score.combined_score:.2f} "
                       f"{'≥' if allowed else '<'} threshold {threshold:.2f}"),
            "details": score.to_dict(),
        }

    def close(self):
        """Close HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
