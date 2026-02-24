"""TrustScore — Bridge from Isnad attestation chains to behavioral trust scoring."""

from .bridge import IsnadBridge, InteractionRecord, EndorsementRecord
from .scorer import TrustScorer
from .scorer_v2 import TrustScorerV2
from .platform_connectors import PlatformReputation, get_connector, CONNECTORS

__all__ = [
    "IsnadBridge", "InteractionRecord", "EndorsementRecord",
    "TrustScorer", "TrustScorerV2",
    "PlatformReputation", "get_connector", "CONNECTORS",
]
