"""isnad — Cryptographic trust chains for AI agent reputation."""

from isnad.core import (
    AgentIdentity, Attestation, TrustChain,
    Delegation, DelegationRegistry,
    RevocationEntry, RevocationRegistry,
)
from isnad.client import IsnadClient, IsnadError
from isnad.discovery import AgentProfile, DiscoveryRegistry, create_profile
from isnad.audit import AuditTrail, AuditEntry, AuditEventType
from isnad.commerce import ServiceListing, TradeRecord, DisputeRecord, CommerceRegistry
from isnad.trustscore import IsnadBridge, TrustScorer
from isnad.rate_limiter import TrustRateLimiter, RateTier, RateCheckResult
from isnad.batch import verify_batch, verify_chain_batch, BatchReport, VerificationResult
from isnad.epochs import (
    EpochPolicy, EpochRegistry,
    DecayCurve, RenewalCondition, EpochState,
    Epoch, CrossDomainBridge, BridgeResult,
    AdaptiveEpochCalculator,
)
# Backwards compatibility
EpochManager = EpochRegistry
from isnad.policy import (
    TrustPolicy, TrustRequirement, PolicyRule, PolicyAction,
    PolicyDecision, EvaluationContext,
    strict_commerce_policy, open_discovery_policy, scoped_delegation_policy,
)

__all__ = [
    "AgentIdentity",
    "Attestation",
    "TrustChain",
    "Delegation",
    "DelegationRegistry",
    "RevocationEntry",
    "RevocationRegistry",
    "IsnadClient",
    "IsnadError",
    "AgentProfile",
    "DiscoveryRegistry",
    "create_profile",
    "AuditTrail",
    "AuditEntry",
    "AuditEventType",
    "ServiceListing",
    "TradeRecord",
    "DisputeRecord",
    "CommerceRegistry",
    "IsnadBridge",
    "TrustScorer",
    "TrustPolicy",
    "TrustRequirement",
    "PolicyRule",
    "PolicyAction",
    "PolicyDecision",
    "EvaluationContext",
    "strict_commerce_policy",
    "open_discovery_policy",
    "scoped_delegation_policy",
    "EpochPolicy",
    "EpochManager",
    "EpochRegistry",
    "DecayCurve",
    "RenewalCondition",
    "EpochState",
    "Epoch",
    "CrossDomainBridge",
    "BridgeResult",
    "AdaptiveEpochCalculator",
    "TrustRateLimiter",
    "RateTier",
    "RateCheckResult",
]
