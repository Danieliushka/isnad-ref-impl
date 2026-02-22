"""
isnad.acp_bridge — Bridge between isnad trust protocol and Virtuals ACP marketplace.

Provides:
- ACPAgentProfile: maps ACP agent data to isnad identity
- ACPTrustReport: generates trust reports for ACP agents
- ACPJobVerifier: verifies job completion with cryptographic attestations
- acp_wallet_to_trust_score: quick trust assessment from on-chain data

This module enables isnad to serve as the trust layer for Virtuals ACP,
providing cryptographic verification and trust scoring for agent commerce.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from .core import AgentIdentity, Attestation


class ACPRiskLevel(Enum):
    """Risk classification for ACP agents."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class ACPAgentProfile:
    """Maps a Virtuals ACP agent to isnad identity model."""
    wallet_address: str  # Base chain address (0x...)
    agent_name: str
    agent_id: Optional[int] = None
    description: str = ""
    offerings_count: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    total_revenue_usdc: float = 0.0
    registered_at: Optional[float] = None  # unix timestamp
    last_active: Optional[float] = None

    @property
    def completion_rate(self) -> float:
        """Job completion rate (0.0 - 1.0)."""
        total = self.completed_jobs + self.failed_jobs
        if total == 0:
            return 0.0
        return self.completed_jobs / total

    @property
    def wallet_hash(self) -> str:
        """Deterministic hash of wallet address for indexing."""
        return hashlib.sha256(self.wallet_address.lower().encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["completion_rate"] = self.completion_rate
        result["wallet_hash"] = self.wallet_hash
        return result


@dataclass
class ACPTrustSignal:
    """A single trust signal derived from ACP data."""
    signal_type: str  # e.g. "job_history", "wallet_age", "offering_quality"
    value: float  # normalized 0.0 - 1.0
    confidence: float  # 0.0 - 1.0
    evidence: str  # human-readable explanation
    timestamp: float = field(default_factory=time.time)

    def weighted_value(self) -> float:
        """Signal value weighted by confidence."""
        return self.value * self.confidence


@dataclass
class ACPTrustReport:
    """Comprehensive trust report for an ACP agent."""
    agent_profile: ACPAgentProfile
    signals: list  # list of ACPTrustSignal
    overall_score: float = 0.0  # 0-100
    risk_level: ACPRiskLevel = ACPRiskLevel.UNKNOWN
    generated_at: float = field(default_factory=time.time)
    report_version: str = "1.0.0"

    def compute_score(self) -> float:
        """
        Compute overall trust score from signals.
        
        Weighted average of signal values, normalized to 0-100.
        Signals with higher confidence contribute more.
        """
        if not self.signals:
            self.overall_score = 0.0
            self.risk_level = ACPRiskLevel.UNKNOWN
            return 0.0

        total_weight = sum(s.confidence for s in self.signals)
        if total_weight == 0:
            self.overall_score = 0.0
            self.risk_level = ACPRiskLevel.UNKNOWN
            return 0.0

        weighted_sum = sum(s.weighted_value() for s in self.signals)
        self.overall_score = round((weighted_sum / total_weight) * 100, 2)
        self.risk_level = self._classify_risk(self.overall_score)
        return self.overall_score

    @staticmethod
    def _classify_risk(score: float) -> ACPRiskLevel:
        """Classify risk level based on trust score."""
        if score >= 80:
            return ACPRiskLevel.LOW
        elif score >= 60:
            return ACPRiskLevel.MEDIUM
        elif score >= 30:
            return ACPRiskLevel.HIGH
        else:
            return ACPRiskLevel.CRITICAL

    def to_dict(self) -> dict:
        return {
            "agent": self.agent_profile.to_dict(),
            "signals": [asdict(s) for s in self.signals],
            "overall_score": self.overall_score,
            "risk_level": self.risk_level.value,
            "generated_at": self.generated_at,
            "report_version": self.report_version,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def analyze_job_history(profile: ACPAgentProfile) -> ACPTrustSignal:
    """
    Derive trust signal from ACP job completion history.
    
    Factors:
    - Completion rate (primary)
    - Volume of jobs (confidence modifier)
    - Revenue (secondary signal)
    """
    rate = profile.completion_rate
    total_jobs = profile.completed_jobs + profile.failed_jobs

    # Confidence scales with sample size (log curve)
    if total_jobs == 0:
        confidence = 0.1
        evidence = "No job history — insufficient data"
    elif total_jobs < 5:
        confidence = 0.3
        evidence = f"{total_jobs} jobs completed — small sample"
    elif total_jobs < 20:
        confidence = 0.6
        evidence = f"{total_jobs} jobs, {rate:.0%} completion rate"
    elif total_jobs < 100:
        confidence = 0.8
        evidence = f"{total_jobs} jobs, {rate:.0%} completion, ${profile.total_revenue_usdc:.2f} revenue"
    else:
        confidence = 0.95
        evidence = f"{total_jobs} jobs, {rate:.0%} completion, ${profile.total_revenue_usdc:.2f} revenue — established track record"

    return ACPTrustSignal(
        signal_type="job_history",
        value=rate,
        confidence=confidence,
        evidence=evidence,
    )


def analyze_offering_quality(profile: ACPAgentProfile) -> ACPTrustSignal:
    """
    Derive trust signal from offering characteristics.
    
    More offerings with descriptions = higher signal.
    """
    count = profile.offerings_count
    has_description = bool(profile.description.strip())

    if count == 0:
        value = 0.1
        evidence = "No active offerings"
    elif count <= 2:
        value = 0.4 if has_description else 0.2
        evidence = f"{count} offerings, {'with' if has_description else 'no'} description"
    elif count <= 5:
        value = 0.7 if has_description else 0.5
        evidence = f"{count} offerings — moderate catalog"
    else:
        value = 0.9 if has_description else 0.7
        evidence = f"{count} offerings — comprehensive catalog"

    return ACPTrustSignal(
        signal_type="offering_quality",
        value=value,
        confidence=0.5,  # offerings alone are weak signal
        evidence=evidence,
    )


def analyze_wallet_activity(
    profile: ACPAgentProfile,
    wallet_age_days: Optional[float] = None,
    transaction_count: Optional[int] = None,
) -> ACPTrustSignal:
    """
    Derive trust signal from on-chain wallet activity.
    
    Factors:
    - Wallet age
    - Transaction volume
    - Activity recency
    """
    signals = []
    evidence_parts = []

    # Wallet age
    if wallet_age_days is not None:
        if wallet_age_days < 1:
            signals.append(0.1)
            evidence_parts.append(f"wallet age: <1 day (⚠️ very new)")
        elif wallet_age_days < 7:
            signals.append(0.3)
            evidence_parts.append(f"wallet age: {wallet_age_days:.0f} days")
        elif wallet_age_days < 30:
            signals.append(0.6)
            evidence_parts.append(f"wallet age: {wallet_age_days:.0f} days")
        elif wallet_age_days < 90:
            signals.append(0.8)
            evidence_parts.append(f"wallet age: {wallet_age_days:.0f} days")
        else:
            signals.append(0.95)
            evidence_parts.append(f"wallet age: {wallet_age_days:.0f} days — established")

    # Transaction count
    if transaction_count is not None:
        if transaction_count == 0:
            signals.append(0.05)
            evidence_parts.append("0 transactions (empty wallet)")
        elif transaction_count < 10:
            signals.append(0.3)
            evidence_parts.append(f"{transaction_count} txns")
        elif transaction_count < 100:
            signals.append(0.7)
            evidence_parts.append(f"{transaction_count} txns — active")
        else:
            signals.append(0.9)
            evidence_parts.append(f"{transaction_count} txns — highly active")

    if not signals:
        return ACPTrustSignal(
            signal_type="wallet_activity",
            value=0.0,
            confidence=0.1,
            evidence="No on-chain data available",
        )

    avg_value = sum(signals) / len(signals)
    confidence = 0.7 if len(signals) > 1 else 0.4

    return ACPTrustSignal(
        signal_type="wallet_activity",
        value=avg_value,
        confidence=confidence,
        evidence="; ".join(evidence_parts),
    )


def analyze_recency(profile: ACPAgentProfile) -> ACPTrustSignal:
    """
    Derive trust signal from how recently the agent was active.
    
    Recent activity = higher trust (agent is maintained, operational).
    """
    if profile.last_active is None:
        return ACPTrustSignal(
            signal_type="recency",
            value=0.3,
            confidence=0.2,
            evidence="No activity timestamp available",
        )

    now = time.time()
    hours_since = (now - profile.last_active) / 3600

    if hours_since < 1:
        value = 1.0
        evidence = "Active within the last hour"
    elif hours_since < 24:
        value = 0.9
        evidence = f"Active {hours_since:.0f}h ago"
    elif hours_since < 168:  # 1 week
        value = 0.7
        evidence = f"Active {hours_since/24:.0f} days ago"
    elif hours_since < 720:  # 30 days
        value = 0.4
        evidence = f"Last active {hours_since/24:.0f} days ago — potentially stale"
    else:
        value = 0.1
        evidence = f"Last active {hours_since/24:.0f} days ago — likely abandoned"

    return ACPTrustSignal(
        signal_type="recency",
        value=value,
        confidence=0.6,
        evidence=evidence,
    )


def generate_trust_report(
    profile: ACPAgentProfile,
    wallet_age_days: Optional[float] = None,
    transaction_count: Optional[int] = None,
) -> ACPTrustReport:
    """
    Generate a comprehensive trust report for an ACP agent.
    
    Combines multiple trust signals into a single scored report.
    """
    signals = [
        analyze_job_history(profile),
        analyze_offering_quality(profile),
        analyze_wallet_activity(profile, wallet_age_days, transaction_count),
        analyze_recency(profile),
    ]

    report = ACPTrustReport(
        agent_profile=profile,
        signals=signals,
    )
    report.compute_score()
    return report


class ACPJobVerifier:
    """
    Verifies ACP job completion using isnad attestations.
    
    Creates cryptographic proof that a job was:
    1. Accepted by the seller
    2. Completed with specific deliverables
    3. Verified by quality checks
    """

    def __init__(self, identity: AgentIdentity):
        self.identity = identity

    def _sign_attestation(
        self,
        subject: str,
        task: str,
        evidence: str = "",
    ) -> Attestation:
        """Create and sign an attestation using the identity."""
        att = Attestation(
            subject=subject,
            witness=self.identity.agent_id,
            task=task,
            evidence=evidence,
            witness_pubkey=self.identity.public_key_hex,
        )
        # Sign the attestation
        sig = self.identity.sign(att.claim_data)
        att.signature = sig.hex() if isinstance(sig, bytes) else sig
        return att

    def create_acceptance_attestation(
        self,
        job_id: str,
        buyer_wallet: str,
        offering_name: str,
        fee_usdc: float,
    ) -> Attestation:
        """Create a signed attestation that a job was accepted."""
        evidence_data = {
            "type": "acp_job_accepted",
            "buyer_wallet": buyer_wallet.lower(),
            "offering": offering_name,
            "fee_usdc": fee_usdc,
        }
        return self._sign_attestation(
            subject=job_id,
            task=f"acp.job.accept:{offering_name}",
            evidence=json.dumps(evidence_data),
        )

    def create_completion_attestation(
        self,
        job_id: str,
        deliverable_hash: str,
        quality_score: Optional[float] = None,
    ) -> Attestation:
        """
        Create a signed attestation that a job was completed.
        
        deliverable_hash: SHA256 of the deliverable content
        quality_score: optional self-assessed quality (0.0-1.0)
        """
        evidence_data = {
            "type": "acp_job_completed",
            "deliverable_hash": deliverable_hash,
        }
        if quality_score is not None:
            evidence_data["quality_score"] = max(0.0, min(1.0, quality_score))

        return self._sign_attestation(
            subject=job_id,
            task="acp.job.complete",
            evidence=json.dumps(evidence_data),
        )

    def create_dispute_attestation(
        self,
        job_id: str,
        reason: str,
        evidence_hash: Optional[str] = None,
    ) -> Attestation:
        """Create a signed attestation for a job dispute."""
        evidence_data = {
            "type": "acp_job_disputed",
            "reason": reason,
        }
        if evidence_hash:
            evidence_data["evidence_hash"] = evidence_hash

        return self._sign_attestation(
            subject=job_id,
            task="acp.job.dispute",
            evidence=json.dumps(evidence_data),
        )
